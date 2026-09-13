"""Home-made statistical outlier detector for market close prices.

Cahier des charges §2.3: a hand-written detection algorithm (z-score / IQR),
not a call into a ready-made ML library, with its complexity documented.

**Why a local window on price levels, not a global check on returns.** The
obvious first design is: compute day-over-day returns for a ticker, then flag
any return whose z-score or IQR fence is exceeded, using the *whole* series as
the reference distribution. That design has a bug that only shows up on a real
fat-fingered spike: a single corrupted price at date D distorts *two*
consecutive returns -- the return entering D (huge positive) and the return
leaving D (huge negative, as the price reverts on D+1) -- so one bad price
produces two flagged dates instead of one, and a caller cannot tell from the
output alone which date actually holds the bad print.

Comparing each price instead to a **local window of its neighbours, with the
point itself excluded from the window's own statistics**, avoids this:

* At the spike date D, the reference window is built entirely from clean
  neighbouring prices, so D's deviation from it is large and D is flagged.
* At D+1 (a normal price), D+1's own window contains the one spiked
  neighbour, but that neighbour affects the window's *dispersion* (its
  std/IQR) far more than its centre (mean/median), because it is a single
  point out of `2 * half_window`. So D+1 is compared against a window whose
  spread already reflects the spike, and D+1 -- an otherwise ordinary price --
  does not stand out from it.

This is a textbook trade-off for point-anomaly detection (related to a Hampel
filter): a window based on levels with the point held out isolates a single
bad print to the date it actually occurred on, which a naive global check on
returns cannot do.

**Complexity.** For one ticker with n observations and a fixed window size w
(default 20, independent of n): computing one point's window statistics is
O(w log w) (sorting the window to get quartiles) or O(w) for the mean/std
pass, so a full pass over the ticker is O(n * w log w) -- linear in n for a
fixed w. Across T tickers with n_t observations each, total time is
O(w log w * sum(n_t)) and memory is O(w) per point evaluated (the window is
never materialised for the whole series at once).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .models import AVERTISSEMENT, PYTHON_OUTLIER_DETECTOR, Anomaly

#: Rule id used in the manifest and in reports for this detector's findings.
RULE_ID = "OUTLIER_RETURN_ZSCORE_IQR"


@dataclass(frozen=True)
class OutlierDetectorConfig:
    #: Trading days considered on each side of the evaluated point.
    half_window: int = 10
    #: |z-score| beyond which a point is flagged.
    z_threshold: float = 4.0
    #: Tukey's fence multiplier: flagged outside [Q1 - k*IQR, Q3 + k*IQR].
    iqr_k: float = 3.0
    #: Minimum non-NaN window observations required to judge a point at all;
    #: below this, dispersion estimates are too noisy to trust.
    min_window_observations: int = 10


def _window_stats(values: np.ndarray) -> tuple[float, float, float, float] | None:
    """mean, std, q1, q3 of ``values``, or None if there is nothing usable."""
    clean = values[~np.isnan(values)]
    if clean.size == 0:
        return None
    mean = float(np.mean(clean))
    std = float(np.std(clean, ddof=0))
    q1, q3 = (float(v) for v in np.quantile(clean, [0.25, 0.75]))
    return mean, std, q1, q3


def _detect_ticker(
    ticker: str, dates: np.ndarray, prices: np.ndarray, config: OutlierDetectorConfig
) -> list[Anomaly]:
    n = len(prices)
    found: list[Anomaly] = []
    for i in range(n):
        price = prices[i]
        if np.isnan(price):
            continue  # a missing close is INGEST_CLOSE_PRICE_REQUIRED's finding, not ours.

        lo, hi = max(0, i - config.half_window), min(n, i + config.half_window + 1)
        window = np.concatenate([prices[lo:i], prices[i + 1 : hi]])
        if np.count_nonzero(~np.isnan(window)) < config.min_window_observations:
            continue  # too close to an edge, or too many neighbours also missing.

        stats = _window_stats(window)
        if stats is None:
            continue
        mean, std, q1, q3 = stats
        iqr = q3 - q1

        z_hit = std > 0 and abs((price - mean) / std) > config.z_threshold
        iqr_hit = iqr > 0 and (price < q1 - config.iqr_k * iqr or price > q3 + config.iqr_k * iqr)
        if not (z_hit or iqr_hit):
            continue

        z_score = (price - mean) / std if std > 0 else float("inf")
        found.append(
            Anomaly(
                rule_id=RULE_ID,
                rule_label="Cours de cloture aberrant (z-score / IQR local)",
                category="COHERENCE_METIER",
                severity=AVERTISSEMENT,
                dataset="market_prices",
                record_key=f"ticker={ticker}&price_date={dates[i]}",
                detector=PYTHON_OUTLIER_DETECTOR,
                field_name="close_price",
                observed_value=f"{price:.4f}",
                message=(
                    f"Cours {price:.4f} pour {ticker} au {dates[i]} hors de la fenetre locale "
                    f"attendue (mediane des {config.half_window * 2} jours voisins entre "
                    f"{q1:.4f} et {q3:.4f}, z-score={z_score:.2f})."
                ),
                estimated_impact=(
                    "Valorisation et performance du jour faussees pour toutes les positions "
                    f"detenant {ticker} a cette date."
                ),
                suggested_fix=(
                    "Rapprocher ce cours de la source de marche (fat finger, action corporate "
                    "non ajustee, ou erreur de flux) avant de valoriser les positions de ce jour."
                ),
            )
        )
    return found


def detect_price_outliers(
    market_prices: pd.DataFrame, config: OutlierDetectorConfig | None = None
) -> list[Anomaly]:
    """Flag statistically aberrant closes, ticker by ticker.

    ``market_prices`` must have at least the columns ``ticker``, ``price_date``,
    ``close_price``. Rows are grouped by ticker and sorted by date before
    detection; the input's own row order does not matter.
    """
    config = config or OutlierDetectorConfig()
    if market_prices.empty:
        return []

    found: list[Anomaly] = []
    for ticker, group in market_prices.sort_values(["ticker", "price_date"], kind="stable").groupby(
        "ticker", sort=True
    ):
        dates = group["price_date"].to_numpy()
        prices = group["close_price"].astype(float).to_numpy()
        found.extend(_detect_ticker(str(ticker), dates, prices, config))
    return found
