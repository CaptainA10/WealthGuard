# Architecture — WealthGuard

Ce document détaille les choix techniques et les compromis assumés, pensé
comme support de préparation d'entretien : chaque section répond à la
question « pourquoi cette techno, pourquoi cette conception, plutôt qu'une
autre ».

## 1. Vue d'ensemble

```
Sources (CSV/Excel) → Pipeline Python ──POST /api/v1/validate──► Moteur Qualité Java (Spring Boot)
                            │
                            ▼
                      PostgreSQL ──► Power BI / Tableau (dashboards métier)
                            │
                            └──► Grafana (monitoring du pipeline lui-même)

Frontend React ──POST /api/v1/validate (appel direct, CORS)──► Moteur Qualité Java
```

Trois langages, trois responsabilités distinctes, aucune redondance :

- **Java** ne connaît que les règles de qualité et leur configuration. Il ne
  sait rien de PostgreSQL, de Yahoo Finance ou du frontend.
- **Python** orchestre : il lit les fichiers source, appelle le moteur Java,
  calcule des indicateurs financiers et charge un entrepôt SQL. Il ne
  réimplémente aucune règle de qualité — il consomme le verdict du moteur
  Java.
- **React** ne parle qu'au moteur Java, directement depuis le navigateur.

Cette séparation est délibérée : elle simule une architecture d'entreprise
réaliste (plusieurs équipes, plusieurs langages) plutôt qu'un monolithe qui
aurait été plus rapide à écrire mais moins représentatif.

## 2. Moteur de qualité (Java / Spring Boot)

### 2.1 Design patterns

- **Strategy** (`QualityRule`) : chaque contrôle est une classe qui implémente
  une interface commune (`definition()`, `evaluate(ValidationContext)`,
  `isApplicable(ValidationContext)`). Le moteur (`ValidationService`) ne
  connaît que l'interface, jamais une règle concrète.
- **Factory** (`QualityRuleFactory`) : transforme une `RuleDefinition`
  (id + paramètres, lus depuis `quality-rules.yml`) en instance concrète de
  `QualityRule`. Ajouter une règle = une entrée dans la Factory + une entrée
  YAML, sans toucher au reste du moteur (principe ouvert/fermé).

Seize règles concrètes couvrent quatre catégories : complétude, unicité,
intégrité référentielle, cohérence métier (signes, plages, chronologie,
concentration, sommes d'allocation).

### 2.2 Pourquoi la configuration n'est pas dans le code

La sévérité, les seuils et même la liste des champs obligatoires sont dans
`quality-rules.yml`, pas dans les classes Java. Durcir un seuil de
concentration de 40 % à 25 %, ou rétrograder un contrôle de BLOQUANT à
AVERTISSEMENT, ne nécessite ni recompilation ni redéploiement — un changement
de configuration qu'un data steward peut faire sans toucher au code.

### 2.3 `ValidationContext` reçoit le batch entier, pas une ligne

Une signature naïve (`evaluate(Position)`) suffirait pour une règle comme
« la quantité est positive », mais pas pour l'unicité d'un identifiant, la
somme des allocations d'un client, ou la concentration d'une ligne dans le
portefeuille — des propriétés du lot ou du client, pas d'une ligne isolée.
`ValidationContext` construit des index O(1) (par client, par instrument) une
seule fois à la construction, pour que chaque règle reste O(P) plutôt que de
réintroduire un scan O(P·C).

### 2.4 Étude de cas : un bug réel trouvé par le test de bout en bout

Le test `test_end_to_end.py` (côté Python) envoie le jeu de données
« landing » au vrai moteur Java et compare la réponse au manifeste
d'anomalies attendues, règle par règle. Il a immédiatement révélé une
divergence : la règle de concentration (`POS_CONCENTRATION_LIMIT`) remontait
4 anomalies au lieu des 2 attendues.

**Cause** : la règle groupait les positions par `clientId` brut
(`ValidationContext.positionsByClientId()`) sans vérifier que ce client
existait réellement dans le référentiel. Deux positions orphelines
(anomalie `ORPHAN_CLIENT_REF`, injectée volontairement) partageaient le même
identifiant client factice `CLI-9999` — formant, aux yeux de la règle, un
faux « portefeuille » de deux lignes où l'une dépassait trivialement 40 %.

**Correction** : la règle ignore désormais tout `clientId` qui ne résout pas
(`context.hasClient(clientId)`), et déclare
`isApplicable = context.hasClientReference()`. Généralisation retenue : toute
règle d'agrégat qui groupe par une clé étrangère doit explicitement vérifier
la résolution de cette clé avant de raisonner sur le groupe — sinon des
lignes orphelines partageant une même clé invalide produisent de faux
positifs statistiquement plausibles.

C'est l'argument concret pour la question d'entretien « pourquoi des tests
de bout en bout, pas seulement des tests unitaires ? » : un test unitaire sur
`PositionConcentrationLimitRule` avec des données bien formées n'aurait
jamais révélé ce cas — il fallait le jeu de données complet, avec ses
anomalies croisées.

## 3. Pipeline Python

### 3.1 Détecteur d'anomalies statistique fait maison

Exigence du cahier des charges : un algorithme de détection écrit à la main
(z-score / IQR), pas un appel à une bibliothèque de ML clé en main.

Le choix le plus significatif n'est pas z-score vs IQR (le détecteur utilise
les deux), mais **la référence contre laquelle chaque prix est comparé**.

Un premier design évident — comparer chaque rendement jour-à-jour à la
distribution globale des rendements du titre — a un défaut qui n'apparaît
que sur un vrai pic ponctuel : un prix corrompu à la date D distord *deux*
rendements consécutifs (l'entrée dans le pic, énorme et positive ; la sortie
du pic le lendemain, énorme et négative). Un seul prix erroné produit alors
deux dates signalées, sans moyen de dire laquelle porte réellement l'erreur.

Le détecteur retenu compare chaque prix à une **fenêtre locale de voisins,
le point exclu de sa propre fenêtre** (proche d'un filtre de Hampel) :

- Au jour du pic, la fenêtre de référence est bâtie uniquement à partir de
  voisins propres → écart énorme → signalé.
- Au jour suivant (prix normal), sa fenêtre contient le seul voisin corrompu,
  ce qui gonfle la dispersion (écart-type / IQR) de cette fenêtre bien plus
  que son centre → le prix normal ne ressort plus comme un écart.

Complexité documentée : O(n · w log w) par titre pour n observations et une
fenêtre de taille fixe w (tri de la fenêtre pour les quartiles) — linéaire en
n pour une fenêtre fixe. Validé avec un rappel de 100 % sur les 5 pics
injectés volontairement, et testé aussi sur les vraies données Yahoo Finance
(où il détecte, sans surprise, d'autres mouvements réels significatifs sur 3
ans d'historique — un comportement attendu, pas un faux positif).

### 3.2 Mise en quarantaine avant chargement

Le pipeline ne charge jamais une ligne visée par une anomalie **BLOQUANT**
dans l'entrepôt PostgreSQL (`quarantine.py`), avec une cascade par
`client_id` : si un client est lui-même invalide (ex. identifiant dupliqué),
ses positions et allocations le sont aussi, sinon le chargement casserait sur
les clés étrangères. Les anomalies AVERTISSEMENT et INFO, elles, chargent
normalement — seule exception : un doublon `(ticker, date)` sur les cours de
marché, qui viole une contrainte de clé primaire physique ; dans ce seul cas,
la ligne est dédupliquée pour le chargement (on garde la dernière reçue) tout
en gardant la détection sur les données brutes — l'anomalie reste visible
dans le rapport, elle n'est jamais cachée.

### 3.3 SQL avancé, pas de logique réimplémentée en pandas

Les indicateurs (valorisation totale, allocation réelle vs cible, top
holdings) sont calculés en SQL, avec CTE et fonctions fenêtres
(`ROW_NUMBER()` pour le dernier cours connu à une date donnée, `RANK()` pour
le classement des lignes d'un portefeuille, `SUM(SUM(...)) OVER (PARTITION
BY client_id)` pour un total de groupe recalculé sans deuxième requête
d'agrégation) — voir `data-pipeline/wealthguard_pipeline/sql/*.sql`. Le
chargement est un *full refresh* (`TRUNCATE ... CASCADE` puis rechargement
dans une transaction) : le pipeline simule un batch quotidien planifié, pas
une synchronisation incrémentale.

## 4. Frontend React

Le frontend appelle le moteur Java **directement depuis le navigateur**
(`POST /api/v1/validate`), pas un rapport pré-calculé — ce qui a nécessité
une configuration CORS explicite côté Spring (`WebConfig`, origines
autorisées configurables). Le corps de la requête est une fixture statique
exportée du jeu de données synthétique (`wg-export-frontend-fixture`), qui
réutilise la même fonction de mapping snake_case → camelCase que le client
Python (`quality_client.build_validate_payload`) — un seul endroit connaît le
contrat JSON du moteur, jamais dupliqué.

### Mode démo (déploiement GitHub Pages)

GitHub Pages n'héberge que des fichiers statiques : il ne peut pas faire
tourner le moteur Java. Le frontend déployé (`captaina10.github.io/WealthGuard`)
tente donc l'appel API en direct en premier (avec un timeout de 4 s pour ne
pas faire attendre un visiteur qui n'a aucune chance d'obtenir une réponse) ;
en cas d'échec, il retombe sur `demo-report.json`, un instantané figé mais
**réel** (généré en POSTant la même fixture à une instance locale du moteur),
avec une bannière explicite plutôt qu'un silence trompeur sur le fait que la
donnée n'est plus temps réel. L'architecture "appel direct navigateur → API
Java" reste donc valable et démontrable en local ; le déploiement public est
une dégradation gracieuse, pas un second chemin de code parallèle à
maintenir — `loadReport()` (`src/api.ts`) est le seul endroit qui connaît les
deux sources.

## 5. Assistant en langage naturel (LangChain)

Traduit une question en français ("Quels clients ont une allocation
obligataire supérieure à 60 % ?") en SQL, exécute la requête, retourne les
lignes (`data-pipeline/wealthguard_pipeline/assistant/`).

**Ce que « sécuriser l'exécution » veut dire concrètement** (cahier des
charges §2.4) : une instruction dans le prompt ("ne réponds qu'avec du
SELECT") n'est pas une barrière de sécurité — un modèle peut être contourné
par le prompt de l'utilisateur, et même un modèle honnête peut se tromper sur
une question complexe. Toute requête générée passe par deux couches
indépendantes avant d'atteindre PostgreSQL :

1. **`security.validate_and_prepare`** — rejette tout ce qui n'est pas une
   instruction `SELECT`/`WITH` unique, tout mot-clé d'écriture ou de DDL où
   qu'il apparaisse dans le texte, et toute table référencée hors d'une
   liste blanche explicite (CTE nommées incluses, mais leur propre corps
   reste vérifié — nommer un CTE `clients` ne permet pas d'en faire une
   porte dérobée vers une table interdite). Plafonne aussi le nombre de
   lignes (`LIMIT`).
2. **Transaction PostgreSQL `READ ONLY`** (`nl_query.py`), avec
   `statement_timeout` — une deuxième couche indépendante de la première :
   même un bug dans le validateur regex ne peut pas devenir une écriture ni
   une requête qui tourne indéfiniment.

Le whitelisting de **colonnes** (également demandé par le cahier des
charges) n'est pas appliqué indépendamment par ce module : le faire
correctement demanderait un vrai analyseur SQL, pas une regex, et une fausse
impression de sécurité au niveau colonne serait pire qu'une limite honnête.
La barrière qui existe à ce niveau est le schéma décrit au modèle dans son
prompt système, combinée au fait qu'accéder à une colonne hors schéma (une
table système, par exemple) nécessite de facto une table hors liste blanche
— déjà rejetée par la couche 1.

**Fournisseur LLM interchangeable par configuration** (`WG_ASSISTANT_PROVIDER`,
`config.AssistantConfig`) : **Groq par défaut** (palier gratuit réel, pas un
essai limité dans le temps), Anthropic en option. C'est l'argument concret
pour justifier LangChain plutôt qu'un simple appel HTTP direct au SDK d'un
fournisseur : la chaîne `prompt | llm | parser` (`nl_query.py`) ne change pas
d'une ligne selon le fournisseur, seule la classe importée dans
`_build_chain` change. Décision prise le 2026-09-14 à la demande explicite de
l'utilisateur, qui ne voulait pas dépendre d'une API payante pour que le
projet reste démontrable.

**Testé sans jamais appeler l'API réelle**, indépendamment du fournisseur
choisi. Le "chain" LangChain est injectable ; tous les tests lui substituent
un faux objet qui renvoie du SQL prédéfini sans appel réseau, y compris les
tests d'intégration qui, eux, utilisent un vrai PostgreSQL local (gratuit)
pour vérifier l'exécution et les deux couches de sécurité. Reste absent du
`docker-compose.yml` par défaut et du déploiement GitHub Pages — même
gratuit, un appel LLM reste un appel réseau à un service tiers, pas quelque
chose à câbler dans le chemin de démo principal — mais est déployé
séparément sur Azure, en service HTTP autonome : voir §8.

**Garde-fou anti-abus sur le déploiement public** (`WG_ASSISTANT_DEMO_KEY`,
`api.py`) : une fois en ligne, `/ask` est un endpoint public qui déclenche un
appel LLM à chaque requête — sans rien, n'importe qui sur Internet pourrait
épuiser le quota gratuit Groq. Un en-tête `X-Demo-Key` partagé, comparé côté
serveur, n'est pas de l'authentification réelle (une seule valeur pour tout
le monde) mais un frein suffisant contre le trafic automatisé, sans ajouter
un vrai système de comptes pour une démo. Absent (donc no-op) en local et
dans tous les tests — n'existe que comme réglage de l'App Service Azure.

## 6. Monitoring vs reporting : deux outils, deux publics

- **Power BI / Tableau** répondent à une question métier : « comment se
  porte le portefeuille de ce client ? ». Public : les conseillers.
- **Grafana** répond à une question opérationnelle : « le pipeline
  tourne-t-il bien, et depuis quand ? ». Alimenté par une table dédiée,
  **append-only** (`wealthguard.pipeline_runs`, jamais tronquée par le
  rechargement quotidien) — un run = une ligne, pour observer une tendance
  dans le temps plutôt qu'un instantané.

## 7. CI/CD

Le dépôt est hébergé sur GitHub (choix du propriétaire du projet), le
pipeline utilise donc GitHub Actions plutôt que GitLab CI — la forme en trois
étapes (test / build / deploy) reste celle demandée initialement.

Le point notable : l'étape de test Python ne se contente pas de mocker le
moteur Java. Elle construit et démarre le vrai jar Spring Boot, démarre un
vrai conteneur de service PostgreSQL, et lance l'intégralité de la suite
pytest — y compris les tests d'intégration — contre ces deux services réels.
Rien n'est simulé : c'est la même couverture qu'un environnement de
développement local une fois Postgres et le moteur Java lancés, exécutée sans
surveillance à chaque push.

## 8. Déploiement Azure réel

Deux composants tournent réellement sur Azure, tous deux déployés
automatiquement à chaque push sur `main`, sur le **même** App Service Plan
F1 (le quota gratuit est par plan, pas par application — deux petites
applications le partagent sans surcoût) :

- Le moteur de qualité Java
  (`wealthguard-quality-engine.azurewebsites.net`, job `deploy-azure`).
- L'assistant LangChain
  (`wealthguard-assistant.azurewebsites.net`, job `deploy-azure-assistant`),
  runtime Python 3.12, démarré par `gunicorn -k uvicorn.workers.UvicornWorker`
  (voir `azure/setup.sh`). Documentation interactive Swagger sur `/docs`.

Pas toute la Phase 9 du cahier des charges pour autant — choix assumé de
périmètre plutôt qu'un défaut :

- **App Service, palier F1 (gratuit, sans limite de temps)**, pas Azure
  Functions + PostgreSQL Flexible Server + Blob Storage comme envisagé
  initialement pour le pipeline d'ingestion. Raison : PostgreSQL managé
  **Azure** n'a **aucun palier gratuit permanent** (contrairement à App
  Service F1 ou Functions Consumption) — le déployer aurait consommé le
  crédit d'essai en continu plutôt qu'une seule fois. `data-pipeline` (Azure
  Functions) et le stockage Blob restent documentés mais non câblés (job
  `deploy-pipeline-simulated`).
- **L'assistant a quand même besoin d'un vrai PostgreSQL en ligne** pour
  répondre à ses questions — contrairement au moteur Java, il ne peut pas
  s'en passer. Solution : [Neon](https://neon.tech), un PostgreSQL managé
  *hors Azure* avec un vrai palier gratuit permanent, branché via les mêmes
  variables `AZURE_POSTGRESQL_*` que `config.py` lit déjà pour Azure ou le
  Docker local — aucune branche de code spécifique à Neon. Détail complet du
  provisionnement dans `data-pipeline/NEON_SETUP.md`. Décision prise le
  2026-09-15 à la demande explicite de l'utilisateur, qui voulait l'assistant
  utilisable en ligne sans pour autant payer un Postgres managé Azure.
- **Authentification sans secret stocké** : l'identité que GitHub Actions
  utilise pour se connecter est une *federated credential* OIDC
  (`azure/setup.sh`), pas un client secret classique — Azure fait confiance
  à un jeton émis par GitHub pour ce dépôt précis et cette branche précise
  (`main`), sans qu'aucun mot de passe ne transite ni ne soit stocké en
  secret GitHub. Le rôle accordé (`Contributor`) est limité au seul groupe
  de ressources du projet, jamais à toute la souscription.
- **Un vrai bug de configuration trouvé en déployant** : la première
  tentative de connexion OIDC a échoué avec `AADSTS700213: No matching
  federated identity record found`. Cause : le `subject` du jeton que
  GitHub émet réellement est
  `repo:OWNER@OWNER_ID/REPO@REPO_ID:ref:refs/heads/main` (avec les
  identifiants numériques du compte et du dépôt), pas le format
  `repo:OWNER/REPO:ref:refs/heads/main` habituellement documenté comme
  référence rapide. `azure/setup.sh` dérive maintenant ces identifiants
  depuis l'API publique GitHub plutôt que de les coder en dur, pour rester
  correct si le dépôt est renommé ou transféré. Bon rappel que la
  documentation de reference simplifie parfois un détail qui casse tout en
  pratique — seul le message d'erreur réel a permis de le diagnostiquer.

## 9. Ce qui n'est pas encore fait, et pourquoi

- **Azure Functions / PostgreSQL managé Azure / Blob Storage** : voir §8 —
  décision de périmètre, pas un oubli.
- **Dashboards Power BI / Tableau** : délibérément laissés à la charge de
  l'auteur du projet, qui maîtrise déjà ces outils — construits à partir des
  indicateurs exposés par `indicators.py`.
- **Whitelisting de colonnes** dans l'assistant en langage naturel : limité
  par conception à ce qu'une regex peut faire raisonnablement — voir §5.

## 10. Correspondance avec les manques identifiés en entretien

| Choix technique | Manque comblé |
|---|---|
| Java / Spring Boot, design patterns explicites | Offres exigeant Java/POO (ex. secteur bancaire/assurance), fondamentaux algorithmiques |
| PostgreSQL, SQL avancé (CTE, fenêtres) | Offres orientées ingénierie de données avec SQL exigeant |
| Algorithme de détection fait maison, complexité documentée | Fondamentaux CS/algorithmique |
| Architecture polyglotte (Java + Python + React) | Offres full-stack |
| GitHub Actions CI/CD complet (test/build/deploy) | Compétences DevOps/CI-CD |
| Grafana (monitoring) + Power BI/Tableau (métier) | Double compétence dataviz opérationnelle et métier |
| Assistant LangChain (requêtage NL sécurisé) | Offres mentionnant LangChain / requêtage en langage naturel |
