import snowflake.connector
import json
import os
from typing import Any, List, Dict, Optional
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
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
        self.last_executed_query = None

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
            
            self.last_executed_query = query
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
        results = self.query(f"EXPLAIN {query}")
        return format_as_table(results)

class SheetsClient:
    def __init__(self, config: Config):
        self.config = config
        self._service = None
        self._drive_service = None

    def get_service(self):
        if not self._service:
            if self.config.google_token_path and os.path.exists(self.config.google_token_path):
                try:
                    with open(self.config.google_token_path, 'r') as token:
                        info = json.load(token)
                        # Ensure using the correct class without passing scopes if they exist in info
                        creds = Credentials.from_authorized_user_info(info)
                        self._service = build('sheets', 'v4', credentials=creds)
                        return self._service
                except Exception as e:
                    print(f"Warning: Failed to use User Token: {e}")
                    import traceback
                    traceback.print_exc()

            if not self.config.google_service_account_path:
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_PATH not set and valid User Token not found")
            
            creds = service_account.Credentials.from_service_account_file(
                self.config.google_service_account_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            )
            self._service = build('sheets', 'v4', credentials=creds)
        return self._service

    def get_drive_service(self):
        if not self._drive_service:
            if self.config.google_token_path and os.path.exists(self.config.google_token_path):
                try:
                    with open(self.config.google_token_path, 'r') as token:
                        info = json.load(token)
                        creds = Credentials.from_authorized_user_info(info)
                        self._drive_service = build('drive', 'v3', credentials=creds)
                        return self._drive_service
                except Exception as e:
                    print(f"Warning: Failed to use User Token: {e}")

            if not self.config.google_service_account_path:
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_PATH not set and valid User Token not found")
            
            creds = service_account.Credentials.from_service_account_file(
                self.config.google_service_account_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            )
            self._drive_service = build('drive', 'v3', credentials=creds)
        return self._drive_service
    
    def rename_sheet(self, spreadsheet_id: str, new_title: str) -> str:
        """Rename a Google Sheet.
        
        Args:
            spreadsheet_id: ID of the spreadsheet to rename
            new_title: New title for the spreadsheet
            
        Returns:
            Success message with new title
        """
        service = self.get_service()
        
        body = {
            'requests': [{
                'updateSpreadsheetProperties': {
                    'properties': {
                        'title': new_title
                    },
                    'fields': 'title'
                }
            }]
        }
        
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        
        return f"Renamed spreadsheet to '{new_title}'"
    
    def create_chart(self, spreadsheet_id: str, sheet_id: int, chart_type: str, 
                     data_range: str, title: str, position_row: int = 0, position_col: int = 0) -> Dict[str, Any]:
        """Create a chart in a Google Sheet.
        
        Args:
            spreadsheet_id: The spreadsheet ID
            sheet_id: The sheet ID (tab ID, not name)
            chart_type: Type of chart ('line', 'bar', 'column', 'pie', 'scatter')
            data_range: Data range in A1 notation (e.g., 'A1:B10')
            title: Chart title
            position_row: Row position for chart (default: 0)
            position_col: Column position for chart (default: 0)
            
        Returns:
            Response from the API
        """
        service = self.get_service()
        
        # Map user-friendly chart types to Google Sheets chart types
        chart_type_map = {
            'line': 'LINE',
            'bar': 'BAR',
            'column': 'COLUMN',
            'pie': 'PIE',
            'scatter': 'SCATTER',
            'area': 'AREA'
        }
        
        google_chart_type = chart_type_map.get(chart_type.lower(), 'LINE')
        
        # Parse the range to get start/end rows and columns
        # Simple parsing for ranges like "A1:B10"
        import re
        match = re.match(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', data_range.upper())
        if not match:
            raise ValueError(f"Invalid data range format: {data_range}")
        
        def col_to_index(col: str) -> int:
            """Convert column letter to 0-based index."""
            result = 0
            for char in col:
                result = result * 26 + (ord(char) - ord('A') + 1)
            return result - 1
        
        start_col = col_to_index(match.group(1))
        start_row = int(match.group(2)) - 1
        end_col = col_to_index(match.group(3)) + 1  # End is exclusive
        end_row = int(match.group(4))  # End is exclusive (already 1-indexed)
        
        # Build chart spec
        chart_spec = {
            'title': title,
            'basicChart': {
                'chartType': google_chart_type,
                'legendPosition': 'RIGHT_LEGEND',
                'axis': [
                    {'position': 'BOTTOM_AXIS'},
                    {'position': 'LEFT_AXIS'}
                ],
                'domains': [{
                    'domain': {
                        'sourceRange': {
                            'sources': [{
                                'sheetId': sheet_id,
                                'startRowIndex': start_row,
                                'endRowIndex': end_row,
                                'startColumnIndex': start_col,
                                'endColumnIndex': start_col + 1
                            }]
                        }
                    }
                }],
                'series': [{
                    'series': {
                        'sourceRange': {
                            'sources': [{
                                'sheetId': sheet_id,
                                'startRowIndex': start_row,
                                'endRowIndex': end_row,
                                'startColumnIndex': start_col + 1,
                                'endColumnIndex': end_col
                            }]
                        }
                    },
                    'targetAxis': 'LEFT_AXIS'
                }],
                'headerCount': 1
            }
        }
        
        # Special handling for pie charts
        if google_chart_type == 'PIE':
            chart_spec = {
                'title': title,
                'pieChart': {
                    'legendPosition': 'RIGHT_LEGEND',
                    'domain': {
                        'sourceRange': {
                            'sources': [{
                                'sheetId': sheet_id,
                                'startRowIndex': start_row,
                                'endRowIndex': end_row,
                                'startColumnIndex': start_col,
                                'endColumnIndex': start_col + 1
                            }]
                        }
                    },
                    'series': {
                        'sourceRange': {
                            'sources': [{
                                'sheetId': sheet_id,
                                'startRowIndex': start_row,
                                'endRowIndex': end_row,
                                'startColumnIndex': start_col + 1,
                                'endColumnIndex': end_col
                            }]
                        }
                    }
                }
            }
        
        # Request body
        requests = [{
            'addChart': {
                'chart': {
                    'spec': chart_spec,
                    'position': {
                        'overlayPosition': {
                            'anchorCell': {
                                'sheetId': sheet_id,
                                'rowIndex': position_row,
                                'columnIndex': position_col
                            }
                        }
                    }
                }
            }
        }]
        
        body = {'requests': requests}
        
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        
        return response

    def read_sheet(self, spreadsheet_id: str, range_name: str) -> List[List[str]]:
        service = self.get_service()
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        return values

    def write_sheet(self, spreadsheet_id: str, range_name: str, values: List[List[Any]]) -> Dict[str, Any]:
        """Write data to a Google Sheet.
        
        Args:
            spreadsheet_id: The spreadsheet ID
            range_name: The range to write to (e.g., 'Sheet1!A1')
            values: The data to write as a 2D list
            
        Returns:
            Dictionary with update information (updatedCells, updatedRows, etc.)
            
        Raises:
            Exception: If the write operation fails
        """
        service = self.get_service()
        body = {
            'values': values
        }
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_name,
            valueInputOption='RAW', body=body).execute()
        
        updated_cells = result.get('updatedCells', 0)
        if updated_cells == 0:
            raise ValueError(f"Write operation returned 0 updated cells. Response: {result}")
        
        return result
            
    def get_sheet_names(self, spreadsheet_id: str) -> List[str]:
        service = self.get_service()
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        return [sheet['properties']['title'] for sheet in metadata.get('sheets', [])]

    def create_sheet(self, title: str) -> str:
        """Create a new spreadsheet and return its ID."""
        service = self.get_service()
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        spreadsheet = service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId').execute()
        return spreadsheet.get('spreadsheetId')

    def share_sheet(self, spreadsheet_id: str, email: str, role: str = 'writer'):
        """Share the spreadsheet with a user via Drive API."""
        drive_service = self.get_drive_service()
        
        permission = {
            'type': 'user',
            'role': role,
            'emailAddress': email
        }
        
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body=permission,
            fields='id',
        ).execute()

    def add_worksheet(self, spreadsheet_id: str, title: str) -> int:
        """Add a new worksheet (tab) to the spreadsheet."""
        service = self.get_service()
        request_body = {
            'requests': [{
                'addSheet': {
                    'properties': {
                        'title': title
                    }
                }
            }]
        }
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=request_body
        ).execute()
        return response['replies'][0]['addSheet']['properties']['sheetId']

    def check_quota(self) -> Dict[str, Any]:
        """Check Drive storage quota."""
        drive_service = self.get_drive_service()
        about = drive_service.about().get(fields="storageQuota").execute()
        return about.get('storageQuota', {})

    def list_files(self, mime_type: Optional[str] = None, page_size: int = 10) -> List[Dict[str, Any]]:
        """List files in Drive, optionally filtered by mimeType."""
        drive_service = self.get_drive_service()
        query = "trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
            
        results = drive_service.files().list(
            q=query,
            pageSize=page_size,
            fields="nextPageToken, files(id, name, mimeType, createdTime, size)",
            orderBy="createdTime"
        ).execute()
        return results.get('files', [])

    def delete_file(self, file_id: str):
        """Permanently delete a file."""
        drive_service = self.get_drive_service()
        drive_service.files().delete(fileId=file_id).execute()

class Toolkit:
    def __init__(self, config: Config):
        self.config = config
        self.snowflake = SnowflakeClient(config)
        self.sheets = SheetsClient(config)
        self.resources = ResourceManager()
        self.error_handler = ErrorHandler()
        



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
