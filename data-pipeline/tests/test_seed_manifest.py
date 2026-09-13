"""Verifies the committed test oracle, per docs/ANOMALIES.md.

``data/seed/anomaly_manifest.json`` is not documentation: it is what
``test_end_to_end.py`` diffs the Java engine's real response against. If this
file were internally inconsistent (a miscounted total, a code with no
manifest entry, two anomalies silently sharing one row) the end-to-end
comparison would be meaningless. This test checks the manifest's own
consistency and its coverage of the catalogue in ``seed/anomalies.py`` --
independently of whether Java or Postgres is available.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from wealthguard_pipeline.config import REPO_ROOT
from wealthguard_pipeline.seed.anomalies import ANOMALY_CATALOGUE

MANIFEST_PATH = REPO_ROOT / "data" / "seed" / "anomaly_manifest.json"

pytestmark = pytest.mark.skipif(not MANIFEST_PATH.exists(), reason="seed dataset not generated")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


class TestManifestInternalConsistency:
    def test_expected_anomaly_count_matches_the_anomaly_list_length(self, manifest):
        assert manifest["expected_anomaly_count"] == len(manifest["anomalies"])

    def test_expected_by_severity_matches_a_fresh_aggregation(self, manifest):
        recomputed = Counter(a["expected_severity"] for a in manifest["anomalies"])
        assert manifest["expected_by_severity"] == dict(sorted(recomputed.items()))

    def test_expected_by_rule_matches_a_fresh_aggregation(self, manifest):
        recomputed = Counter(
            a["expected_rule_id"] for a in manifest["anomalies"] if a["expected_rule_id"]
        )
        assert manifest["expected_by_rule"] == dict(sorted(recomputed.items()))

    def test_expected_by_detector_matches_a_fresh_aggregation(self, manifest):
        recomputed = Counter(a["detector"] for a in manifest["anomalies"])
        assert manifest["expected_by_detector"] == dict(sorted(recomputed.items()))

    def test_row_isolation_no_two_anomalies_share_a_record(self, manifest):
        """Cahier des charges invariant: each corrupted row violates exactly one
        rule, so (dataset, record_key) must be unique across the whole manifest."""
        keys = Counter((a["dataset"], a["record_key"]) for a in manifest["anomalies"])
        shared = {k: v for k, v in keys.items() if v > 1}
        assert shared == {}, f"Rows claimed by more than one injector: {shared}"


class TestManifestCoversTheCatalogue:
    def test_every_catalogue_code_appears_in_the_manifest(self, manifest):
        present = {a["anomaly_code"] for a in manifest["anomalies"]}
        catalogue_codes = {entry.code for entry in ANOMALY_CATALOGUE}
        missing = catalogue_codes - present
        assert missing == set(), f"Catalogue code(s) with no manifest entry: {missing}"

    def test_the_manifest_has_no_code_outside_the_catalogue(self, manifest):
        present = {a["anomaly_code"] for a in manifest["anomalies"]}
        catalogue_codes = {entry.code for entry in ANOMALY_CATALOGUE}
        orphans = present - catalogue_codes
        assert orphans == set(), f"Manifest code(s) with no catalogue entry: {orphans}"

    def test_each_manifest_entry_agrees_with_its_catalogue_definition(self, manifest):
        by_code = {entry.code: entry for entry in ANOMALY_CATALOGUE}
        for anomaly in manifest["anomalies"]:
            entry = by_code[anomaly["anomaly_code"]]
            assert anomaly["dataset"] == entry.dataset
            assert anomaly["detector"] == entry.detector
            assert anomaly["expected_rule_id"] == entry.expected_rule_id
            assert anomaly["expected_severity"] == entry.expected_severity
