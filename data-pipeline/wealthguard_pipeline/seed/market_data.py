"""Market-price enrichment: real Yahoo Finance history, with an offline fallback.

Cahier des charges §2.1 asks for real historical data from a free financial API.
Three constraints pull against each other:

1. The dataset must be *reproducible* -- a reviewer cloning the repo must be able
   to regenerate identical CSVs.
2. Yahoo Finance is an unauthenticated, rate-limited, occasionally-down service.
3. The GitLab CI runner may have no outbound internet access at all.

Resolution: the raw Yahoo download is cached to ``data/seed/cache/`` and that
cache is *versioned in git*. The normal path therefore never hits the network;
``--refresh-market`` explicitly re-downloads. If no cache exists and the network
is unavailable, prices are synthesised with a seeded geometric Brownian motion
and the provenance column records ``SYNTHETIC`` so nothing is ever passed off as
real data.
"""

from __future__ import annotations

import logging
import zlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .instruments import BY_TICKER, Instrument

LOGGER = logging.getLogger(__name__)

#: Trading days per year, used to scale the drift/vol of the fallback generator.
TRADING_DAYS_PER_YEAR = 252

SOURCE_YAHOO = "YAHOO"
SOURCE_SYNTHETIC = "SYNTHETIC"

PRICE_COLUMNS = ["ticker", "price_date", "close_price", "currency", "price_source"]


@dataclass(frozen=True)
class MarketDataResult:
    prices: pd.DataFrame
    """Tidy frame: one row per (ticker, price_date)."""

    provenance: dict[str, str]
    """ticker -> SOURCE_YAHOO | SOURCE_SYNTHETIC."""

    @property
    def real_ticker_count(self) -> int:
        return sum(1 for src in self.provenance.values() if src == SOURCE_YAHOO)


def _ticker_seed(ticker: str, master_seed: int) -> int:
    """Deterministic per-ticker seed.

    ``hash()`` is salted per interpreter run in Python 3, so it cannot be used
    for reproducibility. CRC32 is stable across runs, machines and versions.
    """
    return (zlib.crc32(ticker.encode("utf-8")) ^ (master_seed * 2_654_435_761)) % (2**32)


def synthesise_prices(
    instrument: Instrument,
    trading_days: pd.DatetimeIndex,
    master_seed: int,
) -> pd.DataFrame:
    """Seeded geometric Brownian motion fallback for one instrument.

    S_t = S_{t-1} * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z_t)

    Deterministic given (ticker, master_seed, trading_days). Complexity O(n) in
    the number of trading days, fully vectorised.
    """
    rng = np.random.default_rng(_ticker_seed(instrument.ticker, master_seed))
    n = len(trading_days)
    dt = 1.0 / TRADING_DAYS_PER_YEAR
    shocks = rng.standard_normal(n)
    log_returns = (
        instrument.annual_drift - 0.5 * instrument.annual_vol**2
    ) * dt + instrument.annual_vol * np.sqrt(dt) * shocks
    # Start the path at base_price and walk forward.
    path = instrument.base_price * np.exp(np.cumsum(log_returns))
    return pd.DataFrame(
        {
            "ticker": instrument.ticker,
            "price_date": trading_days,
            "close_price": np.round(path, 4),
            "currency": instrument.currency,
            "price_source": SOURCE_SYNTHETIC,
        }
    )


def _download_from_yahoo(
    tickers: list[str], start: date, end: date
) -> pd.DataFrame:
    """Fetch adjusted closes from Yahoo Finance. Returns an empty frame on failure.

    Kept deliberately defensive: a seed-generation run must never crash because a
    free third-party API changed its response shape or throttled us.
    """
    try:
        import yfinance  # imported lazily: optional `market` extra
    except ImportError:
        LOGGER.warning("yfinance is not installed (pip install -e '.[market]'); falling back to synthetic prices")
        return pd.DataFrame(columns=PRICE_COLUMNS)

    try:
        raw = yfinance.download(
            tickers=tickers,
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
    except Exception as exc:  # noqa: BLE001 - third-party API, any failure is non-fatal
        LOGGER.warning("Yahoo Finance download failed (%s); falling back to synthetic prices", exc)
        return pd.DataFrame(columns=PRICE_COLUMNS)

    if raw is None or raw.empty:
        LOGGER.warning("Yahoo Finance returned no data; falling back to synthetic prices")
        return pd.DataFrame(columns=PRICE_COLUMNS)

    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        try:
            closes = raw[ticker]["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
        except KeyError:
            LOGGER.warning("Ticker %s absent from the Yahoo response", ticker)
            continue
        closes = closes.dropna()
        if closes.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "price_date": pd.to_datetime(closes.index).tz_localize(None),
                    "close_price": np.round(closes.to_numpy(dtype=float), 4),
                    "currency": BY_TICKER[ticker].currency,
                    "price_source": SOURCE_YAHOO,
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def load_market_prices(
    start: date,
    end: date,
    cache_file: Path,
    *,
    master_seed: int,
    offline: bool = False,
    refresh: bool = False,
    tickers: list[str] | None = None,
) -> MarketDataResult:
    """Return one close price per (ticker, trading day) over ``[start, end)``.

    Resolution order: versioned cache -> Yahoo Finance -> seeded synthetic path.
    Any ticker missing from the chosen source is completed synthetically, so the
    returned frame always covers the full universe.
    """
    tickers = tickers or list(BY_TICKER)
    trading_days = pd.bdate_range(start=start, end=end - pd.Timedelta(days=1))

    fetched = pd.DataFrame(columns=PRICE_COLUMNS)
    if cache_file.exists() and not refresh:
        LOGGER.info("Reading cached market prices from %s", cache_file)
        fetched = pd.read_csv(cache_file, parse_dates=["price_date"])
    elif not offline:
        LOGGER.info("Downloading %d tickers from Yahoo Finance (%s -> %s)", len(tickers), start, end)
        fetched = _download_from_yahoo(tickers, start, end)
        if not fetched.empty:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            fetched.sort_values(["ticker", "price_date"]).to_csv(cache_file, index=False)
            LOGGER.info("Cached %d price rows to %s", len(fetched), cache_file)

    if not fetched.empty:
        fetched = fetched[fetched["ticker"].isin(tickers)]

    frames: list[pd.DataFrame] = []
    provenance: dict[str, str] = {}
    for ticker in tickers:
        instrument = BY_TICKER[ticker]
        real = fetched[fetched["ticker"] == ticker] if not fetched.empty else fetched
        # A ticker is only trusted as "real" if the source covers a decent share
        # of the requested window; a 3-row partial response is worse than a
        # clean synthetic path because it silently breaks return calculations.
        if len(real) >= 0.5 * len(trading_days):
            frames.append(real[PRICE_COLUMNS].copy())
            provenance[ticker] = SOURCE_YAHOO
        else:
            frames.append(synthesise_prices(instrument, trading_days, master_seed))
            provenance[ticker] = SOURCE_SYNTHETIC

    prices = pd.concat(frames, ignore_index=True)
    prices["price_date"] = pd.to_datetime(prices["price_date"]).dt.date
    prices = prices.sort_values(["ticker", "price_date"], kind="stable").reset_index(drop=True)
    return MarketDataResult(prices=prices[PRICE_COLUMNS], provenance=provenance)
