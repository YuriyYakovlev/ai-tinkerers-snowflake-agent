import snowflake.connector
import pandas as pd
import json
import os
import csv
from typing import Any, List, Dict, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import Config
from .error_handler import ErrorHandler


class ResourceManager:
    def __init__(self):
        self.file_path = os.path.join(os.path.dirname(__file__), "resources.json")
        self._load_resources()

    def _load_resources(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    self.resources = json.load(f)
            except:
                self.resources = {}
        else:
            self.resources = {}

    def _save_resources(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.resources, f, indent=2)

    def save_alias(self, alias: str, resource_id: str):
        self.resources[alias] = resource_id
        self._save_resources()

    def get_id(self, alias_or_id: str) -> str:
        return self.resources.get(alias_or_id, alias_or_id)
        
    def list_aliases(self) -> Dict[str, str]:
        return self.resources

class SnowflakeClient:
    def __init__(self, config: Config):
        self.config = config
        self._conn = None

    def connect(self):
        if not self._conn:
            self._conn = snowflake.connector.connect(
                user=self.config.snowflake_user,
                password=self.config.snowflake_password,
                account=self.config.snowflake_account,
                warehouse=self.config.snowflake_warehouse,
                database=self.config.snowflake_database,
                schema=self.config.snowflake_schema,
                role=self.config.snowflake_role
            )
        return self._conn

    def query(self, query: str, use_cache: bool = False) -> List[Dict[str, Any]]:
        """Execute a query.
        
        Args:
            query: SQL query to execute
            use_cache: Whether to use query result caching (default: False)
        
        Returns:
            List of result rows as dictionaries
        """
        conn = self.connect()
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            # Fetch results and columns
            columns = [col[0] for col in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            
            return results
        finally:
            cursor.close()
    
    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get metadata about a table.
        
        Args:
            table_name: Table name (can include schema)
        
        Returns:
            Dictionary with table information
        """
        query = f"SHOW COLUMNS IN {table_name}"
        return self.query(query)
    
    def explain_query(self, query: str) -> str:
        """Get query execution plan.
        
        Args:
            query: SQL query to explain
        
        Returns:
            Query execution plan
        """
        conn = self.connect()
        cursor = conn.cursor()
        try:
            cursor.execute(f"EXPLAIN {query}")
            plan = cursor.fetchall()
            return "\n".join(str(row[0]) for row in plan)
        finally:
            cursor.close()

class SheetsClient:
    def __init__(self, config: Config):
        self.config = config
        self._service = None

    def get_service(self):
        if not self._service:
            if not self.config.google_service_account_path:
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_PATH not set")
            
            creds = service_account.Credentials.from_service_account_file(
                self.config.google_service_account_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self._service = build('sheets', 'v4', credentials=creds)
        return self._service

    def read_sheet(self, spreadsheet_id: str, range_name: str) -> List[List[str]]:
        service = self.get_service()
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        return values

    def write_sheet(self, spreadsheet_id: str, range_name: str, values: List[List[Any]]):
        service = self.get_service()
        body = {
            'values': values
        }
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_name,
            valueInputOption='RAW', body=body).execute()
            
    def get_sheet_names(self, spreadsheet_id: str) -> List[str]:
        service = self.get_service()
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        return [sheet['properties']['title'] for sheet in metadata.get('sheets', [])]

class Toolkit:
    def __init__(self, config: Config):
        self.config = config
        self.snowflake = SnowflakeClient(config)
        self.sheets = SheetsClient(config)
        self.resources = ResourceManager()
        self.error_handler = ErrorHandler()
        
    def export_to_excel(self, data: List[Dict[str, Any]], filename: str) -> str:
        """Export data to Excel file.
        
        Args:
            data: List of dictionaries to export
            filename: Output filename
        
        Returns:
            Absolute path to created file
        """
        if not data:
            return "No data to export"
            
        if not filename.endswith('.xlsx'):
            filename += '.xlsx'
            
        full_path = os.path.abspath(filename)
        df = pd.DataFrame(data)
        df.to_excel(full_path, index=False)
        return full_path
    
    def export_to_csv(self, data: List[Dict[str, Any]], filename: str) -> str:
        """Export data to CSV file.
        
        Args:
            data: List of dictionaries to export
            filename: Output filename
        
        Returns:
            Absolute path to created file
        """
        if not data:
            return "No data to export"
        
        if not filename.endswith('.csv'):
            filename += '.csv'
        
        full_path = os.path.abspath(filename)
        
        # Get all unique keys from all dictionaries
        fieldnames = []
        for row in data:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)
        
        with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        return full_path
    
    def export_to_json(self, data: List[Dict[str, Any]], filename: str, pretty: bool = True) -> str:
        """Export data to JSON file.
        
        Args:
            data: List of dictionaries to export
            filename: Output filename
            pretty: Whether to format JSON with indentation
        
        Returns:
            Absolute path to created file
        """
        if not filename.endswith('.json'):
            filename += '.json'
        
        full_path = os.path.abspath(filename)
        
        with open(full_path, 'w', encoding='utf-8') as jsonfile:
            if pretty:
                json.dump(data, jsonfile, indent=2, default=str)
            else:
                json.dump(data, jsonfile, default=str)
        
        return full_path


def format_as_table(data: List[Dict[str, Any]], max_rows: int = 100) -> str:
    """Format query results as a markdown table.
    
    Args:
        data: List of dictionaries to format
        max_rows: Maximum rows to display
    
    Returns:
        Markdown-formatted table string
    """
    if not data:
        return "No data returned"
    
    # Limit rows
    display_data = data[:max_rows]
    total_rows = len(data)
    
    # Get column names
    columns = list(display_data[0].keys())
    
    # Build header
    header = "| " + " | ".join(str(col) for col in columns) + " |"
    separator = "|" + "|".join("------" for _ in columns) + "|"
    
    # Build rows
    rows = []
    for row in display_data:
        values = []
        for col in columns:
            val = row.get(col, "")
            # Convert to string and truncate if too long
            val_str = str(val) if val is not None else ""
            if len(val_str) > 50:
                val_str = val_str[:47] + "..."
            values.append(val_str)
        rows.append("| " + " | ".join(values) + " |")
    
    # Combine
    table = "\n".join([header, separator] + rows)
    
    # Add row count footer
    if total_rows > max_rows:
        table += f"\n\n*Showing {max_rows} of {total_rows} rows*"
    else:
        table += f"\n\n*{total_rows} rows*"
    
    return table
