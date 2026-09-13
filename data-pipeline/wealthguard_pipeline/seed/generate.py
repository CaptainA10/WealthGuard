"""Reproducible generation of the WealthGuard synthetic dataset.

    python -m wealthguard_pipeline.seed.generate --as-of 2026-09-13

Outputs, under ``data/seed/``:

* ``reference/`` -- the clean dataset (ground truth, no anomaly)
* ``landing/``   -- the same dataset with the documented anomalies injected;
                    this is what the pipeline actually ingests
* ``cache/``     -- the raw Yahoo Finance download, versioned so that
                    regeneration works offline and byte-identically
* ``anomaly_manifest.json`` -- machine-readable test oracle (see anomalies.py)

Reproducibility: no wall clock is written to any output. The only time input is
``--as-of``, which defaults to today but is pinned in the committed dataset.
That matters because one anomaly (FUTURE_PURCHASE_DATE) is defined relative to
"today"; without pinning it, the committed CSVs would silently stop being
reproducible tomorrow.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import REPO_ROOT
from . import anomalies as anom
from .instruments import (
    ASSET_CLASSES,
    BY_TICKER,
    INSTRUMENTS,
    REFERENCE_CURRENCIES,
    RISK_PROFILES,
    tickers_for_asset_class,
)
from .market_data import load_market_prices

LOGGER = logging.getLogger(__name__)

DEFAULT_SEED = 42
DEFAULT_CLIENT_COUNT = 45
#: Length of the market-price history. ~3 years gives the outlier detector enough
#: observations per ticker for a stable return distribution.
HISTORY_YEARS = 3

# Obviously-synthetic French name pool (cahier des charges §8: nothing real).
FIRST_NAMES = (
    "Claire", "Julien", "Amelie", "Thibault", "Ines", "Mathieu", "Soraya", "Gregoire",
    "Helene", "Benoit", "Nadia", "Vincent", "Camille", "Olivier", "Farida", "Damien",
    "Sylvie", "Xavier", "Leila", "Pascal", "Margaux", "Antoine", "Sabine", "Renaud",
)
LAST_NAMES = (
    "Berthier", "Lacombe", "Nguyen-Roux", "Delaunay", "Fabre", "Moretti", "Salvador",
    "Vasseur", "Kowalski", "Barbier", "Cheval", "Dumas-Perrin", "Ferrand", "Oliveira",
    "Rambert", "Thevenot", "Aubry", "Meunier",
)
ADVISORS = ("A. Kessler", "M. Oustric", "P. Vandenberghe", "L. Traore")

#: Baseline target allocation per risk profile, in percent, keyed by asset class.
#: Deliberately hand-written rather than random: an OFFENSIF client holding 70%
#: bonds would be an anomaly the rule engine cannot see but a reviewer can.
PROFILE_TARGETS: dict[str, dict[str, float]] = {
    "PRUDENT":   {"ACTIONS": 20.0, "OBLIGATIONS": 65.0, "MATIERES_PREMIERES": 8.0, "IMMOBILIER": 7.0},
    "EQUILIBRE": {"ACTIONS": 45.0, "OBLIGATIONS": 40.0, "MATIERES_PREMIERES": 7.0, "IMMOBILIER": 8.0},
    "DYNAMIQUE": {"ACTIONS": 65.0, "OBLIGATIONS": 20.0, "MATIERES_PREMIERES": 7.0, "IMMOBILIER": 8.0},
    "OFFENSIF":  {"ACTIONS": 82.0, "OBLIGATIONS": 5.0,  "MATIERES_PREMIERES": 8.0, "IMMOBILIER": 5.0},
}

#: Excel is used for the advisors' allocation sheet, CSV for system extracts.
#: Fixed document timestamp so the .xlsx bytes stay reproducible across runs.
XLSX_FIXED_TIMESTAMP = datetime(2026, 1, 1, 0, 0, 0)


@dataclass
class GenerationOptions:
    out_dir: Path
    seed: int
    client_count: int
    as_of: date
    offline: bool
    refresh_market: bool


# ---------------------------------------------------------------------------
# Clean dataset
# ---------------------------------------------------------------------------

def build_instruments() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": inst.ticker,
                "name": inst.name,
                "instrument_type": inst.instrument_type,
                "asset_class": inst.asset_class,
                "currency": inst.currency,
                "exchange": inst.exchange,
            }
            for inst in INSTRUMENTS
        ]
    )


def build_clients(rng: np.random.Generator, count: int, as_of: date) -> pd.DataFrame:
    earliest = as_of - timedelta(days=HISTORY_YEARS * 365 - 30)
    rows = []
    for i in range(count):
        first = FIRST_NAMES[i % len(FIRST_NAMES)]
        last = LAST_NAMES[(i * 7 + 3) % len(LAST_NAMES)]
        # Onboarding spread over the history window, but never in the last 60 days
        # so that every client has room for at least a few purchases.
        offset = int(rng.integers(0, (as_of - earliest).days - 60))
        rows.append(
            {
                "client_id": f"CLI-{1000 + i}",
                "full_name": f"{first} {last}",
                "risk_profile": RISK_PROFILES[int(rng.integers(0, len(RISK_PROFILES)))],
                "reference_currency": REFERENCE_CURRENCIES[int(rng.integers(0, len(REFERENCE_CURRENCIES)))],
                "onboarding_date": earliest + timedelta(days=offset),
                "advisor": ADVISORS[i % len(ADVISORS)],
            }
        )
    return pd.DataFrame(rows)


def build_target_allocations(clients: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Per-client target weights that sum to exactly 100.00.

    The rounding fix matters: naively rounding four perturbed weights to two
    decimals leaves a residual of a few hundredths, which would make *every*
    client violate ALLOC_SUM_EQUALS_100 and drown the deliberately injected
    anomaly in noise.
    """
    rows = []
    for _, client in clients.iterrows():
        base = PROFILE_TARGETS[client["risk_profile"]]
        noise = rng.normal(0.0, 3.0, size=len(ASSET_CLASSES))
        raw = np.array([max(1.0, base[ac] + n) for ac, n in zip(ASSET_CLASSES, noise)])
        weights = np.round(100.0 * raw / raw.sum(), 2)
        # Absorb the rounding residual on the largest weight.
        weights[int(np.argmax(weights))] += round(100.0 - float(weights.sum()), 2)
        for asset_class, weight in zip(ASSET_CLASSES, weights):
            rows.append(
                {
                    "client_id": client["client_id"],
                    "asset_class": asset_class,
                    "target_weight_pct": round(float(weight), 2),
                }
            )
    return pd.DataFrame(rows)


#: Maximum share of a client's cost basis that any single line may represent in
#: the *clean* dataset. Kept well under the POS_CONCENTRATION_LIMIT threshold of
#: 40% on purpose: dropping a line whose quantity or price was corrupted inflates
#: the remaining shares (removing a 22% line scales the others by 1/0.78), and a
#: naturally-occurring breach would be indistinguishable from the two deliberate
#: ones. ``verify_concentration_isolation`` enforces that this actually holds.
MAX_CLEAN_LINE_SHARE = 0.22


def _cap_line_weights(weights: np.ndarray, cap: float) -> np.ndarray:
    """Clip weights to ``cap`` and redistribute the excess over the others.

    Deterministic fixed-point iteration; converges in a handful of passes because
    each round strictly reduces the total excess. Falls back to a uniform split in
    the degenerate case where ``cap * n < 1`` (impossible here: n >= 6, cap = 0.22).
    """
    if cap * len(weights) <= 1.0:
        return np.full(len(weights), 1.0 / len(weights))
    capped = weights.astype(float).copy()
    for _ in range(50):
        excess = np.maximum(capped - cap, 0.0)
        total_excess = float(excess.sum())
        if total_excess <= 1e-12:
            break
        capped = np.minimum(capped, cap)
        headroom = cap - capped
        room_total = float(headroom.sum())
        if room_total <= 1e-12:
            break
        capped = capped + total_excess * headroom / room_total
    return capped / capped.sum()


def _price_lookup(market_prices: pd.DataFrame) -> dict[str, pd.Series]:
    """ticker -> Series indexed by date, for as-of-date price lookups."""
    lookup: dict[str, pd.Series] = {}
    for ticker, group in market_prices.groupby("ticker"):
        series = group.set_index("price_date")["close_price"].sort_index()
        lookup[str(ticker)] = series
    return lookup


def _price_asof(series: pd.Series, day: date) -> float:
    """Last close at or before ``day`` (markets are closed on weekends)."""
    eligible = series.loc[:day]
    if eligible.empty:
        return float(series.iloc[0])
    return float(eligible.iloc[-1])


def build_positions(
    clients: pd.DataFrame,
    allocations: pd.DataFrame,
    market_prices: pd.DataFrame,
    rng: np.random.Generator,
    as_of: date,
) -> pd.DataFrame:
    """Positions consistent with each client's target allocation and onboarding date.

    Purchase prices are the instrument's *real* close on the purchase date plus a
    small execution slippage, so plus/minus latent gains computed downstream are
    economically meaningful instead of random noise.
    """
    lookup = _price_lookup(market_prices)
    history_start = min(series.index.min() for series in lookup.values())
    targets = {
        client_id: dict(zip(group["asset_class"], group["target_weight_pct"]))
        for client_id, group in allocations.groupby("client_id")
    }
    rows = []
    counter = 0
    for _, client in clients.iterrows():
        client_id = client["client_id"]
        weights = targets[client_id]
        # Total portfolio cost basis: log-normal, 150k to a few million euros.
        portfolio_value = float(np.exp(rng.normal(13.2, 0.7)))
        n_positions = int(rng.integers(6, 15))
        # Draw tickers proportionally to the target allocation, so a PRUDENT
        # client really does end up mostly in bonds.
        classes = rng.choice(
            np.array(ASSET_CLASSES),
            size=n_positions,
            replace=True,
            p=np.array([weights[ac] for ac in ASSET_CLASSES]) / 100.0,
        )
        earliest_purchase = max(client["onboarding_date"], history_start)
        latest_purchase = as_of - timedelta(days=5)
        span_days = max(1, (latest_purchase - earliest_purchase).days)
        line_weights = _cap_line_weights(rng.dirichlet(np.ones(n_positions) * 2.5), MAX_CLEAN_LINE_SHARE)
        for asset_class, share in zip(classes, line_weights):
            candidates = tickers_for_asset_class(str(asset_class))
            ticker = str(rng.choice(np.array(candidates)))
            purchase_date = earliest_purchase + timedelta(days=int(rng.integers(0, span_days)))
            market_price = _price_asof(lookup[ticker], purchase_date)
            # +/- 1.5% execution slippage versus the official close.
            purchase_price = round(market_price * float(rng.normal(1.0, 0.015)), 4)
            target_line_value = portfolio_value * float(share)
            quantity = round(max(0.01, target_line_value / purchase_price), 4)
            counter += 1
            rows.append(
                {
                    "position_id": f"POS-{counter:05d}",
                    "client_id": client_id,
                    "ticker": ticker,
                    "quantity": quantity,
                    "purchase_price": purchase_price,
                    "purchase_date": purchase_date,
                    "currency": BY_TICKER[ticker].currency,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # lineterminator="\n" keeps the committed bytes identical on Windows and Linux.
    df.to_csv(path, index=False, lineterminator="\n")


def _write_xlsx(df: pd.DataFrame, path: Path, sheet_name: str) -> None:
    """Write an .xlsx with a pinned document timestamp (reproducible bytes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        props = writer.book.properties
        props.created = XLSX_FIXED_TIMESTAMP
        props.modified = XLSX_FIXED_TIMESTAMP
        props.creator = "WealthGuard seed generator"
        props.lastModifiedBy = "WealthGuard seed generator"


def write_dataset(ds: anom.Dataset, directory: Path, *, excel_allocations: bool) -> None:
    _write_csv(ds.instruments, directory / "instruments.csv")
    _write_csv(ds.clients, directory / "clients.csv")
    _write_csv(ds.positions, directory / "positions.csv")
    _write_csv(ds.market_prices, directory / "market_prices.csv")
    if excel_allocations:
        # The advisors maintain allocations in a spreadsheet, not in a system
        # extract -- so the pipeline has to read Excel as well as CSV (§2.3).
        _write_xlsx(ds.target_allocations, directory / "target_allocations.xlsx", "allocations")
    else:
        _write_csv(ds.target_allocations, directory / "target_allocations.csv")


def verify_concentration_isolation(
    ds: anom.Dataset, injected: list[anom.InjectedAnomaly], limit_pct: float
) -> None:
    """Assert the landing data contains *exactly* the injected concentration breaches.

    Mirrors the Java rule POS_CONCENTRATION_LIMIT line for line: only clients that
    exist in the reference table, only lines with a usable (strictly positive)
    cost basis. Any divergence means a breach appeared as a side effect of another
    injection, which would make the manifest an unreliable oracle -- so the
    generation fails loudly here rather than producing a dataset whose expected
    counts are quietly wrong.
    """
    df = ds.positions
    quantity = pd.to_numeric(df["quantity"], errors="coerce")
    price = pd.to_numeric(df["purchase_price"], errors="coerce")
    usable = df[
        df["client_id"].isin(set(ds.clients["client_id"]))
        & quantity.notna() & price.notna() & (quantity > 0) & (price > 0)
    ].copy()
    usable["cost"] = pd.to_numeric(usable["quantity"]) * pd.to_numeric(usable["purchase_price"])
    totals = usable.groupby("client_id")["cost"].transform("sum")
    share_pct = 100.0 * usable["cost"] / totals
    actual = {
        f"position_id={row.position_id}"
        for row, pct in zip(usable.itertuples(index=False), share_pct)
        if pct > limit_pct
    }
    expected = {
        item.record_key for item in injected if item.anomaly_code == "EXCESSIVE_CONCENTRATION"
    }
    if actual != expected:
        raise RuntimeError(
            "Concentration isolation broken. "
            f"Expected breaches {sorted(expected)}, found {sorted(actual)}. "
            f"Lower MAX_CLEAN_LINE_SHARE (currently {MAX_CLEAN_LINE_SHARE}) and regenerate."
        )
    LOGGER.info("Verified concentration isolation: exactly %d deliberate breach(es)", len(expected))


def build_manifest(
    injected: list[anom.InjectedAnomaly],
    ds: anom.Dataset,
    options: GenerationOptions,
    provenance: dict[str, str],
) -> dict:
    by_severity: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    by_detector: dict[str, int] = {}
    for item in injected:
        by_severity[item.expected_severity] = by_severity.get(item.expected_severity, 0) + 1
        by_detector[item.detector] = by_detector.get(item.detector, 0) + 1
        if item.expected_rule_id:
            by_rule[item.expected_rule_id] = by_rule.get(item.expected_rule_id, 0) + 1
    return {
        "generator_version": "1.0.0",
        "seed": options.seed,
        "as_of_date": options.as_of.isoformat(),
        "row_counts": {
            "instruments": len(ds.instruments),
            "clients": len(ds.clients),
            "positions": len(ds.positions),
            "target_allocations": len(ds.target_allocations),
            "market_prices": len(ds.market_prices),
        },
        "market_data_provenance": dict(sorted(provenance.items())),
        "expected_anomaly_count": len(injected),
        "expected_by_severity": dict(sorted(by_severity.items())),
        "expected_by_rule": dict(sorted(by_rule.items())),
        "expected_by_detector": dict(sorted(by_detector.items())),
        "anomalies": [item.to_dict() for item in injected],
    }


def render_anomalies_doc(manifest: dict) -> str:
    """Generate docs/ANOMALIES.md from the catalogue + the manifest counts."""
    counts: dict[str, int] = {}
    for item in manifest["anomalies"]:
        counts[item["anomaly_code"]] = counts.get(item["anomaly_code"], 0) + 1

    lines = [
        "# Anomalies injectees volontairement",
        "",
        "> Fichier **genere** par `python -m wealthguard_pipeline.seed.generate`.",
        "> Ne pas editer a la main : la source de verite est",
        "> `data-pipeline/wealthguard_pipeline/seed/anomalies.py` (`ANOMALY_CATALOGUE`).",
        "",
        f"- Jeu de donnees genere avec la graine `{manifest['seed']}`, "
        f"date de reference `{manifest['as_of_date']}`.",
        f"- **{manifest['expected_anomaly_count']} anomalies** injectees sur "
        f"{manifest['row_counts']['positions']} positions, "
        f"{manifest['row_counts']['clients']} clients et "
        f"{manifest['row_counts']['market_prices']} cours.",
        "",
        "Repartition attendue par criticite :",
        "",
        "| Criticite | Occurrences |",
        "|---|---|",
    ]
    for severity, total in manifest["expected_by_severity"].items():
        lines.append(f"| {severity} | {total} |")

    lines += [
        "",
        "## Catalogue",
        "",
        "| Code | Jeu de donnees | Detecteur | Regle attendue | Criticite | Occurrences | Description | Impact metier estime |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for entry in anom.ANOMALY_CATALOGUE:
        lines.append(
            f"| `{entry.code}` | {entry.dataset} | {entry.detector} | "
            f"`{entry.expected_rule_id}` | {entry.expected_severity} | "
            f"{counts.get(entry.code, 0)} | {entry.description_fr} | {entry.business_impact_fr} |"
        )

    lines += [
        "",
        "## Comment ce fichier est verifie",
        "",
        "Ce catalogue n'est pas de la documentation declarative : il sert d'oracle de test.",
        "",
        "1. `data/seed/anomaly_manifest.json` liste la cle exacte de chaque enregistrement corrompu.",
        "2. `pytest data-pipeline/tests/test_seed_manifest.py` verifie la coherence du manifeste",
        "   (isolation des lignes, couverture du catalogue, comptes par criticite).",
        "3. `pytest -m integration data-pipeline/tests/test_end_to_end.py` envoie le jeu `landing/`",
        "   au moteur Java et compare la reponse au manifeste, regle par regle.",
        "",
        "Toute regle ajoutee cote Java sans entree correspondante ici (ou l'inverse) fait",
        "echouer la suite de tests.",
        "",
        "## Invariant d'isolation",
        "",
        "Chaque injection reserve sa ligne de facon exclusive (`RowClaimer`), afin qu'une",
        "ligne corrompue ne viole qu'une seule regle. C'est ce qui rend le decompte",
        "interpretable : si le moteur remonte 24 anomalies au lieu de "
        f"{manifest['expected_anomaly_count']}, l'ecart est",
        "forcement un faux positif identifiable, pas un effet de bord de l'injection.",
        "",
    ]
    return "\n".join(lines)


def generate(options: GenerationOptions) -> dict:
    rng = np.random.default_rng(options.seed)
    start = options.as_of - timedelta(days=HISTORY_YEARS * 365)

    LOGGER.info("Loading market prices (%s -> %s)", start, options.as_of)
    market = load_market_prices(
        start=start,
        end=options.as_of,
        cache_file=options.out_dir / "cache" / "yahoo_closes.csv",
        master_seed=options.seed,
        offline=options.offline,
        refresh=options.refresh_market,
    )
    LOGGER.info(
        "Market prices: %d rows, %d/%d tickers from Yahoo Finance",
        len(market.prices), market.real_ticker_count, len(market.provenance),
    )

    instruments = build_instruments()
    clients = build_clients(rng, options.client_count, options.as_of)
    allocations = build_target_allocations(clients, rng)
    positions = build_positions(clients, allocations, market.prices, rng, options.as_of)
    LOGGER.info("Clean dataset: %d clients, %d positions", len(clients), len(positions))

    clean = anom.Dataset(
        clients=clients,
        instruments=instruments,
        positions=positions,
        target_allocations=allocations,
        market_prices=market.prices,
    )
    write_dataset(clean, options.out_dir / "reference", excel_allocations=False)

    landing = anom.Dataset(
        clients=clients.copy(deep=True),
        instruments=instruments.copy(deep=True),
        positions=positions.copy(deep=True),
        target_allocations=allocations.copy(deep=True),
        market_prices=market.prices.copy(deep=True),
    )
    injected = anom.inject_all(landing, seed=options.seed, today=options.as_of)
    verify_concentration_isolation(landing, injected, anom.CONCENTRATION_LIMIT_PCT)
    write_dataset(landing, options.out_dir / "landing", excel_allocations=True)

    manifest = build_manifest(injected, landing, options, market.provenance)
    manifest_path = options.out_dir / "anomaly_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    doc_path = REPO_ROOT / "docs" / "ANOMALIES.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(render_anomalies_doc(manifest), encoding="utf-8")

    LOGGER.info("Wrote %s and %s", manifest_path, doc_path)
    return manifest


def parse_args(argv: list[str] | None = None) -> GenerationOptions:
    parser = argparse.ArgumentParser(description="Generate the WealthGuard synthetic dataset")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "seed",
                        help="output directory (default: <repo>/data/seed)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--clients", type=int, default=DEFAULT_CLIENT_COUNT)
    parser.add_argument("--as-of", type=lambda s: date.fromisoformat(s), default=date.today(),
                        help="reference date; pin it to keep the dataset reproducible")
    parser.add_argument("--offline", action="store_true",
                        help="never call Yahoo Finance; use the cache or synthetic prices")
    parser.add_argument("--refresh-market", action="store_true",
                        help="force a fresh Yahoo Finance download and update the cache")
    args = parser.parse_args(argv)
    return GenerationOptions(
        out_dir=args.out.resolve(),
        seed=args.seed,
        client_count=args.clients,
        as_of=args.as_of,
        offline=args.offline,
        refresh_market=args.refresh_market,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    options = parse_args(argv)
    manifest = generate(options)
    print(
        f"OK: {manifest['expected_anomaly_count']} anomalies injected across "
        f"{manifest['row_counts']['positions']} positions "
        f"(seed={manifest['seed']}, as_of={manifest['as_of_date']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
