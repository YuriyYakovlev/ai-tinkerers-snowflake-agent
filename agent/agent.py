import json
import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from google import genai
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import PrivateAttr, Field

from .config import Config
from .tool_definitions import mcp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts.md"
AGENT_NAME = "snowflake_agent"
AGENT_DESCRIPTION = "AI agent for Snowflake and Google Sheets integration"
MODEL_NAME = "gemini-2.5-flash"


def load_prompt() -> str:
    try:
        return PROMPT_PATH.read_text()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found at {PROMPT_PATH}")
        return "You are a helpful assistant."


def sanitize_schema(schema: dict[str, Any], is_root: bool = True) -> dict[str, Any]:
    """Remove fields unsupported by Gemini from a JSON schema."""
    if not isinstance(schema, dict):
        return schema

    clean = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            continue
        if is_root and key == "title":
            continue

        if isinstance(value, dict):
            clean[key] = (
                {k: sanitize_schema(v, is_root=False) for k, v in value.items()}
                if key == "properties"
                else sanitize_schema(value, is_root=False)
            )
        elif isinstance(value, list):
            clean[key] = [sanitize_schema(i, is_root=False) if isinstance(i, dict) else i for i in value]
        else:
            clean[key] = value

    return clean


def build_gemini_tools_from_mcp() -> list[types.Tool]:
    """Build Gemini FunctionDeclarations from FastMCP tools."""
    if mcp is None:
        logger.error("FastMCP instance is None")
        return []

    tools_map = {}

    # Try fast synchronous private access first; fall back to async public API
    try:
        tools_map = mcp._tool_manager._tools
    except AttributeError:
        async def _get():
            return await mcp.get_tools()

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with ThreadPoolExecutor() as pool:
                    tools_map = pool.submit(asyncio.run, _get()).result()
            else:
                tools_map = asyncio.run(_get())
        except Exception as e:
            logger.error(f"Failed to load MCP tools: {e}")
            return []

    if not tools_map:
        logger.warning("No MCP tools found")
        return []

    declarations = []
    for name, tool in tools_map.items():
        try:
            declarations.append(
                types.FunctionDeclaration(
                    name=name,
                    description=tool.description,
                    parameters=sanitize_schema(tool.parameters),
                )
            )
        except Exception as e:
            logger.error(f"Failed to convert tool '{name}': {e}")

    if not declarations:
        return []

    logger.info(f"Loaded {len(declarations)} MCP tools")
    return [types.Tool(function_declarations=declarations)]


class Agent(BaseAgent):
    """Snowflake AI Agent."""

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    agent_config: Config = Field(default=None)
    agent_name: str = Field(default=AGENT_NAME)
    model_name: str = Field(default=MODEL_NAME)
    system_prompt: str = Field(default="")
    gemini_tools: list = Field(default_factory=list)
    _client: Optional[genai.Client] = PrivateAttr(default=None)

    def __init__(self, config: Config, name: str = AGENT_NAME, **kwargs):
        tools = build_gemini_tools_from_mcp()
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

    @property
    def client(self) -> genai.Client:
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

    async def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Executing tool: {tool_name}")
        try:
            try:
                tool = await mcp.get_tool(tool_name)
            except Exception as e:
                logger.error(f"Tool lookup failed for '{tool_name}': {e}")
                return {"error": f"Unknown tool: {tool_name}"}

            if tool is None:
                return {"error": f"Unknown tool: {tool_name}"}

            result_str = await tool.fn(**args)

            try:
                parsed = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                parsed = result_str

            return {"result": parsed} if isinstance(parsed, (list, str, int, float, bool, type(None))) else parsed

        except Exception as e:
            logger.exception(f"Error executing tool '{tool_name}': {e}")
            return {"error": str(e)}

    def _get_history(self, ctx: InvocationContext) -> list[types.Content]:
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

    def _clean_response(self, text: str) -> str:
        """Strip SQL code blocks from response text."""
        import re
        text = re.sub(r'```sql\n.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'```snowflake\n.*?```', '', text, flags=re.DOTALL)
        return text.strip()

    async def run_async(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        user_message = ctx.get("user_content") if isinstance(ctx, dict) else getattr(ctx, "user_content", None)
        invocation_id = ctx.get("invocation_id") if isinstance(ctx, dict) else getattr(ctx, "invocation_id", None)

        logger.info(f"run_async: user_message type={type(user_message).__name__}, invocation_id={invocation_id}")

        if not user_message:
            yield Event(
                author=self.name,
                invocation_id=invocation_id,
                content=types.Content(parts=[types.Part(text="Please provide a message.")]),
            )
            return

        contents = self._get_history(ctx)
        if isinstance(user_message, str):
            contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
        else:
            contents.append(user_message)

        gen_config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=self.gemini_tools or None,
            temperature=0.0,
        )

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=contents,
                config=gen_config,
            )

            while response.candidates:
                candidate = response.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    break

                func_calls = [p for p in candidate.content.parts if p.function_call]

                if not func_calls:
                    text_parts = [p.text for p in candidate.content.parts if p.text]
                    if text_parts:
                        yield Event(
                            author=self.name,
                            invocation_id=invocation_id,
                            content=types.Content(parts=[types.Part(text=self._clean_response("\n".join(text_parts)))]),
                        )
                    return

                contents.append(candidate.content)

                tool_responses = []
                for part in func_calls:
                    fc = part.function_call
                    result = await self._execute_tool(fc.name, dict(fc.args))
                    tool_responses.append(types.Part(
                        function_response=types.FunctionResponse(name=fc.name, response=result)
                    ))

                contents.append(types.Content(role="user", parts=tool_responses))
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=contents,
                    config=gen_config,
                )

            yield Event(author=self.name, invocation_id=invocation_id, actions=EventActions(escalate=False))

        except Exception as e:
            logger.error(f"Error in run_async: {e}", exc_info=True)
            yield Event(
                author=self.name,
                invocation_id=invocation_id,
                content=types.Content(parts=[types.Part(text=f"An error occurred: {e}")]),
            )


def create_agent() -> Agent:
    return Agent(Config.from_env())


root_agent = create_agent()
