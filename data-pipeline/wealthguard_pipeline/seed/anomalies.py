"""Deliberate, documented anomaly injection.

Cahier des charges §2.1 and §5.6: anomalies must be injected on purpose and
listed in a document, so that a demo can show "here is what we broke, here is
what the engine caught".

Design decision -- the *manifest is the test oracle*. Every injection records the
exact record key it corrupted, which rule is expected to flag it and at which
severity. ``data/seed/anomaly_manifest.json`` is therefore not documentation
that can drift: ``tests/test_seed_manifest.py`` and the end-to-end validation
check asserts the engine's output against it. If someone adds a rule or changes
a severity without updating the catalogue, the build fails.

Isolation invariant: each injection claims its target row exclusively (see
``RowClaimer``). One corrupted row therefore violates exactly one rule, which
keeps the manifest unambiguous -- otherwise "the engine reported 24 anomalies
instead of 19" would be impossible to interpret.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from .instruments import RISK_PROFILES, UNKNOWN_TICKER_SENTINEL

LOGGER = logging.getLogger(__name__)

# --- Severity levels, mirroring com.wealthguard.quality.domain.Severity -------
BLOQUANT = "BLOQUANT"
AVERTISSEMENT = "AVERTISSEMENT"
INFO = "INFO"

# --- Which component is expected to catch the anomaly ------------------------
JAVA_RULE_ENGINE = "JAVA_RULE_ENGINE"
PYTHON_OUTLIER_DETECTOR = "PYTHON_OUTLIER_DETECTOR"
PYTHON_INGESTION = "PYTHON_INGESTION"

#: A client_id that is guaranteed absent from clients.csv.
ORPHAN_CLIENT_ID = "CLI-9999"

#: Concentration threshold shared with the Java rule POS_CONCENTRATION_LIMIT.
#: Duplicated constant, asserted equal by the end-to-end test.
CONCENTRATION_LIMIT_PCT = 40.0


@dataclass
class Dataset:
    """The five landing tables, mutated in place by the injectors."""

    clients: pd.DataFrame
    instruments: pd.DataFrame
    positions: pd.DataFrame
    target_allocations: pd.DataFrame
    market_prices: pd.DataFrame


@dataclass(frozen=True)
class InjectedAnomaly:
    """One concrete corrupted record, as written to the manifest."""

    anomaly_code: str
    dataset: str
    record_key: str
    field: str | None
    original_value: str | None
    injected_value: str | None
    detector: str
    expected_rule_id: str | None
    expected_severity: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "anomaly_code": self.anomaly_code,
            "dataset": self.dataset,
            "record_key": self.record_key,
            "field": self.field,
            "original_value": self.original_value,
            "injected_value": self.injected_value,
            "detector": self.detector,
            "expected_rule_id": self.expected_rule_id,
            "expected_severity": self.expected_severity,
        }


class RowClaimer:
    """Hands out row indices exclusively, so two injectors never share a row."""

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng
        self._claimed: dict[str, set[int]] = {}

    def claim(self, dataset: str, candidates: pd.Index, count: int) -> list[int]:
        taken = self._claimed.setdefault(dataset, set())
        available = [int(i) for i in candidates if int(i) not in taken]
        if len(available) < count:
            raise ValueError(
                f"Not enough unclaimed rows in {dataset}: need {count}, {len(available)} available. "
                f"Generate a larger dataset (--clients) or lower the injection count."
            )
        # Sorted then sampled without replacement: deterministic for a given rng.
        picked = self._rng.choice(np.array(sorted(available)), size=count, replace=False)
        chosen = sorted(int(i) for i in picked)
        taken.update(chosen)
        return chosen

    def is_claimed(self, dataset: str, index: int) -> bool:
        return index in self._claimed.get(dataset, set())


# ---------------------------------------------------------------------------
# Injectors. Signature: (Dataset, RowClaimer, np.random.Generator, date)
#                       -> list[InjectedAnomaly]
# ---------------------------------------------------------------------------

Injector = Callable[[Dataset, RowClaimer, np.random.Generator, date], list[InjectedAnomaly]]


def _fmt(value: object) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (date, pd.Timestamp)):
        return str(value)
    return str(value)


def _positions_field(
    ds: Dataset,
    claimer: RowClaimer,
    code: str,
    field_name: str,
    count: int,
    new_value_fn: Callable[[pd.Series], object],
    detector: str,
    rule_id: str | None,
    severity: str,
) -> list[InjectedAnomaly]:
    """Shared body for the "overwrite one field of N position rows" injectors."""
    out: list[InjectedAnomaly] = []
    for idx in claimer.claim("positions", ds.positions.index, count):
        row = ds.positions.loc[idx]
        original = row[field_name]
        new_value = new_value_fn(row)
        ds.positions.at[idx, field_name] = new_value
        out.append(
            InjectedAnomaly(
                anomaly_code=code,
                dataset="positions",
                record_key=f"position_id={row['position_id']}",
                field=field_name,
                original_value=_fmt(original),
                injected_value=_fmt(new_value),
                detector=detector,
                expected_rule_id=rule_id,
                expected_severity=severity,
            )
        )
    return out


def inject_duplicate_position_id(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """Append rows re-using an existing position_id -> breaks primary-key uniqueness."""
    out: list[InjectedAnomaly] = []
    for idx in claimer.claim("positions", ds.positions.index, 2):
        row = ds.positions.loc[idx].copy()
        # Different quantity, same key: a genuine double-booking, not a byte-identical
        # duplicate that a naive drop_duplicates() would silently absorb.
        row["quantity"] = round(float(row["quantity"]) * 1.5, 4)
        ds.positions.loc[len(ds.positions)] = row
        out.append(
            InjectedAnomaly(
                anomaly_code="DUP_POSITION_ID",
                dataset="positions",
                record_key=f"position_id={row['position_id']}",
                field="position_id",
                original_value=str(row["position_id"]),
                injected_value=str(row["position_id"]),
                detector=JAVA_RULE_ENGINE,
                expected_rule_id="POS_UNIQUE_ID",
                expected_severity=BLOQUANT,
            )
        )
    return out


def inject_missing_client_id(ds: Dataset, claimer: RowClaimer, rng, today: date):
    return _positions_field(
        ds, claimer, "MISSING_CLIENT_ID", "client_id", 2,
        lambda row: "", JAVA_RULE_ENGINE, "POS_REQUIRED_FIELDS", BLOQUANT,
    )


def inject_missing_quantity(ds: Dataset, claimer: RowClaimer, rng, today: date):
    return _positions_field(
        ds, claimer, "MISSING_QUANTITY", "quantity", 2,
        lambda row: np.nan, JAVA_RULE_ENGINE, "POS_REQUIRED_FIELDS", BLOQUANT,
    )


def inject_negative_quantity(ds: Dataset, claimer: RowClaimer, rng, today: date):
    return _positions_field(
        ds, claimer, "NEGATIVE_QUANTITY", "quantity", 3,
        lambda row: -abs(float(row["quantity"])), JAVA_RULE_ENGINE,
        "POS_POSITIVE_QUANTITY", BLOQUANT,
    )


def inject_non_positive_price(ds: Dataset, claimer: RowClaimer, rng, today: date):
    # One exact zero and two negatives: zero is the boundary case that a naive
    # `price < 0` check lets through.
    values = [0.0, -12.5, -1.0]
    counter = iter(values)
    return _positions_field(
        ds, claimer, "NON_POSITIVE_PURCHASE_PRICE", "purchase_price", len(values),
        lambda row: next(counter), JAVA_RULE_ENGINE,
        "POS_POSITIVE_PURCHASE_PRICE", BLOQUANT,
    )


def inject_unknown_ticker(ds: Dataset, claimer: RowClaimer, rng, today: date):
    return _positions_field(
        ds, claimer, "UNKNOWN_TICKER", "ticker", 2,
        lambda row: UNKNOWN_TICKER_SENTINEL, JAVA_RULE_ENGINE,
        "POS_KNOWN_INSTRUMENT", BLOQUANT,
    )


def inject_orphan_client_ref(ds: Dataset, claimer: RowClaimer, rng, today: date):
    return _positions_field(
        ds, claimer, "ORPHAN_CLIENT_REF", "client_id", 2,
        lambda row: ORPHAN_CLIENT_ID, JAVA_RULE_ENGINE,
        "POS_KNOWN_CLIENT", BLOQUANT,
    )


def inject_future_purchase_date(ds: Dataset, claimer: RowClaimer, rng, today: date):
    return _positions_field(
        ds, claimer, "FUTURE_PURCHASE_DATE", "purchase_date", 2,
        lambda row: today + timedelta(days=45), JAVA_RULE_ENGINE,
        "POS_PURCHASE_DATE_NOT_FUTURE", BLOQUANT,
    )


def inject_purchase_before_onboarding(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """A position bought before the client was onboarded: impossible, but plausible
    enough to survive a human eyeball -- exactly the kind of silent error a rule
    engine earns its keep on."""
    onboarding = dict(zip(ds.clients["client_id"], ds.clients["onboarding_date"]))
    out: list[InjectedAnomaly] = []
    # Only rows whose client actually exists, otherwise the referential rule fires first.
    candidates = ds.positions.index[ds.positions["client_id"].isin(onboarding)]
    for idx in claimer.claim("positions", candidates, 2):
        row = ds.positions.loc[idx]
        original = row["purchase_date"]
        new_value = onboarding[row["client_id"]] - timedelta(days=60)
        ds.positions.at[idx, "purchase_date"] = new_value
        out.append(
            InjectedAnomaly(
                anomaly_code="PURCHASE_BEFORE_ONBOARDING",
                dataset="positions",
                record_key=f"position_id={row['position_id']}",
                field="purchase_date",
                original_value=_fmt(original),
                injected_value=_fmt(new_value),
                detector=JAVA_RULE_ENGINE,
                expected_rule_id="POS_PURCHASE_AFTER_ONBOARDING",
                expected_severity=AVERTISSEMENT,
            )
        )
    return out


def inject_currency_mismatch(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """Position booked in a currency the instrument does not trade in."""
    instrument_ccy = dict(zip(ds.instruments["ticker"], ds.instruments["currency"]))

    def flip(row: pd.Series) -> str:
        return "CHF" if instrument_ccy.get(row["ticker"]) != "CHF" else "JPY"

    candidates = ds.positions.index[ds.positions["ticker"].isin(instrument_ccy)]
    out: list[InjectedAnomaly] = []
    for idx in claimer.claim("positions", candidates, 2):
        row = ds.positions.loc[idx]
        original = row["currency"]
        new_value = flip(row)
        ds.positions.at[idx, "currency"] = new_value
        out.append(
            InjectedAnomaly(
                anomaly_code="CURRENCY_MISMATCH",
                dataset="positions",
                record_key=f"position_id={row['position_id']}",
                field="currency",
                original_value=_fmt(original),
                injected_value=new_value,
                detector=JAVA_RULE_ENGINE,
                expected_rule_id="POS_CURRENCY_MATCHES_INSTRUMENT",
                expected_severity=AVERTISSEMENT,
            )
        )
    return out


def inject_excessive_concentration(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """Inflate one holding until it represents ~60% of its client's cost basis.

    Not a data *error* -- the row is perfectly well-formed. It is a breach of the
    firm's investment policy, which is why it is an AVERTISSEMENT and why it
    belongs in the same engine: a quality platform that only checks types misses
    the anomalies that actually cost money.
    """
    df = ds.positions
    # Same population as the Java rule POS_CONCENTRATION_LIMIT: only positions
    # with a usable cost basis contribute to the denominator. Keeping the two
    # definitions aligned is what lets the manifest predict the engine's verdict.
    valid = df[
        df["client_id"].isin(ds.clients["client_id"])
        & df["quantity"].notna()
        & df["purchase_price"].notna()
        & (pd.to_numeric(df["quantity"], errors="coerce") > 0)
        & (pd.to_numeric(df["purchase_price"], errors="coerce") > 0)
    ].copy()
    valid["cost"] = valid["quantity"].astype(float) * valid["purchase_price"].astype(float)
    out: list[InjectedAnomaly] = []
    target_share = 0.60
    # Deterministic client order; pick clients with enough positions that 60% is a
    # real breach rather than an artefact of holding only two lines.
    sizes = valid.groupby("client_id").size()
    eligible = sorted(sizes[sizes >= 5].index)
    for client_id in eligible[:2]:
        client_rows = valid[valid["client_id"] == client_id]
        idx = int(client_rows["cost"].idxmax())
        if claimer.is_claimed("positions", idx):
            continue
        claimer.claim("positions", pd.Index([idx]), 1)
        total_others = float(client_rows["cost"].sum() - client_rows.loc[idx, "cost"])
        price = float(df.at[idx, "purchase_price"])
        # Solve: new_cost / (new_cost + total_others) = target_share
        new_cost = total_others * target_share / (1.0 - target_share)
        original_qty = float(df.at[idx, "quantity"])
        new_qty = round(new_cost / price, 4)
        ds.positions.at[idx, "quantity"] = new_qty
        out.append(
            InjectedAnomaly(
                anomaly_code="EXCESSIVE_CONCENTRATION",
                dataset="positions",
                record_key=f"position_id={df.at[idx, 'position_id']}",
                field="quantity",
                original_value=_fmt(original_qty),
                injected_value=_fmt(new_qty),
                detector=JAVA_RULE_ENGINE,
                expected_rule_id="POS_CONCENTRATION_LIMIT",
                expected_severity=AVERTISSEMENT,
            )
        )
    return out


def inject_excessive_quantity_precision(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """12.3456789 shares: harmless in isolation, a sign of a broken upstream export."""
    return _positions_field(
        ds, claimer, "EXCESSIVE_QUANTITY_PRECISION", "quantity", 2,
        lambda row: round(float(row["quantity"]) + 0.1234567, 7),
        JAVA_RULE_ENGINE, "POS_QUANTITY_PRECISION", INFO,
    )


def inject_duplicate_client_id(ds: Dataset, claimer: RowClaimer, rng, today: date):
    out: list[InjectedAnomaly] = []
    for idx in claimer.claim("clients", ds.clients.index, 1):
        row = ds.clients.loc[idx].copy()
        row["full_name"] = f"{row['full_name']} (doublon)"
        ds.clients.loc[len(ds.clients)] = row
        out.append(
            InjectedAnomaly(
                anomaly_code="DUP_CLIENT_ID",
                dataset="clients",
                record_key=f"client_id={row['client_id']}",
                field="client_id",
                original_value=str(row["client_id"]),
                injected_value=str(row["client_id"]),
                detector=JAVA_RULE_ENGINE,
                expected_rule_id="CLI_UNIQUE_ID",
                expected_severity=BLOQUANT,
            )
        )
    return out


def inject_invalid_risk_profile(ds: Dataset, claimer: RowClaimer, rng, today: date):
    out: list[InjectedAnomaly] = []
    # "AGRESSIF" looks like a valid profile but is not in the reference list --
    # the classic free-text-instead-of-enum defect.
    bogus = "AGRESSIF"
    assert bogus not in RISK_PROFILES
    for idx in claimer.claim("clients", ds.clients.index, 2):
        row = ds.clients.loc[idx]
        original = row["risk_profile"]
        ds.clients.at[idx, "risk_profile"] = bogus
        out.append(
            InjectedAnomaly(
                anomaly_code="INVALID_RISK_PROFILE",
                dataset="clients",
                record_key=f"client_id={row['client_id']}",
                field="risk_profile",
                original_value=str(original),
                injected_value=bogus,
                detector=JAVA_RULE_ENGINE,
                expected_rule_id="CLI_KNOWN_RISK_PROFILE",
                expected_severity=AVERTISSEMENT,
            )
        )
    return out


def inject_allocation_sum_mismatch(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """Bump one weight so the client's target allocation sums to 107% instead of 100%."""
    out: list[InjectedAnomaly] = []
    clients = sorted(ds.target_allocations["client_id"].unique())
    picked = rng.choice(np.array(clients), size=3, replace=False)
    for client_id in sorted(str(c) for c in picked):
        rows = ds.target_allocations.index[ds.target_allocations["client_id"] == client_id]
        idx = int(rows[0])
        claimer.claim("target_allocations", pd.Index([idx]), 1)
        original = float(ds.target_allocations.at[idx, "target_weight_pct"])
        new_value = round(original + 7.0, 2)
        ds.target_allocations.at[idx, "target_weight_pct"] = new_value
        out.append(
            InjectedAnomaly(
                anomaly_code="ALLOCATION_SUM_MISMATCH",
                dataset="target_allocations",
                record_key=f"client_id={client_id}",
                field="target_weight_pct",
                original_value=_fmt(original),
                injected_value=_fmt(new_value),
                detector=JAVA_RULE_ENGINE,
                expected_rule_id="ALLOC_SUM_EQUALS_100",
                expected_severity=AVERTISSEMENT,
            )
        )
    return out


def inject_allocation_weight_out_of_range(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """Set one weight negative and compensate on another line of the same client.

    The compensation is deliberate: it keeps the sum at 100 so this row violates
    *only* ALLOC_WEIGHT_IN_RANGE. Without it the manifest could not say which
    rule "should" have fired.
    """
    out: list[InjectedAnomaly] = []
    counts = ds.target_allocations.groupby("client_id").size()
    eligible = sorted(counts[counts >= 2].index)
    for client_id in eligible:
        rows = [int(i) for i in ds.target_allocations.index[ds.target_allocations["client_id"] == client_id]]
        if any(claimer.is_claimed("target_allocations", i) for i in rows):
            continue
        victim, donor = rows[0], rows[1]
        claimer.claim("target_allocations", pd.Index([victim, donor]), 2)
        original = float(ds.target_allocations.at[victim, "target_weight_pct"])
        new_value = -5.0
        delta = original - new_value
        ds.target_allocations.at[victim, "target_weight_pct"] = new_value
        ds.target_allocations.at[donor, "target_weight_pct"] = round(
            float(ds.target_allocations.at[donor, "target_weight_pct"]) + delta, 2
        )
        out.append(
            InjectedAnomaly(
                anomaly_code="ALLOCATION_WEIGHT_OUT_OF_RANGE",
                dataset="target_allocations",
                record_key=f"client_id={client_id}&asset_class={ds.target_allocations.at[victim, 'asset_class']}",
                field="target_weight_pct",
                original_value=_fmt(original),
                injected_value=_fmt(new_value),
                detector=JAVA_RULE_ENGINE,
                expected_rule_id="ALLOC_WEIGHT_IN_RANGE",
                expected_severity=BLOQUANT,
            )
        )
        break
    return out


def inject_orphan_allocation_client(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """Append a target-allocation line for a client that does not exist.

    Weight is exactly 100 on a single asset class, which is deliberate: the
    orphan client's weights then sum to 100 and sit inside [0, 100], so this row
    violates ALLOC_KNOWN_CLIENT and *only* ALLOC_KNOWN_CLIENT. The isolation
    invariant is preserved without having to make one rule aware of another.
    """
    row = {
        "client_id": ORPHAN_CLIENT_ID,
        "asset_class": "OBLIGATIONS",
        "target_weight_pct": 100.0,
    }
    ds.target_allocations.loc[len(ds.target_allocations)] = row
    return [
        InjectedAnomaly(
            anomaly_code="ORPHAN_ALLOCATION_CLIENT_REF",
            dataset="target_allocations",
            record_key=f"client_id={ORPHAN_CLIENT_ID}&asset_class=OBLIGATIONS",
            field="client_id",
            original_value=None,
            injected_value=ORPHAN_CLIENT_ID,
            detector=JAVA_RULE_ENGINE,
            expected_rule_id="ALLOC_KNOWN_CLIENT",
            expected_severity=BLOQUANT,
        )
    ]


def inject_duplicate_market_price(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """Two closes for the same (ticker, day) -- caught during Python ingestion."""
    out: list[InjectedAnomaly] = []
    for idx in claimer.claim("market_prices", ds.market_prices.index, 3):
        row = ds.market_prices.loc[idx].copy()
        row["close_price"] = round(float(row["close_price"]) * 1.001, 4)
        ds.market_prices.loc[len(ds.market_prices)] = row
        out.append(
            InjectedAnomaly(
                anomaly_code="DUP_MARKET_PRICE",
                dataset="market_prices",
                record_key=f"ticker={row['ticker']}&price_date={row['price_date']}",
                field="close_price",
                original_value=_fmt(ds.market_prices.at[idx, "close_price"]),
                injected_value=_fmt(row["close_price"]),
                detector=PYTHON_INGESTION,
                expected_rule_id="INGEST_UNIQUE_PRICE_PER_DAY",
                expected_severity=AVERTISSEMENT,
            )
        )
    return out


def inject_missing_close_price(ds: Dataset, claimer: RowClaimer, rng, today: date):
    out: list[InjectedAnomaly] = []
    for idx in claimer.claim("market_prices", ds.market_prices.index, 4):
        row = ds.market_prices.loc[idx]
        original = row["close_price"]
        ds.market_prices.at[idx, "close_price"] = np.nan
        out.append(
            InjectedAnomaly(
                anomaly_code="MISSING_CLOSE_PRICE",
                dataset="market_prices",
                record_key=f"ticker={row['ticker']}&price_date={row['price_date']}",
                field="close_price",
                original_value=_fmt(original),
                injected_value=None,
                detector=PYTHON_INGESTION,
                expected_rule_id="INGEST_CLOSE_PRICE_REQUIRED",
                expected_severity=AVERTISSEMENT,
            )
        )
    return out


def inject_price_spike(ds: Dataset, claimer: RowClaimer, rng, today: date):
    """A fat-fingered close, 4.5x the real one.

    This is the target of the home-made statistical detector
    (``wealthguard_pipeline.outliers``), not of a business rule: no fixed
    threshold can say that 612.50 is wrong for ASML but right for LVMH. Only the
    distribution of that ticker's own returns can.
    """
    out: list[InjectedAnomaly] = []
    df = ds.market_prices
    # Avoid the first/last third of a ticker's series: a spike at the edge cannot
    # be evaluated against a centred return window, so it would be an unfair test
    # of the detector rather than a realistic one.
    ordered = df.sort_values(["ticker", "price_date"], kind="stable")
    rank = ordered.groupby("ticker").cumcount()
    size = ordered.groupby("ticker")["ticker"].transform("size")
    interior_mask = (rank >= size // 3) & (rank < size - size // 3)
    candidates = ordered.index[interior_mask]
    for idx in claimer.claim("market_prices", candidates, 5):
        row = df.loc[idx]
        original = float(row["close_price"])
        new_value = round(original * 4.5, 4)
        ds.market_prices.at[idx, "close_price"] = new_value
        out.append(
            InjectedAnomaly(
                anomaly_code="PRICE_SPIKE",
                dataset="market_prices",
                record_key=f"ticker={row['ticker']}&price_date={row['price_date']}",
                field="close_price",
                original_value=_fmt(original),
                injected_value=_fmt(new_value),
                detector=PYTHON_OUTLIER_DETECTOR,
                expected_rule_id="OUTLIER_RETURN_ZSCORE_IQR",
                expected_severity=AVERTISSEMENT,
            )
        )
    return out


@dataclass(frozen=True)
class AnomalyType:
    """Catalogue entry -- the source of truth for docs/ANOMALIES.md."""

    code: str
    dataset: str
    detector: str
    expected_rule_id: str | None
    expected_severity: str
    description_fr: str
    business_impact_fr: str
    injector: Injector = field(compare=False, repr=False)


#: Ordered catalogue. Order matters: additive injectors (duplicates) run after the
#: field-overwriting ones so that appended rows never get corrupted twice.
ANOMALY_CATALOGUE: tuple[AnomalyType, ...] = (
    AnomalyType(
        "MISSING_CLIENT_ID", "positions", JAVA_RULE_ENGINE, "POS_REQUIRED_FIELDS", BLOQUANT,
        "Le client_id de la position est vide.",
        "Position non rattachable a un portefeuille : elle disparait de toute valorisation client.",
        inject_missing_client_id,
    ),
    AnomalyType(
        "MISSING_QUANTITY", "positions", JAVA_RULE_ENGINE, "POS_REQUIRED_FIELDS", BLOQUANT,
        "La quantite de la position est absente.",
        "Valorisation impossible : la ligne est ignoree ou comptee a zero, sous-estimant l'encours.",
        inject_missing_quantity,
    ),
    AnomalyType(
        "NEGATIVE_QUANTITY", "positions", JAVA_RULE_ENGINE, "POS_POSITIVE_QUANTITY", BLOQUANT,
        "Quantite strictement negative sur un portefeuille long-only.",
        "Valorisation negative : l'encours total du client est minore.",
        inject_negative_quantity,
    ),
    AnomalyType(
        "NON_POSITIVE_PURCHASE_PRICE", "positions", JAVA_RULE_ENGINE, "POS_POSITIVE_PURCHASE_PRICE", BLOQUANT,
        "Prix d'achat nul ou negatif (le zero est le cas limite classique).",
        "Prix de revient fausse : la plus-value latente devient infinie ou absurde.",
        inject_non_positive_price,
    ),
    AnomalyType(
        "UNKNOWN_TICKER", "positions", JAVA_RULE_ENGINE, "POS_KNOWN_INSTRUMENT", BLOQUANT,
        "Ticker absent du referentiel instruments.",
        "Aucun prix de marche disponible : la position ne peut pas etre valorisee ni classee.",
        inject_unknown_ticker,
    ),
    AnomalyType(
        "ORPHAN_CLIENT_REF", "positions", JAVA_RULE_ENGINE, "POS_KNOWN_CLIENT", BLOQUANT,
        "client_id qui ne correspond a aucun client du referentiel.",
        "Encours orphelin : le total plateforme ne reconcilie plus avec la somme des clients.",
        inject_orphan_client_ref,
    ),
    AnomalyType(
        "FUTURE_PURCHASE_DATE", "positions", JAVA_RULE_ENGINE, "POS_PURCHASE_DATE_NOT_FUTURE", BLOQUANT,
        "Date d'achat posterieure a la date du jour.",
        "Performance calculee sur une duree negative : indicateur de performance invalide.",
        inject_future_purchase_date,
    ),
    AnomalyType(
        "PURCHASE_BEFORE_ONBOARDING", "positions", JAVA_RULE_ENGINE, "POS_PURCHASE_AFTER_ONBOARDING", AVERTISSEMENT,
        "Achat anterieur a la date d'entree en relation du client.",
        "Incoherence chronologique : soit la position appartient a un autre client, soit la date d'onboarding est fausse.",
        inject_purchase_before_onboarding,
    ),
    AnomalyType(
        "CURRENCY_MISMATCH", "positions", JAVA_RULE_ENGINE, "POS_CURRENCY_MATCHES_INSTRUMENT", AVERTISSEMENT,
        "Devise de la position differente de la devise de cotation de l'instrument.",
        "Melange de devises non converti : l'allocation en pourcentage est fausse.",
        inject_currency_mismatch,
    ),
    AnomalyType(
        "EXCESSIVE_CONCENTRATION", "positions", JAVA_RULE_ENGINE, "POS_CONCENTRATION_LIMIT", AVERTISSEMENT,
        f"Une ligne depasse {CONCENTRATION_LIMIT_PCT:.0f} % du prix de revient du portefeuille.",
        "Risque de concentration contraire a la politique d'investissement : alerte conformite.",
        inject_excessive_concentration,
    ),
    AnomalyType(
        "EXCESSIVE_QUANTITY_PRECISION", "positions", JAVA_RULE_ENGINE, "POS_QUANTITY_PRECISION", INFO,
        "Quantite comportant plus de 4 decimales.",
        "Aucun impact de valorisation, mais signale un export amont degrade (arrondi flottant).",
        inject_excessive_quantity_precision,
    ),
    AnomalyType(
        "INVALID_RISK_PROFILE", "clients", JAVA_RULE_ENGINE, "CLI_KNOWN_RISK_PROFILE", AVERTISSEMENT,
        "Profil de risque hors nomenclature (ex. 'AGRESSIF' au lieu de 'OFFENSIF').",
        "Controle d'adequation impossible : on ne peut pas comparer l'allocation reelle a la cible du profil.",
        inject_invalid_risk_profile,
    ),
    AnomalyType(
        "ALLOCATION_SUM_MISMATCH", "target_allocations", JAVA_RULE_ENGINE, "ALLOC_SUM_EQUALS_100", AVERTISSEMENT,
        "Somme des allocations cibles differente de 100 % (107 % ici).",
        "Cible d'allocation inexploitable : tout ecart cible/reel calcule dessus est biaise.",
        inject_allocation_sum_mismatch,
    ),
    AnomalyType(
        "ALLOCATION_WEIGHT_OUT_OF_RANGE", "target_allocations", JAVA_RULE_ENGINE, "ALLOC_WEIGHT_IN_RANGE", BLOQUANT,
        "Poids cible hors de l'intervalle [0, 100] (-5 % ici), la somme restant a 100 %.",
        "Cible negative impossible : revele une inversion de signe dans l'outil amont.",
        inject_allocation_weight_out_of_range,
    ),
    AnomalyType(
        "ORPHAN_ALLOCATION_CLIENT_REF", "target_allocations", JAVA_RULE_ENGINE, "ALLOC_KNOWN_CLIENT", BLOQUANT,
        "Ligne d'allocation cible rattachee a un client inexistant.",
        "Cible fantome : les ecarts cible/reel agreges au niveau cabinet sont fausses.",
        inject_orphan_allocation_client,
    ),
    AnomalyType(
        "DUP_POSITION_ID", "positions", JAVA_RULE_ENGINE, "POS_UNIQUE_ID", BLOQUANT,
        "Deux lignes partagent le meme position_id avec des quantites differentes.",
        "Double comptage de l'encours : l'actif sous gestion est surevalue.",
        inject_duplicate_position_id,
    ),
    AnomalyType(
        "DUP_CLIENT_ID", "clients", JAVA_RULE_ENGINE, "CLI_UNIQUE_ID", BLOQUANT,
        "Deux fiches client portent le meme client_id.",
        "Jointure en eventail : chaque position du client est comptee deux fois.",
        inject_duplicate_client_id,
    ),
    AnomalyType(
        "MISSING_CLOSE_PRICE", "market_prices", PYTHON_INGESTION, "INGEST_CLOSE_PRICE_REQUIRED", AVERTISSEMENT,
        "Cours de cloture absent pour un couple (ticker, date).",
        "Trou dans la serie : la valorisation du jour retombe sur le dernier cours connu.",
        inject_missing_close_price,
    ),
    AnomalyType(
        "DUP_MARKET_PRICE", "market_prices", PYTHON_INGESTION, "INGEST_UNIQUE_PRICE_PER_DAY", AVERTISSEMENT,
        "Deux cours de cloture pour le meme couple (ticker, date).",
        "Jointure en eventail sur les prix : duplication de chaque position valorisee ce jour-la.",
        inject_duplicate_market_price,
    ),
    AnomalyType(
        "PRICE_SPIKE", "market_prices", PYTHON_OUTLIER_DETECTOR, "OUTLIER_RETURN_ZSCORE_IQR", AVERTISSEMENT,
        "Cours de cloture multiplie par 4,5 (erreur de saisie).",
        "Valorisation et performance du jour totalement faussees pour toutes les positions sur ce titre.",
        inject_price_spike,
    ),
)


def inject_all(ds: Dataset, *, seed: int, today: date) -> list[InjectedAnomaly]:
    """Run the whole catalogue against ``ds`` in place and return the manifest rows."""
    rng = np.random.default_rng(seed)
    claimer = RowClaimer(rng)
    injected: list[InjectedAnomaly] = []
    for anomaly_type in ANOMALY_CATALOGUE:
        produced = anomaly_type.injector(ds, claimer, rng, today)
        if not produced:
            raise RuntimeError(
                f"Injector for {anomaly_type.code} produced no anomaly -- the dataset is "
                f"probably too small for it to find an eligible row."
            )
        for item in produced:
            if item.anomaly_code != anomaly_type.code:
                raise RuntimeError(
                    f"Injector for {anomaly_type.code} emitted code {item.anomaly_code}"
                )
        LOGGER.info("Injected %-32s %d occurrence(s)", anomaly_type.code, len(produced))
        injected.extend(produced)
    return injected
