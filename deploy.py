import os
import sys

from dotenv import load_dotenv
import vertexai
from vertexai import agent_engines
from agent.agent import root_agent

load_dotenv()

PROJECT_ID = "z-agentspace-trial"
LOCATION = "us-central1"
STAGING_BUCKET = "gs://z-agentspace-trial-reasoning-engine"
REASONING_ENGINE_NAME = os.getenv("REASONING_ENGINE_NAME")

REQUIREMENTS = [
    "google-cloud-aiplatform[adk,agent_engines]==1.129.0",
    "google-adk[mcp]==1.20.0",
    "google-genai>=1.0.0",
    "mcp>=1.0.0",
    "snowflake-connector-python[pandas]>=3.15.0",
    "python-dotenv",
    "google-api-python-client>=2.0.0",
    "google-auth>=2.0.0",
    "google-auth-oauthlib>=1.0.0",
    "fastmcp>=2.14.3",
    "pydantic>=2.0.0",
]

ENV_VARS = {
    "SNOWFLAKE_ACCOUNT": os.getenv("SNOWFLAKE_ACCOUNT"),
    "SNOWFLAKE_USER": os.getenv("SNOWFLAKE_USER"),
    "SNOWFLAKE_PASSWORD": os.getenv("SNOWFLAKE_PASSWORD"),
    "SNOWFLAKE_ROLE": os.getenv("SNOWFLAKE_ROLE"),
    "SNOWFLAKE_WAREHOUSE": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "SNOWFLAKE_DATABASE": os.getenv("SNOWFLAKE_DATABASE"),
    "SNOWFLAKE_SCHEMA": os.getenv("SNOWFLAKE_SCHEMA"),
    "GOOGLE_SHEETS_USER_EMAIL": os.getenv("GOOGLE_SHEETS_USER_EMAIL"),
    "SMTP_HOST": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "SMTP_PORT": os.getenv("SMTP_PORT", "587"),
    "SMTP_USER": os.getenv("SMTP_USER"),
    "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD"),
    "SMTP_FROM_EMAIL": os.getenv("SMTP_FROM_EMAIL"),
    "SMTP_FROM_NAME": os.getenv("SMTP_FROM_NAME"),
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
}


def _init_vertexai():
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)


def _make_app():
    return agent_engines.AdkApp(agent=root_agent, enable_tracing=True)


def create():
    _init_vertexai()
    remote_app = agent_engines.create(
        agent_engine=_make_app(),
        requirements=REQUIREMENTS,
        extra_packages=["./agent"],
        env_vars=ENV_VARS,
        display_name="AI Tinkerers Snowflake Agent",
        description="Connects to Snowflake via MCP",
    )
    print("Created agent:", remote_app.resource_name)


def update():
    _init_vertexai()
    remote_app = agent_engines.update(
        resource_name=REASONING_ENGINE_NAME,
        agent_engine=_make_app(),
        requirements=REQUIREMENTS,
        extra_packages=["./agent"],
        env_vars=ENV_VARS,
        display_name="AI Tinkerers Snowflake Agent",
        description="Connects to Snowflake via MCP",
    )
    print("Updated agent:", remote_app.resource_name)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python deploy.py [create|update]")
        sys.exit(1)

    command = sys.argv[1].lower()
    if command == "create":
        create()
    elif command == "update":
        update()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python deploy.py [create|update]")