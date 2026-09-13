from __future__ import annotations

from datetime import date

import pandas as pd

from wealthguard_pipeline.ingest import Dataset
from wealthguard_pipeline.models import AVERTISSEMENT, BLOQUANT, JAVA_RULE_ENGINE, Anomaly
from wealthguard_pipeline.quarantine import quarantine


def _dataset() -> Dataset:
    clients = pd.DataFrame(
        {
            "client_id": ["C1", "C2"],
            "full_name": ["Client One", "Client Two"],
            "risk_profile": ["EQUILIBRE", "PRUDENT"],
            "reference_currency": ["EUR", "EUR"],
            "onboarding_date": [date(2020, 1, 1), date(2020, 1, 1)],
            "advisor": ["A", "A"],
        }
    )
    instruments = pd.DataFrame(
        {"ticker": ["AAPL"], "name": ["Apple"], "instrument_type": ["STOCK"], "asset_class": ["ACTIONS"],
         "currency": ["USD"], "exchange": ["NASDAQ"]}
    )
    positions = pd.DataFrame(
        {
            "position_id": ["P1", "P2", "P3"],
            "client_id": ["C1", "C2", "UNKNOWN"],
            "ticker": ["AAPL", "AAPL", "AAPL"],
            "quantity": [10.0, 5.0, 1.0],
            "purchase_price": [100.0, 100.0, 100.0],
            "purchase_date": [date(2021, 1, 1)] * 3,
            "currency": ["USD"] * 3,
        }
    )
    allocations = pd.DataFrame(
        {"client_id": ["C1", "C2"], "asset_class": ["ACTIONS", "ACTIONS"], "target_weight_pct": [100.0, 100.0]}
    )
    market_prices = pd.DataFrame(columns=["ticker", "price_date", "close_price", "currency", "price_source"])
    return Dataset(clients, instruments, positions, allocations, market_prices)


def _bloquant(dataset: str, record_key: str, rule_id: str = "SOME_RULE") -> Anomaly:
    return Anomaly(
        rule_id=rule_id, rule_label=rule_id, category="COHERENCE_METIER", severity=BLOQUANT,
        dataset=dataset, record_key=record_key, detector=JAVA_RULE_ENGINE,
    )


class TestQuarantine:
    def test_drops_the_position_flagged_bloquant(self):
        ds = _dataset()
        anomalies = [_bloquant("positions", "position_id=P3", "POS_KNOWN_CLIENT")]

        result = quarantine(ds, anomalies)

        assert set(result.positions["position_id"]) == {"P1", "P2"}

    def test_avertissement_findings_do_not_trigger_quarantine(self):
        ds = _dataset()
        warning = Anomaly(
            rule_id="POS_CURRENCY_MATCHES_INSTRUMENT", rule_label="x", category="COHERENCE_METIER",
            severity=AVERTISSEMENT, dataset="positions", record_key="position_id=P1", detector=JAVA_RULE_ENGINE,
        )

        result = quarantine(ds, [warning])

        assert set(result.positions["position_id"]) == {"P1", "P2", "P3"}

    def test_dropping_a_duplicated_client_cascades_to_its_positions_and_allocations(self):
        ds = _dataset()
        anomalies = [_bloquant("clients", "client_id=C1", "CLI_UNIQUE_ID")]

        result = quarantine(ds, anomalies)

        assert set(result.clients["client_id"]) == {"C2"}
        # P3 references "UNKNOWN", not C1, so it is untouched by this anomaly --
        # only C1's own positions and allocations must disappear.
        assert set(result.positions["client_id"]) == {"C2", "UNKNOWN"}
        assert "P1" not in set(result.positions["position_id"])
        assert set(result.target_allocations["client_id"]) == {"C2"}

    def test_drops_only_the_flagged_allocation_line_not_the_whole_client(self):
        ds = _dataset()
        anomalies = [_bloquant("target_allocations", "client_id=C1&asset_class=ACTIONS", "ALLOC_WEIGHT_IN_RANGE")]

        result = quarantine(ds, anomalies)

        assert set(result.clients["client_id"]) == {"C1", "C2"}
        assert list(result.target_allocations["client_id"]) == ["C2"]

    def test_instruments_and_market_prices_are_never_filtered(self):
        ds = _dataset()
        anomalies = [_bloquant("positions", "position_id=P1", "POS_POSITIVE_QUANTITY")]

        result = quarantine(ds, anomalies)

        assert len(result.instruments) == len(ds.instruments)
        assert result.market_prices is ds.market_prices

    def test_no_anomalies_leaves_the_dataset_untouched(self):
        ds = _dataset()

        result = quarantine(ds, [])

        assert len(result.positions) == len(ds.positions)
        assert len(result.clients) == len(ds.clients)
        assert len(result.target_allocations) == len(ds.target_allocations)
