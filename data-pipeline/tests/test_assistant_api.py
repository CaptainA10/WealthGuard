"""Tests for the FastAPI surface -- no network, no LLM, no Postgres. The
`get_assistant` dependency is overridden with an in-memory fake, following
the same principle as test_assistant_nl_query.py: nothing here can spend
money or needs external infrastructure to run.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wealthguard_pipeline.assistant.api import app, get_assistant
from wealthguard_pipeline.assistant.nl_query import AssistantAnswer
from wealthguard_pipeline.assistant.security import QueryValidationError


class FakeAssistant:
    def __init__(self, answer: AssistantAnswer | None = None, error: Exception | None = None):
        self._answer = answer
        self._error = error
        self.asked: list[str] = []

    def ask(self, question: str) -> AssistantAnswer:
        self.asked.append(question)
        if self._error is not None:
            raise self._error
        assert self._answer is not None
        return self._answer


def _override(fake: FakeAssistant) -> None:
    app.dependency_overrides[get_assistant] = lambda: fake


def _clear_override() -> None:
    app.dependency_overrides.pop(get_assistant, None)


class TestAskEndpoint:
    def test_returns_the_assistants_answer(self):
        answer = AssistantAnswer(
            question="Quels clients ?",
            sql="SELECT client_id FROM clients LIMIT 50",
            columns=["client_id"],
            rows=[{"client_id": "C1"}, {"client_id": "C2"}],
        )
        fake = FakeAssistant(answer=answer)
        _override(fake)
        try:
            client = TestClient(app)
            response = client.post("/ask", json={"question": "Quels clients ?"})
        finally:
            _clear_override()

        assert response.status_code == 200
        body = response.json()
        assert body["sql"] == answer.sql
        assert body["rows"] == answer.rows
        assert fake.asked == ["Quels clients ?"]

    def test_maps_a_validation_error_to_422(self):
        fake = FakeAssistant(error=QueryValidationError("Table non autorisee"))
        _override(fake)
        try:
            client = TestClient(app)
            response = client.post("/ask", json={"question": "..."})
        finally:
            _clear_override()

        assert response.status_code == 422
        assert "Table non autorisee" in response.json()["detail"]

    def test_health_endpoint_needs_no_auth(self):
        assert TestClient(app).get("/health").status_code == 200

    def test_rejects_a_request_missing_the_question_field(self):
        fake = FakeAssistant(answer=AssistantAnswer("", "", [], []))
        _override(fake)
        try:
            client = TestClient(app)
            response = client.post("/ask", json={})
        finally:
            _clear_override()

        assert response.status_code == 422


class TestDemoKeyGate:
    """WG_ASSISTANT_DEMO_KEY is unset in every TestAskEndpoint case above (and
    in local dev) -- the gate must be a no-op then. It only activates once
    the Azure deployment sets that app setting, to stop random internet
    traffic from burning through the free-tier Groq quota."""

    def test_no_op_when_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("WG_ASSISTANT_DEMO_KEY", raising=False)
        fake = FakeAssistant(answer=AssistantAnswer("q", "SELECT 1", ["x"], []))
        _override(fake)
        try:
            response = TestClient(app).post("/ask", json={"question": "q"})
        finally:
            _clear_override()
        assert response.status_code == 200

    def test_rejects_missing_or_wrong_header_when_set(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("WG_ASSISTANT_DEMO_KEY", "secret123")
        fake = FakeAssistant(answer=AssistantAnswer("q", "SELECT 1", ["x"], []))
        _override(fake)
        try:
            client = TestClient(app)
            missing = client.post("/ask", json={"question": "q"})
            wrong = client.post("/ask", json={"question": "q"}, headers={"X-Demo-Key": "nope"})
            right = client.post("/ask", json={"question": "q"}, headers={"X-Demo-Key": "secret123"})
        finally:
            _clear_override()
        assert missing.status_code == 401
        assert wrong.status_code == 401
        assert right.status_code == 200
