"""
agent/core/agent.py
===================

The heart of the AI agent: the ``Agent`` class that drives the
**Gemini generate-and-call-tool loop**.

Architecture Overview
---------------------
This agent is built on Google ADK's ``BaseAgent``.  The runtime loop works
like this::

    User message
        ↓
    Gemini ``generate_content`` (with tools available)
        ↓ LLM decides: answer directly OR call a tool
    ┌───────────────────┐      ┌──────────────────────────────┐
    │  Text response    │  OR  │  FunctionCall(name, args)     │
    │  → yield Event   │      │  → _execute_tool(name, args)  │
    └───────────────────┘      │  → append FunctionResponse   │
                               │  → re-call generate_content  │
                               └──────────────────────────────┘

This loop repeats until Gemini returns a plain text answer (no function
calls in the response), at which point the final text is yielded as an
ADK ``Event`` back to the caller.

Key Design Decisions
--------------------
- ``temperature=0.0``  — We want deterministic SQL generation and factual
  business answers, not creative hallucinations.
- ``asyncio.to_thread`` — The Gemini SDK's ``generate_content`` is a blocking
  call.  We offload it to a thread-pool to keep the async event loop
  responsive (important inside Vertex AI Reasoning Engine).
- ``_clean_response``  — Strips SQL code fences from the final answer.  The
  system prompt forbids the LLM from showing SQL, but this is a safety net.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncGenerator, Optional

from google import genai
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import Field, PrivateAttr

from ..config import Config
from ..tool_definitions.registry import mcp
from .mcp_registry import build_gemini_tools_from_mcp
from .prompt_loader import load_prompt

logger = logging.getLogger(__name__)

# ── Agent identity constants ─────────────────────────────────────────────────
AGENT_NAME = "snowflake_agent"
AGENT_DESCRIPTION = (
    "Business Intelligence Agent — answers natural-language questions about "
    "Snowflake data and can export insights to Google Sheets."
)
MODEL_NAME = "gemini-2.5-flash"


class Agent(BaseAgent):
    """Snowflake Business Intelligence Agent.

    Inherits from ``google.adk.agents.BaseAgent`` which provides the ADK
    session management, event system, and deployment scaffolding.

    The agent uses the **Gemini** model via ``google.genai.Client``.  Tools
    are registered through **FastMCP** (see ``tool_definitions/``) and
    converted to Gemini ``FunctionDeclaration`` objects at startup.

    Attributes
    ----------
    agent_config:
        Application configuration (Snowflake creds, Google creds, SMTP, etc.).
    model_name:
        Gemini model identifier.
    system_prompt:
        The full system prompt loaded from ``prompts.md``.
    gemini_tools:
        List of ``types.Tool`` objects passed to each ``generate_content`` call.
    _client:
        Lazy-initialised ``genai.Client``.  Not set until first use to allow
        environment variables to be loaded before the client is constructed.
    """

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    agent_config: Config = Field(default=None)
    agent_name: str = Field(default=AGENT_NAME)
    model_name: str = Field(default=MODEL_NAME)
    system_prompt: str = Field(default="")
    gemini_tools: list = Field(default_factory=list)

    # PrivateAttr: Pydantic won't serialise this — it's a live SDK object.
    _client: Optional[genai.Client] = PrivateAttr(default=None)

    def __init__(self, config: Config, name: str = AGENT_NAME, **kwargs):
        """Initialise the agent.

        Loads the system prompt and converts FastMCP tools to Gemini format
        at construction time so startup errors surface immediately.

        Parameters
        ----------
        config:
            Populated ``Config`` instance (typically from ``Config.from_env()``).
        name:
            ADK agent name — used as the ``author`` field on emitted events.
        """
        tools = build_gemini_tools_from_mcp(mcp)
        super().__init__(
            name=name,
            description=kwargs.pop("description", AGENT_DESCRIPTION),
            agent_config=config,
            agent_name=name,
            model_name=MODEL_NAME,
            system_prompt=load_prompt(),
            gemini_tools=tools,
            **kwargs,
        )
        self._client = None

    # ── Gemini client (lazy init) ─────────────────────────────────────────────

    @property
    def client(self) -> genai.Client:
        """Return the Gemini API client, constructing it on first access.

        Auth strategy (in priority order):
        1. ``GOOGLE_API_KEY`` env var  → direct API key auth (local dev)
        2. Vertex AI project/location  → service-account / ADC auth (production)
        """
        if self._client is None:
            if self.agent_config is None:
                self.agent_config = Config.from_env()

            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                self._client = genai.Client(api_key=api_key)
            else:
                project = self.agent_config.google_cloud_project or os.getenv("GOOGLE_CLOUD_PROJECT")
                location = self.agent_config.google_cloud_location or "us-central1"
                self._client = genai.Client(vertexai=True, project=project, location=location)
        return self._client

    # ── Tool execution ────────────────────────────────────────────────────────

    async def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute an MCP tool by name and return the result.

        This method is called each time Gemini emits a ``FunctionCall`` part
        in its response.  It looks the tool up in the FastMCP registry and
        invokes the underlying Python function.

        Parameters
        ----------
        tool_name:
            The name exactly as registered via ``@mcp.tool()``.
        args:
            Keyword arguments extracted from the LLM's ``FunctionCall``.

        Returns
        -------
        dict
            Result dict suitable for wrapping in a ``FunctionResponse``.
        """
        logger.info("Executing tool: %s | args: %s", tool_name, list(args.keys()))
        try:
            tool = await mcp.get_tool(tool_name)
            if tool is None:
                return {"error": f"Unknown tool: {tool_name}"}

            result_str = await tool.fn(**args)

            # FastMCP tool functions always return strings (JSON or plain text).
            # Parse JSON so we return structured data to Gemini when possible.
            try:
                parsed = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                parsed = result_str

            return (
                {"result": parsed}
                if isinstance(parsed, (list, str, int, float, bool, type(None)))
                else parsed
            )

        except Exception as e:
            logger.exception("Error executing tool '%s': %s", tool_name, e)
            return {"error": str(e)}

    # ── History reconstruction ────────────────────────────────────────────────

    def _get_history(self, ctx: InvocationContext) -> list[types.Content]:
        """Reconstruct conversation history from the ADK session.

        ADK stores conversation turns as ``Event`` objects in the session.
        Gemini's ``generate_content`` expects a list of ``types.Content``
        objects.  This method converts between the two formats.

        Multi-turn context is essential for follow-up questions like
        "export that to Google Sheets" — without history Gemini wouldn't know
        what "that" refers to.

        Parameters
        ----------
        ctx:
            The ADK ``InvocationContext`` for the current turn.

        Returns
        -------
        list[types.Content]
            Ordered conversation history (oldest first) ready for the API.
        """
        events = []
        if hasattr(ctx, "session") and ctx.session and hasattr(ctx.session, "events"):
            events = ctx.session.events or []
        elif hasattr(ctx, "history"):
            events = ctx.history or []

        history = []
        for event in events:
            if not event.content:
                continue
            content = None

            if isinstance(event.content, types.Content):
                content = event.content
            elif isinstance(event.content, dict) and "parts" in event.content:
                try:
                    parts = [
                        types.Part(text=p["text"]) if isinstance(p, dict) and "text" in p
                        else types.Part(text=p.text) if hasattr(p, "text") and p.text
                        else None
                        for p in event.content["parts"]
                    ]
                    parts = [p for p in parts if p]
                    if parts:
                        content = types.Content(parts=parts)
                except Exception:
                    pass
            elif isinstance(event.content, str):
                content = types.Content(parts=[types.Part(text=event.content)])

            if content:
                if not content.role:
                    content.role = "model" if event.author == self.name else "user"
                history.append(content)

        return history

    # ── Response cleaning ─────────────────────────────────────────────────────

    def _clean_response(self, text: str) -> str:
        """Strip SQL code fences from the response text.

        The system prompt instructs the LLM to never show raw SQL.  This is a
        safety net that removes any SQL blocks that slip through.

        Parameters
        ----------
        text:
            Raw text from Gemini's response.

        Returns
        -------
        str
            Text with SQL code fences removed and leading/trailing whitespace
            stripped.
        """
        text = re.sub(r'```sql\n.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'```snowflake\n.*?```', '', text, flags=re.DOTALL)
        return text.strip()

    # ── ADK entry point ───────────────────────────────────────────────────────

    async def run_async(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Main agent loop — called by ADK for every user turn.

        Implements the **generate → check for tool calls → execute → repeat**
        pattern:

        1. Reconstruct conversation history.
        2. Append the new user message.
        3. Call Gemini with the system prompt and registered tools.
        4. If the response contains ``FunctionCall`` parts, execute each tool
           and feed the results back to Gemini (step 3).
        5. When Gemini returns a plain text response, yield it as an ADK
           ``Event`` and return.

        Parameters
        ----------
        ctx:
            ADK invocation context carrying the user message, session state,
            and invocation ID.

        Yields
        ------
        Event
            One or more ADK events.  Typically one final text event, but can
            include intermediate events for streaming.
        """
        user_message = (
            ctx.get("user_content") if isinstance(ctx, dict)
            else getattr(ctx, "user_content", None)
        )
        invocation_id = (
            ctx.get("invocation_id") if isinstance(ctx, dict)
            else getattr(ctx, "invocation_id", None)
        )

        logger.info(
            "run_async started | user_message_type=%s | invocation_id=%s",
            type(user_message).__name__,
            invocation_id,
        )

        if not user_message:
            yield Event(
                author=self.name,
                invocation_id=invocation_id,
                content=types.Content(parts=[types.Part(text="Please provide a message.")]),
            )
            return

        # Build the full contents list: [history...] + [current user message]
        contents = self._get_history(ctx)
        if isinstance(user_message, str):
            contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
        else:
            contents.append(user_message)

        # temperature=0 → deterministic answers; important for SQL generation
        gen_config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=self.gemini_tools or None,
            temperature=0.0,
        )

        try:
            # Offload blocking SDK call to thread pool
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=contents,
                config=gen_config,
            )

            # ── Tool-call loop ────────────────────────────────────────────────
            while response.candidates:
                candidate = response.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    break

                func_calls = [p for p in candidate.content.parts if p.function_call]

                if not func_calls:
                    # No tool calls → this is the final text answer
                    text_parts = [p.text for p in candidate.content.parts if p.text]
                    if text_parts:
                        yield Event(
                            author=self.name,
                            invocation_id=invocation_id,
                            content=types.Content(
                                parts=[types.Part(text=self._clean_response("\n".join(text_parts)))]
                            ),
                        )
                    return

                # Append the model's tool-call turn to the conversation
                contents.append(candidate.content)

                # Execute all tool calls in this turn (may be multiple)
                tool_responses = []
                for part in func_calls:
                    fc = part.function_call
                    result = await self._execute_tool(fc.name, dict(fc.args))
                    tool_responses.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fc.name, response=result
                            )
                        )
                    )

                # Feed tool results back and get the next Gemini response
                contents.append(types.Content(role="user", parts=tool_responses))
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=contents,
                    config=gen_config,
                )

            # Yield a no-op event so ADK knows the turn is complete
            yield Event(
                author=self.name,
                invocation_id=invocation_id,
                actions=EventActions(escalate=False),
            )

        except Exception as e:
            logger.error("Error in run_async: %s", e, exc_info=True)
            yield Event(
                author=self.name,
                invocation_id=invocation_id,
                content=types.Content(parts=[types.Part(text=f"An error occurred: {e}")]),
            )


# ── Factory & module-level root_agent ────────────────────────────────────────

def create_agent() -> Agent:
    """Instantiate the agent from environment variables.

    This is the standard entry point used by ``agent/__init__.py`` and
    ``deploy.py``.  All configuration is read from ``.env`` (or the process
    environment).

    Returns
    -------
    Agent
        A fully configured, ready-to-run ``Agent`` instance.
    """
    return Agent(Config.from_env())


# ADK discovers the agent via this module-level variable.
# ``deploy.py`` also imports it directly.
root_agent = create_agent()
