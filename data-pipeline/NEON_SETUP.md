# Déployer une base Neon pour l'assistant LangChain (Azure)

Contexte : le moteur qualité Java est déployé sur Azure App Service (voir
[azure/setup.sh](../azure/setup.sh)), mais **Azure Database for PostgreSQL
n'a aucun palier gratuit permanent** — une décision déjà documentée dans
[ARCHITECTURE.md](../ARCHITECTURE.md) §8 pour ne pas dépenser. L'assistant
LangChain, lui, a besoin d'un vrai PostgreSQL en ligne pour répondre aux
questions (`SELECT` en lecture seule sur `clients`, `positions`, etc.), donc
une fois déployé sur Azure il ne peut plus pointer sur le PostgreSQL local
de `docker-compose.yml`.

[Neon](https://neon.tech) fournit un PostgreSQL managé avec un palier
gratuit permanent (pas un essai limité dans le temps) : 0,5 Go de stockage,
mise en veille automatique après inactivité (le premier appel après une
veille prend ~1 seconde de plus, ensuite c'est normal). Largement suffisant
pour ce jeu de données synthétique (46 clients, ~435 positions).

`config.py` lit déjà les variables `AZURE_POSTGRESQL_HOST/PORT/DATABASE/
USER/PASSWORD/SSL` — les mêmes noms qu'Azure injecterait pour son propre
Postgres managé. Neon n'a donc nécessité **aucun nouveau code** : on pointe
juste ces variables vers Neon au lieu d'Azure ou du Docker local.

## 1. Créer le projet Neon (une fois, dans le navigateur)

1. [neon.tech](https://neon.tech) → *Sign up* (GitHub OAuth le plus rapide,
   aucune carte bancaire demandée pour le palier gratuit).
2. *Create a project* → nom `wealthguard`, région la plus proche de
   `francecentral` (ex. `Europe (Frankfurt)`).
3. Le dashboard du projet affiche une *Connection string* du type :
   ```
   postgresql://<user>:<password>@<host>/<database>?sslmode=require
   ```
   Note les 4 morceaux séparément (`<user>`, `<password>`, `<host>`,
   `<database>`) — c'est ce que les étapes suivantes réutilisent.

## 2. Créer le schéma et charger de vraies données

Le schéma (`sql/schema.sql`, y compris les 3 vues Power BI/Tableau) et le
chargement des données passent déjà par le même code que le pipeline local
(`db.init_schema` + `wealthguard_pipeline.main`) — donc pas de script de
migration séparé : on exécute simplement le pipeline habituel en pointant
temporairement sur Neon au lieu du Docker local.

**PowerShell**, depuis `data-pipeline/` (ne touche pas au `.env` local — ces
variables ne valent que pour cette commande) :

```powershell
$env:AZURE_POSTGRESQL_HOST = "<host neon>"
$env:AZURE_POSTGRESQL_PORT = "5432"
$env:AZURE_POSTGRESQL_DATABASE = "<database neon>"
$env:AZURE_POSTGRESQL_USER = "<user neon>"
$env:AZURE_POSTGRESQL_PASSWORD = "<password neon>"
$env:AZURE_POSTGRESQL_SSL = "true"

python -m wealthguard_pipeline.main --as-of 2026-09-13 --reports-dir ..\data\reports

Remove-Item Env:AZURE_POSTGRESQL_HOST,Env:AZURE_POSTGRESQL_PORT,Env:AZURE_POSTGRESQL_DATABASE,Env:AZURE_POSTGRESQL_USER,Env:AZURE_POSTGRESQL_PASSWORD,Env:AZURE_POSTGRESQL_SSL
```

Vérifie ensuite depuis le dashboard Neon (onglet *Tables*) que
`wealthguard.clients`, `wealthguard.positions`, etc. contiennent des lignes.

## 3. Ajouter les secrets GitHub

`Settings → Secrets and variables → Actions → New repository secret`, un
secret par ligne (consommés par le job `deploy-azure-assistant` de
`.github/workflows/ci.yml`) :

| Secret | Valeur |
|---|---|
| `GROQ_API_KEY` | ta clé [console.groq.com/keys](https://console.groq.com/keys) |
| `WG_ASSISTANT_DEMO_KEY` | une valeur que tu inventes (ex. `openssl rand -hex 16`) — sert de garde-fou anti-abus sur l'endpoint public, voir `assistant/api.py` |
| `NEON_HOST` | `<host neon>` |
| `NEON_DATABASE` | `<database neon>` |
| `NEON_USER` | `<user neon>` |
| `NEON_PASSWORD` | `<password neon>` |

`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` existent déjà
(mis en place pour le moteur Java) et sont réutilisés tels quels : une seule
identité OIDC, Contributor sur tout `wealthguard-rg`.

## 4. Provisionner la Web App et déployer

```bash
# Azure Cloud Shell (portal.azure.com -> ">_"), idempotent, peut se relancer
bash azure/setup.sh
```

crée la Web App `wealthguard-assistant` (Python 3.12, même plan F1 gratuit
que le moteur Java). Le prochain push sur `main` (ou un re-run du job
`deploy-azure-assistant`) déploie le code et applique les secrets
ci-dessus.

## 5. Tester

```bash
curl https://wealthguard-assistant.azurewebsites.net/health
# {"status": "ok"}

curl -X POST https://wealthguard-assistant.azurewebsites.net/ask \
  -H "Content-Type: application/json" \
  -H "X-Demo-Key: <la valeur WG_ASSISTANT_DEMO_KEY choisie ci-dessus>" \
  -d '{"question": "Quels sont les 5 clients avec le plus de positions ?"}'
```

Documentation interactive (Swagger UI, générée automatiquement par
FastAPI) : https://wealthguard-assistant.azurewebsites.net/docs — utilisable
directement dans le navigateur (bouton *Authorize* pour renseigner
`X-Demo-Key`).
