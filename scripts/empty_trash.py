
import os
import sys

# Ensure we can import from agent
sys.path.append(os.getcwd())

from agent.config import Config
from agent.tools import Toolkit

def empty_trash():
    print("--- Emptying Google Drive Trash ---")
    
    try:
        config = Config()
        toolkit = Toolkit(config)
        drive = toolkit.sheets.get_drive_service()
        
        print("Emptying trash...")
        drive.files().emptyTrash().execute()
        print("✅ Trash emptied successfully.")

        # Check Quota again
        print("\nChecking Quota after emptying trash:")
        quota = toolkit.sheets.check_quota()
        usage = int(quota.get('usage', 0))
        limit = int(quota.get('limit', -1))
        print(f"Usage: {usage/1024/1024:.2f} MB")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    empty_trash()
