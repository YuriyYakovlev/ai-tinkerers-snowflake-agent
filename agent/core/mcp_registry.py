"""
mcp_registry.py
===============

Bridges the **MCP (Model Context Protocol)** tool registry into the format
that the **Gemini API** expects.

Background: MCP vs. Gemini tool format
---------------------------------------
- FastMCP stores tools as Python callables with Pydantic-inferred JSON schemas.
- Gemini's ``generate_content`` API accepts tools as ``FunctionDeclaration``
  objects with a specific subset of JSON Schema.

This module performs the translation:

    FastMCP tool registry
        ↓  ``build_gemini_tools_from_mcp()``
    List[types.FunctionDeclaration]
        ↓  wrapped in types.Tool
    Passed to ``GenerateContentConfig.tools``

Why ``sanitize_schema``?
------------------------
Gemini rejects certain JSON Schema keywords (``additionalProperties``,
top-level ``title``).  ``sanitize_schema`` strips these before sending the
schema to the API, making the translation lossless for everything the LLM
actually needs.

Private registry access
-----------------------
The fastest path to the tool map is via ``mcp._tool_manager._tools``.  This
accesses a private attribute, which is intentional — FastMCP doesn't expose a
synchronous public API.  We fall back to the async public ``mcp.get_tools()``
if the private attribute is not available in a future FastMCP version.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)


def sanitize_schema(schema: dict[str, Any], is_root: bool = True) -> dict[str, Any]:
    """Recursively strip JSON Schema keywords that Gemini does not support.

    Gemini rejects:
    - ``additionalProperties`` — not part of Gemini's supported subset
    - Top-level ``title`` — redundant because the function name serves as the title

    Parameters
    ----------
    schema:
        The raw JSON Schema dict produced by FastMCP / Pydantic.
    is_root:
        ``True`` when processing the top-level schema object (strips ``title``).
        Set to ``False`` for recursive calls on nested properties.

    Returns
    -------
    dict
        A cleaned copy of the schema safe for Gemini.
    """
    if not isinstance(schema, dict):
        return schema

    clean = {}
    for key, value in schema.items():
        # Strip keywords Gemini rejects
        if key == "additionalProperties":
            continue
        if is_root and key == "title":
            continue

        # Recurse into nested dicts
        if isinstance(value, dict):
            clean[key] = (
                {k: sanitize_schema(v, is_root=False) for k, v in value.items()}
                if key == "properties"
                else sanitize_schema(value, is_root=False)
            )
        elif isinstance(value, list):
            clean[key] = [
                sanitize_schema(i, is_root=False) if isinstance(i, dict) else i
                for i in value
            ]
        else:
            clean[key] = value

    return clean


def build_gemini_tools_from_mcp(mcp) -> list[types.Tool]:
    """Convert all registered FastMCP tools into Gemini ``FunctionDeclaration`` objects.

    This function is the MCP → Gemini bridge.  It reads the tool registry from
    the FastMCP server instance and converts each tool into the format Gemini
    expects, so the LLM can discover and call them.

    Parameters
    ----------
    mcp:
        The ``FastMCP`` server instance (from ``tool_definitions.registry``).

    Returns
    -------
    list[types.Tool]
        A single-element list containing a ``types.Tool`` with all
        ``FunctionDeclaration`` objects, or an empty list on failure.

    Raises
    ------
    Does not raise — all errors are caught and logged so the agent can still
    start even if tool loading fails for a subset of tools.
    """
    if mcp is None:
        logger.error("FastMCP instance is None — cannot build tools.")
        return []

    tools_map = {}

    # ── Fast path: access the private tool manager (synchronous, no event loop needed)
    try:
        tools_map = mcp._tool_manager._tools
    except AttributeError:
        # ── Slow path: use the public async API if private access is unavailable
        # (guards against future FastMCP API changes)
        logger.debug("Private _tool_manager not found — falling back to async get_tools()")

        async def _get():
            return await mcp.get_tools()

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # We're inside a running event loop (e.g. Jupyter, ADK).
                # asyncio.run() would deadlock, so we spin up a thread.
                with ThreadPoolExecutor() as pool:
                    tools_map = pool.submit(asyncio.run, _get()).result()
            else:
                tools_map = asyncio.run(_get())
        except Exception as e:
            logger.error("Failed to load MCP tools via async API: %s", e)
            return []

    if not tools_map:
        logger.warning("No MCP tools found in registry.")
        return []

    declarations = []
    for name, tool in tools_map.items():
        try:
            declarations.append(
                types.FunctionDeclaration(
                    name=name,
                    description=tool.description,
                    # sanitize_schema makes the Pydantic-generated schema Gemini-safe
                    parameters=sanitize_schema(tool.parameters),
                )
            )
        except Exception as e:
            logger.error("Failed to convert tool '%s' to FunctionDeclaration: %s", name, e)

    if not declarations:
        logger.warning("All tool conversions failed — no FunctionDeclarations built.")
        return []

    logger.info("Successfully registered %d MCP tools with Gemini.", len(declarations))
    return [types.Tool(function_declarations=declarations)]
