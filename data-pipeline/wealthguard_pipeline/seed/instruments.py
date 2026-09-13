"""The investable universe: 18 real tickers used as the reference table.

These are genuine, publicly traded instruments (cahier des charges §2.1), which
is what makes the market-price enrichment meaningful. The *positions* built on
top of them are synthetic.

``base_price`` / ``annual_drift`` / ``annual_vol`` are only used by the offline
fallback price generator (``market_data.synthesise_prices``) when Yahoo Finance
is unreachable -- they are order-of-magnitude plausible, not predictions.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Asset classes used by the target-allocation model and the reporting layer.
#: Kept in French because this is the vocabulary of the business users (a French
#: family office) and it is what the dashboards and the NL assistant expose.
ASSET_CLASSES: tuple[str, ...] = (
    "ACTIONS",
    "OBLIGATIONS",
    "MATIERES_PREMIERES",
    "IMMOBILIER",
)

#: Risk profiles, ordered from the most defensive to the most aggressive.
RISK_PROFILES: tuple[str, ...] = ("PRUDENT", "EQUILIBRE", "DYNAMIQUE", "OFFENSIF")

#: Reference currencies a client portfolio can be denominated in.
REFERENCE_CURRENCIES: tuple[str, ...] = ("EUR", "USD")


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    instrument_type: str  # STOCK | ETF
    asset_class: str
    currency: str
    exchange: str
    base_price: float
    annual_drift: float
    annual_vol: float


INSTRUMENTS: tuple[Instrument, ...] = (
    # --- Equities, US ---
    Instrument("AAPL", "Apple Inc.", "STOCK", "ACTIONS", "USD", "NASDAQ", 225.0, 0.11, 0.26),
    Instrument("MSFT", "Microsoft Corporation", "STOCK", "ACTIONS", "USD", "NASDAQ", 415.0, 0.12, 0.24),
    Instrument("NVDA", "NVIDIA Corporation", "STOCK", "ACTIONS", "USD", "NASDAQ", 135.0, 0.25, 0.48),
    Instrument("JNJ", "Johnson & Johnson", "STOCK", "ACTIONS", "USD", "NYSE", 155.0, 0.05, 0.16),
    Instrument("JPM", "JPMorgan Chase & Co.", "STOCK", "ACTIONS", "USD", "NYSE", 215.0, 0.09, 0.22),
    # --- Equities, Europe ---
    Instrument("MC.PA", "LVMH Moet Hennessy Louis Vuitton", "STOCK", "ACTIONS", "EUR", "EURONEXT_PARIS", 640.0, 0.06, 0.27),
    Instrument("TTE.PA", "TotalEnergies SE", "STOCK", "ACTIONS", "EUR", "EURONEXT_PARIS", 60.0, 0.05, 0.23),
    Instrument("SAN.PA", "Sanofi S.A.", "STOCK", "ACTIONS", "EUR", "EURONEXT_PARIS", 95.0, 0.04, 0.19),
    Instrument("ASML.AS", "ASML Holding N.V.", "STOCK", "ACTIONS", "EUR", "EURONEXT_AMSTERDAM", 700.0, 0.14, 0.35),
    Instrument("SAP.DE", "SAP SE", "STOCK", "ACTIONS", "EUR", "XETRA", 215.0, 0.13, 0.25),
    # --- Equity ETFs ---
    Instrument("SPY", "SPDR S&P 500 ETF Trust", "ETF", "ACTIONS", "USD", "NYSEARCA", 570.0, 0.09, 0.17),
    Instrument("QQQ", "Invesco QQQ Trust", "ETF", "ACTIONS", "USD", "NASDAQ", 490.0, 0.13, 0.23),
    Instrument("IWDA.AS", "iShares Core MSCI World UCITS ETF", "ETF", "ACTIONS", "EUR", "EURONEXT_AMSTERDAM", 95.0, 0.08, 0.15),
    # --- Bond ETFs ---
    Instrument("AGG", "iShares Core U.S. Aggregate Bond ETF", "ETF", "OBLIGATIONS", "USD", "NYSEARCA", 100.0, 0.03, 0.06),
    Instrument("TLT", "iShares 20+ Year Treasury Bond ETF", "ETF", "OBLIGATIONS", "USD", "NASDAQ", 92.0, 0.02, 0.14),
    Instrument("BND", "Vanguard Total Bond Market ETF", "ETF", "OBLIGATIONS", "USD", "NASDAQ", 74.0, 0.03, 0.06),
    # --- Commodities ---
    Instrument("GLD", "SPDR Gold Shares", "ETF", "MATIERES_PREMIERES", "USD", "NYSEARCA", 245.0, 0.07, 0.15),
    # --- Real estate ---
    Instrument("VNQ", "Vanguard Real Estate ETF", "ETF", "IMMOBILIER", "USD", "NYSEARCA", 93.0, 0.04, 0.19),
)

#: Ticker -> Instrument, for O(1) lookups.
BY_TICKER: dict[str, Instrument] = {inst.ticker: inst for inst in INSTRUMENTS}

#: A ticker that deliberately does NOT exist in the reference table. Injected in
#: the landing files to exercise the referential-integrity rule
#: (POS_KNOWN_INSTRUMENT) -- see seed/anomalies.py.
UNKNOWN_TICKER_SENTINEL = "ZZZZ.XX"


def tickers_for_asset_class(asset_class: str) -> list[str]:
    return [inst.ticker for inst in INSTRUMENTS if inst.asset_class == asset_class]


def __post_check() -> None:
    """Fail fast at import time if the universe becomes inconsistent."""
    if len(BY_TICKER) != len(INSTRUMENTS):
        raise ValueError("Duplicate ticker in INSTRUMENTS")
    unknown = {inst.asset_class for inst in INSTRUMENTS} - set(ASSET_CLASSES)
    if unknown:
        raise ValueError(f"Instrument(s) with an asset class outside ASSET_CLASSES: {unknown}")
    empty = [ac for ac in ASSET_CLASSES if not tickers_for_asset_class(ac)]
    if empty:
        raise ValueError(f"Asset class(es) with no instrument: {empty}")


__post_check()
