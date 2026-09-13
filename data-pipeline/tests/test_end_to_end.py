"""Sends the committed ``landing/`` dataset to the real Java quality engine and
diffs its verdict against the manifest, rule by rule (docs/ANOMALIES.md).

Run the engine first (``mvn -pl quality-engine spring-boot:run``, or the
built jar), then:

    pytest -m integration data-pipeline/tests/test_end_to_end.py

Skips cleanly when the engine is not reachable or the dataset has not been
generated, so the default ``pytest`` run stays green without Java running.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from wealthguard_pipeline import ingest
from wealthguard_pipeline.config import REPO_ROOT, get_settings
from wealthguard_pipeline.models import JAVA_RULE_ENGINE
from wealthguard_pipeline.quality_client import QualityEngineClient

pytestmark = pytest.mark.integration

LANDING_DIR = REPO_ROOT / "data" / "seed" / "landing"
MANIFEST_PATH = REPO_ROOT / "data" / "seed" / "anomaly_manifest.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip("seed dataset not generated")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validation_report(manifest):
    if not LANDING_DIR.exists():
        pytest.skip("seed dataset not generated")
    dataset = ingest.load_landing(LANDING_DIR)
    as_of = date.fromisoformat(manifest["as_of_date"])
    client = QualityEngineClient(get_settings().quality_api)
    try:
        return client.validate(
            dataset.positions, dataset.clients, dataset.instruments, dataset.target_allocations, as_of
        )
    except ConnectionError as exc:
        pytest.skip(f"Java quality engine not reachable ({exc}); start quality-engine first.")


def _expected_counts_by_rule_for_java(manifest: dict) -> dict[str, int]:
    """Only the codes the manifest attributes to the Java engine -- the
    Python-side detectors (PYTHON_INGESTION, PYTHON_OUTLIER_DETECTOR) are
    never sent to this API, so the engine cannot and must not report them."""
    java_rule_ids = {
        entry["expected_rule_id"]
        for entry in manifest["anomalies"]
        if entry["detector"] == JAVA_RULE_ENGINE
    }
    return {
        rule_id: count
        for rule_id, count in manifest["expected_by_rule"].items()
        if rule_id in java_rule_ids
    }


class TestEndToEnd:
    def test_engine_reports_exactly_the_expected_count_per_rule(self, validation_report, manifest):
        expected = _expected_counts_by_rule_for_java(manifest)

        assert validation_report.counts_by_rule == expected

    def test_engine_executed_every_java_rule_the_manifest_expects_to_fire(self, validation_report, manifest):
        expected_rule_ids = set(_expected_counts_by_rule_for_java(manifest))

        assert expected_rule_ids <= set(validation_report.executed_rules)

    def test_total_blocking_count_matches_the_manifest(self, validation_report, manifest):
        expected_blocking = sum(
            1
            for entry in manifest["anomalies"]
            if entry["detector"] == JAVA_RULE_ENGINE and entry["expected_severity"] == "BLOQUANT"
        )

        assert validation_report.counts["blockingAnomalies"] == expected_blocking
