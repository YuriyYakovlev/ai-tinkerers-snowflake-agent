"""
deploy.py
=========

Deploys the Agent to Vertex AI Reasoning Engine.

Usage
-----
    # First-time deploy (creates a new Reasoning Engine instance):
    python deploy.py create

    # Redeploy after code changes (updates an existing instance):
    python deploy.py update

For ``update``, set REASONING_ENGINE_NAME in .env to the resource name
returned by a previous ``create`` run:

    REASONING_ENGINE_NAME=projects/123/locations/us-central1/reasoningEngines/456

Environment Variables Required
-------------------------------
All Snowflake and SMTP credentials must be set in .env — they are forwarded
to the remote Reasoning Engine via ``env_vars``.  See ``agent/config.py`` for
the full list.

How deployment works
--------------------
Vertex AI Reasoning Engine runs the agent in a managed container.  The
``extra_packages=["./agent"]`` argument bundles the local ``agent/`` package
into the deployment artifact so the remote container has access to all the
sub-packages (``core/``, ``tools/``, ``tool_definitions/``).
"""

import os
import sys

from dotenv import load_dotenv
import vertexai
from vertexai import agent_engines

# V2: root_agent is now exported from agent/__init__.py via agent.core.agent
from agent import root_agent

load_dotenv()

# ── Vertex AI / GCS configuration ────────────────────────────────────────────
PROJECT_ID = "z-agentspace-trial"
LOCATION = "us-central1"
STAGING_BUCKET = "gs://z-agentspace-trial-reasoning-engine"

# Resource name of an existing Reasoning Engine (used for `update` command).
# Set REASONING_ENGINE_NAME in .env after running `create` for the first time.
REASONING_ENGINE_NAME = os.getenv("REASONING_ENGINE_NAME")

# ── Python package requirements ───────────────────────────────────────────────
# These are installed in the remote Reasoning Engine container at deployment.
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

# ── Remote environment variables ──────────────────────────────────────────────
# These are injected into the Reasoning Engine container's environment at
# runtime (equivalent to the .env file in local development).
# IMPORTANT: never hard-code credentials here — always pull from local .env.
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
    """Initialise the Vertex AI SDK with project, region, and staging bucket."""
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)


def _make_app():
    """Wrap root_agent in an ADK app with tracing enabled."""
    return agent_engines.AdkApp(agent=root_agent, enable_tracing=True)


def create():
    """Create a new Vertex AI Reasoning Engine instance.

    Run this once for the first deployment.  Copy the printed resource name
    into your .env as ``REASONING_ENGINE_NAME`` for future ``update`` runs.
    """
    _init_vertexai()
    remote_app = agent_engines.create(
        agent_engine=_make_app(),
        requirements=REQUIREMENTS,
        # Bundles the entire agent/ package (including core/, tools/,
        # tool_definitions/ sub-packages) into the deployment artifact.
        extra_packages=["./agent"],
        env_vars=ENV_VARS,
        display_name="AI Tinkerers Snowflake Agent",
        description="Connects to Snowflake via MCP",
    )
    print("Created agent:", remote_app.resource_name)
    print(f"\nAdd this to your .env for future updates:\nREASONING_ENGINE_NAME={remote_app.resource_name}")


def update():
    """Update an existing Reasoning Engine instance with the latest code.

    Requires REASONING_ENGINE_NAME to be set in .env.
    """
    if not REASONING_ENGINE_NAME:
        print("Error: REASONING_ENGINE_NAME is not set in .env")
        print("Run `python deploy.py create` first to create the engine.")
        sys.exit(1)

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