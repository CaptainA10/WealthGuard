"""End-to-end orchestration (cahier des charges §2.3):

    ingest (CSV/Excel) -> Python ingestion checks -> home-made outlier
    detection -> Java quality engine (POST /api/v1/validate) -> quarantine
    BLOQUANT rows -> load PostgreSQL -> SQL indicators -> write report.

    python -m wealthguard_pipeline.main --landing data/seed/landing --as-of 2026-09-13
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import pandas as pd

from . import db, indicators, ingest, outliers
from . import quarantine as qtn
from .config import REPO_ROOT, get_settings
from .models import AVERTISSEMENT, BLOQUANT, INFO, Anomaly
from .quality_client import QualityEngineClient

LOGGER = logging.getLogger(__name__)


def run(landing_dir: Path, as_of: date, reports_dir: Path) -> dict:
    started_at = time.perf_counter()
    settings = get_settings()

    dataset = ingest.load_landing(landing_dir)
    LOGGER.info(
        "Ingested %d positions, %d clients, %d instruments, %d allocations, %d price rows",
        len(dataset.positions), len(dataset.clients), len(dataset.instruments),
        len(dataset.target_allocations), len(dataset.market_prices),
    )

    python_anomalies: list[Anomaly] = []
    python_anomalies += ingest.check_market_prices(dataset.market_prices)
    python_anomalies += outliers.detect_price_outliers(dataset.market_prices)
    LOGGER.info("Python ingestion + outlier detector: %d finding(s)", len(python_anomalies))

    client = QualityEngineClient(settings.quality_api)
    report = client.validate(
        dataset.positions, dataset.clients, dataset.instruments, dataset.target_allocations, as_of
    )
    LOGGER.info(
        "Java quality engine: %d anomalies (%d blocking) across %d executed rule(s)",
        report.counts["anomalies"], report.counts["blockingAnomalies"], len(report.executed_rules),
    )

    all_anomalies = list(report.anomalies) + python_anomalies

    clean_dataset = qtn.quarantine(dataset, report.anomalies)
    LOGGER.info(
        "After quarantine: %d/%d positions, %d/%d clients, %d/%d allocation lines loadable",
        len(clean_dataset.positions), len(dataset.positions),
        len(clean_dataset.clients), len(dataset.clients),
        len(clean_dataset.target_allocations), len(dataset.target_allocations),
    )
    # Deduplicated for loading only: check_market_prices() above already saw
    # (and reported) every duplicate on the original frame.
    deduped_prices = ingest.dedupe_market_prices(clean_dataset.market_prices)
    clean_dataset = replace(clean_dataset, market_prices=deduped_prices)

    engine = db.build_engine(settings.database)
    db.init_schema(engine)
    db.load_dataset(engine, clean_dataset)
    LOGGER.info("Loaded the quarantined dataset into %s", settings.database.safe_repr())

    valuation = indicators.portfolio_valuation(engine, as_of)
    allocation = indicators.allocation_vs_target(engine, as_of)
    holdings = indicators.top_holdings(engine, as_of)

    reports_dir.mkdir(parents=True, exist_ok=True)
    _write_reports(reports_dir, as_of, all_anomalies, valuation, allocation, holdings)

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    summary = {
        "as_of_date": as_of,
        "anomaly_count": len(all_anomalies),
        "bloquant_count": sum(1 for a in all_anomalies if a.severity == BLOQUANT),
        "avertissement_count": sum(1 for a in all_anomalies if a.severity == AVERTISSEMENT),
        "info_count": sum(1 for a in all_anomalies if a.severity == INFO),
        "clients_valued": int(len(valuation)),
        "total_market_value": float(valuation["total_market_value"].sum()) if not valuation.empty else 0.0,
        "duration_ms": duration_ms,
    }
    db.record_run(engine, summary)
    LOGGER.info("Recorded this run in wealthguard.pipeline_runs (duration=%d ms)", duration_ms)

    return {
        "as_of": as_of.isoformat(),
        "anomaly_count": summary["anomaly_count"],
        "blocking_count": summary["bloquant_count"],
        "clients_valued": summary["clients_valued"],
        "total_market_value": summary["total_market_value"],
    }


def _write_reports(
    reports_dir: Path,
    as_of: date,
    anomalies: list[Anomaly],
    valuation: pd.DataFrame,
    allocation: pd.DataFrame,
    holdings: pd.DataFrame,
) -> None:
    anomalies_payload = {
        "as_of": as_of.isoformat(),
        "anomaly_count": len(anomalies),
        "anomalies": [asdict(a) for a in anomalies],
    }
    (reports_dir / "anomalies.json").write_text(
        json.dumps(anomalies_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    valuation.to_csv(reports_dir / "portfolio_valuation.csv", index=False)
    allocation.to_csv(reports_dir / "allocation_vs_target.csv", index=False)
    holdings.to_csv(reports_dir / "top_holdings.csv", index=False)
    LOGGER.info("Wrote reports to %s", reports_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the WealthGuard data pipeline")
    parser.add_argument(
        "--landing", type=Path, default=REPO_ROOT / "data" / "seed" / "landing",
        help="directory holding clients/instruments/positions/target_allocations/market_prices",
    )
    parser.add_argument(
        "--as-of", type=lambda s: date.fromisoformat(s), default=date.today(),
        help="valuation date (defaults to today)",
    )
    parser.add_argument(
        "--reports-dir", type=Path, default=None,
        help="output directory for reports (defaults to WG_REPORTS_DIR / <repo>/data/reports)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    args = parse_args(argv)
    reports_dir = args.reports_dir or get_settings().paths.reports_dir
    summary = run(args.landing, args.as_of, reports_dir)
    print(
        f"OK: {summary['anomaly_count']} anomalies ({summary['blocking_count']} blocking), "
        f"{summary['clients_valued']} clients valued, "
        f"total market value {summary['total_market_value']:,.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
