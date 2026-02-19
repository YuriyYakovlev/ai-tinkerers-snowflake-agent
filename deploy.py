import os
import sys
from dotenv import load_dotenv
import vertexai
from vertexai import agent_engines
from agent.agent import root_agent

# Load environment variables
load_dotenv()

# Project configuration
PROJECT_ID = "z-agentspace-trial"
LOCATION = "us-central1"
STAGING_BUCKET = "gs://z-agentspace-trial-reasoning-engine"

REASONING_ENGINE_NAME = os.getenv("REASONING_ENGINE_NAME")

print("DEBUG: Checking local environment variables before deploy...")
keys_to_check = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "REASONING_ENGINE_NAME",
]
for key in keys_to_check:
    val = os.getenv(key)
    if val:
        if "PASSWORD" in key:
             print(f"DEBUG: {key} is SET (masked: {val[:2]}***{val[-2:] if len(val)>4 else ''})")
        else:
             print(f"DEBUG: {key} = {val}")
    else:
        print(f"DEBUG: {key} is NOT SET (This will cause empty vars in cloud!)")

def create():
    print(f"Initializing Vertex AI for project {PROJECT_ID}...")
    vertexai.init(
        project=PROJECT_ID,
        location=LOCATION,
        staging_bucket=STAGING_BUCKET,
    )

    print("Creating AdkApp...")
    app = agent_engines.AdkApp(
        agent=root_agent,
        enable_tracing=True,
    )

    print("Deploying Reasoning Engine...")
    remote_app = agent_engines.create(
        agent_engine=app,
        requirements=[
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
        ],
        extra_packages=[
            "./agent",
        ],
        env_vars={
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
            "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true"
        },
        display_name="AI Tinkerers Snowflake Agent",
        description="Connects to Snowflake via MCP",
    )

    print("Deployed agent:", remote_app.resource_name)


def update():
    vertexai.init(
        project=PROJECT_ID,
        location=LOCATION,
        staging_bucket=STAGING_BUCKET,
    )

    app = agent_engines.AdkApp(
        agent=root_agent,
        enable_tracing=True,
    )

    remote_app = agent_engines.update(
        resource_name=REASONING_ENGINE_NAME,
        agent_engine=app,
        requirements=[
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
        ],
        extra_packages=[
            "./agent",
        ],
        env_vars={
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
            "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true"
        },
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
        print("Unknown command:", command)
        print("Usage: python deploy.py [create|update]")