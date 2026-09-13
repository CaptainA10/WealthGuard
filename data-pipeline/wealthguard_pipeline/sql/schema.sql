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
