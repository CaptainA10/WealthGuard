-- WealthGuard warehouse schema.
--
-- Loaded by wealthguard_pipeline.db.init_schema() and, for a from-scratch local
-- Docker Postgres, mounted by docker-compose.yml into
-- /docker-entrypoint-initdb.d so a fresh container already has it.
--
-- Foreign keys are deliberate, not decorative: they are the safety net behind
-- wealthguard_pipeline.quarantine -- if a BLOQUANT row ever slipped through
-- the quarantine step, the load would fail loudly here instead of silently
-- corrupting an indicator.

CREATE SCHEMA IF NOT EXISTS wealthguard;

SET search_path TO wealthguard;

CREATE TABLE IF NOT EXISTS clients (
    client_id           TEXT PRIMARY KEY,
    full_name           TEXT NOT NULL,
    risk_profile        TEXT NOT NULL,
    reference_currency  TEXT NOT NULL,
    onboarding_date     DATE NOT NULL,
    advisor             TEXT
);

CREATE TABLE IF NOT EXISTS instruments (
    ticker           TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    instrument_type  TEXT NOT NULL,
    asset_class      TEXT NOT NULL,
    currency         TEXT NOT NULL,
    exchange         TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    position_id     TEXT PRIMARY KEY,
    client_id       TEXT NOT NULL REFERENCES clients(client_id),
    ticker          TEXT NOT NULL REFERENCES instruments(ticker),
    quantity        NUMERIC NOT NULL,
    purchase_price  NUMERIC NOT NULL,
    purchase_date   DATE NOT NULL,
    currency        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_prices (
    ticker        TEXT NOT NULL REFERENCES instruments(ticker),
    price_date    DATE NOT NULL,
    close_price   NUMERIC,
    currency      TEXT,
    price_source  TEXT,
    PRIMARY KEY (ticker, price_date)
);

CREATE TABLE IF NOT EXISTS target_allocations (
    client_id          TEXT NOT NULL REFERENCES clients(client_id),
    asset_class        TEXT NOT NULL,
    target_weight_pct  NUMERIC NOT NULL,
    PRIMARY KEY (client_id, asset_class)
);

CREATE INDEX IF NOT EXISTS idx_positions_client_id ON positions(client_id);
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
CREATE INDEX IF NOT EXISTS idx_market_prices_ticker_date ON market_prices(ticker, price_date);

-- Append-only run history, for the Grafana monitoring dashboard (ops view of
-- the pipeline itself, distinct from the Power BI/Tableau business dashboards
-- built on the tables above). Never truncated by db.load_dataset(): a full
-- refresh replaces the day's data but must never erase yesterday's trend.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    as_of_date           DATE NOT NULL,
    anomaly_count        INTEGER NOT NULL,
    bloquant_count       INTEGER NOT NULL,
    avertissement_count  INTEGER NOT NULL,
    info_count           INTEGER NOT NULL,
    clients_valued       INTEGER NOT NULL,
    total_market_value   NUMERIC NOT NULL,
    duration_ms          BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_run_at ON pipeline_runs(run_at);

-- ---------------------------------------------------------------------------
-- Views for Power BI / Tableau (cahier des charges §2.5): the same CTE +
-- window-function logic as sql/*.sql, minus the :as_of_date /:top_n bind
-- parameters a plain VIEW cannot take. Point a BI tool's PostgreSQL connector
-- at these three and it sees ready-made tables -- no CTE or window function
-- needs writing again in Power Query / Tableau's calculated fields.
--
-- Evaluated as of CURRENT_DATE rather than a parameter: a BI tool wants "the
-- current state" refreshed on its own schedule, not one frozen valuation
-- date. v_top_holdings deliberately does not cap row count -- it exposes
-- rank_in_portfolio and lets the BI tool's own Top-N filter/visual decide,
-- which is the idiomatic way to do that in Power BI or Tableau rather than
-- baking a fixed N into the source.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_portfolio_valuation AS
WITH ranked_prices AS (
    SELECT
        ticker,
        close_price,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY price_date DESC) AS rn
    FROM market_prices
    WHERE price_date <= CURRENT_DATE AND close_price IS NOT NULL
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
    FROM positions p
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
FROM clients c
LEFT JOIN position_valuation pv ON pv.client_id = c.client_id
GROUP BY c.client_id, c.full_name, c.risk_profile, c.reference_currency;

CREATE OR REPLACE VIEW v_allocation_vs_target AS
WITH ranked_prices AS (
    SELECT
        ticker,
        close_price,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY price_date DESC) AS rn
    FROM market_prices
    WHERE price_date <= CURRENT_DATE AND close_price IS NOT NULL
),
latest_price AS (
    SELECT ticker, close_price FROM ranked_prices WHERE rn = 1
),
position_value AS (
    SELECT
        p.client_id,
        i.asset_class,
        p.quantity * lp.close_price AS market_value
    FROM positions p
    JOIN instruments i ON i.ticker = p.ticker
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
JOIN clients c ON c.client_id = cv.client_id
LEFT JOIN target_allocations ta
    ON ta.client_id = cv.client_id AND ta.asset_class = cv.asset_class;

CREATE OR REPLACE VIEW v_top_holdings AS
WITH ranked_prices AS (
    SELECT
        ticker,
        close_price,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY price_date DESC) AS rn
    FROM market_prices
    WHERE price_date <= CURRENT_DATE AND close_price IS NOT NULL
),
latest_price AS (
    SELECT ticker, close_price FROM ranked_prices WHERE rn = 1
)
SELECT
    p.client_id,
    c.full_name,
    p.position_id,
    p.ticker,
    i.asset_class,
    ROUND(p.quantity * lp.close_price, 2) AS market_value,
    RANK() OVER (
        PARTITION BY p.client_id ORDER BY p.quantity * lp.close_price DESC
    ) AS rank_in_portfolio
FROM positions p
JOIN clients c ON c.client_id = p.client_id
JOIN instruments i ON i.ticker = p.ticker
JOIN latest_price lp ON lp.ticker = p.ticker
WHERE p.quantity > 0 AND p.purchase_price > 0;
