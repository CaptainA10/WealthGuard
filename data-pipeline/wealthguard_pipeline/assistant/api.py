"""Thin HTTP surface over the assistant (cahier des charges §2.4).

    uvicorn wealthguard_pipeline.assistant.api:app --port 8090

All the security logic lives in ``security.py`` / ``nl_query.py``; this
module only maps a request/response shape and a validation failure onto an
HTTP status code.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from .. import db
from ..config import get_settings
from .nl_query import NaturalLanguageQueryAssistant
from .security import QueryValidationError

app = FastAPI(title="WealthGuard — Assistant en langage naturel", version="1.0.0")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[dict]


def get_assistant() -> NaturalLanguageQueryAssistant:
    """FastAPI dependency, built fresh per call so the DB engine and the LLM
    client always reflect current settings. Overridden in tests with a fake
    chain -- see ``tests/test_assistant_api.py`` -- so importing this module,
    and running its tests, never requires a GROQ_API_KEY/ANTHROPIC_API_KEY."""
    settings = get_settings()
    engine = db.build_engine(settings.database)
    return NaturalLanguageQueryAssistant(settings.assistant, engine)


@app.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest, assistant: NaturalLanguageQueryAssistant = Depends(get_assistant)
) -> AskResponse:
    try:
        answer = assistant.ask(request.question)
    except QueryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AskResponse(
        question=answer.question, sql=answer.sql, columns=answer.columns, rows=answer.rows
    )
