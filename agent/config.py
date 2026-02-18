import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    """Configuration for the Snowflake Agent."""
    google_api_key: Optional[str] = os.getenv("GOOGLE_API_KEY")
    google_cloud_project: Optional[str] = os.getenv("GOOGLE_CLOUD_PROJECT")
    google_cloud_location: Optional[str] = os.getenv("GOOGLE_CLOUD_LOCATION")
    
    # Snowflake Credentials
    snowflake_user: Optional[str] = os.getenv("SNOWFLAKE_USER")
    snowflake_password: Optional[str] = os.getenv("SNOWFLAKE_PASSWORD")
    snowflake_account: Optional[str] = os.getenv("SNOWFLAKE_ACCOUNT")
    snowflake_warehouse: Optional[str] = os.getenv("SNOWFLAKE_WAREHOUSE")
    snowflake_database: Optional[str] = os.getenv("SNOWFLAKE_DATABASE")
    snowflake_schema: Optional[str] = os.getenv("SNOWFLAKE_SCHEMA")
    snowflake_role: Optional[str] = os.getenv("SNOWFLAKE_ROLE")
    
    # Google Sheets Credentials
    # For service account
    google_service_account_path: Optional[str] = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
    # For user auth (OAuth 2.0)
    # Default to finding token.json in the same directory as config.py
    google_token_path: Optional[str] = os.getenv("GOOGLE_TOKEN_PATH", 
                                               os.path.join(os.path.dirname(__file__), "token.json"))
    google_sheets_user_email: Optional[str] = os.getenv("GOOGLE_SHEETS_USER_EMAIL")
    
    # Email SMTP Configuration (for campaign emails)
    smtp_host: Optional[str] = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: Optional[str] = os.getenv("SMTP_USER")  # Your email address
    smtp_password: Optional[str] = os.getenv("SMTP_PASSWORD")  # App password
    smtp_from_email: Optional[str] = os.getenv("SMTP_FROM_EMAIL")  # Sender email
    smtp_from_name: Optional[str] = os.getenv("SMTP_FROM_NAME", "Campaign Team")
    
    @classmethod
    def from_env(cls) -> "Config":
        return cls()
