import unittest
import sys
import os
import json
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Mock FastMCP decorators BEFORE importing tool_definitions
sys.modules['fastmcp'] = MagicMock()
mock_mcp = MagicMock()
mock_mcp.tool.return_value = lambda x: x 
sys.modules['fastmcp'].FastMCP.return_value = mock_mcp

from agent import tool_definitions

class TestAgentTools(unittest.TestCase):
    
    def setUp(self):
        # Create a mock toolkit
        self.mock_toolkit = MagicMock()
        self.mock_toolkit.snowflake = MagicMock()
        self.mock_toolkit.sheets = MagicMock()
        self.mock_toolkit.resources = MagicMock()
        self.mock_toolkit.error_handler = MagicMock()
        self.mock_toolkit.config = MagicMock()
        
        # Default behaviors
        self.mock_toolkit.error_handler.handle_snowflake_error.return_value = ("Unknown", "Error", [])
        self.mock_toolkit.error_handler.format_error_response.side_effect = lambda e, t, m, s, q=None: f"Error: {m}"
        
        # Patch the get_toolkit function
        self.patcher = patch('agent.tool_definitions.get_toolkit', return_value=self.mock_toolkit)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def run_async(self, coro):
        return asyncio.run(coro)

    # --- Internal Discovery Tools Tests ---

    def test_list_databases_internal(self):
        import datetime
        self.mock_toolkit.snowflake.query.return_value = [{
            "name": "FINANCIALS", 
            "owner": "SYSADMIN", 
            "created_on": datetime.datetime.now()
        }]
        result = self.run_async(tool_definitions._list_databases_internal())
        self.assertIn("| FINANCIALS |", result)
        self.assertIn("| SYSADMIN |", result)

    def test_list_schemas_internal(self):
        import datetime
        self.mock_toolkit.snowflake.query.return_value = [{
            "database_name": "FINANCIALS",
            "name": "PUBLIC", 
            "created_on": datetime.datetime.now()
        }]
        result = self.run_async(tool_definitions._list_schemas_internal("FINANCIALS"))
        self.assertIn("PUBLIC", result)

    def test_list_tables_internal(self):
        self.mock_toolkit.snowflake.query.return_value = [{
            "schema_name": "PUBLIC",
            "name": "CUSTOMERS", 
            "kind": "TABLE",
            "rows": 1000
        }]
        result = self.run_async(tool_definitions._list_tables_internal("PUBLIC"))
        self.assertIn("| CUSTOMERS |", result)
        self.assertIn("| 1000 |", result)

    # --- Business User Tools Tests ---

    def test_query_data_internal(self):
        self.mock_toolkit.snowflake.query.return_value = [{"revenue": 100000}]
        result = self.run_async(tool_definitions._query_data_internal("SELECT revenue FROM sales"))
        self.assertIn("| revenue |", result)
        self.assertIn("| 100000 |", result)

    def test_get_account_info_success(self):
        self.mock_toolkit.snowflake.query.return_value = [{
            "ACCOUNT_NAME": "Acme Corp", 
            "REVENUE": 150000
        }]
        result = self.run_async(tool_definitions.get_account_info("Acme Corp"))
        self.assertIn("Acme Corp", result)
        self.mock_toolkit.snowflake.query.assert_called()

    def test_get_account_info_not_found(self):
        self.mock_toolkit.snowflake.query.return_value = []
        result = self.run_async(tool_definitions.get_account_info("NonExistent"))
        self.assertIn("couldn't find", result.lower())

    # --- Google Sheets Tools Tests ---
    
    def test_create_new_sheet(self):
        self.mock_toolkit.sheets.create_sheet.return_value = "new_sheet_123"
        self.mock_toolkit.config.google_sheets_user_email = "test@example.com"
        
        result = self.run_async(tool_definitions.create_new_sheet("Monthly Report"))
        
        data = json.loads(result)
        self.assertEqual(data["spreadsheet_id"], "new_sheet_123")
        self.assertEqual(data["alias"], "monthly_report")
        self.mock_toolkit.resources.save_alias.assert_called_with("monthly_report", "new_sheet_123")

    def test_save_resource_alias(self):
        result = self.run_async(tool_definitions.save_resource_alias("sales_report", "sheet_456"))
        self.assertIn("Saved alias", result)
        self.mock_toolkit.resources.save_alias.assert_called_with("sales_report", "sheet_456")

    def test_list_resource_aliases(self):
        self.mock_toolkit.resources.list_aliases.return_value = [
            {"alias": "sales_report", "resource_id": "sheet_123"},
            {"alias": "customer_list", "resource_id": "sheet_456"}
        ]
        result = self.run_async(tool_definitions.list_resource_aliases())
        self.assertIn("sales_report", result)
        self.assertIn("customer_list", result)

    def test_replicate_data_to_sheet_with_query(self):
        self.mock_toolkit.resources.get_id.return_value = "sheet_789"
        self.mock_toolkit.sheets.get_sheet_names.return_value = []
        self.mock_toolkit.sheets.write_sheet.return_value = {"updatedCells": 100, "updatedRows": 10}
        self.mock_toolkit.snowflake.query.return_value = [{"customer": "Acme", "revenue": 50000}]
        
        result = self.run_async(tool_definitions.replicate_data_to_sheet(
            "my_sheet", 
            "Sales Data",
            query="SELECT * FROM sales"
        ))
        
        self.assertIn("Successfully replicated", result)
        self.mock_toolkit.snowflake.query.assert_called_with("SELECT * FROM sales")

    def test_replicate_data_to_sheet_auto_query(self):
        self.mock_toolkit.resources.get_id.return_value = "sheet_789"
        self.mock_toolkit.sheets.get_sheet_names.return_value = []
        self.mock_toolkit.sheets.write_sheet.return_value = {"updatedCells": 50, "updatedRows": 5}
        self.mock_toolkit.snowflake.last_executed_query = "SELECT * FROM recent_query"
        self.mock_toolkit.snowflake.query.return_value = [{"col": "val"}]
        
        result = self.run_async(tool_definitions.replicate_data_to_sheet("my_sheet", "Tab1"))
        
        self.assertIn("Successfully replicated", result)
        self.mock_toolkit.snowflake.query.assert_called_with("SELECT * FROM recent_query")

    def test_read_google_sheet(self):
        self.mock_toolkit.resources.get_id.return_value = "sheet_111"
        self.mock_toolkit.sheets.read_sheet.return_value = [
            ["Name", "Revenue"],
            ["Acme", "50000"],
            ["TechCo", "75000"]
        ]
        
        result = self.run_async(tool_definitions.read_google_sheet("sales_sheet", "Sheet1"))
        
        data = json.loads(result)
        self.assertEqual(len(data), 3)
        # Data comes back as list of lists, not list of dicts
        self.assertEqual(data[0][0], "Name")

if __name__ == '__main__':
    unittest.main()
