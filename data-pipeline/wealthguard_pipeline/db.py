"""PostgreSQL connection, schema management and bulk loading.

One schema (``wealthguard``), loaded fresh on every pipeline run: this is a
full-refresh batch job (cahier des charges: "Azure Functions, declenchement
planifie, tous les jours a 6h"), not an incremental one, so truncating before
loading is the correct behaviour, not a shortcut.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from .config import DatabaseConfig
from .ingest import Dataset

SCHEMA = "wealthguard"

#: Load order matters: a table can only be loaded after every table its
#: foreign keys point to. market_prices and target_allocations reference
#: instruments and clients respectively but not each other, so either order
#: between them is fine.
_LOAD_ORDER: tuple[str, ...] = (
    "clients",
    "instruments",
    "positions",
    "market_prices",
    "target_allocations",
)


def build_engine(config: DatabaseConfig) -> Engine:
    return create_engine(config.sqlalchemy_url, future=True)


def _sql_resource(filename: str) -> str:
    return importlib.resources.files("wealthguard_pipeline").joinpath("sql", filename).read_text(encoding="utf-8")


def init_schema(engine: Engine) -> None:
    """Create the schema and tables if they do not already exist."""
    schema_sql = _sql_resource("schema.sql")
    with engine.begin() as conn:
        for statement in _split_statements(schema_sql):
            conn.execute(text(statement))


def _split_statements(sql: str) -> list[str]:
    """Strip ``--`` comment lines, then split what remains on top-level ``;``
    -- good enough for our DDL (no stored procedures or dollar-quoted bodies
    containing semicolons).

    Comment lines are stripped *before* splitting, not filtered out
    statement-by-statement afterwards: a statement preceded by a multi-line
    comment block (every table in this file has one) produces a chunk whose
    first line is a comment even though real SQL follows, and checking only
    the chunk's own first line would silently drop the whole statement.
    """
    code_lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(code_lines).split(";") if s.strip()]


def load_dataset(engine: Engine, dataset: Dataset) -> None:
    """Truncate every warehouse table and reload it from ``dataset``.

    Truncated and reloaded in FK-safe order within one transaction: either the
    whole batch lands, or none of it does, so a failure partway through never
    leaves the warehouse half a day's data ahead of another table.
    """
    frames: dict[str, pd.DataFrame] = {
        "clients": dataset.clients,
        "instruments": dataset.instruments,
        "positions": dataset.positions,
        "market_prices": dataset.market_prices,
        "target_allocations": dataset.target_allocations,
    }
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {', '.join(f'{SCHEMA}.{t}' for t in reversed(_LOAD_ORDER))} CASCADE"))
        for table in _LOAD_ORDER:
            frames[table].to_sql(
                table, conn, schema=SCHEMA, if_exists="append", index=False, method="multi", chunksize=1000
            )


def read_sql_file(filename: str, engine: Engine, params: dict) -> pd.DataFrame:
    """Run one packaged ``sql/*.sql`` file and return the result as a DataFrame."""
    sql = _sql_resource(filename)
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def record_run(engine: Engine, run: dict) -> None:
    """Append one row to ``pipeline_runs`` -- the source table for the Grafana
    monitoring dashboard. Unlike :func:`load_dataset`, this never truncates:
    the whole point is a history to plot a trend over.

    ``run`` keys: ``as_of_date``, ``anomaly_count``, ``bloquant_count``,
    ``avertissement_count``, ``info_count``, ``clients_valued``,
    ``total_market_value``, ``duration_ms``.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {SCHEMA}.pipeline_runs "
                "(as_of_date, anomaly_count, bloquant_count, avertissement_count, info_count, "
                " clients_valued, total_market_value, duration_ms) "
                "VALUES (:as_of_date, :anomaly_count, :bloquant_count, :avertissement_count, :info_count, "
                " :clients_valued, :total_market_value, :duration_ms)"
            ),
            run,
        )
