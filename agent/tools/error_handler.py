"""
agent/tools/error_handler.py
=============================

User-friendly, actionable error handling for Snowflake and Google Sheets.

Design Strategy
---------------
Raw database exceptions (``SnowflakeSQLException``, Google API ``HttpError``)
contain technical jargon that is meaningless to a business user.

``ErrorHandler`` uses **pattern matching** against the exception message to
identify the type of failure and return:

1. A user-friendly ``message`` (what went wrong in plain English).
2. Concrete ``suggestions`` (what the user or agent should do next).

This transforms ``"SQL compilation error: Object 'SCHEMA.TABLE' does not
exist or not authorized"`` into:

    ❌ TableNotFound
    The table you're trying to access doesn't exist or you don't have permission.
    Suggestions: Check the table name spelling, verify schema prefix, ...

It is deliberately implemented as **static methods** so callers don't need to
instantiate the class repeatedly; the error patterns are class-level constants.
"""

import re
from typing import Dict, List, Optional, Tuple


class ErrorHandler:
    """Translates raw exceptions into user-friendly messages with suggestions.

    Attributes
    ----------
    SNOWFLAKE_ERRORS:
        Map of error pattern (regex) → ``{type, message, suggestions}``.
    SHEETS_ERRORS:
        Map of error string fragment → ``{type, message, suggestions}``.
    """

    # ── Snowflake error patterns ──────────────────────────────────────────────
    # Keys are regex patterns matched against the lowercased exception message.
    SNOWFLAKE_ERRORS: Dict[str, dict] = {
        "does not exist or not authorized": {
            "type": "TableNotFound",
            "message": "The table or view you're trying to access doesn't exist or you don't have permission.",
            "suggestions": [
                "Check the table name spelling",
                "Ensure you're using the correct schema (format: SCHEMA.TABLE)",
                "Verify you have SELECT permission on this table",
            ],
        },
        "SQL compilation error": {
            "type": "SQLSyntaxError",
            "message": "There's a syntax error in your SQL query.",
            "suggestions": [
                "Check for missing commas or quotes",
                "Verify column names exist in the table",
                "Try simplifying the query to isolate the issue",
            ],
        },
        "Numeric value.*out of range": {
            "type": "NumericOverflow",
            "message": "A numeric value in your query result is too large.",
            "suggestions": [
                "Use CAST() to convert to a larger data type",
                "Apply filters to reduce the range of values",
                "Consider using TO_VARCHAR() for very large numbers",
            ],
        },
        "Invalid identifier": {
            "type": "InvalidIdentifier",
            "message": "A column or table name in your query is invalid.",
            "suggestions": [
                "Use double quotes for case-sensitive or special character names",
                "Check for typos in column/table names",
            ],
        },
        "Division by zero": {
            "type": "DivisionByZero",
            "message": "Your query attempted to divide by zero.",
            "suggestions": [
                "Add a WHERE clause to filter out zero denominators",
                "Use NULLIF() to handle zero values: field / NULLIF(divisor, 0)",
                "Use a CASE statement to handle zero denominators",
            ],
        },
        "authentication failed": {
            "type": "AuthenticationError",
            "message": "Failed to authenticate with Snowflake.",
            "suggestions": [
                "Check your SNOWFLAKE_USER and SNOWFLAKE_PASSWORD in .env",
                "Verify your Snowflake account name is correct",
                "Ensure your credentials haven't expired",
            ],
        },
        "Warehouse.*does not exist": {
            "type": "WarehouseNotFound",
            "message": "The specified warehouse doesn't exist or isn't accessible.",
            "suggestions": [
                "Check SNOWFLAKE_WAREHOUSE in your .env file",
                "Verify the warehouse name spelling",
                "Ensure the warehouse is running and not suspended",
            ],
        },
    }

    # ── Google Sheets error patterns ──────────────────────────────────────────
    SHEETS_ERRORS: Dict[str, dict] = {
        "403": {
            "type": "PermissionDenied",
            "message": "Access denied to the Google Sheet.",
            "suggestions": [
                "Share the sheet with your service account email",
                "Check GOOGLE_SERVICE_ACCOUNT_PATH points to the correct file",
                "Verify the service account has Editor or Viewer permissions",
            ],
        },
        "404": {
            "type": "SheetNotFound",
            "message": "The spreadsheet or sheet tab was not found.",
            "suggestions": [
                "Verify the spreadsheet ID is correct",
                "Check that the sheet tab name matches exactly (case-sensitive)",
                "Ensure the spreadsheet hasn't been deleted",
            ],
        },
        "Unable to parse range": {
            "type": "InvalidRange",
            "message": "The sheet range format is invalid.",
            "suggestions": [
                "Use A1 notation (e.g., 'Sheet1!A1:B10')",
                "Ensure the sheet name is correct",
                "Use single quotes for sheet names with spaces: 'My Sheet'!A1",
            ],
        },
        "INVALID_ARGUMENT": {
            "type": "InvalidArgument",
            "message": "Invalid argument provided to Google Sheets API.",
            "suggestions": [
                "Check that values are properly formatted",
                "Ensure range notation is correct",
            ],
        },
    }

    @staticmethod
    def handle_snowflake_error(error: Exception) -> Tuple[str, str, List[str]]:
        """Match a Snowflake exception to a known error pattern.

        Parameters
        ----------
        error:
            Exception raised by the Snowflake connector.

        Returns
        -------
        Tuple[str, str, List[str]]
            ``(error_type, user_message, suggestions)``
        """
        error_str = str(error).lower()
        for pattern, info in ErrorHandler.SNOWFLAKE_ERRORS.items():
            if re.search(pattern.lower(), error_str):
                return info["type"], info["message"], info["suggestions"]

        return (
            "SnowflakeError",
            "An error occurred while executing your Snowflake query.",
            [
                "Check the error details above",
                "Verify your SQL syntax is correct",
                "Try breaking down complex queries into simpler parts",
            ],
        )

    @staticmethod
    def handle_sheets_error(error: Exception) -> Tuple[str, str, List[str]]:
        """Match a Google Sheets API exception to a known error pattern.

        Parameters
        ----------
        error:
            Exception raised by the Google Sheets API client.

        Returns
        -------
        Tuple[str, str, List[str]]
            ``(error_type, user_message, suggestions)``
        """
        error_str = str(error)
        for pattern, info in ErrorHandler.SHEETS_ERRORS.items():
            if pattern in error_str:
                return info["type"], info["message"], info["suggestions"]

        return (
            "GoogleSheetsError",
            "An error occurred while accessing Google Sheets.",
            [
                "Verify the spreadsheet ID is correct",
                "Check that the service account has proper permissions",
                "Try the operation again — might be a temporary API issue",
            ],
        )

    @staticmethod
    def format_error_response(
        error: Exception,
        error_type: str,
        message: str,
        suggestions: List[str],
        query: Optional[str] = None,
    ) -> str:
        """Render a user-facing error response string.

        Parameters
        ----------
        error:
            Original exception (used for the technical details section).
        error_type:
            Short error category label.
        message:
            User-friendly description of what went wrong.
        suggestions:
            Ordered list of things to try.
        query:
            Optional SQL query that caused the error (shown in a code block).

        Returns
        -------
        str
            Markdown-formatted error response ready to send to the user.
        """
        response = f"❌ **{error_type}**\n\n{message}\n\n"

        if query:
            response += f"**Query:**\n```sql\n{query}\n```\n\n"

        response += "**💡 Suggestions:**\n"
        for i, suggestion in enumerate(suggestions, 1):
            response += f"{i}. {suggestion}\n"

        response += f"\n**Technical Details:**\n{error}"
        return response

    @staticmethod
    def suggest_fixes(error_type: str, context: Optional[Dict] = None) -> str:
        """Provide context-aware additional suggestions.

        Parameters
        ----------
        error_type:
            Short error category label from ``handle_snowflake_error`` /
            ``handle_sheets_error``.
        context:
            Optional dict with keys like ``available_tables``,
            ``available_columns``, or ``available_sheets``.

        Returns
        -------
        str
            Additional suggestion text, or ``""`` if no context-specific help
            is available.
        """
        if error_type == "TableNotFound" and context and context.get("available_tables"):
            tables = context["available_tables"]
            return "\n**Available tables:**\n" + "\n".join(f"  - {t}" for t in tables[:10])
        if error_type == "InvalidIdentifier" and context and context.get("available_columns"):
            columns = context["available_columns"]
            return "\n**Available columns:**\n" + "\n".join(f"  - {c}" for c in columns)
        if error_type == "SheetNotFound" and context and context.get("available_sheets"):
            sheets = context["available_sheets"]
            return "\n**Available sheets:**\n" + "\n".join(f"  - {s}" for s in sheets)
        return ""
