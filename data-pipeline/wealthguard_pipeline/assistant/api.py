"""Thin HTTP surface over the assistant (cahier des charges §2.4).

    uvicorn wealthguard_pipeline.assistant.api:app --port 8090

All the security logic lives in ``security.py`` / ``nl_query.py``; this
module only maps a request/response shape and a validation failure onto an
HTTP status code.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .. import db
from ..config import get_settings
from .nl_query import NaturalLanguageQueryAssistant
from .security import QueryValidationError

app = FastAPI(title="WealthGuard — Assistant en langage naturel", version="1.0.0")

# Same convention as the Java quality-engine's WEALTHGUARD_CORS_ALLOWED_ORIGINS
# (see azure/setup.sh): comma-separated origins, absent = no cross-origin calls.
_cors_origins = [o.strip() for o in os.environ.get("WEALTHGUARD_CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["POST"],
        allow_headers=["Content-Type", "X-Demo-Key"],
    )


def require_demo_key(x_demo_key: str | None = Header(default=None)) -> None:
    """Optional shared-secret gate on /ask.

    Unset in local dev and in every test (get_assistant is overridden there
    anyway), so this changes nothing for the existing test suite. Set only on
    the public Azure deployment (WG_ASSISTANT_DEMO_KEY app setting) -- it is
    not real authentication, just a brake against random internet traffic
    burning through a free-tier Groq quota. See ARCHITECTURE.md §8.
    """
    expected = os.environ.get("WG_ASSISTANT_DEMO_KEY", "").strip()
    if expected and x_demo_key != expected:
        raise HTTPException(status_code=401, detail="En-tête X-Demo-Key manquant ou invalide")


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


@app.get("/health")
def health() -> dict[str, str]:
    """Unauthenticated liveness probe for Azure App Service's health check."""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(require_demo_key)])
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
