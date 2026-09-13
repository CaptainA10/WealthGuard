from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from wealthguard_pipeline import ingest
from wealthguard_pipeline.config import REPO_ROOT
from wealthguard_pipeline.models import INFO  # noqa: F401  (sanity import)

LANDING_DIR = REPO_ROOT / "data" / "seed" / "landing"


class TestCheckMarketPrices:
    def test_flags_a_missing_close_price(self):
        df = pd.DataFrame(
            {
                "ticker": ["AAPL", "AAPL"],
                "price_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "close_price": [100.0, np.nan],
            }
        )

        found = ingest.check_market_prices(df)

        assert len(found) == 1
        assert found[0].rule_id == ingest.INGEST_CLOSE_PRICE_REQUIRED
        assert found[0].record_key == "ticker=AAPL&price_date=2024-01-02"

    def test_flags_a_duplicated_ticker_date_pair(self):
        df = pd.DataFrame(
            {
                "ticker": ["AAPL", "AAPL", "MSFT"],
                "price_date": [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 1)],
                "close_price": [100.0, 100.5, 200.0],
            }
        )

        found = ingest.check_market_prices(df)

        assert len(found) == 1
        assert found[0].rule_id == ingest.INGEST_UNIQUE_PRICE_PER_DAY
        assert found[0].observed_value == "2 occurrences"

    def test_reports_nothing_on_a_clean_feed(self):
        df = pd.DataFrame(
            {
                "ticker": ["AAPL", "MSFT"],
                "price_date": [date(2024, 1, 1), date(2024, 1, 1)],
                "close_price": [100.0, 200.0],
            }
        )

        assert ingest.check_market_prices(df) == []

    def test_a_row_can_be_both_missing_and_duplicated(self):
        df = pd.DataFrame(
            {
                "ticker": ["AAPL", "AAPL"],
                "price_date": [date(2024, 1, 1), date(2024, 1, 1)],
                "close_price": [np.nan, np.nan],
            }
        )

        found = ingest.check_market_prices(df)

        rule_ids = {a.rule_id for a in found}
        assert rule_ids == {ingest.INGEST_CLOSE_PRICE_REQUIRED, ingest.INGEST_UNIQUE_PRICE_PER_DAY}


class TestDedupeMarketPrices:
    def test_keeps_the_last_row_for_a_duplicated_pair(self):
        df = pd.DataFrame(
            {
                "ticker": ["AAPL", "AAPL"],
                "price_date": [date(2024, 1, 1), date(2024, 1, 1)],
                "close_price": [100.0, 100.5],
            }
        )

        result = ingest.dedupe_market_prices(df)

        assert len(result) == 1
        assert result.iloc[0]["close_price"] == 100.5

    def test_leaves_a_clean_frame_untouched(self):
        df = pd.DataFrame(
            {
                "ticker": ["AAPL", "MSFT"],
                "price_date": [date(2024, 1, 1), date(2024, 1, 1)],
                "close_price": [100.0, 200.0],
            }
        )

        result = ingest.dedupe_market_prices(df)

        assert len(result) == 2


class TestLoadLanding:
    @pytest.mark.skipif(not LANDING_DIR.exists(), reason="seed dataset not generated")
    def test_reads_the_committed_seed_dataset(self):
        dataset = ingest.load_landing(LANDING_DIR)

        assert not dataset.clients.empty
        assert not dataset.instruments.empty
        assert not dataset.positions.empty
        assert not dataset.market_prices.empty
        # target_allocations.xlsx in landing/ -- exercises the Excel fallback path.
        assert not dataset.target_allocations.empty
        assert set(dataset.target_allocations.columns) >= {"client_id", "asset_class", "target_weight_pct"}

    def test_falls_back_to_excel_when_no_csv_exists(self, tmp_path):
        df = pd.DataFrame({"client_id": ["C1"], "asset_class": ["ACTIONS"], "target_weight_pct": [100.0]})
        df.to_excel(tmp_path / "target_allocations.xlsx", index=False)
        for name, cols in [
            ("clients", ["client_id", "full_name", "risk_profile", "reference_currency", "onboarding_date", "advisor"]),
            ("instruments", ["ticker", "name", "instrument_type", "asset_class", "currency", "exchange"]),
            ("positions", ["position_id", "client_id", "ticker", "quantity", "purchase_price", "purchase_date", "currency"]),
            ("market_prices", ["ticker", "price_date", "close_price", "currency", "price_source"]),
        ]:
            pd.DataFrame(columns=cols).to_csv(tmp_path / f"{name}.csv", index=False)

        dataset = ingest.load_landing(tmp_path)

        assert list(dataset.target_allocations["client_id"]) == ["C1"]

    def test_raises_a_clear_error_when_a_table_is_missing_entirely(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ingest.load_landing(tmp_path)
