"""
agent/tool_definitions
======================

This sub-package contains every **MCP tool** that the LLM can invoke.

How tools work
--------------
1. ``registry.py`` creates a single ``FastMCP`` server instance (``mcp``).
2. Each domain module (``query_tools``, ``discovery_tools``, etc.) imports
   ``mcp`` from ``registry`` and decorates functions with ``@mcp.tool()``.
   The decorator registers the function's name, docstring, and Pydantic-inferred
   parameter schema with the FastMCP server — no manual JSON schema required.
3. ``agent/core/mcp_registry.py`` iterates the FastMCP tool registry and
   converts each entry into a Gemini ``FunctionDeclaration`` so the LLM can
   discover and invoke them.

Tool categories
---------------
- ``query_tools.py``     — Deterministic (hardcoded SQL) + Generative (Text-to-SQL)
- ``discovery_tools.py`` — Internal database/schema/table discovery
- ``sheets_tools.py``    — Google Sheets create, read, write, chart, alias
- ``email_tools.py``     — Email campaign execution
"""

from .registry import mcp  # noqa: F401
