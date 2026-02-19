"""
agent/tools
===========

The **tools** sub-package contains all infrastructure clients and shared
utilities.  Nothing in this package is visible to the LLM directly — these
are the *internal* building blocks that the MCP tool functions (in
``tool_definitions/``) use.

Modules
-------
- ``snowflake_client.py``  — Snowflake connection and query execution.
- ``sheets_client.py``     — Google Sheets + Drive API wrappers.
- ``resource_manager.py``  — Alias → Sheet-ID persistence (resources.json).
- ``error_handler.py``     — Pattern-matched, user-friendly error formatting.
- ``toolkit.py``           — Dependency-injection container that wires all
                             clients together and passes them to tool functions.
- ``formatters.py``        — Shared output formatting helpers (e.g. Markdown
                             tables from query results).
"""

from .toolkit import Toolkit  # noqa: F401
from .formatters import format_as_table  # noqa: F401
