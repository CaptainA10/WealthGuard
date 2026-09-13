"""Portfolio indicators (cahier des charges §2.3): valorisation totale,
allocation par classe d'actif, performance par client, plus-values latentes.

Each function runs one packaged, hand-written SQL query (joins, CTEs, window
functions -- see ``sql/*.sql``) against the warehouse; none of this recomputes
in pandas what PostgreSQL already does set-at-a-time.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import Engine

from . import db


def portfolio_valuation(engine: Engine, as_of: date) -> pd.DataFrame:
    """Per client: total cost basis, total market value, unrealized gain (amount and %)."""
    return db.read_sql_file("portfolio_valuation.sql", engine, {"as_of_date": as_of})


def allocation_vs_target(engine: Engine, as_of: date) -> pd.DataFrame:
    """Per client and asset class: actual weight, target weight, and the gap."""
    return db.read_sql_file("allocation_vs_target.sql", engine, {"as_of_date": as_of})


def top_holdings(engine: Engine, as_of: date, top_n: int = 3) -> pd.DataFrame:
    """The ``top_n`` largest lines of every client's portfolio by market value."""
    return db.read_sql_file("top_holdings.sql", engine, {"as_of_date": as_of, "top_n": top_n})
