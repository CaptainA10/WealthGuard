"""Ingestion of the source files (CSV and Excel, cahier des charges §2.3).

The Java engine owns every check that needs the *client/instrument/allocation*
reference data (completeness, uniqueness, referential integrity, business
coherence on positions and allocations -- see quality-engine). Two checks on
``market_prices`` are deliberately kept on the Python side instead: they are
pure ingestion hygiene on a dataset the Java engine never receives, and doing
them here, before anything is loaded, is the natural place to reject a
duplicated or missing daily close.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .models import AVERTISSEMENT, PYTHON_INGESTION, Anomaly

INGEST_CLOSE_PRICE_REQUIRED = "INGEST_CLOSE_PRICE_REQUIRED"
INGEST_UNIQUE_PRICE_PER_DAY = "INGEST_UNIQUE_PRICE_PER_DAY"

_POSITION_DATE_COLUMNS = ["purchase_date"]
_CLIENT_DATE_COLUMNS = ["onboarding_date"]
_MARKET_PRICE_DATE_COLUMNS = ["price_date"]


@dataclass(frozen=True)
class Dataset:
    """The five landing tables as ingested, before any quality check runs."""

    clients: pd.DataFrame
    instruments: pd.DataFrame
    positions: pd.DataFrame
    target_allocations: pd.DataFrame
    market_prices: pd.DataFrame


def _read_table(directory: Path, stem: str, *, date_columns: list[str] | None = None) -> pd.DataFrame:
    """Read ``<stem>.csv`` or, failing that, ``<stem>.xlsx`` from ``directory``.

    The advisors' allocation sheet is Excel while every system extract is CSV
    (cahier des charges §2.3: the pipeline must read both) -- trying CSV first
    and falling back to Excel means callers do not need to know which format a
    given landing drop used.
    """
    csv_path = directory / f"{stem}.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path, parse_dates=date_columns or None)
    xlsx_path = directory / f"{stem}.xlsx"
    if xlsx_path.exists():
        df = pd.read_excel(xlsx_path)
        for col in date_columns or []:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
        return df
    raise FileNotFoundError(f"Neither {csv_path} nor {xlsx_path} exists")


def load_landing(directory: Path) -> Dataset:
    """Read the five landing tables from ``directory`` (CSV, with an Excel fallback)."""
    return Dataset(
        clients=_read_table(directory, "clients", date_columns=_CLIENT_DATE_COLUMNS),
        instruments=_read_table(directory, "instruments"),
        positions=_read_table(directory, "positions", date_columns=_POSITION_DATE_COLUMNS),
        target_allocations=_read_table(directory, "target_allocations"),
        market_prices=_read_table(directory, "market_prices", date_columns=_MARKET_PRICE_DATE_COLUMNS),
    )


def check_market_prices(market_prices: pd.DataFrame) -> list[Anomaly]:
    """Ingestion-time hygiene on the price feed: no gap, no duplicated day.

    Complexity: O(n log n) (a single groupby + sort over n price rows), versus
    the O(n^2) of comparing every row to every other row.
    """
    found: list[Anomaly] = []

    missing = market_prices[market_prices["close_price"].isna()]
    for row in missing.itertuples(index=False):
        found.append(
            Anomaly(
                rule_id=INGEST_CLOSE_PRICE_REQUIRED,
                rule_label="Cours de cloture obligatoire",
                category="COMPLETUDE",
                severity=AVERTISSEMENT,
                dataset="market_prices",
                record_key=f"ticker={row.ticker}&price_date={row.price_date}",
                detector=PYTHON_INGESTION,
                field_name="close_price",
                observed_value=None,
                message=f"Cours de cloture absent pour {row.ticker} au {row.price_date}.",
                estimated_impact=(
                    "Trou dans la serie : la valorisation du jour retombe sur le dernier "
                    "cours connu, sous-estimant ou surestimant l'encours selon la tendance."
                ),
                suggested_fix=(
                    "Rejouer l'extraction du fournisseur de donnees de marche pour ce "
                    "couple (ticker, date) ; a defaut, propager le dernier cours connu "
                    "explicitement plutot que de laisser un trou silencieux."
                ),
            )
        )

    duplicate_keys = market_prices.groupby(["ticker", "price_date"]).size()
    duplicate_keys = duplicate_keys[duplicate_keys > 1]
    for (ticker, price_date), occurrences in duplicate_keys.items():
        found.append(
            Anomaly(
                rule_id=INGEST_UNIQUE_PRICE_PER_DAY,
                rule_label="Un seul cours par jour et par ticker",
                category="UNICITE",
                severity=AVERTISSEMENT,
                dataset="market_prices",
                record_key=f"ticker={ticker}&price_date={price_date}",
                detector=PYTHON_INGESTION,
                field_name="close_price",
                observed_value=f"{occurrences} occurrences",
                message=f"{occurrences} cours de cloture pour {ticker} au {price_date} au lieu d'un seul.",
                estimated_impact=(
                    "Jointure en eventail sur les prix : chaque position valorisee ce "
                    "jour-la avec ce ticker est dupliquee autant de fois qu'il y a de cours."
                ),
                suggested_fix=(
                    "Deduplication a la source (fournisseur de donnees de marche) ; en "
                    "attendant, ne charger que le dernier cours recu pour ce couple."
                ),
            )
        )

    return found


def dedupe_market_prices(market_prices: pd.DataFrame) -> pd.DataFrame:
    """Keep one close per (ticker, price_date) for loading into the warehouse.

    ``market_prices`` is the one table where an AVERTISSEMENT-level finding
    (``INGEST_UNIQUE_PRICE_PER_DAY``) would otherwise still hit a hard primary
    key conflict at load time -- unlike a BLOQUANT anomaly, it is not routed
    through ``quarantine`` first. Keeping the *last* received row mirrors the
    rule's own suggested fix ("ne charger que le dernier cours recu pour ce
    couple"); the duplicate is still reported by :func:`check_market_prices`
    against the original, undeduplicated frame, so nothing here hides it from
    the anomaly report.
    """
    return market_prices.drop_duplicates(subset=["ticker", "price_date"], keep="last").reset_index(drop=True)
