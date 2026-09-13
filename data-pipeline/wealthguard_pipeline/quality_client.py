"""HTTP client for the Java quality engine (cahier des charges §2.3).

Deliberately the *only* place that knows the Java API's JSON shape (camelCase
field names, ISO dates) -- everywhere else in the pipeline works with plain
pandas DataFrames in the seed generator's snake_case column names. This is
what makes the two languages' contract explicit and auditable in one file
instead of scattered `.rename()` calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests

from .config import QualityApiConfig
from .models import JAVA_RULE_ENGINE, Anomaly

#: DataFrame column (snake_case) -> Java DTO field (camelCase), per dataset.
_POSITION_FIELDS = {
    "position_id": "positionId",
    "client_id": "clientId",
    "ticker": "ticker",
    "quantity": "quantity",
    "purchase_price": "purchasePrice",
    "purchase_date": "purchaseDate",
    "currency": "currency",
}
_CLIENT_FIELDS = {
    "client_id": "clientId",
    "full_name": "fullName",
    "risk_profile": "riskProfile",
    "reference_currency": "referenceCurrency",
    "onboarding_date": "onboardingDate",
    "advisor": "advisor",
}
_INSTRUMENT_FIELDS = {
    "ticker": "ticker",
    "name": "name",
    "instrument_type": "instrumentType",
    "asset_class": "assetClass",
    "currency": "currency",
    "exchange": "exchange",
}
_ALLOCATION_FIELDS = {
    "client_id": "clientId",
    "asset_class": "assetClass",
    "target_weight_pct": "targetWeightPct",
}


def _to_wire(value: object) -> object:
    """One DataFrame cell -> a JSON-safe value for the Java DTOs.

    ``NaN`` becomes ``None`` (a genuinely absent value, which is what the
    completeness rule is meant to catch) and dates render as ISO-8601 strings,
    which is the only format Spring's Jackson configuration accepts for a
    ``LocalDate`` field.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if pd.isna(value):  # catches pandas NaT and other pandas-null sentinels
        return None
    return value


def _records(df: pd.DataFrame, field_map: dict[str, str]) -> list[dict]:
    """Rename ``df``'s columns per ``field_map`` and serialise each row to a dict."""
    if df.empty:
        return []
    renamed = df[list(field_map)].rename(columns=field_map)
    return [{k: _to_wire(v) for k, v in row.items()} for row in renamed.to_dict(orient="records")]


@dataclass(frozen=True)
class ValidationReport:
    """Python-side mirror of ``com.wealthguard.quality.domain.ValidationReport``."""

    report_id: str
    evaluation_date: str
    counts: dict
    counts_by_severity: dict
    counts_by_rule: dict
    counts_by_category: dict
    executed_rules: list[str]
    duration_millis: int
    anomalies: list[Anomaly]

    @property
    def has_blocking_anomalies(self) -> bool:
        return self.counts.get("blockingAnomalies", 0) > 0


def _parse_report(payload: dict) -> ValidationReport:
    anomalies = [
        Anomaly(
            rule_id=a["ruleId"],
            rule_label=a["ruleLabel"],
            category=a["category"],
            severity=a["severity"],
            dataset=a["dataset"],
            record_key=a["recordKey"],
            detector=JAVA_RULE_ENGINE,
            field_name=a.get("fieldName"),
            observed_value=a.get("observedValue"),
            message=a.get("message", ""),
            estimated_impact=a.get("estimatedImpact", ""),
            suggested_fix=a.get("suggestedFix", ""),
        )
        for a in payload["anomalies"]
    ]
    return ValidationReport(
        report_id=payload["reportId"],
        evaluation_date=payload["evaluationDate"],
        counts=payload["counts"],
        counts_by_severity=payload["countsBySeverity"],
        counts_by_rule=payload["countsByRule"],
        counts_by_category=payload["countsByCategory"],
        executed_rules=payload["executedRules"],
        duration_millis=payload["durationMillis"],
        anomalies=anomalies,
    )


class QualityEngineClient:
    """Thin REST client for ``POST /api/v1/validate`` and ``GET /api/v1/rules``."""

    def __init__(self, config: QualityApiConfig, session: requests.Session | None = None):
        self._config = config
        self._session = session or requests.Session()

    def validate(
        self,
        positions: pd.DataFrame,
        clients: pd.DataFrame,
        instruments: pd.DataFrame,
        target_allocations: pd.DataFrame,
        evaluation_date: date,
    ) -> ValidationReport:
        """Validate one batch. Retries transient failures up to ``max_retries`` times.

        Reference data (clients/instruments/target_allocations) is sent whole
        alongside the positions: the engine is stateless per request, so a
        referential or aggregate rule (e.g. ``ALLOC_SUM_EQUALS_100``) only sees
        the full picture if every call carries it. This works unmodified for
        batches that fit in one HTTP request -- the case for this dataset
        (a few hundred positions) and for a single family office's daily
        volume in general. A pipeline ingesting a custodian file large enough
        to require chunking positions across multiple calls would need to
        send the aggregate-level datasets (clients, target_allocations) with
        only the first chunk and merge the resulting reports itself, to avoid
        double-counting a client-level anomaly once per chunk; that scenario
        is out of scope here.
        """
        payload = {
            "positions": _records(positions, _POSITION_FIELDS),
            "clients": _records(clients, _CLIENT_FIELDS),
            "instruments": _records(instruments, _INSTRUMENT_FIELDS),
            "targetAllocations": _records(target_allocations, _ALLOCATION_FIELDS),
            "evaluationDate": evaluation_date.isoformat(),
        }
        url = f"{self._config.base_url}/api/v1/validate"

        last_error: Exception | None = None
        for attempt in range(1, self._config.max_retries + 1):
            try:
                response = self._session.post(url, json=payload, timeout=self._config.timeout_seconds)
                response.raise_for_status()
                return _parse_report(response.json())
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self._config.max_retries:
                    break
        raise ConnectionError(
            f"Could not reach the quality engine at {url} after {self._config.max_retries} attempt(s)"
        ) from last_error
