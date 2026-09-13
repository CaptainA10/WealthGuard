"""Shared anomaly model, common to every detector in the pipeline.

Three different components can find a data-quality problem: the Java rule
engine (``quality_client``), the Python ingestion checks (``ingest``), and the
home-made statistical outlier detector (``outliers``). All three report through
this one dataclass so the final report is a single flat list, not three
differently-shaped ones the caller has to reconcile -- and so a Java-side
finding and a Python-side finding read identically in the JSON report and in
the React anomaly list.

Field names and the severity vocabulary mirror
``com.wealthguard.quality.domain.Anomaly`` / ``Severity`` on the Java side
(quality-engine/src/main/java/com/wealthguard/quality/domain/). Keeping the two
independent (rather than importing one from the other across the language
boundary) is deliberate: the contract is the shape and the string values, not a
shared runtime dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

#: Mirrors com.wealthguard.quality.domain.Severity.
BLOQUANT = "BLOQUANT"
AVERTISSEMENT = "AVERTISSEMENT"
INFO = "INFO"

#: Which component produced a finding -- lets a report reader tell "the Java
#: engine rejected this row" from "the Python outlier detector flagged this".
JAVA_RULE_ENGINE = "JAVA_RULE_ENGINE"
PYTHON_INGESTION = "PYTHON_INGESTION"
PYTHON_OUTLIER_DETECTOR = "PYTHON_OUTLIER_DETECTOR"


@dataclass(frozen=True)
class Anomaly:
    """One quality finding, from whichever detector produced it.

    Mirrors ``com.wealthguard.quality.domain.Anomaly`` field for field, plus
    ``detector`` to say which component (Java or Python) is responsible --
    the Java record does not need that field because, on its side, there is
    only ever one detector.
    """

    rule_id: str
    rule_label: str
    category: str
    severity: str
    dataset: str
    record_key: str
    detector: str
    field_name: str | None = None
    observed_value: str | None = None
    message: str = ""
    estimated_impact: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
