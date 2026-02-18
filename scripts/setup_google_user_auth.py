import os
import pickle
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Scopes required
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

CREDENTIALS_FILE = 'client_secret.json'
TOKEN_FILE = 'token.json'

def setup_auth():
    creds = None
    
    # 1. Check for existing token
    if os.path.exists(TOKEN_FILE):
        print("Found existing token.json, verifying validity...")
        try:
            with open(TOKEN_FILE, 'r') as token:
                data = json.load(token)
                creds = Credentials.from_authorized_user_info(data, SCOPES)
        except Exception as e:
            print(f"Error reading token: {e}")

    # 2. Refresh or Login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expired, refreshing...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Refresh failed: {e}. Starting fresh login.")
                creds = None
        
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"\n❌ ERROR: '{CREDENTIALS_FILE}' not found.")
                print("1. Go to Google Cloud Console > APIs & Services > Credentials")
                print("2. Create OAuth Client ID (Desktop App)")
                print("3. Download JSON and save it as 'client_secret.json' in this folder.")
                return

            print("\nStarting Login Flow...")
            print("Please check your browser to authorize the app.")
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            # Use a fixed port to make it easier (optional) or let it pick one
            creds = flow.run_local_server(port=0)
            
        # 3. Save Token
        print(f"Saving new token to '{TOKEN_FILE}'...")
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    print("\n✅ Authentication Successful!")
    print(f"Credentials saved to: {os.path.abspath(TOKEN_FILE)}")
    print("You can now update your .env to point to this token if needed, or I will update the code.")

if __name__ == "__main__":
    setup_auth()
