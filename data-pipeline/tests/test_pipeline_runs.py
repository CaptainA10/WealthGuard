"""Integration tests for wealthguard.pipeline_runs -- the Grafana source table.

Run the local database first (``docker compose up -d postgres``), then:

    pytest -m integration data-pipeline/tests/test_pipeline_runs.py
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from wealthguard_pipeline import db
from wealthguard_pipeline.config import get_settings
from wealthguard_pipeline.ingest import Dataset

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    try:
        settings = get_settings()
        engine = db.build_engine(settings.database)
        db.init_schema(engine)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable ({exc}); run `docker compose up -d postgres` first.")
    return engine


def _run(as_of: date, **overrides) -> dict:
    base = {
        "as_of_date": as_of,
        "anomaly_count": 10,
        "bloquant_count": 4,
        "avertissement_count": 5,
        "info_count": 1,
        "clients_valued": 3,
        "total_market_value": 12345.67,
        "duration_ms": 250,
    }
    base.update(overrides)
    return base


class TestRecordRun:
    def test_appends_a_row_that_can_be_read_back(self, engine):
        db.record_run(engine, _run(date(2024, 1, 1)))

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM wealthguard.pipeline_runs WHERE as_of_date = :d ORDER BY run_at DESC LIMIT 1"),
                {"d": date(2024, 1, 1)},
            ).mappings().one()

        assert row["anomaly_count"] == 10
        assert row["bloquant_count"] == 4
        assert float(row["total_market_value"]) == pytest.approx(12345.67)
        assert row["run_id"] is not None
        assert row["run_at"] is not None

    def test_loading_a_new_dataset_does_not_erase_run_history(self, engine):
        # pipeline_runs is append-only and persists across separate test
        # sessions against the same local Postgres, so this counts a delta
        # rather than asserting an absolute 0-or-1 -- a prior session may
        # already have left rows for this same as_of_date.
        with engine.connect() as conn:
            before = conn.execute(
                text("SELECT count(*) FROM wealthguard.pipeline_runs WHERE as_of_date = :d"),
                {"d": date(2024, 1, 2)},
            ).scalar_one()

        db.record_run(engine, _run(date(2024, 1, 2)))

        empty = Dataset(
            clients=pd.DataFrame(columns=["client_id", "full_name", "risk_profile", "reference_currency", "onboarding_date", "advisor"]),
            instruments=pd.DataFrame(columns=["ticker", "name", "instrument_type", "asset_class", "currency", "exchange"]),
            positions=pd.DataFrame(columns=["position_id", "client_id", "ticker", "quantity", "purchase_price", "purchase_date", "currency"]),
            target_allocations=pd.DataFrame(columns=["client_id", "asset_class", "target_weight_pct"]),
            market_prices=pd.DataFrame(columns=["ticker", "price_date", "close_price", "currency", "price_source"]),
        )
        db.load_dataset(engine, empty)

        with engine.connect() as conn:
            after = conn.execute(
                text("SELECT count(*) FROM wealthguard.pipeline_runs WHERE as_of_date = :d"),
                {"d": date(2024, 1, 2)},
            ).scalar_one()

        assert after == before + 1

    def test_multiple_runs_accumulate_rather_than_overwrite(self, engine):
        with engine.begin() as conn:
            before = conn.execute(text("SELECT count(*) FROM wealthguard.pipeline_runs")).scalar_one()

        db.record_run(engine, _run(date(2024, 1, 3)))
        db.record_run(engine, _run(date(2024, 1, 4)))

        with engine.connect() as conn:
            after = conn.execute(text("SELECT count(*) FROM wealthguard.pipeline_runs")).scalar_one()

        assert after == before + 2
