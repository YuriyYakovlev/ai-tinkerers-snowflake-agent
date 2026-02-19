"""
agent/__init__.py
=================

Entry point for the Agent package.

This module re-exports ``root_agent`` — the fully configured agent instance —
so that Google ADK and ``deploy.py`` can discover it with a simple import::

    from agent import root_agent

ADK looks for a module-level ``root_agent`` variable to identify the agent
when running ``adk web`` or deploying to Vertex AI Reasoning Engine.
The actual agent logic lives in ``agent.core.agent``.
"""

from .core.agent import Agent, create_agent, root_agent  # noqa: F401

__all__ = ["root_agent", "create_agent", "Agent"]
