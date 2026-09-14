"""Tests for the FastAPI surface -- no network, no LLM, no Postgres. The
`get_assistant` dependency is overridden with an in-memory fake, following
the same principle as test_assistant_nl_query.py: nothing here can spend
money or needs external infrastructure to run.
"""

from __future__ import annotations

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

    def test_rejects_a_request_missing_the_question_field(self):
        fake = FakeAssistant(answer=AssistantAnswer("", "", [], []))
        _override(fake)
        try:
            client = TestClient(app)
            response = client.post("/ask", json={})
        finally:
            _clear_override()

        assert response.status_code == 422
