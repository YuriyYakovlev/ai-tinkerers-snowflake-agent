"""AI Agent - MCP Architecture"""

import json
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from google import genai
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import PrivateAttr, Field

from .config import Config
from .tools import Toolkit
from .tool_definitions import mcp

PROMPT_PATH = Path(__file__).parent / "prompts.md"
AGENT_NAME = "snowflake_agent"
AGENT_DESCRIPTION = "AI agent for Snowflake and Google Sheets integration"
MODEL_NAME = "gemini-2.5-flash"

def load_prompt() -> str:
    try:
        return PROMPT_PATH.read_text()
    except FileNotFoundError:
        return "You are a helpful assistant."


def sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove unsupported fields from JSON schema for Gemini compatibility."""
    if not isinstance(schema, dict):
        return schema
        
    clean_schema = {}
    for key, value in schema.items():
        if key in ("additionalProperties", "title"):
            continue
            
        if isinstance(value, dict):
            clean_schema[key] = sanitize_schema(value)
        elif isinstance(value, list):
            clean_schema[key] = [sanitize_schema(item) if isinstance(item, dict) else item for item in value]
        else:
            clean_schema[key] = value
            
    return clean_schema

def build_gemini_tools_from_mcp() -> list[types.Tool]:
    """Convert FastMCP tools to Gemini function declarations."""
    tools_map = mcp._tool_manager._tools
    
    declarations = [
        types.FunctionDeclaration(
            name=name,
            description=tool.description,
            parameters=sanitize_schema(tool.parameters),
        )
        for name, tool in tools_map.items()
    ]
    
    return [types.Tool(function_declarations=declarations)]

class Agent(BaseAgent):
    """Snowflake AI Agent using MCP architecture."""

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    agent_config: Config = Field(default=None)
    toolkit: Optional[Toolkit] = Field(default=None)
    agent_name: str = Field(default=AGENT_NAME)
    model_name: str = Field(default=MODEL_NAME)
    system_prompt: str = Field(default="")
    gemini_tools: list = Field(default_factory=list)
    _client: Optional[genai.Client] = PrivateAttr(default=None)

    def __init__(self, config: Config, name: str = AGENT_NAME, **kwargs):
        super().__init__(
            name=name,
            description=kwargs.pop("description", AGENT_DESCRIPTION),
            agent_config=config,
            agent_name=name,
            model_name=MODEL_NAME,
            system_prompt=load_prompt(),
            gemini_tools=build_gemini_tools_from_mcp(),
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
        """Execute a tool with MCP-style error handling."""
        if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
             tools_map = mcp._tool_manager._tools
        else:
             tools_map = {}

        if tool_name not in tools_map:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            tool_func = tools_map[tool_name].fn
            # Google GenAI SDK handles argument parsing
            result_str = await tool_func(**args)
            
            try:
                parsed_result = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                parsed_result = result_str
                
            # Gemini expects a dictionary for FunctionResponse
            if isinstance(parsed_result, (list, str, int, float, bool, type(None))):
                return {"result": parsed_result}
            return parsed_result
                
        except Exception as e:
            return {"error": str(e), "tool": tool_name}

    def _get_history(self, ctx: InvocationContext) -> list[types.Content]:
        history = []
        events = []
        if hasattr(ctx, "session") and ctx.session and hasattr(ctx.session, "events"):
            events = ctx.session.events or []
        elif hasattr(ctx, "history"):
            events = ctx.history or []
        
        if not events:
            return history

        for event in events:
            if not event.content:
                continue

            content = None
            if isinstance(event.content, types.Content):
                content = event.content
            elif isinstance(event.content, dict):
                 try:
                    if "parts" in event.content:
                        parts = []
                        for part in event.content["parts"]:
                            if isinstance(part, dict):
                                if "text" in part:
                                    parts.append(types.Part(text=part["text"]))
                            elif hasattr(part, "text") and part.text:
                                parts.append(types.Part(text=part.text))
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

    async def run_async(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        user_message = ctx.user_content
        if not user_message:
            yield Event(
                author=self.name,
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
            tools=self.gemini_tools,
            temperature=0.7,
        )

        response = self.client.models.generate_content(
            model=self.model_name, contents=contents, config=gen_config
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
                        content=types.Content(parts=[types.Part(text="\n".join(text_parts))]),
                    )
                break

            contents.append(candidate.content)
            responses = []
            for part in func_calls:
                fc = part.function_call
                result = await self._execute_tool(fc.name, dict(fc.args))
                responses.append(types.Part(
                    function_response=types.FunctionResponse(name=fc.name, response=result)
                ))

            contents.append(types.Content(role="user", parts=responses))
            response = self.client.models.generate_content(
                model=self.model_name, contents=contents, config=gen_config
            )

        yield Event(author=self.name, actions=EventActions(escalate=False))

def create_agent() -> Agent:
    return Agent(Config.from_env())

root_agent = create_agent()
