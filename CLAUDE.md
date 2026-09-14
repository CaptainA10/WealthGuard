# WealthGuard — guide pour Claude Code

Plateforme de qualité data & reporting pour un family office fictif : ingestion de
positions de portefeuille, détection d'anomalies, calcul d'indicateurs de
valorisation, restitution via dashboards/API. Projet portfolio destiné aux
entretiens Data/Analytics Engineering — chaque brique technique comble un manque
identifié sur une offre de stage réelle (voir `docs/ARCHITECTURE.md` une fois
écrit, et le cahier des charges original conservé par l'utilisateur).

**Contrainte non négociable (cahier des charges §8) :** aucune logique métier ne
doit être un simple wrapper de bibliothèque. Le moteur de règles Java et
l'algorithme de détection statistique doivent être écrits, pas importés.

## Architecture cible

```
Sources (CSV/API) → Pipeline Python (data-pipeline/) ──POST /api/v1/validate──► Moteur Qualité Java (quality-engine/)
                                │
                                ▼
                          PostgreSQL ──► Power BI / Tableau (métier, fait par l'utilisateur)
                                │
                                └──► Grafana (monitoring ops, table pipeline_runs, append-only)

Frontend React (frontend/) ──POST /api/v1/validate (CORS, appel direct navigateur)──► Moteur Qualité Java
```

Le pipeline Python appelle le moteur Java via HTTP (`POST /api/v1/validate`) —
architecture polyglotte assumée, pas un exercice académique isolé.

## Structure du dépôt

- `quality-engine/` — moteur de règles qualité, **Java 17 / Spring Boot 3.3**, Maven.
- `data-pipeline/` — pipeline **Python 3.11+** (`wealthguard_pipeline`), packaging
  setuptools, tests pytest.
- `data/seed/` — dataset synthétique versionné (généré, pas écrit à la main).
- `docs/` — documentation générée ou de référence (`ANOMALIES.md` est **généré**,
  ne pas éditer à la main).
- `frontend/` — app React (Vite + TypeScript), appelle le moteur Java
  directement depuis le navigateur. `sql/` (racine) — placeholder vide, pas
  utilisé ; les fichiers SQL réels vivent dans
  `data-pipeline/wealthguard_pipeline/sql/` (packagés avec le pipeline,
  `pyproject.toml[tool.setuptools.package-data]`).
- `grafana/` — provisioning (datasources/dashboards) monté par
  `docker-compose.yml` dans le conteneur Grafana ; pas un module applicatif,
  juste de la config.
- `docker-compose.yml`, `.env.example` — Postgres + Grafana pour le
  développement local ; `cp .env.example .env` puis `docker compose up -d`.

## État réel d'avancement (à tenir à jour — ne pas décrire l'aspirationnel comme fait)

Phases du cahier des charges §6 :

1. **Socle données — FAIT.** `data-pipeline/wealthguard_pipeline/seed/` génère
   `clients`, `positions`, `market_prices`, `target_allocations` avec anomalies
   injectées documentées dans `docs/ANOMALIES.md` (généré depuis
   `seed/anomalies.py::ANOMALY_CATALOGUE`, la source de vérité). Génération
   reproductible : `python -m wealthguard_pipeline.seed.generate --as-of <date>`,
   graine fixe, aucune horloge murale dans les sorties committées.
2. **Moteur qualité Java — FAIT** (`mvn verify` passe : 104 tests JUnit 5, gate
   JaCoCo 85% de couverture de branches respectée sur chaque sous-package de
   `com.wealthguard.quality.rules.*`, jar Spring Boot exécutable généré et testé
   manuellement en local sur `/api/v1/validate` et `/api/v1/rules`).
   - Domaine (`domain/`) : records `Position`, `Client`, `Instrument`,
     `TargetAllocation`, `Anomaly`, `ValidationReport`, `ValidationContext`
     (index O(1) par client/instrument), enums `Severity`, `RuleCategory`.
   - Règles (`rules/*`) : 16 règles concrètes (Strategy) couvrant les 4
     catégories du cahier des charges (COMPLETUDE, UNICITE, REFERENTIEL,
     COHERENCE_METIER) -- la liste exacte des ids est dans `RuleIds` et dans
     `quality-rules.yml`.
   - `QualityRuleFactory` (`rules/QualityRuleFactory.java`) : pattern Factory,
     `Map<String, Function<RuleDefinition, QualityRule>>` construit à partir de
     `RuleIds`. Lève `UnknownRuleException` (fatal, arrête le boot) si
     `quality-rules.yml` référence un id inconnu.
   - Configuration (`config/`) : `QualityRulesProperties`
     (`@ConfigurationProperties(prefix = "wealthguard.quality")`, un record) lié
     à `src/main/resources/quality-rules.yml`, importé via
     `spring.config.import` dans `application.yml`. `QualityRuleRegistryConfig`
     construit la liste des `QualityRule` au démarrage via la Factory.
   - Service (`service/ValidationService.java`) : orchestre
     `ValidationContext` -> boucle sur les règles (en sautant celles dont
     `isApplicable()` est faux) -> `ValidationReport`.
   - API (`api/`) : `ValidationController` expose `POST /api/v1/validate` et
     `GET /api/v1/rules` (celui-ci renvoie `RuleSummary`, pas `RuleDefinition`
     brut, car `RuleParameters` n'a pas de getters bean-style et casserait la
     sérialisation Jackson).
   - `QualityEngineApplication` (`@SpringBootApplication`), `application.yml`,
     `quality-rules.yml` : présents.
   - Tests : un fichier de test par règle (comportement + cas limites), plus
     `QualityRuleFactoryTest` (vérifie par réflexion que la Factory connaît
     exactement les ids de `RuleIds`, ni plus ni moins), `ValidationServiceTest`,
     `ValidationControllerTest` (`@WebMvcTest` + `MockMvc`),
     `QualityEngineApplicationTests` (`@SpringBootTest` : démarre le contexte
     complet contre le vrai `quality-rules.yml`), `RuleParametersTest` et
     `RuleDefinitionTest` (dédiés, car ce sont ces deux classes qui font
     l'essentiel des branches du package racine `com.wealthguard.quality.rules`).
   - **Pas encore fait** : rien côté Java pour la Phase 2 elle-même.
3. **Pipeline Python — FAIT** (51 tests pytest verts, y compris 10 tests
   d'intégration réels contre Postgres dockerisé + le moteur Java lancé en
   local ; `python -m wealthguard_pipeline.main` tourne de bout en bout sur le
   jeu `data/seed/landing/`).
   - `ingest.py` : lit CSV et, en fallback, Excel (`load_landing`) ; détecte
     `INGEST_CLOSE_PRICE_REQUIRED` et `INGEST_UNIQUE_PRICE_PER_DAY` sur
     `market_prices` (les deux seuls controles cote Python, cf. `docs/ANOMALIES.md`) ;
     `dedupe_market_prices` deduplique pour le chargement (garde la derniere
     ligne recue) sans jamais cacher l'anomalie, detectee sur les donnees brutes.
   - `outliers.py` : detecteur fait maison (§2.3) -- **pas** de z-score/IQR
     global sur les rendements (ca double-compte un pic ponctuel, voir le
     docstring), mais un z-score/IQR sur une **fenetre locale de niveaux de
     prix, le point exclu de sa propre fenetre** (proche d'un filtre de
     Hampel). Complexite O(n * w log w) documentee. Rappel verifie a 100% sur
     les 5 `PRICE_SPIKE` injectes (`tests/test_outliers.py::TestDetectPriceOutliersOnTheRealSeedDataset`),
     plus ~19 mouvements reels detectes sur les vraies donnees Yahoo Finance
     (attendu, pas un bug -- voir "Bug reel trouve" ci-dessous).
   - `quality_client.py` : `QualityEngineClient` -- seul endroit qui connait le
     JSON camelCase du DTO Java ; convertit NaN -> null, dates -> ISO ; retries
     configurables (`WG_QUALITY_API_RETRIES`).
   - `quarantine.py` : retire du dataset toute ligne visee par une anomalie
     **BLOQUANT**, avec cascade par `client_id` (ex. `CLI_UNIQUE_ID` retire
     aussi les positions/allocations de ce client) -- sinon le chargement
     Postgres casserait sur les FK. Les anomalies AVERTISSEMENT/INFO ne
     quarantinent rien.
   - `db.py` + `sql/schema.sql` + `sql/*.sql` : schema `wealthguard` (5 tables,
     FK + index), chargement full-refresh (`TRUNCATE ... CASCADE` puis reload,
     un run = un batch complet, pas d'incrémental). Requêtes avancées :
     `portfolio_valuation.sql` (CTE + `ROW_NUMBER()` pour le dernier cours),
     `allocation_vs_target.sql` (`SUM(SUM(...)) OVER (PARTITION BY client_id)`
     apres un GROUP BY), `top_holdings.sql` (`RANK() OVER (... ORDER BY
     market_value DESC)`).
   - `indicators.py` : valorisation totale + plus-value latente par client,
     allocation reelle vs cible par classe d'actif, top holdings.
   - `main.py` (`wg-run-pipeline`) : orchestre ingest -> checks Python ->
     appel Java -> quarantine -> load Postgres -> indicateurs -> écrit
     `data/reports/{anomalies.json,portfolio_valuation.csv,allocation_vs_target.csv,top_holdings.csv}`.
   - **Pas encore fait** : Azure Functions/Blob Storage (Phase 9), déploiement.

   ### Bug réel trouvé et corrigé pendant cette phase

   Le test `tests/test_end_to_end.py` (envoie `landing/` au vrai moteur Java,
   compare au manifest regle par regle) a immediatement trouve une divergence
   reelle : `POS_CONCENTRATION_LIMIT` remontait 4 anomalies au lieu de 2.
   Cause : `PositionConcentrationLimitRule` (cote Java) groupait les positions
   par `clientId` brut sans verifier que ce client existait -- les 2 positions
   `ORPHAN_CLIENT_REF` (meme `client_id` factice `CLI-9999`) formaient un faux
   "portefeuille" de 2 lignes ou l'une depassait trivialement 40%. Corrige dans
   `quality-engine` : la regle ignore desormais un `clientId` qui ne resout
   pas (`context.hasClient(clientId)`), et declare `isApplicable =
   context.hasClientReference()`. Voir le javadoc de la regle et
   `PositionConcentrationLimitRuleTest::skipsPositionsWhoseClientIdDoesNotResolve`.
   **Cette classe de bug** (une regle d'agregat qui groupe par une cle
   etrangere sans verifier sa resolution) merite d'etre revue sur toute future
   regle d'agregat par client.
4. **PostgreSQL + SQL avancé — FAIT** (schema + requêtes ci-dessus). Local via
   `docker-compose.yml` (service `postgres`, image `postgres:16-alpine`, monte
   `data-pipeline/wealthguard_pipeline/sql/schema.sql` en script d'init).

   ### Bug réel trouvé et corrigé : `db.init_schema` supprimait silencieusement des statements

   `db._split_statements()` filtrait un chunk entier des qu'il **commençait**
   par un commentaire `--`, sans verifier si du vrai SQL suivait ce
   commentaire dans le meme chunk. Or chaque `CREATE TABLE` de `schema.sql`
   est precede d'un bloc de commentaire explicatif -- donc **chaque**
   `CREATE TABLE` (y compris `CREATE SCHEMA` lui-meme) etait silencieusement
   ignore par `init_schema()`. Masque depuis le debut par le script d'init
   Docker (qui execute le fichier brut via `psql`, insensible a ce bug) ;
   demasque uniquement quand `pipeline_runs` (ajoutee apres coup, donc jamais
   creee par le script d'init du volume Postgres deja existant) a eu besoin
   que `init_schema()` la cree vraiment -- trouve en relançant le pipeline
   contre l'infra reelle une fois Docker Desktop de nouveau disponible.
   Corrige en filtrant les lignes de commentaire **avant** de découper sur
   `;`, pas après (voir `db.py` et `tests/test_db.py`, qui pin ce cas
   precis). **Retenue generale** : `_split_statements` n'est exercee par
   aucun test d'integration qui recree vraiment un schema absent depuis rien
   -- seule une execution contre une base deja peuplee via le script Docker
   aurait continue a masquer ce genre de regression.
5. **Dashboards Power BI / Tableau** — **délégué à l'utilisateur** (déjà
   maîtrisés, faits en cours — décision explicite du 2026-09-14, ne pas les
   construire soi-même). Les indicateurs SQL de la Phase 4 (`indicators.py`,
   `sql/*.sql`) sont la source de données prévue pour ces dashboards.
6. **Frontend React — FAIT** (`frontend/`, Vite + React 19 + TypeScript).
   Appelle **directement** le moteur Java depuis le navigateur (cahier des
   charges §2.5 : "en temps reel via l'API Java"), pas un rapport pré-calculé :
   - `src/api.ts` : charge `public/data/validate-request.json` (fixture
     statique exportée du jeu `landing/` par
     `wg-export-frontend-fixture` = `wealthguard_pipeline.seed.export_frontend_fixture`,
     qui réutilise `quality_client.build_validate_payload` — un seul endroit
     connaît le mapping snake_case -> camelCase) puis `POST` ce JSON vers
     `VITE_QUALITY_API_URL` (`.env`, défaut `http://localhost:8080`).
   - `src/types.ts` : miroir TypeScript de `ValidationReport`/`Anomaly`.
   - `src/components/` : `SummaryBar`, `SeverityFilter` (filtre par
     BLOQUANT/AVERTISSEMENT/INFO), `AnomalyTable`, `SeverityBadge`.
   - Côté Java : `config/WebConfig.java` ajoute le CORS sur `/api/**`
     (`wealthguard.cors.allowed-origins`, défaut `localhost:5173`/`:4173` —
     sans ça le navigateur bloque l'appel avant qu'il n'atteigne Spring), testé
     par `WebConfigTest` (vraie requête preflight via MockMvc).
   - **Deploiement GitHub Pages** (a la demande explicite de l'utilisateur,
     2026-09-14) : `.github/workflows/ci.yml` job `deploy-pages`, build avec
     `npm run build -- --mode gh-pages` (base `/WealthGuard/`, voir
     `vite.config.ts`), publie sur
     [captaina10.github.io/WealthGuard](https://captaina10.github.io/WealthGuard/).
     GitHub Pages ne sert que du statique : `loadReport()` (`src/api.ts`)
     tente l'appel Java en direct (timeout 4s) puis retombe sur
     `public/data/demo-report.json` (instantane fige mais **reel**, genere
     via `curl -X POST` contre un moteur local, voir
     `public/data/README.md` pour la regenerer) avec une banniere explicite
     dans l'UI plutot qu'un faux temps reel silencieux. **Depuis le
     deploiement Azure reel (Phase 9 ci-dessous), l'appel en direct
     reussit** : le dashboard public montre desormais la vraie validation
     temps reel pour un visiteur normal, le mode demo n'etant plus qu'un
     repli pour le cas ou le moteur Azure serait down. **Necessitait
     l'activation manuelle, une seule fois, de Settings -> Pages -> Source =
     "GitHub Actions"** sur le depot -- echoue sinon a l'etape
     `actions/configure-pages@v5` avec un message clair ; deja fait par
     l'utilisateur.
   - **Verifie en conditions reelles** (pas seulement via curl) : `npm run
     lint`, `npm run build` (les deux modes, defaut et `gh-pages`), le site
     deploye repond en 200 avec les bons chemins d'assets, et
     `demo-report.json` est bien accessible derriere la banniere.
   - **Grafana (monitoring ops du pipeline, pas du metier)** : ajoute en plus
     du React/Tableau/PowerBI demandes, a la demande explicite de
     l'utilisateur. `docker-compose.yml` service `grafana`
     (`grafana/grafana-oss:11.3.1`), provisioning auto (aucun clic UI) via
     `grafana/provisioning/{datasources,dashboards}/` et
     `grafana/dashboards/pipeline-monitoring.json`. Source : table
     **append-only** `wealthguard.pipeline_runs` (jamais tronquee par
     `db.load_dataset`, ecrite par `db.record_run()` a la fin de
     `main.run()` — un run = une ligne, historique dans le temps).
     **Teste avec un vrai conteneur** une fois Docker Desktop et l'espace
     disque redevenus disponibles dans la meme session : datasource et
     dashboard bien provisionnes (verifie via l'API Grafana), pipeline lance
     deux fois de suite, donnees visibles dans `pipeline_runs`. Voir le bug
     `db.init_schema` ci-dessous, trouve a cette occasion.
7. **Assistant LangChain — FAIT** (`data-pipeline/wealthguard_pipeline/assistant/`).
   - `security.py` : whitelist de tables (CTE nommees exemptees pour
     elles-memes, mais leur corps reste verifie), rejet de tout mot-cle
     d'ecriture/DDL, une seule instruction, `LIMIT` impose. Enterement
     testable sans LLM (`tests/test_assistant_security.py`, exhaustif).
   - `nl_query.py` (`NaturalLanguageQueryAssistant`) : chaine LangChain
     (`prompt | <ChatGroq ou ChatAnthropic> | StrOutputParser`)
     **injectable** — le parametre `chain` permet de remplacer le LLM par un
     faux objet dans les tests, jamais d'appel reseau paye. Execute la
     requete validee dans une transaction Postgres `READ ONLY` +
     `statement_timeout` (deuxieme couche de securite, independante de la
     regex).
   - `api.py` (FastAPI, `POST /ask`) et `cli.py` (`wg-ask`, entry point
     `pyproject.toml`).
   - **Fournisseur LLM configurable, Groq par defaut** (`WG_ASSISTANT_PROVIDER`,
     defaut `groq`, `config.AssistantConfig._ASSISTANT_PROVIDERS`) —
     changement demande par l'utilisateur le 2026-09-15 : Groq a un vrai
     palier gratuit (pas un essai), contrairement a Anthropic. `provider`
     choisit a la fois la variable d'env de cle (`GROQ_API_KEY` /
     `ANTHROPIC_API_KEY`) et le modele par defaut ; passer
     `WG_ASSISTANT_PROVIDER=anthropic` bascule sur Claude sans toucher au
     code -- c'est precisement l'argument d'entretien pour justifier
     LangChain plutot qu'un appel SDK direct a un seul fournisseur.
   - Tous les tests (`test_assistant_security.py`, `test_assistant_nl_query.py`
     [integration, vrai Postgres local gratuit + faux LLM], `test_assistant_api.py`
     [FastAPI TestClient + dependance surchargee]) passent sans
     `GROQ_API_KEY`/`ANTHROPIC_API_KEY` funded ni requete reseau, quel que
     soit le fournisseur configure. Volontairement absent du
     `docker-compose.yml` par defaut et du deploiement GitHub Pages (meme
     gratuit, un appel LLM reste un appel reseau tiers, pas quelque chose a
     cabler dans un chemin de demo public) -- mais deploye separement sur
     Azure, voir point 9 ci-dessous.
   - **Garde-fou `WG_ASSISTANT_DEMO_KEY`** (`api.py`) : ajoute le 2026-09-15
     avant le deploiement public -- sans lui, `/ask` serait un endpoint
     public qui declenche un appel LLM par requete, exploitable pour epuiser
     le quota gratuit Groq. En-tete `X-Demo-Key` compare a une valeur choisie
     par l'utilisateur ; no-op si la variable d'env est absente (donc aucun
     test existant ni le dev local n'est affecte -- verifie par
     `TestDemoKeyGate` dans `test_assistant_api.py`). Nouveau endpoint
     `GET /health`, sans auth, pour le health check App Service.
   - **Deux bugs reels trouves et corriges pendant l'ecriture des tests** :
     (1) un CTE nomme (`WITH totals AS (...) SELECT * FROM totals`) etait
     rejete comme "table inconnue" — corrige en extrayant les noms de CTE
     et en les exemptant du whitelist check (mais pas leur corps, sinon un
     CTE nomme `clients` pourrait servir de porte derobee) ; (2) le pattern
     regex pour reperer les CTE suivants (`, nom AS (`) utilisait `\b` juste
     avant la virgule, qui ne matche jamais quand le caractere precedent
     (ex. `)`) n'est pas alphanumerique — `\b` ne matche qu'entre un
     caractere de mot et un caractere hors mot, jamais entre deux caracteres
     hors mot. Voir `security.py` pour le detail.
8. **CI/CD — FAIT, sur GitHub Actions (pas GitLab)** — `.github/workflows/ci.yml` :
   `test-java` (`mvn verify`), `test-python` (démarre le vrai jar Spring Boot +
   un vrai conteneur service Postgres, lance toute la suite pytest y compris
   les tests d'intégration -- rien n'est mocké), `test-frontend` (`oxlint` +
   `tsc` + `vite build`), `build` (jar + wheel + bundle frontend en artefacts,
   `main` uniquement), `deploy` (documenté/simulé, pas d'abonnement Azure).
   Vérifié localement avant push (`npm run lint`, `npm run build`,
   `python -m build`) ; premier run déclenché sur push, statut à vérifier
   (`https://github.com/CaptainA10/WealthGuard/actions`).
9. **Déploiement Azure — FAIT (partiellement, par choix)** : le moteur Java
   tourne réellement sur Azure App Service, palier F1 gratuit
   (`wealthguard-quality-engine.azurewebsites.net`), déployé automatiquement
   par le job `deploy-azure` du CI à chaque push sur `main`. Le dashboard
   public GitHub Pages pointe dessus (`VITE_QUALITY_API_URL` fixé au build
   dans `deploy-pages`) -- **validation en temps réel pour un vrai visiteur
   externe**, plus seulement le mode démo (qui reste le repli si le moteur
   est down). `data-pipeline` (Azure Functions), Blob Storage et PostgreSQL
   managé restent documentés mais non câblés (job
   `deploy-pipeline-simulated`) -- décision assumée : Postgres managé n'a
   aucun palier gratuit permanent sur Azure, contrairement a App Service F1,
   et l'utilisateur a un budget de credit (`Azure for Students`, 86$) qu'il
   ne veut pas voir grignote par une ressource qui tourne en continu.
   - `azure/setup.sh` : script one-shot, a lancer dans Azure Cloud Shell
     (aucun outil Azure disponible dans cet environnement agent -- ni `az`
     CLI installe, ni token API). Idempotent (peut se relancer sans erreur).
     Cree un resource group, une identite GitHub Actions en **OIDC
     (federated credential), sans aucun secret client stocke**, role
     `Contributor` limite a ce seul resource group, le plan App Service F1 +
     la Web App Java 17, et le CORS pour l'origine GitHub Pages.
   - **Bug reel de configuration trouve en deployant** : premiere tentative
     de connexion OIDC echouee avec `AADSTS700213: No matching federated
     identity record found`. Le `subject` reellement emis par GitHub est
     `repo:OWNER@OWNER_ID/REPO@REPO_ID:ref:refs/heads/main` (avec les IDs
     numeriques du compte/repo), **pas** le format
     `repo:OWNER/REPO:ref:refs/heads/main` de la doc de reference rapide.
     Corrige en derivant `OWNER_ID`/`REPO_ID` depuis l'API publique GitHub
     dans le script plutot que de coder en dur l'ancien format. Voir
     ARCHITECTURE.md §8 pour le recit complet -- utile en entretien.
   - Aucun acces agent a l'API GitHub Actions dans cette session (pas de
     `gh` CLI, pas de `GH_TOKEN`/`GITHUB_TOKEN`, credential.helper=manager
     non exploitable pour l'API) -- chaque "Re-run failed jobs" a du etre
     declenche manuellement par l'utilisateur dans l'UI GitHub.
   - **Assistant LangChain sur Azure -- CODE/INFRA PRET, DEPLOIEMENT REEL A
     FINALISER PAR L'UTILISATEUR** (demande explicite du 2026-09-15 : "je
     veux deployer l'assistant... pour qu'il soit utilisable en ligne").
     Cote code, tout est fait et teste localement (voir point 7) :
     `azure/setup.sh` etend maintenant l'etape 6/6 pour creer une deuxieme
     Web App Linux Python 3.12 (`wealthguard-assistant`) sur le **meme** plan
     F1 (le quota gratuit est par plan, pas par app) ; `ci.yml` ajoute le job
     `deploy-azure-assistant` (zippe `wealthguard_pipeline/` +
     `requirements-azure.txt` -- liste volontairement plus etroite que
     l'extra `[assistant]` de `pyproject.toml`, sans yfinance/openpyxl/azure
     -- et applique les secrets a chaque deploiement) ; startup command
     `gunicorn -k uvicorn.workers.UvicornWorker`. **Le vrai blocage n'etait
     pas Azure mais Postgres** : `AZURE_POSTGRESQL_*` (config.py) doit
     pointer sur une vraie base en ligne, or Azure Database for PostgreSQL
     n'a aucun palier gratuit permanent (deja documente) -- resolu en
     branchant [Neon](https://neon.tech) (palier gratuit permanent, hors
     Azure) sur ces memes variables d'env, sans nouveau code. Voir
     `data-pipeline/NEON_SETUP.md` pour la procedure complete.
     **Ce qui reste a faire, et que seul l'utilisateur peut faire** (compte
     tiers, secrets GitHub) : creer le compte/projet Neon, executer le
     pipeline une fois contre Neon pour charger de vraies donnees, ajouter
     les secrets GitHub (`GROQ_API_KEY`, `WG_ASSISTANT_DEMO_KEY`,
     `NEON_HOST/DATABASE/USER/PASSWORD`), relancer `azure/setup.sh` dans
     Cloud Shell (idempotent). **Ne pas dire "assistant deploye" tant que
     l'utilisateur n'a pas confirme que l'URL Azure repond reellement.**
10. **Documentation finale — FAIT.** `README.md` (démarrage rapide, stack,
    structure) et `ARCHITECTURE.md` (choix techniques, compromis, étude de cas
    du bug de concentration, tableau de correspondance offres — pensé comme
    support d'entretien) à la racine.

Avant de dire qu'une phase est terminée, vérifier l'état réel des fichiers
(`Glob`), ne pas se fier à ce tableau seul — il peut devenir obsolète.

## Conventions et invariants établis (à respecter en continuant le projet)

- **Aucun secret en dur.** `data-pipeline/wealthguard_pipeline/config.py` est le
  *seul* endroit qui lit `os.environ`. Toute nouvelle configuration passe par ce
  module, avec `_require`/`_optional`/`_int`/`_bool`. Les variables Postgres
  suivent la convention Azure App Service (`AZURE_POSTGRESQL_*`) pour que le même
  code tourne en local (Docker) et sur Azure sans changement, seules les valeurs
  diffèrent.
- **`RuleIds` est un contrat cross-langage.** Ces chaînes relient trois choses :
  le futur registre de la Factory Java, un futur `quality-rules.yml`, et le
  catalogue d'anomalies Python (`seed/anomalies.py`). Un renommage doit se faire
  aux trois endroits ; un test de bout en bout est censé comparer cet ensemble au
  manifest de seed (`data/seed/anomaly_manifest.json`) — à écrire.
- **`QualityRule.evaluate` reçoit tout le `ValidationContext`, pas un seul
  enregistrement.** Volontaire : certaines règles (unicité, somme des
  allocations, concentration) sont des propriétés du batch ou du client, pas
  d'une ligne isolée. `AbstractPositionRule` redonne la commodité "par ligne" aux
  règles qui n'en ont pas besoin.
- **`isApplicable()` distingue "règle passée" de "règle non applicable".** Une
  règle référentielle sans table de référence dans la requête doit être reportée
  comme *ignorée*, pas silencieusement verte.
- **Génération de données reproductible.** Le seed generator ne doit jamais
  écrire l'heure d'exécution dans les fichiers committés ; le seul paramètre
  temporel est `--as-of`, épinglé dans les CSV versionnés (une anomalie,
  `FUTURE_PURCHASE_DATE`, est relative à "aujourd'hui").
- **`docs/ANOMALIES.md` est généré, ne pas l'éditer à la main** — modifier
  `seed/anomalies.py::ANOMALY_CATALOGUE` puis régénérer.
- **Design patterns explicites requis** (cahier des charges, motivé par l'offre
  QRT) : Strategy pour les règles (fait) et Factory pour leur instanciation
  (fait, `QualityRuleFactory`) — les garder visibles et nommés comme tels dans
  le code et les docstrings, ils font partie du pitch d'entretien.
- **`RuleParameters` n'a pas de getters bean-style**, donc ne jamais la
  sérialiser en JSON directement (Jackson échoue sur un bean sans propriété).
  `GET /api/v1/rules` passe par le DTO `RuleSummary` pour cette raison ; tout
  nouvel endpoint qui expose une `RuleDefinition` doit faire pareil.
- **Le contrôleur, pas les règles, lit l'horloge.** `ValidateRequest.evaluationDateOrToday()`
  utilise `LocalDate.now()` en l'absence de date fournie ; c'est la seule
  lecture d'horloge ambiante tolérée dans le moteur, précisément parce que
  c'est à la frontière HTTP et non dans une règle (voir la conception de
  `ValidationContext.evaluationDate()`).
- **Une règle d'agrégat par client doit vérifier que le client résout.**
  `ValidationContext.positionsByClientId()` groupe par `clientId` brut, sans
  savoir si la clé est réelle. Toute règle qui raisonne sur "le portefeuille du
  client" (concentration, futures règles similaires) doit explicitement
  ignorer les groupes dont `context.hasClient(clientId)` est faux — sinon des
  positions orphelines partageant un même `client_id` factice forment un faux
  "portefeuille" et déclenchent des faux positifs (bug réel trouvé et corrigé
  sur `PositionConcentrationLimitRule`, voir Phase 3 ci-dessus).
- **Seul `quarantine.py` retire des lignes AVANT chargement Postgres, et
  seulement les BLOQUANT.** Une anomalie AVERTISSEMENT/INFO doit rester
  chargeable — sauf si elle viole une contrainte physique du schéma (ex.
  doublon `(ticker, price_date)` sur une clé primaire) : dans ce seul cas,
  dédupliquer pour le chargement (`ingest.dedupe_market_prices`) tout en
  gardant la détection sur les données brutes, jamais l'inverse.
- **Le détecteur d'outliers compare un prix à sa fenêtre locale, pas aux
  rendements globaux.** Un z-score/IQR global sur les rendements jour-à-jour
  flague deux fois un pic ponctuel (l'entrée ET la sortie du pic). Voir le
  docstring de `outliers.py` avant de "simplifier" cet algorithme.

## Commandes utiles (vérifiées à ce jour)

```bash
# Générer / régénérer le dataset synthétique
cd data-pipeline && python -m wealthguard_pipeline.seed.generate --as-of 2026-09-13

# Java : build + tests -- 107 tests JUnit 5, gate JaCoCo 85% sur les règles
cd quality-engine && mvn test
cd quality-engine && mvn verify

# Lancer le moteur en local (port 8080 par defaut, SERVER_PORT pour changer)
cd quality-engine && mvn spring-boot:run
# ou : java -jar target/quality-engine-1.0.0.jar

# Postgres + Grafana en local (une fois : cp .env.example .env)
docker compose up -d
# Grafana : http://localhost:3000 (identifiants dans .env, defaut admin/admin,
# anonyme autorise en lecture) ; dashboard "WealthGuard" provisionne au demarrage.

# Python : installer le package (édition) + extras dev/marché
cd data-pipeline && pip install -e ".[dev,market]"
# + extras assistant (LangChain/FastAPI), seulement si besoin :
cd data-pipeline && pip install -e ".[assistant]"

# Assistant NL (necessite GROQ_API_KEY -- gratuit -- ou ANTHROPIC_API_KEY
# + WG_ASSISTANT_PROVIDER=anthropic ; jamais appele par les tests)
cd data-pipeline && wg-ask "Quels clients ont une allocation obligataire superieure a 60% ?"
# ou en service HTTP local :
cd data-pipeline && python -m uvicorn wealthguard_pipeline.assistant.api:app --port 8090
# -> http://localhost:8090/docs (Swagger). WG_ASSISTANT_DEMO_KEY absent en
# local = pas d'en-tete requis ; verifie manuellement le 2026-09-15 (/health
# et /docs en 200, /ask repond reellement via Groq + Postgres local).

# Exporter la fixture pour le frontend (a refaire si le seed dataset change)
cd data-pipeline && wg-export-frontend-fixture --as-of 2026-09-13

# Frontend React (le moteur Java doit tourner ; VITE_QUALITY_API_URL dans frontend/.env)
cd frontend && npm install && npm run dev

# Tests unitaires seuls (pas de Docker/Java requis, tourne toujours vert)
cd data-pipeline && pytest
# Tests d'intégration (Postgres + moteur Java doivent tourner)
cd data-pipeline && pytest -m integration

# Pipeline complet de bout en bout (Postgres + moteur Java doivent tourner)
cd data-pipeline && python -m wealthguard_pipeline.main --as-of 2026-09-13
```

Aucun Maven/JDK/Docker n'était garanti dans le PATH au moment de la rédaction
de ce fichier. Un JDK 17 Adoptium existe sous
`C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot` (pas dans le PATH) ;
Maven a été téléchargé à la volée dans le scratchpad. Docker Desktop, lui,
était bien disponible et fonctionnel (`docker compose`, `docker exec`). Si une
commande échoue avec "command not found", vérifier ce point avant de conclure
à un problème du projet. Le port 8080 est régulièrement pris par un autre
conteneur local (Airflow) sur cette machine — utiliser `SERVER_PORT=8099` (ou
autre) pour le moteur Java si besoin, et `WG_QUALITY_API_URL` assorti côté
Python.

## Pièges connus

- Un `.gitignore` racine existe (exclut `.venv/`, `__pycache__/`,
  `*.egg-info/`, `target/`, `node_modules/`, `.env`, `data/reports/`) — vérifier
  qu'il reste à jour si un nouvel outil ajoute son propre dossier de build.
- Le dépôt est poussé sur `https://github.com/CaptainA10/WealthGuard.git`,
  branche `main` — malgré le cahier des charges §2.7 qui demandait GitLab
  ("pour une fois") ; l'utilisateur a explicitement donné une URL GitHub le
  2026-09-14, donc GitHub prime sur la préférence écrite dans le cahier des
  charges. **Résolu** : la Phase 8 (CI/CD) a été adaptée à GitHub Actions
  (`.github/workflows/ci.yml`) plutôt qu'un `.gitlab-ci.yml` — décision prise
  sans reconfirmer avec l'utilisateur vu le signal déjà fort (deux push sur
  GitHub, aucune mention de GitLab). Si l'utilisateur veut quand même un
  miroir GitLab pour le pitch d'entretien Sopra Steria/Bel, ce sera une tâche
  séparée, pas une modification de ce workflow.
- `docker-compose.yml` monte `data-pipeline/wealthguard_pipeline/sql/schema.sql`
  dans `/docker-entrypoint-initdb.d/` — ce script ne s'exécute qu'à la
  **création** du volume Postgres. Après une modification du schéma, il faut
  soit `docker compose down -v` (perd les données locales) soit appliquer le
  nouveau SQL manuellement ; `db.init_schema()` côté Python ne fait que du
  `CREATE TABLE IF NOT EXISTS`, il ne migre pas un schéma existant.

### Incident disque du 2026-09-14 — vérifier avant de lancer npm/Docker/Maven

Le disque `C:` s'est retrouvé à **0 octet libre sur 260 Go** en pleine session
(scaffolding React + `npm install`), faisant planter **Docker Desktop**
("Docker Desktop is unable to start") et échouer `npm install` (`ENOSPC`), et
même des commandes basiques comme `cat` ("No space left on device"). Le
répertoire WealthGuard ne pesait que ~230 Mo. **Cause racine identifiée** :
`C:\Users\Lenovo\OneDrive - Groupe ESAIP` pesait **142,9 Go** (probablement
Documents/Bureau/Images redirigés par Known Folder Move) -- Docker
(`AppData\Local\Docker`, ~23 Go) et WSL (~23 Go) ne sont qu'une fraction du
problème. Nettoyage sûr effectué : cache pip (~2,1 Go), cache yarn/npm,
corbeille, dossier Temp -- aucun n'a suffi seul, l'espace disponible est
resté sous les 2 Go pendant une bonne partie de la session, avec des **écarts
soudains d'plusieurs Go en quelques minutes** observés dans les deux sens
(très probablement une synchronisation OneDrive active en arrière-plan, pas
un effet de ce que fait Claude).

**Docker Desktop a fini par redémarrer proprement** une fois quelques Go
libérés, via `Stop-Process` sur `Docker Desktop`/`com.docker.backend` puis
relance de `Docker Desktop.exe` (`wsl --shutdown` seul n'avait pas suffi).
Après redémarrage, Postgres, Grafana et le moteur Java ont tous été testés
avec succès en conditions réelles dans cette même session (voir Phases 2-4,
6 ci-dessus) -- donc **si Docker refuse de démarrer dans une future session,
ce n'est pas forcément définitif** : vérifier l'espace disque, libérer
quelques Go si besoin, puis tenter ce redémarrage avant de conclure à un
blocage. Le nettoyage OneDrive ("Libérer de l'espace", clic droit dans
l'Explorateur -- ne supprime rien, juste des copies locales) reste, lui, non
fait à la fin de cette session et est la vraie solution durable.

**Avant toute commande `npm install`, `docker compose up` ou `mvn` dans une
future session** : vérifier `df -h /c/Users/Lenovo/wealthguard` (ou
`Get-PSDrive C`). Si l'espace disponible est à nouveau proche de zéro, ne pas
retenter une installation lourde sans en informer l'utilisateur d'abord — ce
n'est pas un problème du projet WealthGuard, c'est un problème d'espace disque
machine plus large qui dépasse le périmètre de ce dépôt.
