"""Natural-language querying assistant (cahier des charges §2.4): "Quels
clients ont une allocation obligataire superieure a 60 % ?" -> generated SQL
-> rows.

Deliberately not `langchain_experimental.sql`'s ready-made SQL chain: that
executes whatever the model produced with no independent check, which is
exactly what the cahier des charges asks *not* to do ("securiser
l'execution des requetes generees"). This module keeps LangChain to what it
is good at -- prompting a chat model and parsing its text output -- and
routes every result through :mod:`security` before it ever reaches
PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from sqlalchemy import Engine, text

from ..config import AssistantConfig
from . import security

#: Kept in sync by hand with data-pipeline/wealthguard_pipeline/sql/schema.sql
#: -- there are only five tables, and generating this from the schema file
#: would be more machinery than the problem warrants.
SCHEMA_DESCRIPTION = """
Schema PostgreSQL "wealthguard" :

clients(client_id TEXT, full_name TEXT, risk_profile TEXT, reference_currency TEXT, onboarding_date DATE, advisor TEXT)
instruments(ticker TEXT, name TEXT, instrument_type TEXT, asset_class TEXT, currency TEXT, exchange TEXT)
positions(position_id TEXT, client_id TEXT, ticker TEXT, quantity NUMERIC, purchase_price NUMERIC, purchase_date DATE, currency TEXT)
market_prices(ticker TEXT, price_date DATE, close_price NUMERIC, currency TEXT, price_source TEXT)
target_allocations(client_id TEXT, asset_class TEXT, target_weight_pct NUMERIC)

Valeurs possibles de asset_class : ACTIONS, OBLIGATIONS, MATIERES_PREMIERES, IMMOBILIER.
Valeurs possibles de risk_profile : PRUDENT, EQUILIBRE, DYNAMIQUE, OFFENSIF.
""".strip()

SYSTEM_PROMPT = f"""Tu es un generateur de requetes SQL PostgreSQL en lecture seule pour WealthGuard, \
une plateforme de gestion de patrimoine.

{SCHEMA_DESCRIPTION}

Regles strictes, sans exception :
- Reponds UNIQUEMENT avec la requete SQL. Pas d'explication, pas de balises markdown.
- Une seule instruction, SELECT ou WITH ... SELECT. Jamais INSERT/UPDATE/DELETE/DDL.
- N'utilise que les tables listees ci-dessus, sans prefixe de schema.
- N'invente jamais une colonne ou une table absente du schema ci-dessus."""


@dataclass(frozen=True)
class AssistantAnswer:
    question: str
    sql: str
    columns: list[str]
    rows: list[dict]


class NaturalLanguageQueryAssistant:
    """Turns a French question into a validated, executed, read-only query.

    ``chain`` is injectable (any LangChain ``Runnable`` whose ``invoke``
    takes ``{"question": str}`` and returns a SQL string) specifically so
    tests can supply a fake chain and never call a paid LLM API -- see
    ``tests/test_assistant_nl_query.py``.
    """

    def __init__(self, config: AssistantConfig, engine: Engine, chain: Runnable | None = None):
        self._config = config
        self._engine = engine
        self._chain = chain if chain is not None else self._build_chain(config)

    @staticmethod
    def _build_chain(config: AssistantConfig) -> Runnable:
        # Imported lazily: langchain-anthropic is an optional extra, and a
        # caller supplying their own `chain` should not need it installed.
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(model=config.model, api_key=config.api_key, temperature=0)
        prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM_PROMPT), ("human", "{question}")]
        )
        return prompt | llm | StrOutputParser()

    def ask(self, question: str) -> AssistantAnswer:
        """Generate SQL for ``question``, validate it, run it, return the rows.

        Raises :class:`security.QueryValidationError` if the generated SQL
        fails the safety gate -- the caller decides how to surface that
        (see ``api.py``'s HTTP 422 mapping).
        """
        raw_sql = self._chain.invoke({"question": question})
        sql = security.validate_and_prepare(
            raw_sql, allowed_tables=security.ALLOWED_TABLES, max_rows=self._config.max_rows
        )
        columns, rows = self._execute_read_only(sql)
        return AssistantAnswer(question=question, sql=sql, columns=columns, rows=rows)

    def _execute_read_only(self, sql: str) -> tuple[list[str], list[dict]]:
        """Run ``sql`` in a Postgres READ ONLY transaction with a statement
        timeout -- the second, independent layer behind ``security``'s
        whitelist: even a gap in that regex-based check cannot become a
        write or a runaway query here."""
        with self._engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SET TRANSACTION READ ONLY"))
                conn.execute(text(f"SET LOCAL statement_timeout = {self._config.statement_timeout_ms}"))
                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
        return columns, rows
