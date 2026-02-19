
import os
import sys
from google.cloud import aiplatform
import vertexai
from vertexai.preview import reasoning_engines

# Project configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "z-agentspace-trial")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
STAGING_BUCKET = os.getenv("STAGING_BUCKET", "gs://z-agentspace-trial-reasoning-engine")

def list_agents():
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)
    
    print(f"Listing Reasoning Engines in {PROJECT_ID}/{LOCATION}...")
    try:
        # Expected to return a list of ReasoningEngine objects
        agents = reasoning_engines.ReasoningEngine.list()
        
        if not agents:
            print("No agents found.")
            return

        print(f"Found {len(agents)} agents.")
        
        # Sort by creation time (descending) if possible, or just list them
        # The object might have create_time or update_time
        # Let's inspect the first one
        
        sorted_agents = sorted(agents, key=lambda x: x.create_time, reverse=True)
        
        for agent in sorted_agents[:5]:
            print(f"Name: {agent.resource_name}")
            print(f"Display Name: {agent.display_name}")
            print(f"Created: {agent.create_time}")
            print("-" * 20)
            
        latest = sorted_agents[0]
        print(f"LATEST_AGENT_ID={latest.resource_name}")

    except Exception as e:
        print(f"Error listing agents: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    list_agents()
