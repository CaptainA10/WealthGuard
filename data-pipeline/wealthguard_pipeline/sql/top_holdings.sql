-- Top :top_n lignes par client en valeur de marche.
--
-- RANK() OVER (PARTITION BY client_id ORDER BY market_value DESC) : une
-- deuxieme famille de fonction fenetre (classement) distincte des agregats
-- utilises dans allocation_vs_target.sql. RANK() plutot que ROW_NUMBER() pour
-- que deux lignes de valeur strictement egale partagent le meme rang plutot
-- que d'etre departagees arbitrairement.
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
        p.position_id,
        p.ticker,
        p.quantity * lp.close_price AS market_value,
        RANK() OVER (
            PARTITION BY p.client_id ORDER BY p.quantity * lp.close_price DESC
        ) AS rank_in_portfolio
    FROM wealthguard.positions p
    JOIN latest_price lp ON lp.ticker = p.ticker
    WHERE p.quantity > 0 AND p.purchase_price > 0
)
SELECT
    pv.client_id,
    c.full_name,
    pv.rank_in_portfolio,
    pv.position_id,
    pv.ticker,
    ROUND(pv.market_value, 2) AS market_value
FROM position_value pv
JOIN wealthguard.clients c ON c.client_id = pv.client_id
WHERE pv.rank_in_portfolio <= :top_n
ORDER BY pv.client_id, pv.rank_in_portfolio;
