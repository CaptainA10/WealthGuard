from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from wealthguard_pipeline import ingest
from wealthguard_pipeline.config import REPO_ROOT
from wealthguard_pipeline.outliers import OutlierDetectorConfig, detect_price_outliers

TICKER = "TEST"
LANDING_DIR = REPO_ROOT / "data" / "seed" / "landing"
MANIFEST_PATH = REPO_ROOT / "data" / "seed" / "anomaly_manifest.json"


def _series(prices: list[float], start: date = date(2024, 1, 1)) -> pd.DataFrame:
    dates = [start + timedelta(days=i) for i in range(len(prices))]
    return pd.DataFrame({"ticker": TICKER, "price_date": dates, "close_price": prices})


def _stable_prices(n: int, base: float = 100.0, noise: float = 0.5, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(base + rng.normal(0.0, noise, size=n))


class TestDetectPriceOutliers:
    def test_flags_a_single_point_spike_and_only_that_point(self):
        prices = _stable_prices(41)
        spike_index = 20
        prices[spike_index] *= 4.5
        df = _series(prices)

        found = detect_price_outliers(df)

        flagged_dates = {a.record_key for a in found}
        expected_key = f"ticker={TICKER}&price_date={date(2024, 1, 1) + timedelta(days=spike_index)}"
        assert flagged_dates == {expected_key}

    def test_reports_no_outlier_on_a_stable_series(self):
        df = _series(_stable_prices(60))

        assert detect_price_outliers(df) == []

    def test_does_not_flag_the_day_after_a_spike(self):
        prices = _stable_prices(41)
        spike_index = 20
        prices[spike_index] *= 4.5
        df = _series(prices)

        found = detect_price_outliers(df)

        next_day_key = f"ticker={TICKER}&price_date={date(2024, 1, 1) + timedelta(days=spike_index + 1)}"
        assert next_day_key not in {a.record_key for a in found}

    def test_skips_every_point_when_the_series_is_too_short_for_the_window(self):
        # 5 points total, but 10 are required just to trust the window's own
        # dispersion: every point must be skipped, not mis-judged on a thin sample.
        config = OutlierDetectorConfig(half_window=10, min_window_observations=10)
        prices = _stable_prices(5)
        prices[2] *= 4.5
        df = _series(prices)

        found = detect_price_outliers(df, config)

        assert found == []

    def test_still_judges_a_point_with_enough_one_sided_neighbours(self):
        # Near the start of a longer series, the window is one-sided but still
        # has >= min_window_observations points, so the point must be judged.
        config = OutlierDetectorConfig(half_window=10, min_window_observations=10)
        prices = _stable_prices(15)
        prices[2] *= 4.5
        df = _series(prices)

        found = detect_price_outliers(df, config)

        assert {a.record_key for a in found} == {
            f"ticker={TICKER}&price_date={date(2024, 1, 1) + timedelta(days=2)}"
        }

    def test_ignores_nan_prices_without_crashing(self):
        prices = _stable_prices(41)
        prices[20] = float("nan")
        df = _series(prices)

        found = detect_price_outliers(df)

        assert all(a.record_key != f"ticker={TICKER}&price_date={date(2024, 1, 1) + timedelta(days=20)}" for a in found)

    def test_handles_an_empty_frame(self):
        empty = pd.DataFrame(columns=["ticker", "price_date", "close_price"])

        assert detect_price_outliers(empty) == []

    def test_handles_a_constant_series_without_dividing_by_zero(self):
        df = _series([100.0] * 41)

        assert detect_price_outliers(df) == []

    def test_detects_independently_per_ticker(self):
        a = _stable_prices(41, seed=1)
        a[20] *= 4.5
        b = _stable_prices(41, seed=2)  # no spike
        df = pd.concat(
            [
                _series(a).assign(ticker="AAA"),
                _series(b).assign(ticker="BBB"),
            ],
            ignore_index=True,
        )

        found = detect_price_outliers(df)

        assert {a.record_key.split("&")[0] for a in found} == {"ticker=AAA"}

    @pytest.mark.parametrize("field", ["ticker", "price_date", "close_price"])
    def test_required_columns_must_be_present(self, field):
        df = _series(_stable_prices(10)).drop(columns=[field])

        with pytest.raises(KeyError):
            detect_price_outliers(df)


@pytest.mark.skipif(not (LANDING_DIR.exists() and MANIFEST_PATH.exists()), reason="seed dataset not generated")
class TestDetectPriceOutliersOnTheRealSeedDataset:
    """Regression check against real Yahoo Finance history (docs/ANOMALIES.md):
    all 5 deliberately injected PRICE_SPIKE rows must be recalled. The detector
    is expected to also flag genuine large moves in the real data beyond those
    5 -- that is the point of running it on real history rather than only a
    synthetic fixture -- so this asserts recall on the known spikes, not an
    exact total count.
    """

    def test_recalls_every_deliberately_injected_spike(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        expected_keys = {
            a["record_key"] for a in manifest["anomalies"] if a["anomaly_code"] == "PRICE_SPIKE"
        }
        assert expected_keys, "manifest has no PRICE_SPIKE entries to check against"

        dataset = ingest.load_landing(LANDING_DIR)
        found = detect_price_outliers(dataset.market_prices)
        found_keys = {a.record_key for a in found}

        # record_key dates render with a time component (pandas Timestamp) on
        # the detector's side but not in the manifest -- compare on the date.
        found_dates_by_ticker: dict[str, set[str]] = {}
        for key in found_keys:
            ticker_part, date_part = key.split("&price_date=")
            found_dates_by_ticker.setdefault(ticker_part, set()).add(date_part.split("T")[0])

        missed = [
            key for key in expected_keys
            if key.split("&price_date=")[1] not in found_dates_by_ticker.get(key.split("&price_date=")[0], set())
        ]
        assert missed == [], f"PRICE_SPIKE row(s) not recalled by the detector: {missed}"
