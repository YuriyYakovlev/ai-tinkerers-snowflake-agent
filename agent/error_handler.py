"""Error Handler - User-friendly error handling with actionable suggestions."""

import re
from typing import Dict, Optional, Tuple


class ErrorHandler:
    """Handles errors and provides user-friendly messages with suggestions."""
    
    # Common error patterns and their solutions
    SNOWFLAKE_ERRORS = {
        "does not exist or not authorized": {
            "type": "TableNotFound",
            "message": "The table or view you're trying to access doesn't exist or you don't have permission.",
            "suggestions": [
                "Check the table name spelling",
                "Ensure you're using the correct schema (format: SCHEMA.TABLE)",
                "Use preview_table() to see available tables",
                "Verify you have SELECT permission on this table"
            ]
        },
        "SQL compilation error": {
            "type": "SQLSyntaxError",
            "message": "There's a syntax error in your SQL query.",
            "suggestions": [
                "Check for missing commas or quotes",
                "Verify column names exist in the table",
                "Use get_table_schema() to see available columns",
                "Try simplifying the query to isolate the issue"
            ]
        },
        "Numeric value.*out of range": {
            "type": "NumericOverflow",
            "message": "A numeric value in your query result is too large.",
            "suggestions": [
                "Use CAST() to convert to a larger data type",
                "Apply filters to reduce the range of values",
                "Consider using TO_VARCHAR() for very large numbers"
            ]
        },
        "Invalid identifier": {
            "type": "InvalidIdentifier",
            "message": "A column or table name in your query is invalid.",
            "suggestions": [
                "Use double quotes for case-sensitive or special character names",
                "Check for typos in column/table names",
                "Use get_table_schema() to see exact column names"
            ]
        },
        "Division by zero": {
            "type": "DivisionByZero",
            "message": "Your query attempted to divide by zero.",
            "suggestions": [
                "Add a WHERE clause to filter out zero denominators",
                "Use NULLIF() to handle zero values: field / NULLIF(divisor, 0)",
                "Use a CASE statement to handle zero denominators"
            ]
        },
        "authentication failed": {
            "type": "AuthenticationError",
            "message": "Failed to authenticate with Snowflake.",
            "suggestions": [
                "Check your SNOWFLAKE_USER and SNOWFLAKE_PASSWORD in .env",
                "Verify your Snowflake account name is correct",
                "Ensure your credentials haven't expired",
                "Check if your IP is whitelisted in Snowflake"
            ]
        },
        "Warehouse.*does not exist": {
            "type": "WarehouseNotFound",
            "message": "The specified warehouse doesn't exist or isn't accessible.",
            "suggestions": [
                "Check SNOWFLAKE_WAREHOUSE in your .env file",
                "Verify the warehouse name spelling",
                "Ensure the warehouse is running and not suspended",
                "Check if you have USAGE privilege on the warehouse"
            ]
        }
    }
    
    SHEETS_ERRORS = {
        "403": {
            "type": "PermissionDenied",
            "message": "Access denied to the Google Sheet.",
            "suggestions": [
                "Share the sheet with your service account email",
                "Check GOOGLE_SERVICE_ACCOUNT_PATH points to the correct file",
                "Verify the service account has Editor or Viewer permissions",
                "Ensure the spreadsheet ID is correct"
            ]
        },
        "404": {
            "type": "SheetNotFound",
            "message": "The spreadsheet or sheet tab was not found.",
            "suggestions": [
                "Verify the spreadsheet ID is correct",
                "Check that the sheet tab name matches exactly (case-sensitive)",
                "Ensure the spreadsheet hasn't been deleted",
                "Try listing available sheets first"
            ]
        },
        "Unable to parse range": {
            "type": "InvalidRange",
            "message": "The sheet range format is invalid.",
            "suggestions": [
                "Use A1 notation (e.g., 'Sheet1!A1:B10')",
                "Ensure the sheet name is correct",
                "For full sheet, just use the sheet name",
                "Use single quotes for sheet names with spaces: 'My Sheet'!A1"
            ]
        },
        "INVALID_ARGUMENT": {
            "type": "InvalidArgument",
            "message": "Invalid argument provided to Google Sheets API.",
            "suggestions": [
                "Check that values are properly formatted",
                "Ensure range notation is correct",
                "Verify sheet name doesn't contain invalid characters"
            ]
        }
    }
    
    @staticmethod
    def handle_snowflake_error(error: Exception) -> Tuple[str, str, list]:
        """Handle Snowflake-specific errors.
        
        Args:
            error: Exception from Snowflake
        
        Returns:
            Tuple of (error_type, message, suggestions)
        """
        error_str = str(error).lower()
        
        # Try to match against known patterns
        for pattern, info in ErrorHandler.SNOWFLAKE_ERRORS.items():
            if re.search(pattern.lower(), error_str):
                return (
                    info["type"],
                    info["message"],
                    info["suggestions"]
                )
        
        # Generic Snowflake error
        return (
            "SnowflakeError",
            "An error occurred while executing your Snowflake query.",
            [
                "Check the error details above",
                "Verify your SQL syntax is correct",
                "Ensure all referenced tables and columns exist",
                "Try breaking down complex queries into simpler parts"
            ]
        )
    
    @staticmethod
    def handle_sheets_error(error: Exception) -> Tuple[str, str, list]:
        """Handle Google Sheets-specific errors.
        
        Args:
            error: Exception from Google Sheets API
        
        Returns:
            Tuple of (error_type, message, suggestions)
        """
        error_str = str(error)
        
        # Try to match against known patterns
        for pattern, info in ErrorHandler.SHEETS_ERRORS.items():
            if pattern in error_str:
                return (
                    info["type"],
                    info["message"],
                    info["suggestions"]
                )
        
        # Generic Sheets error
        return (
            "GoogleSheetsError",
            "An error occurred while accessing Google Sheets.",
            [
                "Verify the spreadsheet ID is correct",
                "Check that the service account has proper permissions",
                "Ensure the sheet hasn't been deleted or moved",
                "Try the operation again - might be a temporary API issue"
            ]
        )
    
    @staticmethod
    def format_error_response(
        error: Exception,
        error_type: str,
        message: str,
        suggestions: list,
        query: Optional[str] = None
    ) -> str:
        """Format a comprehensive error response.
        
        Args:
            error: Original exception
            error_type: Type of error
            message: User-friendly message
            suggestions: List of suggestions
            query: Optional query that caused the error
        
        Returns:
            Formatted error message
        """
        response = f"❌ **{error_type}**\n\n"
        response += f"{message}\n\n"
        
        if query:
            response += f"**Query:**\n```sql\n{query}\n```\n\n"
        
        response += "**💡 Suggestions:**\n"
        for i, suggestion in enumerate(suggestions, 1):
            response += f"{i}. {suggestion}\n"
        
        response += f"\n**Technical Details:**\n{str(error)}"
        
        return response
    
    @staticmethod
    def suggest_fixes(error_type: str, context: Optional[Dict] = None) -> str:
        """Get specific fix suggestions based on error type.
        
        Args:
            error_type: Type of error
            context: Optional context (e.g., available tables, columns)
        
        Returns:
            Formatted suggestions
        """
        if error_type == "TableNotFound" and context and context.get("available_tables"):
            tables = context["available_tables"]
            return f"\n**Available tables:**\n" + "\n".join(f"  - {t}" for t in tables[:10])
        
        if error_type == "InvalidIdentifier" and context and context.get("available_columns"):
            columns = context["available_columns"]
            return f"\n**Available columns:**\n" + "\n".join(f"  - {c}" for c in columns)
        
        if error_type == "SheetNotFound" and context and context.get("available_sheets"):
            sheets = context["available_sheets"]
            return f"\n**Available sheets:**\n" + "\n".join(f"  - {s}" for s in sheets)
        
        return ""
