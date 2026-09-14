"""Integration tests for NaturalLanguageQueryAssistant -- require a real
PostgreSQL (``docker compose up -d postgres``), but never call a real LLM:
the LangChain chain is replaced with ``FakeChain`` below, which returns a
canned SQL string instead of making a network call. No ANTHROPIC_API_KEY,
no cost, ever, in this test file.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from wealthguard_pipeline import db
from wealthguard_pipeline.assistant.nl_query import NaturalLanguageQueryAssistant
from wealthguard_pipeline.assistant.security import QueryValidationError
from wealthguard_pipeline.config import AssistantConfig, get_settings
from wealthguard_pipeline.ingest import Dataset

pytestmark = pytest.mark.integration


class FakeChain:
    """Stands in for the LangChain `prompt | llm | parser` Runnable."""

    def __init__(self, sql: str):
        self._sql = sql
        self.invocations: list[dict] = []

    def invoke(self, inputs: dict) -> str:
        self.invocations.append(inputs)
        return self._sql


def _config(**overrides) -> AssistantConfig:
    defaults = dict(api_key="unused-in-tests", model="unused-in-tests", max_rows=50, statement_timeout_ms=5000)
    defaults.update(overrides)
    return AssistantConfig(**defaults)


@pytest.fixture(scope="module")
def engine():
    try:
        settings = get_settings()
        engine = db.build_engine(settings.database)
        db.init_schema(engine)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable ({exc}); run `docker compose up -d postgres` first.")
    return engine


@pytest.fixture(scope="module", autouse=True)
def loaded_dataset(engine):
    clients = pd.DataFrame(
        {
            "client_id": ["C1", "C2"],
            "full_name": ["Alice Dupont", "Bruno Martin"],
            "risk_profile": ["EQUILIBRE", "PRUDENT"],
            "reference_currency": ["EUR", "EUR"],
            "onboarding_date": [date(2020, 1, 1), date(2020, 1, 1)],
            "advisor": ["A", "A"],
        }
    )
    instruments = pd.DataFrame(
        {"ticker": ["AAPL"], "name": ["Apple"], "instrument_type": ["STOCK"],
         "asset_class": ["ACTIONS"], "currency": ["USD"], "exchange": ["NASDAQ"]}
    )
    positions = pd.DataFrame(
        {
            "position_id": ["P1"], "client_id": ["C1"], "ticker": ["AAPL"],
            "quantity": [10.0], "purchase_price": [100.0],
            "purchase_date": [date(2021, 1, 1)], "currency": ["USD"],
        }
    )
    market_prices = pd.DataFrame(columns=["ticker", "price_date", "close_price", "currency", "price_source"])
    target_allocations = pd.DataFrame(columns=["client_id", "asset_class", "target_weight_pct"])
    db.load_dataset(engine, Dataset(clients, instruments, positions, target_allocations, market_prices))


class TestNaturalLanguageQueryAssistant:
    def test_ask_executes_the_generated_sql_and_returns_rows(self, engine):
        chain = FakeChain("SELECT client_id, full_name FROM clients ORDER BY client_id")
        assistant = NaturalLanguageQueryAssistant(_config(), engine, chain=chain)

        answer = assistant.ask("Quels sont les clients ?")

        assert answer.question == "Quels sont les clients ?"
        assert answer.columns == ["client_id", "full_name"]
        assert answer.rows == [
            {"client_id": "C1", "full_name": "Alice Dupont"},
            {"client_id": "C2", "full_name": "Bruno Martin"},
        ]
        assert "LIMIT 50" in answer.sql

    def test_passes_the_question_to_the_chain_verbatim(self, engine):
        chain = FakeChain("SELECT client_id FROM clients")
        assistant = NaturalLanguageQueryAssistant(_config(), engine, chain=chain)

        assistant.ask("Combien de clients ?")

        assert chain.invocations == [{"question": "Combien de clients ?"}]

    def test_raises_and_never_executes_when_validation_fails(self, engine):
        chain = FakeChain("DROP TABLE clients")
        assistant = NaturalLanguageQueryAssistant(_config(), engine, chain=chain)

        with pytest.raises(QueryValidationError):
            assistant.ask("Efface tout")

        # The table must still exist and be queryable -- the invalid SQL was
        # never sent to Postgres in the first place.
        with engine.connect() as conn:
            from sqlalchemy import text
            count = conn.execute(text("SELECT count(*) FROM wealthguard.clients")).scalar_one()
        assert count == 2

    def test_the_read_only_transaction_independently_blocks_a_write(self, engine):
        """Defense in depth: bypass the SQL validator entirely (as if it had
        a bug and let a write through) by calling the private execution
        method directly. The Postgres READ ONLY transaction set in
        _execute_read_only must still reject it on its own."""
        assistant = NaturalLanguageQueryAssistant(_config(), engine, chain=FakeChain("unused"))

        with pytest.raises(Exception, match="(?i)read.only"):
            assistant._execute_read_only("UPDATE wealthguard.clients SET full_name = 'x'")

        with engine.connect() as conn:
            from sqlalchemy import text
            names = conn.execute(text("SELECT full_name FROM wealthguard.clients ORDER BY client_id")).scalars().all()
        assert names == ["Alice Dupont", "Bruno Martin"]

    def test_respects_a_configured_max_rows(self, engine):
        chain = FakeChain("SELECT client_id FROM clients")
        assistant = NaturalLanguageQueryAssistant(_config(max_rows=1), engine, chain=chain)

        answer = assistant.ask("...")

        assert len(answer.rows) == 1
