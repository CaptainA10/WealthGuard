"""Terminal demo of the assistant.

    wg-ask "Quels clients ont une allocation obligataire superieure a 60 % ?"

Requires a funded ``ANTHROPIC_API_KEY`` -- this is the one WealthGuard
component that costs money to run live, which is why it is kept out of the
GitHub Pages demo and out of the default `docker compose up` stack. See
ARCHITECTURE.md.
"""

from __future__ import annotations

import argparse
import json

from .. import db
from ..config import get_settings
from .nl_query import NaturalLanguageQueryAssistant


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pose une question en langage naturel a WealthGuard")
    parser.add_argument("question")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = db.build_engine(settings.database)
    assistant = NaturalLanguageQueryAssistant(settings.assistant, engine)
    answer = assistant.ask(args.question)

    print(f"SQL : {answer.sql}\n")
    print(json.dumps(answer.rows, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
