-- Allocation reelle par classe d'actif vs allocation cible, par client.
--
-- "class_value" agrege d'abord par (client, classe), puis
-- SUM(SUM(market_value)) OVER (PARTITION BY client_id) recalcule le total du
-- client sans repasser par une deuxieme requete d'agregation : la fonction
-- fenetre s'applique apres le GROUP BY, sur le resultat deja agrege.
-- LEFT JOIN vers target_allocations pour afficher l'ecart cible/reel, y
-- compris quand aucune position ne couvre encore une classe cible.
WITH ranked_prices AS (
    SELECT
        ticker,
        close_price,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY price_date DESC) AS rn
    FROM wealthguard.market_prices
    WHERE price_date <= :as_of_date AND close_price IS NOT NULL
),
latest_price AS (
    SELECT ticker, close_price FROM ranked_prices WHERE rn = 1
),
position_value AS (
    SELECT
        p.client_id,
        i.asset_class,
        p.quantity * lp.close_price AS market_value
    FROM wealthguard.positions p
    JOIN wealthguard.instruments i ON i.ticker = p.ticker
    JOIN latest_price lp ON lp.ticker = p.ticker
    WHERE p.quantity > 0 AND p.purchase_price > 0
),
class_value AS (
    SELECT
        client_id,
        asset_class,
        SUM(market_value) AS class_market_value,
        SUM(SUM(market_value)) OVER (PARTITION BY client_id) AS client_market_value
    FROM position_value
    GROUP BY client_id, asset_class
)
SELECT
    cv.client_id,
    c.full_name,
    cv.asset_class,
    ROUND(cv.class_market_value, 2) AS class_market_value,
    ROUND(100.0 * cv.class_market_value / NULLIF(cv.client_market_value, 0), 2) AS actual_weight_pct,
    ta.target_weight_pct,
    ROUND(
        100.0 * cv.class_market_value / NULLIF(cv.client_market_value, 0) - ta.target_weight_pct,
        2
    ) AS gap_pct
FROM class_value cv
JOIN wealthguard.clients c ON c.client_id = cv.client_id
LEFT JOIN wealthguard.target_allocations ta
    ON ta.client_id = cv.client_id AND ta.asset_class = cv.asset_class
ORDER BY cv.client_id, cv.asset_class;
