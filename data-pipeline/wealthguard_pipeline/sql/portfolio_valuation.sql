-- Valorisation totale, cout de revient et plus-value latente, par client.
--
-- CTE "ranked_prices" : fonction fenetre ROW_NUMBER() pour ne garder que le
-- dernier cours connu au plus tard a :as_of_date, sans sous-requete correlee.
-- Jointures positions -> instruments (implicite via le dernier cours) ->
-- clients, puis agregation. LEFT JOIN clients -> position_valuation pour que
-- les clients sans position valorisable apparaissent quand meme, a zero.
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
position_valuation AS (
    SELECT
        p.client_id,
        p.position_id,
        p.quantity * p.purchase_price AS cost_basis,
        p.quantity * lp.close_price AS market_value
    FROM wealthguard.positions p
    JOIN latest_price lp ON lp.ticker = p.ticker
    WHERE p.quantity > 0 AND p.purchase_price > 0
)
SELECT
    c.client_id,
    c.full_name,
    c.risk_profile,
    c.reference_currency,
    COALESCE(SUM(pv.cost_basis), 0)                                    AS total_cost_basis,
    COALESCE(SUM(pv.market_value), 0)                                  AS total_market_value,
    COALESCE(SUM(pv.market_value) - SUM(pv.cost_basis), 0)             AS unrealized_gain,
    CASE
        WHEN COALESCE(SUM(pv.cost_basis), 0) = 0 THEN NULL
        ELSE ROUND(100.0 * (SUM(pv.market_value) - SUM(pv.cost_basis)) / SUM(pv.cost_basis), 2)
    END                                                                 AS unrealized_gain_pct
FROM wealthguard.clients c
LEFT JOIN position_valuation pv ON pv.client_id = c.client_id
GROUP BY c.client_id, c.full_name, c.risk_profile, c.reference_currency
ORDER BY total_market_value DESC;
