
import os
import sys

# Add the current directory to sys.path
sys.path.append(os.getcwd())

from google.cloud import aiplatform
import vertexai
from vertexai.preview import reasoning_engines

# Project configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "z-agentspace-trial")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
STAGING_BUCKET = os.getenv("STAGING_BUCKET", "gs://z-agentspace-trial-reasoning-engine")

def query_agent(agent_name: str, input_text: str):
    """
    Queries the deployed Reasoning Engine agent.
    
    Args:
        agent_name: The resource name or ID of the deployed agent.
        input_text: The user's input query.
    """
    print(f"Querying agent: {agent_name}")
    print(f"Input: {input_text}")
    
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)
    

    try:
        # Get the remote agent
        remote_agent = reasoning_engines.ReasoningEngine(agent_name)
        
        print(f"DEBUG: remote_agent type: {type(remote_agent)}")
        print(f"DEBUG: dir(remote_agent): {dir(remote_agent)}")

        # Query the agent
        if hasattr(remote_agent, "query"):
            response = remote_agent.query(input=input_text)
            print("\n--- Response (query) ---")
            print(response)
            print("----------------")
        elif hasattr(remote_agent, "stream_query"):
             # It might return a generator
             print("Calling stream_query...")
             response_gen = remote_agent.stream_query(input=input_text)
             print("\n--- Response (stream_query) ---")
             for chunk in response_gen:
                 print(chunk, end="")
             print("\n----------------")
        else:
             print("No 'query' or 'stream_query' method found!")
             # Try to find any callable that looks like query
             for attr in dir(remote_agent):
                 if "query" in attr or "run" in attr:
                     print(f"Found method candidate: {attr}")

    except Exception as e:
        print(f"\n❌ Error querying agent: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    if len(sys.argv) < 3:
        print("Usage: python scripts/query_agent.py <agent_resource_name_or_id> <query_text>")
        print("Example: python scripts/query_agent.py projects/123/locations/us-central1/reasoningEngines/456 'Show me sales'")
        sys.exit(1)
        
    agent_id = sys.argv[1]
    query = sys.argv[2]
    
    query_agent(agent_id, query)
