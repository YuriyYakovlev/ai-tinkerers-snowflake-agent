#!/bin/bash
set -e

# -------------------------
# CONFIG
# -------------------------
PROJECT_ID="z-agentspace-trial"
APP_ID="gemini-enterprise-17609662_1760966203550"
REASONING_ENGINE_LOCATION="us-central1"
ADK_DEPLOYMENT_ID="5806315297610661888"
ENDPOINT_LOCATION="us-"
DISPLAY_NAME="AI Tinkerers Snowflake Agent"
DESCRIPTION="Snowflake MCP Connector running on Vertex Agent Engine"
# -------------------------

echo "Adding ADK agent to Gemini Enterprise..."
echo "---------------------------------------"
echo "Project: ${PROJECT_ID}"
echo "App ID: ${APP_ID}"
echo "Reasoning Engine ID: ${ADK_DEPLOYMENT_ID}"
echo ""

curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: ${PROJECT_ID}" \
  "https://${ENDPOINT_LOCATION}discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/us/collections/default_collection/engines/${APP_ID}/assistants/default_assistant/agents" \
  -d "{
    \"displayName\": \"${DISPLAY_NAME}\",
    \"description\": \"${DESCRIPTION}\",
    \"adkAgentDefinition\": {
      \"provisionedReasoningEngine\": {
        \"reasoningEngine\": \"projects/${PROJECT_ID}/locations/${REASONING_ENGINE_LOCATION}/reasoningEngines/${ADK_DEPLOYMENT_ID}\"
      }
    },
  }" | jq

echo ""
echo "✓ Done!"
echo "You can now check the agent in Gemini Enterprise UI."
