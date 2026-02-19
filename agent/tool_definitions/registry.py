"""
agent/tool_definitions/registry.py
====================================

Single ``FastMCP`` server instance shared across all tool definition modules.

How FastMCP Works
-----------------
``FastMCP`` is a lightweight Python library that simplifies building MCP
(Model Context Protocol) tool servers.  Here's what it does for us:

1. **Automatic JSON Schema** — When you decorate a Python function with
   ``@mcp.tool()``, FastMCP inspects the function's type hints and docstring
   to **automatically build the JSON Schema** that describes the tool's
   parameters.  You don't write a single line of JSON.

2. **Tool Registry** — FastMCP maintains an internal registry of all
   decorated tools.  ``agent/core/mcp_registry.py`` reads this registry to
   convert the tools into Gemini ``FunctionDeclaration`` objects.

3. **Singleton Pattern** — There is exactly **one** ``mcp`` instance.  All
   tool modules import it from here and use the same ``@mcp.tool()`` decorator.
   This ensures all tools are registered in the same server.

Why not one big file?
---------------------
Splitting tools into domain files (``query_tools``, ``sheets_tools``, etc.)
keeps each file focused and easy to read.  The imports below ensure all tool
decorators run at startup, registering every tool on this single ``mcp``
instance.
"""

from fastmcp import FastMCP

# The central MCP server.  All @mcp.tool() decorators register on this object.
mcp = FastMCP("Snowflake BI Agent")

# ── Import all tool modules to trigger @mcp.tool() registration ──────────────
# The order of imports doesn't matter for correctness; all tools end up in the
# same registry.  We import here (rather than in __init__.py) so that this
# module fully initialises before any consumer reads ``mcp``.
from . import query_tools      # noqa: E402, F401
from . import discovery_tools  # noqa: E402, F401
from . import sheets_tools     # noqa: E402, F401
from . import email_tools      # noqa: E402, F401
