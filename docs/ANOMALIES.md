# Anomalies injectees volontairement

> Fichier **genere** par `python -m wealthguard_pipeline.seed.generate`.
> Ne pas editer a la main : la source de verite est
> `data-pipeline/wealthguard_pipeline/seed/anomalies.py` (`ANOMALY_CATALOGUE`).

- Jeu de donnees genere avec la graine `42`, date de reference `2026-09-13`.
- **46 anomalies** injectees sur 435 positions, 46 clients et 13589 cours.

Repartition attendue par criticite :

| Criticite | Occurrences |
|---|---|
| AVERTISSEMENT | 23 |
| BLOQUANT | 21 |
| INFO | 2 |

## Catalogue

| Code | Jeu de donnees | Detecteur | Regle attendue | Criticite | Occurrences | Description | Impact metier estime |
|---|---|---|---|---|---|---|---|
| `MISSING_CLIENT_ID` | positions | JAVA_RULE_ENGINE | `POS_REQUIRED_FIELDS` | BLOQUANT | 2 | Le client_id de la position est vide. | Position non rattachable a un portefeuille : elle disparait de toute valorisation client. |
| `MISSING_QUANTITY` | positions | JAVA_RULE_ENGINE | `POS_REQUIRED_FIELDS` | BLOQUANT | 2 | La quantite de la position est absente. | Valorisation impossible : la ligne est ignoree ou comptee a zero, sous-estimant l'encours. |
| `NEGATIVE_QUANTITY` | positions | JAVA_RULE_ENGINE | `POS_POSITIVE_QUANTITY` | BLOQUANT | 3 | Quantite strictement negative sur un portefeuille long-only. | Valorisation negative : l'encours total du client est minore. |
| `NON_POSITIVE_PURCHASE_PRICE` | positions | JAVA_RULE_ENGINE | `POS_POSITIVE_PURCHASE_PRICE` | BLOQUANT | 3 | Prix d'achat nul ou negatif (le zero est le cas limite classique). | Prix de revient fausse : la plus-value latente devient infinie ou absurde. |
| `UNKNOWN_TICKER` | positions | JAVA_RULE_ENGINE | `POS_KNOWN_INSTRUMENT` | BLOQUANT | 2 | Ticker absent du referentiel instruments. | Aucun prix de marche disponible : la position ne peut pas etre valorisee ni classee. |
| `ORPHAN_CLIENT_REF` | positions | JAVA_RULE_ENGINE | `POS_KNOWN_CLIENT` | BLOQUANT | 2 | client_id qui ne correspond a aucun client du referentiel. | Encours orphelin : le total plateforme ne reconcilie plus avec la somme des clients. |
| `FUTURE_PURCHASE_DATE` | positions | JAVA_RULE_ENGINE | `POS_PURCHASE_DATE_NOT_FUTURE` | BLOQUANT | 2 | Date d'achat posterieure a la date du jour. | Performance calculee sur une duree negative : indicateur de performance invalide. |
| `PURCHASE_BEFORE_ONBOARDING` | positions | JAVA_RULE_ENGINE | `POS_PURCHASE_AFTER_ONBOARDING` | AVERTISSEMENT | 2 | Achat anterieur a la date d'entree en relation du client. | Incoherence chronologique : soit la position appartient a un autre client, soit la date d'onboarding est fausse. |
| `CURRENCY_MISMATCH` | positions | JAVA_RULE_ENGINE | `POS_CURRENCY_MATCHES_INSTRUMENT` | AVERTISSEMENT | 2 | Devise de la position differente de la devise de cotation de l'instrument. | Melange de devises non converti : l'allocation en pourcentage est fausse. |
| `EXCESSIVE_CONCENTRATION` | positions | JAVA_RULE_ENGINE | `POS_CONCENTRATION_LIMIT` | AVERTISSEMENT | 2 | Une ligne depasse 40 % du prix de revient du portefeuille. | Risque de concentration contraire a la politique d'investissement : alerte conformite. |
| `EXCESSIVE_QUANTITY_PRECISION` | positions | JAVA_RULE_ENGINE | `POS_QUANTITY_PRECISION` | INFO | 2 | Quantite comportant plus de 4 decimales. | Aucun impact de valorisation, mais signale un export amont degrade (arrondi flottant). |
| `INVALID_RISK_PROFILE` | clients | JAVA_RULE_ENGINE | `CLI_KNOWN_RISK_PROFILE` | AVERTISSEMENT | 2 | Profil de risque hors nomenclature (ex. 'AGRESSIF' au lieu de 'OFFENSIF'). | Controle d'adequation impossible : on ne peut pas comparer l'allocation reelle a la cible du profil. |
| `ALLOCATION_SUM_MISMATCH` | target_allocations | JAVA_RULE_ENGINE | `ALLOC_SUM_EQUALS_100` | AVERTISSEMENT | 3 | Somme des allocations cibles differente de 100 % (107 % ici). | Cible d'allocation inexploitable : tout ecart cible/reel calcule dessus est biaise. |
| `ALLOCATION_WEIGHT_OUT_OF_RANGE` | target_allocations | JAVA_RULE_ENGINE | `ALLOC_WEIGHT_IN_RANGE` | BLOQUANT | 1 | Poids cible hors de l'intervalle [0, 100] (-5 % ici), la somme restant a 100 %. | Cible negative impossible : revele une inversion de signe dans l'outil amont. |
| `ORPHAN_ALLOCATION_CLIENT_REF` | target_allocations | JAVA_RULE_ENGINE | `ALLOC_KNOWN_CLIENT` | BLOQUANT | 1 | Ligne d'allocation cible rattachee a un client inexistant. | Cible fantome : les ecarts cible/reel agreges au niveau cabinet sont fausses. |
| `DUP_POSITION_ID` | positions | JAVA_RULE_ENGINE | `POS_UNIQUE_ID` | BLOQUANT | 2 | Deux lignes partagent le meme position_id avec des quantites differentes. | Double comptage de l'encours : l'actif sous gestion est surevalue. |
| `DUP_CLIENT_ID` | clients | JAVA_RULE_ENGINE | `CLI_UNIQUE_ID` | BLOQUANT | 1 | Deux fiches client portent le meme client_id. | Jointure en eventail : chaque position du client est comptee deux fois. |
| `MISSING_CLOSE_PRICE` | market_prices | PYTHON_INGESTION | `INGEST_CLOSE_PRICE_REQUIRED` | AVERTISSEMENT | 4 | Cours de cloture absent pour un couple (ticker, date). | Trou dans la serie : la valorisation du jour retombe sur le dernier cours connu. |
| `DUP_MARKET_PRICE` | market_prices | PYTHON_INGESTION | `INGEST_UNIQUE_PRICE_PER_DAY` | AVERTISSEMENT | 3 | Deux cours de cloture pour le meme couple (ticker, date). | Jointure en eventail sur les prix : duplication de chaque position valorisee ce jour-la. |
| `PRICE_SPIKE` | market_prices | PYTHON_OUTLIER_DETECTOR | `OUTLIER_RETURN_ZSCORE_IQR` | AVERTISSEMENT | 5 | Cours de cloture multiplie par 4,5 (erreur de saisie). | Valorisation et performance du jour totalement faussees pour toutes les positions sur ce titre. |

## Comment ce fichier est verifie

Ce catalogue n'est pas de la documentation declarative : il sert d'oracle de test.

1. `data/seed/anomaly_manifest.json` liste la cle exacte de chaque enregistrement corrompu.
2. `pytest data-pipeline/tests/test_seed_manifest.py` verifie la coherence du manifeste
   (isolation des lignes, couverture du catalogue, comptes par criticite).
3. `pytest -m integration data-pipeline/tests/test_end_to_end.py` envoie le jeu `landing/`
   au moteur Java et compare la reponse au manifeste, regle par regle.

Toute regle ajoutee cote Java sans entree correspondante ici (ou l'inverse) fait
echouer la suite de tests.

## Invariant d'isolation

Chaque injection reserve sa ligne de facon exclusive (`RowClaimer`), afin qu'une
ligne corrompue ne viole qu'une seule regle. C'est ce qui rend le decompte
interpretable : si le moteur remonte 24 anomalies au lieu de 46, l'ecart est
forcement un faux positif identifiable, pas un effet de bord de l'injection.
