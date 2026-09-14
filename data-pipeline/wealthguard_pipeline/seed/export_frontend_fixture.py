"""Export the landing dataset as the exact JSON body the React frontend POSTs
straight to the Java quality engine from the browser.

    python -m wealthguard_pipeline.seed.export_frontend_fixture --as-of 2026-09-13

Cahier des charges §2.5: the frontend must show anomalies "en temps reel via
l'API Java", i.e. call the engine directly rather than read a pre-computed
report -- so what the frontend needs is not a report, it is exactly this
request body. Regenerated whenever the seed dataset is regenerated (same
``--as-of``), so it never drifts from ``data/seed/landing/``.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

from ..config import REPO_ROOT
from ..ingest import load_landing
from ..quality_client import build_validate_payload

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT = REPO_ROOT / "frontend" / "public" / "data" / "validate-request.json"


def export(landing_dir: Path, as_of: date, output_path: Path) -> None:
    dataset = load_landing(landing_dir)
    payload = build_validate_payload(
        dataset.positions, dataset.clients, dataset.instruments, dataset.target_allocations, as_of
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LOGGER.info(
        "Wrote %s (%d positions, %d clients, %d instruments, %d allocations)",
        output_path, len(payload["positions"]), len(payload["clients"]),
        len(payload["instruments"]), len(payload["targetAllocations"]),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing", type=Path, default=REPO_ROOT / "data" / "seed" / "landing")
    parser.add_argument("--as-of", type=lambda s: date.fromisoformat(s), default=date.today())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    args = parse_args(argv)
    export(args.landing, args.as_of, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
