from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
import responses

from wealthguard_pipeline.config import QualityApiConfig
from wealthguard_pipeline.models import JAVA_RULE_ENGINE
from wealthguard_pipeline.quality_client import QualityEngineClient, _records

BASE_URL = "http://quality-engine.test"


def _config(**overrides) -> QualityApiConfig:
    defaults = dict(base_url=BASE_URL, timeout_seconds=5.0, batch_size=500, max_retries=2)
    defaults.update(overrides)
    return QualityApiConfig(**defaults)


def _positions_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "position_id": ["P1"],
            "client_id": ["C1"],
            "ticker": ["AAPL"],
            "quantity": [10.0],
            "purchase_price": [np.nan],
            "purchase_date": [date(2024, 1, 1)],
            "currency": ["USD"],
        }
    )


REPORT_PAYLOAD = {
    "reportId": "r1",
    "validatedAt": "2024-06-15T00:00:00Z",
    "evaluationDate": "2024-06-15",
    "counts": {"positions": 1, "clients": 0, "instruments": 0, "targetAllocations": 0, "anomalies": 1, "blockingAnomalies": 1},
    "countsBySeverity": {"BLOQUANT": 1, "AVERTISSEMENT": 0, "INFO": 0},
    "countsByRule": {"POS_REQUIRED_FIELDS": 1},
    "countsByCategory": {"COMPLETUDE": 1},
    "executedRules": ["POS_REQUIRED_FIELDS"],
    "durationMillis": 3,
    "anomalies": [
        {
            "ruleId": "POS_REQUIRED_FIELDS", "ruleLabel": "label", "category": "COMPLETUDE", "severity": "BLOQUANT",
            "dataset": "positions", "recordKey": "position_id=P1", "fieldName": "purchasePrice",
            "observedValue": None, "message": "msg", "estimatedImpact": "impact", "suggestedFix": "fix",
        }
    ],
}


class TestRecords:
    def test_renames_columns_to_camel_case_and_converts_nan_to_none(self):
        records = _records(
            _positions_df(),
            {"position_id": "positionId", "quantity": "quantity", "purchase_price": "purchasePrice",
             "purchase_date": "purchaseDate"},
        )

        assert records == [
            {"positionId": "P1", "quantity": 10.0, "purchasePrice": None, "purchaseDate": "2024-01-01"}
        ]

    def test_returns_an_empty_list_for_an_empty_dataframe(self):
        empty = pd.DataFrame(columns=["position_id"])

        assert _records(empty, {"position_id": "positionId"}) == []


class TestQualityEngineClient:
    @responses.activate
    def test_sends_the_expected_json_payload_and_parses_the_report(self):
        captured = {}

        def handler(request):
            import json
            captured["body"] = json.loads(request.body)
            return (200, {}, json.dumps(REPORT_PAYLOAD))

        responses.add_callback(
            responses.POST, f"{BASE_URL}/api/v1/validate", callback=handler, content_type="application/json"
        )
        client = QualityEngineClient(_config())

        report = client.validate(_positions_df(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), date(2024, 6, 15))

        assert captured["body"]["evaluationDate"] == "2024-06-15"
        assert captured["body"]["positions"] == [
            {"positionId": "P1", "clientId": "C1", "ticker": "AAPL", "quantity": 10.0,
             "purchasePrice": None, "purchaseDate": "2024-01-01", "currency": "USD"}
        ]
        assert captured["body"]["clients"] == []

        assert report.report_id == "r1"
        assert report.has_blocking_anomalies is True
        assert len(report.anomalies) == 1
        assert report.anomalies[0].detector == JAVA_RULE_ENGINE
        assert report.anomalies[0].rule_id == "POS_REQUIRED_FIELDS"

    @responses.activate
    def test_retries_on_failure_and_succeeds_on_the_last_attempt(self):
        responses.add(responses.POST, f"{BASE_URL}/api/v1/validate", status=503)
        responses.add(responses.POST, f"{BASE_URL}/api/v1/validate", json=REPORT_PAYLOAD, status=200)
        client = QualityEngineClient(_config(max_retries=2))

        report = client.validate(_positions_df(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), date(2024, 6, 15))

        assert report.report_id == "r1"
        assert len(responses.calls) == 2

    @responses.activate
    def test_raises_after_exhausting_retries(self):
        responses.add(responses.POST, f"{BASE_URL}/api/v1/validate", status=500)
        responses.add(responses.POST, f"{BASE_URL}/api/v1/validate", status=500)
        client = QualityEngineClient(_config(max_retries=2))

        with pytest.raises(ConnectionError):
            client.validate(_positions_df(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), date(2024, 6, 15))

        assert len(responses.calls) == 2
