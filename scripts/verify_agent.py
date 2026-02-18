import asyncio
import os
import sys

# Add the current directory to sys.path so we can import the agent
sys.path.append(os.getcwd())

from agent.tool_definitions import search_snowflake, read_google_sheet, replicate_data_to_sheet, get_toolkit
# from agent.tools import get_toolkit  # Incorrect

async def verify_snowflake():
    print("Testing Snowflake connection...")
    try:
        # Simple query to check connection
        toolkit = get_toolkit()
        # Use a list query or simple select 1
        result = toolkit.snowflake.query("SELECT CURRENT_VERSION()")
        print(f"✅ Snowflake Connection Successful. Version info: {result}")
        return True
    except Exception as e:
        print(f"❌ Snowflake Connection Failed: {e}")
        return False

async def verify_sheets():
    print("\nTesting Google Sheets connection...")
    # We need a spreadsheet ID to test. 
    # Since we don't have one provided by the user yet, we will just check if the client initializes.
    try:
        toolkit = get_toolkit()
        service = toolkit.sheets.get_service()
        print(f"✅ Google Sheets Service Initialized Successfuly", service)
        return True
    except Exception as e:
        print(f"❌ Google Sheets Initialization Failed: {e}")
        return False

async def main():
    print("Starting Verification...")
    sf_ok = await verify_snowflake()
    gs_ok = await verify_sheets()
    
    if sf_ok and gs_ok:
        print("\n🎉 Verification Complete: All systems go!")
    else:
        print("\n⚠️ Verification Completed with Issues.")

if __name__ == "__main__":
    asyncio.run(main())
