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
Sources (CSV/API) → Pipeline Python (data-pipeline/) → API REST → Moteur Qualité Java (quality-engine/)
                                ↓                                          ↓
                          PostgreSQL  ←───────────────────────────────────┘
                                ↓
                    Power BI / Tableau · Frontend React (frontend/) · Assistant LangChain
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
- `frontend/`, `sql/` — placeholders vides, pas encore commencés.

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
   - **Pas encore fait** : rien côté Java pour la Phase 2 elle-même ; ce qui
     reste est la Phase 3 (le pipeline Python doit appeler cette API, ce qu'il
     ne fait pas encore).
3. **Pipeline Python** — **PAS COMMENCÉ.** `config.py` existe (lecture d'env
   complète, voir conventions ci-dessous) mais aucune logique d'ingestion, aucun
   appel à l'API Java, aucun calcul d'indicateurs, aucun algorithme
   z-score/IQR maison. `pyproject.toml` déclare un entry point
   `wg-run-pipeline = wealthguard_pipeline.main:main` — **ce module n'existe pas
   encore**, ne pas supposer qu'il tourne.
4. **PostgreSQL + SQL avancé** — pas commencé (`sql/` vide, pas de docker-compose,
   pas de migration).
5. **Dashboards Power BI / Tableau** — pas commencé.
6. **Frontend React** — pas commencé (`frontend/` vide).
7. **Assistant LangChain** — pas commencé (`assistant/` existe dans
   `wealthguard_pipeline/` mais est vide ; dépendances déclarées dans
   `pyproject.toml[assistant]`).
8. **CI/CD GitLab** — pas commencé, pas de `.gitlab-ci.yml`.
9. **Déploiement Azure** — pas commencé.
10. **Documentation finale** (`README.md`, `ARCHITECTURE.md` à la racine) — pas
    encore écrite.

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

## Commandes utiles (vérifiées à ce jour)

```bash
# Générer / régénérer le dataset synthétique
cd data-pipeline && python -m wealthguard_pipeline.seed.generate --as-of 2026-09-13

# Java : build + tests -- 104 tests JUnit 5, gate JaCoCo 85% sur les règles
cd quality-engine && mvn test
cd quality-engine && mvn verify

# Lancer le moteur en local (port 8080 par defaut, SERVER_PORT pour changer)
cd quality-engine && mvn spring-boot:run
# ou : java -jar target/quality-engine-1.0.0.jar

# Python : pas encore de tests écrits dans data-pipeline/tests (vide)
cd data-pipeline && pytest
```

Aucun Maven/JDK n'était installé dans l'environnement au moment de la
rédaction de ce fichier (`mvn`/`java` absents du PATH) alors qu'un JDK 17
Adoptium existe sous `C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot` ;
Maven a été téléchargé à la volée dans le scratchpad pour lancer les tests.
Si `mvn` échoue avec "command not found", vérifier ce point avant de conclure
à un problème du projet.

Ne pas inventer d'autres commandes (ex. `wg-run-pipeline`, docker-compose) tant
que les fichiers correspondants n'existent pas.

## Pièges connus

- Un `.gitignore` racine existe désormais (exclut `.venv/`, `__pycache__/`,
  `*.egg-info/`, `target/`, `node_modules/`, `.env`) — vérifier qu'il reste à
  jour si un nouvel outil ajoute son propre dossier de build.
- Aucun commit n'existe encore sur `master` au moment de la rédaction de ce
  fichier — tout le travail listé ci-dessus est untracked.
