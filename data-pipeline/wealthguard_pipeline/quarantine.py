"""Keep BLOQUANT-flagged rows out of the warehouse before they are loaded.

The Java engine's verdict is advisory until this step: a BLOQUANT anomaly
means "loading this row as-is would corrupt an indicator" (see
``com.wealthguard.quality.domain.Severity``), so the pipeline must actually
act on that verdict rather than just log it. AVERTISSEMENT and INFO rows are
left untouched -- they load, with their caveat surfaced in the anomaly report
alongside the indicators, not hidden from them.
"""

from __future__ import annotations

from .ingest import Dataset
from .models import BLOQUANT, Anomaly


def _parse_record_key(record_key: str) -> dict[str, str]:
    """``"client_id=C1&asset_class=ACTIONS"`` -> ``{"client_id": "C1", "asset_class": "ACTIONS"}``."""
    parsed: dict[str, str] = {}
    for part in record_key.split("&"):
        key, sep, value = part.partition("=")
        if sep:
            parsed[key] = value
    return parsed


def quarantine(dataset: Dataset, anomalies: list[Anomaly]) -> Dataset:
    """Drop every row a BLOQUANT anomaly was raised against, cascading on client_id.

    Positions and target-allocation lines are excluded by their own record key
    (``position_id`` / ``client_id`` + ``asset_class``) *and*, separately, by
    ``client_id`` when that client itself was excluded (e.g. a duplicated
    ``CLI_UNIQUE_ID`` fiche) -- otherwise those rows would violate the
    warehouse's foreign keys instead of being cleanly quarantined.
    """
    blocking = [a for a in anomalies if a.severity == BLOQUANT]

    excluded_position_ids = {
        _parse_record_key(a.record_key)["position_id"]
        for a in blocking
        if a.dataset == "positions" and "position_id" in _parse_record_key(a.record_key)
    }
    excluded_client_ids = {
        _parse_record_key(a.record_key)["client_id"]
        for a in blocking
        if a.dataset == "clients" and "client_id" in _parse_record_key(a.record_key)
    }
    excluded_allocation_keys = {
        (parsed["client_id"], parsed["asset_class"])
        for a in blocking
        if a.dataset == "target_allocations"
        for parsed in [_parse_record_key(a.record_key)]
        if "client_id" in parsed and "asset_class" in parsed
    }

    clients = dataset.clients[~dataset.clients["client_id"].isin(excluded_client_ids)]

    positions = dataset.positions[
        ~dataset.positions["position_id"].isin(excluded_position_ids)
        & ~dataset.positions["client_id"].isin(excluded_client_ids)
    ]

    target_allocations = dataset.target_allocations[
        ~dataset.target_allocations["client_id"].isin(excluded_client_ids)
        & ~dataset.target_allocations.apply(
            lambda row: (row["client_id"], row["asset_class"]) in excluded_allocation_keys, axis=1
        )
    ]

    return Dataset(
        clients=clients,
        instruments=dataset.instruments,
        positions=positions,
        target_allocations=target_allocations,
        market_prices=dataset.market_prices,
    )
