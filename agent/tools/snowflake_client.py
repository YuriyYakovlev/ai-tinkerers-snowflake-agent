"""
agent/tools/snowflake_client.py
================================

Snowflake connectivity and query execution.

Connection Strategy
-------------------
The client uses a **lazy connection** pattern: the Snowflake connector is not
instantiated until the first query is made.  This avoids failing at import time
if credentials are missing, giving the agent a chance to start and surface a
helpful error message on first use instead.

Cursor Lifecycle
----------------
Each call to ``query()`` opens a new cursor, executes the SQL, fetches all
results into memory, and closes the cursor.  This is safe for the read-heavy
workload of a BI agent and avoids leaving open cursors that could exhaust the
connection's resources.
"""

import logging
from typing import Any, Dict, List

import snowflake.connector

from ..config import Config

logger = logging.getLogger(__name__)


class SnowflakeClient:
    """Manages a single Snowflake connection and executes SQL queries.

    Parameters
    ----------
    config:
        Populated ``Config`` instance with all ``SNOWFLAKE_*`` credentials.

    Attributes
    ----------
    last_executed_query:
        Stores the most recently executed SQL string.  Used by
        ``replicate_data_to_sheet`` when the agent wants to re-use the last
        query without the user repeating themselves.
    """

    def __init__(self, config: Config):
        self.config = config
        self._conn = None
        self.last_executed_query: str | None = None

    def connect(self) -> snowflake.connector.SnowflakeConnection:
        """Open (or return the existing) Snowflake connection.

        The connection is reused across multiple queries within the same agent
        session, avoiding repeated authentication round-trips.

        Returns
        -------
        SnowflakeConnection
            An authenticated, open Snowflake connection.

        Raises
        ------
        snowflake.connector.errors.Error
            If the credentials are invalid or the network is unreachable.
        """
        if not self._conn:
            logger.info("Opening Snowflake connection to account: %s", self.config.snowflake_account)
            self._conn = snowflake.connector.connect(
                user=self.config.snowflake_user,
                password=self.config.snowflake_password,
                account=self.config.snowflake_account,
                warehouse=self.config.snowflake_warehouse,
                database=self.config.snowflake_database,
                schema=self.config.snowflake_schema,
                role=self.config.snowflake_role,
            )
        return self._conn

    def query(self, sql: str, use_cache: bool = False) -> List[Dict[str, Any]]:
        """Execute a SQL statement and return all rows as a list of dicts.

        Parameters
        ----------
        sql:
            Valid Snowflake SQL string.
        use_cache:
            Presently unused — reserved for future result-caching support.
            Snowflake itself caches query results for 24 h by default.

        Returns
        -------
        List[Dict[str, Any]]
            Each element is a row dict with column-name keys.  Column names
            are taken from ``cursor.description`` and preserve the
            original case from the schema.

        Raises
        ------
        snowflake.connector.errors.ProgrammingError
            On SQL syntax errors or missing objects.
        snowflake.connector.errors.DatabaseError
            On connection or warehouse issues.
        """
        conn = self.connect()
        cursor = conn.cursor()
        try:
            logger.debug("Executing SQL: %.200s", sql)
            cursor.execute(sql)
            columns = [col[0] for col in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            self.last_executed_query = sql
            logger.info("Query returned %d rows.", len(results))
            return results
        finally:
            cursor.close()

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Return column metadata for a table using ``SHOW COLUMNS IN``.

        Parameters
        ----------
        table_name:
            Fully qualified table name (e.g. ``"SCHEMA.TABLE"``).

        Returns
        -------
        List[Dict[str, Any]]
            One dict per column with metadata fields from Snowflake.
        """
        return self.query(f"SHOW COLUMNS IN {table_name}")

    def explain_query(self, sql: str) -> str:
        """Return the Snowflake query execution plan as a Markdown table.

        Useful for debugging slow queries or understanding how Snowflake
        plans to process a complex join.

        Parameters
        ----------
        sql:
            SQL query to explain.

        Returns
        -------
        str
            Markdown table of the execution plan steps.
        """
        from .formatters import format_as_table
        results = self.query(f"EXPLAIN {sql}")
        return format_as_table(results)
