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
