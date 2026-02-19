"""
agent/core
==========

The **core** sub-package contains the agent runtime:

- ``agent.py``       — The ADK BaseAgent subclass that drives the Gemini
                       generate-and-call-tool loop.
- ``mcp_registry.py`` — Bridges FastMCP tool definitions into the Gemini
                        FunctionDeclaration format that the LLM understands.
- ``prompt_loader.py`` — Reads the system prompt from ``prompts.md`` so the
                         prompt can be updated without touching code.
"""

from .agent import Agent, create_agent, root_agent  # noqa: F401
