"""Read-only, table-whitelisted safety gate for LLM-generated SQL.

Cahier des charges §2.4: "Securiser l'execution des requetes generees
(whitelist de tables/colonnes, requetes en lecture seule uniquement)".

A prompt instruction ("only ever write SELECT") is not a security boundary:
a language model can be prompted around, and even an honest model can slip
on a complex question. Every query this assistant generates passes through
:func:`validate_and_prepare` regardless of what the model was told, and the
connection that finally executes it opens a Postgres ``READ ONLY``
transaction on top (see ``nl_query.py``) as an independent second layer --
so a gap in this regex-based check is still not a write.

**Scope, honestly stated.** Table-level whitelisting here is strict: every
``FROM``/``JOIN`` target is checked against an explicit allow-list, and an
unrecognised one is rejected outright. Column-level whitelisting is not
independently enforced by this module -- doing that correctly needs a real
SQL parser, not a regex, and a false sense of column-level safety would be
worse than an honest gap. The column boundary that exists is the model's
system prompt (the schema it is told about) plus the fact that unknown
*tables* -- which is how one would actually reach a column outside the
schema, e.g. a system catalog -- are already rejected.
"""

from __future__ import annotations

import re

ALLOWED_TABLES = frozenset(
    {"clients", "instruments", "positions", "market_prices", "target_allocations"}
)

#: Any of these appearing as a standalone SQL keyword anywhere in the query is
#: an instant rejection -- deliberately broader than "not a SELECT", since a
#: CTE or subquery could otherwise smuggle a write past a naive check that
#: only inspects the first keyword.
_FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "copy", "call", "execute", "vacuum", "merge",
    "into", "comment", "listen", "notify", "lock", "reindex", "refresh",
)
_FORBIDDEN_PATTERN = re.compile(r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE)

_LEADING_KEYWORD_PATTERN = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

#: A table name after FROM/JOIN, optionally schema-qualified
#: ("wealthguard.positions") or double-quoted.
_TABLE_REFERENCE_PATTERN = re.compile(
    r"\b(?:from|join)\s+(?:\"?wealthguard\"?\.)?\"?([a-zA-Z_][a-zA-Z0-9_]*)\"?", re.IGNORECASE
)

#: A CTE name declared by `WITH name AS (` or a subsequent `, name AS (` --
#: these are legitimate FROM/JOIN targets in the rest of the query even
#: though they are not real tables, so they must not be rejected as unknown.
#: `\b` is applied only around "with", not around ",": a comma is often
#: preceded by another non-word character (e.g. the ")" closing the previous
#: CTE's body), and `\b` never matches between two non-word characters.
_CTE_NAME_PATTERN = re.compile(
    r"(?:\bwith\b|,)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", re.IGNORECASE
)

_LIMIT_PATTERN = re.compile(r"\blimit\s+\d+", re.IGNORECASE)

#: Strip a ```sql ... ``` (or bare ```...```) fence a chat model wraps the
#: query in despite being told not to -- a formatting quirk, not a security
#: concern, but leaving it in would make every query fail the leading-keyword
#: check.
_CODE_FENCE_PATTERN = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class QueryValidationError(ValueError):
    """The generated SQL failed the safety gate and was never executed."""


def validate_and_prepare(
    sql: str, *, allowed_tables: frozenset[str] = ALLOWED_TABLES, max_rows: int
) -> str:
    """Return a safe-to-execute version of ``sql``, or raise ``QueryValidationError``.

    Fails closed: an unrecognised table reference, a stray semicolon
    suggesting a second statement, or any forbidden keyword anywhere in the
    text all reject the query rather than trying to sanitise it.
    """
    candidate = _CODE_FENCE_PATTERN.sub("", sql).strip()
    if not candidate:
        raise QueryValidationError("La requete generee est vide.")

    if candidate.endswith(";"):
        candidate = candidate[:-1].strip()
    if ";" in candidate:
        raise QueryValidationError("Une seule instruction est autorisee par requete.")

    if not _LEADING_KEYWORD_PATTERN.match(candidate):
        raise QueryValidationError(
            "Seules les requetes SELECT (ou WITH ... SELECT) sont autorisees."
        )

    forbidden = _FORBIDDEN_PATTERN.search(candidate)
    if forbidden:
        raise QueryValidationError(f"Mot-cle interdit dans la requete : '{forbidden.group(1)}'.")

    referenced = {m.group(1).lower() for m in _TABLE_REFERENCE_PATTERN.finditer(candidate)}
    if not referenced:
        raise QueryValidationError("Aucune table reconnue dans la requete (FROM/JOIN attendu).")
    cte_names = {m.group(1).lower() for m in _CTE_NAME_PATTERN.finditer(candidate)}
    unknown = referenced - allowed_tables - cte_names
    if unknown:
        raise QueryValidationError(
            f"Table(s) non autorisee(s) : {sorted(unknown)}. "
            f"Tables autorisees : {sorted(allowed_tables)}."
        )

    if not _LIMIT_PATTERN.search(candidate):
        candidate = f"{candidate} LIMIT {max_rows}"

    return candidate
