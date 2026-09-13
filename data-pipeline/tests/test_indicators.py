"""Integration tests for the SQL indicators -- require a real PostgreSQL.

Run the local database first (``docker compose up -d postgres``), then:

    pytest -m integration data-pipeline/tests/test_indicators.py

Skips cleanly (rather than failing) when the database is not reachable, so
the default ``pytest`` run stays green on a machine without Docker running.

These tests truncate and reload the ``wealthguard`` schema's tables with a
small, hand-computed dataset -- do not point ``AZURE_POSTGRESQL_*`` at a
database whose data you want to keep.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from wealthguard_pipeline import db, indicators
from wealthguard_pipeline.config import get_settings
from wealthguard_pipeline.ingest import Dataset

pytestmark = pytest.mark.integration

AS_OF = date(2024, 1, 10)


@pytest.fixture(scope="module")
def engine():
    try:
        settings = get_settings()
        engine = db.build_engine(settings.database)
        db.init_schema(engine)
    except Exception as exc:  # noqa: BLE001 - broad on purpose: any reason to skip is the same reason.
        pytest.skip(f"PostgreSQL not reachable ({exc}); run `docker compose up -d postgres` first.")
    return engine


@pytest.fixture(scope="module", autouse=True)
def loaded_dataset(engine):
    clients = pd.DataFrame(
        {
            "client_id": ["C1", "C2"],
            "full_name": ["Client One", "Client Two"],
            "risk_profile": ["EQUILIBRE", "PRUDENT"],
            "reference_currency": ["EUR", "EUR"],
            "onboarding_date": [date(2020, 1, 1), date(2020, 1, 1)],
            "advisor": ["A. Kessler", "A. Kessler"],
        }
    )
    instruments = pd.DataFrame(
        {
            "ticker": ["TICK1", "TICK2"],
            "name": ["Test Equity", "Test Bond"],
            "instrument_type": ["STOCK", "ETF"],
            "asset_class": ["ACTIONS", "OBLIGATIONS"],
            "currency": ["USD", "USD"],
            "exchange": ["TEST", "TEST"],
        }
    )
    positions = pd.DataFrame(
        {
            "position_id": ["P1", "P2", "P3"],
            "client_id": ["C1", "C1", "C2"],
            "ticker": ["TICK1", "TICK2", "TICK1"],
            "quantity": [10.0, 5.0, 2.0],
            "purchase_price": [100.0, 50.0, 100.0],
            "purchase_date": [date(2023, 1, 1)] * 3,
            "currency": ["USD"] * 3,
        }
    )
    market_prices = pd.DataFrame(
        {
            "ticker": ["TICK1", "TICK1", "TICK2", "TICK2"],
            "price_date": [date(2024, 1, 1), date(2024, 1, 5), date(2024, 1, 1), date(2024, 1, 5)],
            "close_price": [100.0, 120.0, 50.0, 55.0],
            "currency": ["USD"] * 4,
            "price_source": ["SYNTHETIC"] * 4,
        }
    )
    target_allocations = pd.DataFrame(
        {
            "client_id": ["C1", "C1", "C2"],
            "asset_class": ["ACTIONS", "OBLIGATIONS", "ACTIONS"],
            "target_weight_pct": [70.0, 30.0, 100.0],
        }
    )
    db.load_dataset(engine, Dataset(clients, instruments, positions, target_allocations, market_prices))


class TestPortfolioValuation:
    def test_uses_the_latest_price_at_or_before_as_of(self, engine):
        result = indicators.portfolio_valuation(engine, AS_OF).set_index("client_id")

        # C1: cost 10*100 + 5*50 = 1250; market 10*120 + 5*55 = 1475.
        assert result.loc["C1", "total_cost_basis"] == pytest.approx(1250.0)
        assert result.loc["C1", "total_market_value"] == pytest.approx(1475.0)
        assert result.loc["C1", "unrealized_gain"] == pytest.approx(225.0)
        assert result.loc["C1", "unrealized_gain_pct"] == pytest.approx(18.0)

    def test_ignores_prices_after_the_valuation_date(self, engine):
        result = indicators.portfolio_valuation(engine, date(2024, 1, 2)).set_index("client_id")

        # Only the 2024-01-01 close (100 / 50) should be visible.
        assert result.loc["C1", "total_market_value"] == pytest.approx(10 * 100.0 + 5 * 50.0)

    def test_a_client_with_no_position_still_appears(self, engine):
        result = indicators.portfolio_valuation(engine, AS_OF)

        assert set(result["client_id"]) == {"C1", "C2"}


class TestAllocationVsTarget:
    def test_computes_actual_weight_and_the_gap_to_target(self, engine):
        result = indicators.allocation_vs_target(engine, AS_OF).set_index(["client_id", "asset_class"])

        actions = result.loc[("C1", "ACTIONS")]
        assert actions["actual_weight_pct"] == pytest.approx(1200 / 1475 * 100, abs=0.01)
        assert actions["target_weight_pct"] == pytest.approx(70.0)
        assert actions["gap_pct"] == pytest.approx(1200 / 1475 * 100 - 70.0, abs=0.01)

    def test_weights_of_one_client_sum_to_one_hundred(self, engine):
        result = indicators.allocation_vs_target(engine, AS_OF)

        c1_total = result[result["client_id"] == "C1"]["actual_weight_pct"].sum()
        assert c1_total == pytest.approx(100.0, abs=0.02)


class TestTopHoldings:
    def test_ranks_holdings_by_market_value_descending(self, engine):
        result = indicators.top_holdings(engine, AS_OF, top_n=1)
        c1_top = result[result["client_id"] == "C1"].iloc[0]

        assert c1_top["position_id"] == "P1"  # 10*120=1200 beats 5*55=275
        assert c1_top["rank_in_portfolio"] == 1

    def test_respects_top_n(self, engine):
        result = indicators.top_holdings(engine, AS_OF, top_n=1)

        assert (result.groupby("client_id").size() == 1).all()
