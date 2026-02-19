"""
agent/tool_definitions/discovery_tools.py
==========================================

**[INTERNAL]** Database, schema, and table discovery tools.

Why ``[INTERNAL]``?
-------------------
The ``[INTERNAL]`` prefix in tool names is a convention established in the
agent's system prompt.  It tells the LLM two things:

1. **Don't expose these results directly to the user** — database/schema/
   table names are technical implementation details, not business concepts.
   The agent should use discovery results to *construct queries*, not to
   read out a list of table names.

2. **Use for orientation, not output** — these tools are the equivalent of
   ``SHOW TABLES`` in a SQL client: useful for a developer navigating an
   unfamiliar schema, but not what a business user wants to see in their
   chat window.

These three tools form a discovery hierarchy:
    _list_databases_internal
        └── _list_schemas_internal(database_name)
                └── _list_tables_internal(schema_name)
"""

import logging

from .registry import mcp
from ..tools.formatters import format_as_table
from ..config import Config
from ..tools.toolkit import Toolkit

logger = logging.getLogger(__name__)

_toolkit: Toolkit | None = None


def get_toolkit() -> Toolkit:
    """Return the lazy-initialised Toolkit singleton."""
    global _toolkit
    if _toolkit is None:
        _toolkit = Toolkit(Config.from_env())
    return _toolkit


@mcp.tool()
async def _list_databases_internal() -> str:
    """[INTERNAL] Discover available Snowflake databases.

    Use this internally to find data sources.
    DO NOT show database names to users — use this information to construct
    queries only.

    Returns
    -------
    str
        Markdown table of databases with name, owner, and creation date.
    """
    toolkit = get_toolkit()
    try:
        results = toolkit.snowflake.query("SHOW DATABASES", use_cache=False)
        databases = []
        for row in results:
            created_on = row.get("created_on", row.get("CREATED_ON", ""))
            if hasattr(created_on, "isoformat"):
                created_on = created_on.isoformat()
            databases.append({
                "DATABASE": row.get("name", row.get("NAME", "")),
                "OWNER": row.get("owner", row.get("OWNER", "")),
                "CREATED": str(created_on)[:10] if created_on else "",
            })
        return format_as_table(databases)
    except Exception as e:
        return f"Error listing databases: {e}"


@mcp.tool()
async def _list_schemas_internal(database_name: str = "") -> str:
    """[INTERNAL] Discover available schemas within a Snowflake database.

    Use this internally to explore database structure.
    DO NOT show schema/database names to users — use this to find where data
    lives and then construct targeted queries.

    Parameters
    ----------
    database_name:
        Optional. Limit discovery to schemas inside this database.
        Defaults to the current database context.

    Returns
    -------
    str
        Markdown table of schemas with database, schema name, and creation date.
    """
    toolkit = get_toolkit()
    try:
        query = f"SHOW SCHEMAS IN DATABASE {database_name}" if database_name else "SHOW SCHEMAS"
        results = toolkit.snowflake.query(query, use_cache=False)
        schemas = []
        for row in results:
            created_on = row.get("created_on", row.get("CREATED_ON", ""))
            if hasattr(created_on, "isoformat"):
                created_on = created_on.isoformat()
            db_name = row.get("database_name", row.get("DATABASE_NAME", ""))
            schema_name = row.get("name", row.get("NAME", ""))
            schemas.append({
                "DATABASE": db_name,
                "SCHEMA": f"{db_name}.{schema_name}" if db_name else schema_name,
                "CREATED": str(created_on)[:10] if created_on else "",
            })
        return format_as_table(schemas)
    except Exception as e:
        return f"Error listing schemas: {e}"


@mcp.tool()
async def _list_tables_internal(schema_name: str = "") -> str:
    """[INTERNAL] Discover available tables within a Snowflake schema.

    Use this internally to find what data exists before constructing a query.
    DO NOT show table names to users — use this to explore structure, then
    present results in business terms.

    Parameters
    ----------
    schema_name:
        Optional. Fully-qualified schema (e.g. ``"FINANCIALS.PUBLIC"``).
        Defaults to the current schema context.

    Returns
    -------
    str
        Markdown table of tables with schema, table name, type, and row count.
    """
    toolkit = get_toolkit()
    try:
        query = f"SHOW TABLES IN SCHEMA {schema_name}" if schema_name else "SHOW TABLES"
        results = toolkit.snowflake.query(query, use_cache=False)
        tables = []
        for row in results:
            tables.append({
                "SCHEMA": row.get("schema_name", row.get("SCHEMA_NAME", "")),
                "TABLE": row.get("name", row.get("NAME", "")),
                "TYPE": row.get("kind", row.get("KIND", "TABLE")),
                "ROWS": row.get("rows", row.get("ROWS", 0)),
            })
        return format_as_table(tables)
    except Exception as e:
        return f"Error listing tables: {e}"
