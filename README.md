# WealthGuard

Plateforme de qualité data & reporting pour un cabinet de gestion de fortune
(family office) fictif. Ingestion de positions de portefeuille, détection
d'anomalies via un moteur de règles Java configurable, calcul d'indicateurs
de valorisation en SQL avancé, restitution via une API, un frontend React et
des dashboards.

Projet portfolio : toutes les données sont synthétiques (voir [§ Données
synthétiques](#données-synthétiques-et-anomalies-injectées)) ; chaque brique
technique est un choix délibéré, détaillé dans
[ARCHITECTURE.md](ARCHITECTURE.md).

## Architecture

```
Sources (CSV/Excel) → Pipeline Python ──POST /api/v1/validate──► Moteur Qualité Java (Spring Boot)
                            │
                            ▼
                      PostgreSQL ──► Power BI / Tableau (dashboards métier)
                            │
                            └──► Grafana (monitoring du pipeline lui-même)

Frontend React ──POST /api/v1/validate (appel direct, CORS)──► Moteur Qualité Java
```

Le pipeline Python et le frontend React parlent tous les deux au moteur Java
en HTTP — une architecture polyglotte assumée, pas un simple exercice
académique. Détail des choix et compromis dans
[ARCHITECTURE.md](ARCHITECTURE.md).

## Stack technique

| Domaine | Techno |
|---|---|
| Moteur de qualité | Java 17, Spring Boot 3.3, Maven |
| Pipeline data | Python 3.12, pandas, SQLAlchemy |
| Base de données | PostgreSQL 16 |
| Frontend | React 19, TypeScript, Vite |
| Monitoring | Grafana (provisionné automatiquement) |
| Dataviz métier | Power BI, Tableau |
| CI/CD | GitHub Actions |
| Conteneurisation locale | Docker Compose |

## Démarrage rapide

Prérequis : JDK 17, Python 3.12+, Node 22+, Docker.

```bash
git clone https://github.com/CaptainA10/WealthGuard.git
cd WealthGuard
cp .env.example .env

# 1. Infrastructure locale (PostgreSQL + Grafana)
docker compose up -d

# 2. Moteur de qualité Java (port 8080)
cd quality-engine
mvn spring-boot:run
# API : http://localhost:8080/api/v1/validate — doc interactive : http://localhost:8080/swagger-ui.html

# 3. Pipeline Python (nouveau terminal, depuis la racine)
cd data-pipeline
pip install -e ".[dev,market]"
python -m wealthguard_pipeline.main --as-of 2026-09-13
# écrit data/reports/{anomalies.json, portfolio_valuation.csv, allocation_vs_target.csv, top_holdings.csv}

# 4. Frontend React (nouveau terminal)
cd frontend
npm install
npm run dev
# http://localhost:5173
```

Grafana (monitoring du pipeline) : http://localhost:3000, identifiants dans
`.env` (défaut `admin` / `admin`), dashboard « WealthGuard » provisionné
automatiquement — alimenté par la table `wealthguard.pipeline_runs`, remplie
à chaque exécution de `wealthguard_pipeline.main`.

### Régénérer le jeu de données

Le jeu de données versionné sous `data/seed/` est déjà généré et committé —
l'étape ci-dessus n'est nécessaire que pour le régénérer (nouvelle graine,
nouvelle date de référence) :

```bash
cd data-pipeline
python -m wealthguard_pipeline.seed.generate --as-of 2026-09-13
wg-export-frontend-fixture --as-of 2026-09-13   # regénère la fixture du frontend
```

### Assistant en langage naturel

Le reste du projet (pipeline, moteur Java, frontend, Grafana, CI/CD, dashboard
en ligne) fonctionne entièrement **sans** cette brique, donc elle n'est ni
dans le `docker-compose.yml` par défaut, ni dans la démo GitHub Pages — mais
elle est **déployée en ligne séparément**, sur Azure :
[wealthguard-assistant.azurewebsites.net/docs](https://wealthguard-assistant.azurewebsites.net/docs)
(Swagger UI ; nécessite l'en-tête `X-Demo-Key`, garde-fou anti-abus décrit
dans [ARCHITECTURE.md](ARCHITECTURE.md) §5 — demander la valeur si besoin).
Fournisseur LLM par défaut : **Groq** (palier gratuit réel, pas un essai —
clé sur [console.groq.com/keys](https://console.groq.com/keys)). LangChain
étant agnostique du fournisseur, passer sur Claude (payant) ne change pas
une ligne de code :

```bash
cd data-pipeline
export GROQ_API_KEY=gsk_...
wg-ask "Quels clients ont une allocation obligataire superieure a 60 % ?"
# ou, en service HTTP :
uvicorn wealthguard_pipeline.assistant.api:app --port 8090

# Pour utiliser Claude a la place :
export WG_ASSISTANT_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

La sécurité (whitelist de tables, lecture seule, cf. cahier des charges §2.4)
est testée intégralement en simulant le LLM — voir
`tests/test_assistant_security.py` et `tests/test_assistant_nl_query.py` —
aucun de ces tests n'appelle l'API réelle ni ne coûte quoi que ce soit.

## Tests

```bash
# Java : 109 tests JUnit 5, gate de couverture JaCoCo 85% sur les règles
cd quality-engine && mvn verify

# Python : tests unitaires (aucune dépendance externe requise)
cd data-pipeline && pytest
# Python : tests d'intégration (Postgres + moteur Java doivent tourner)
cd data-pipeline && pytest -m integration
```

Le pipeline CI/CD (`.github/workflows/ci.yml`) exécute l'intégralité de
cette suite — y compris les tests d'intégration Python, contre un vrai
PostgreSQL et le vrai jar Spring Boot démarré en tâche de fond — à chaque
push.

## Données synthétiques et anomalies injectées

`data/seed/` contient un jeu de données synthétique reproductible : 46
clients, ~435 positions, 18 instruments réels (cours historiques réels via
Yahoo Finance), avec **46 anomalies injectées volontairement et documentées**
dans [docs/ANOMALIES.md](docs/ANOMALIES.md) — ce fichier sert aussi d'oracle
de test pour la suite de bout en bout. Rien n'est une donnée réelle de
client.

## Dashboards

- **Dashboard React en ligne** :
  [captaina10.github.io/WealthGuard](https://captaina10.github.io/WealthGuard/)
  (déployé automatiquement par `.github/workflows/ci.yml` à chaque push sur
  `main`) — connecté au **moteur de qualité Java réellement déployé sur
  Azure** (`wealthguard-quality-engine.azurewebsites.net`, App Service,
  palier gratuit F1), donc validation en **temps réel**, pas un instantané.
  Si le moteur venait à être indisponible, la page retombe automatiquement
  sur un instantané figé (bannière visible) — voir
  [ARCHITECTURE.md](ARCHITECTURE.md) pour le détail du mode démo et du
  déploiement Azure.
- **Assistant en langage naturel (LangChain)** : voir
  [§ Assistant en langage naturel](#assistant-en-langage-naturel) —
  déployé sur Azure, un PostgreSQL séparé ([Neon](https://neon.tech), voir
  `data-pipeline/NEON_SETUP.md`).
- **Power BI / Tableau** (reporting métier — valorisation, allocation,
  performance) : à construire à partir des indicateurs exposés par
  `data-pipeline/wealthguard_pipeline/indicators.py` /
  `data/reports/*.csv`. _Liens à ajouter ici une fois publiés._
- **Grafana** (monitoring du pipeline) : provisionné automatiquement en
  local, voir [§ Démarrage rapide](#démarrage-rapide).

## Structure du dépôt

```
quality-engine/    Moteur de règles qualité (Java / Spring Boot)
data-pipeline/      Pipeline Python (ingestion, appel API, indicateurs SQL)
frontend/           Dashboard React (liste d'anomalies en temps réel)
data/seed/           Jeu de données synthétique versionné
docs/                Documentation générée (catalogue d'anomalies)
grafana/             Provisioning Grafana (datasource + dashboard)
.github/workflows/  CI/CD
```

## Documentation complémentaire

- [ARCHITECTURE.md](ARCHITECTURE.md) — choix techniques, compromis, complexité
  algorithmique.
- [docs/ANOMALIES.md](docs/ANOMALIES.md) — catalogue des anomalies injectées.
