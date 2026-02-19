"""
agent/tool_definitions/sheets_tools.py
========================================

Google Sheets tools exposed to the LLM via FastMCP.

These tools form the "output layer" of the BI agent — after querying
Snowflake, the agent can persist and share results through Google Sheets.

Tool Responsibilities
---------------------
- ``create_new_sheet``         — Create a spreadsheet and auto-share with user.
- ``rename_sheet``             — Rename a spreadsheet.
- ``create_chart_in_sheet``    — Visualise data with a chart.
- ``save_resource_alias``      — Save a memorable name for a Sheet ID.
- ``list_resource_aliases``    — Show all saved aliases.
- ``prune_drive_files``        — Free Drive storage by removing old files.
- ``read_google_sheet``        — Read a range from a Sheet.
- ``replicate_data_to_sheet``  — Export Snowflake query results to a Sheet.

All tools resolve ``sheet_id_or_alias`` via ``ResourceManager.get_id()``
so users can refer to sheets by alias rather than opaque 44-char IDs.
"""

import datetime
import json
import logging

from pydantic import Field

from .registry import mcp
from ..config import Config
from ..tools.toolkit import Toolkit

logger = logging.getLogger(__name__)

_toolkit: Toolkit | None = None


def get_toolkit() -> Toolkit:
    """Return the lazy-initialised Toolkit singleton."""
    global _toolkit
    if _toolkit is None:
        _toolkit = Toolkit(Config.from_env())
    return _toolkit


@mcp.tool()
async def create_new_sheet(
    title: str = Field(..., description="Title for the new spreadsheet"),
) -> str:
    """Create a new Google Sheet and share it with the configured user email.

    After creation, the sheet is saved with an auto-generated alias
    (e.g. ``"q4_report"`` for a sheet titled ``"Q4 Report"``) so subsequent
    tools can reference it by name instead of ID.

    Parameters
    ----------
    title:
        Display name for the new spreadsheet.

    Returns
    -------
    str
        JSON with ``status``, ``spreadsheet_id``, ``alias``, and ``url``.
    """
    toolkit = get_toolkit()
    try:
        spreadsheet_id = toolkit.sheets.create_sheet(title)
    except Exception as create_error:
        # Check if this is a storage quota issue before generic error
        if "403" in str(create_error) or "quota" in str(create_error).lower():
            try:
                quota = toolkit.sheets.check_quota()
                usage = int(quota.get("usage", 0))
                limit = int(quota.get("limit", -1))
                if limit > 0 and usage >= limit:
                    return (
                        f"❌ Drive storage full ({usage / 1024 / 1024:.2f} MB / "
                        f"{limit / 1024 / 1024:.2f} MB).\n\n"
                        "Use `prune_drive_files` to free space."
                    )
            except Exception:
                pass
        return f"Error creating sheet: {create_error}"

    user_email = toolkit.config.google_sheets_user_email
    share_status = ""
    if user_email:
        try:
            toolkit.sheets.share_sheet(spreadsheet_id, user_email)
            share_status = f" and shared with {user_email}"
        except Exception as share_error:
            share_status = f" (Auto-share failed: {str(share_error)[:60]})"
    else:
        share_status = " (No user email configured for auto-share)"

    alias = title.lower().replace(" ", "_")
    toolkit.resources.save_alias(alias, spreadsheet_id)

    return json.dumps({
        "status": "success",
        "message": f"Created sheet '{title}'{share_status}",
        "spreadsheet_id": spreadsheet_id,
        "alias": alias,
        "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
    }, indent=2)


@mcp.tool()
async def rename_sheet(
    sheet_alias_or_id: str = Field(..., description="Sheet alias or ID to rename"),
    new_name: str = Field(..., description="New name for the sheet"),
) -> str:
    """Rename an existing Google Sheet and update the alias store.

    Parameters
    ----------
    sheet_alias_or_id:
        Current alias or raw spreadsheet ID.
    new_name:
        New display name for the sheet.

    Returns
    -------
    str
        Confirmation message with the sheet URL and new alias.
    """
    toolkit = get_toolkit()
    try:
        spreadsheet_id = toolkit.resources.get_id(sheet_alias_or_id)
        toolkit.sheets.rename_sheet(spreadsheet_id, new_name)
        new_alias = new_name.lower().replace(" ", "_")
        toolkit.resources.save_alias(new_alias, spreadsheet_id)
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        return f"✓ Renamed sheet to '{new_name}'\n\nURL: {url}\nNew alias: '{new_alias}'"
    except Exception as e:
        return f"Error renaming sheet: {e}"


@mcp.tool()
async def create_chart_in_sheet(
    spreadsheet_id: str = Field(..., description="Spreadsheet ID or alias"),
    sheet_name: str = Field(..., description="Sheet tab name containing the data"),
    chart_type: str = Field(..., description="Chart type: 'line', 'bar', 'column', 'pie', 'scatter', or 'area'"),
    data_range: str = Field(..., description="Data range in A1 notation (e.g., 'A1:B10')"),
    chart_title: str = Field(..., description="Title for the chart"),
) -> str:
    """Create a chart in a Google Sheet for visual insights.

    Use this after exporting data to visualise trends, comparisons, or proportions.

    Parameters
    ----------
    spreadsheet_id:
        Alias or raw spreadsheet ID.
    sheet_name:
        Worksheet tab name where the source data lives.
    chart_type:
        One of: ``line``, ``bar``, ``column``, ``pie``, ``scatter``, ``area``.
    data_range:
        A1 notation range covering headers + data (e.g. ``"A1:B10"``).
    chart_title:
        Title shown above the chart.

    Returns
    -------
    str
        Confirmation with the sheet URL.
    """
    toolkit = get_toolkit()
    try:
        actual_id = toolkit.resources.get_id(spreadsheet_id)
        service = toolkit.sheets.get_service()
        metadata = service.spreadsheets().get(spreadsheetId=actual_id).execute()

        sheet_id = next(
            (s["properties"]["sheetId"] for s in metadata.get("sheets", [])
             if s["properties"]["title"] == sheet_name),
            None,
        )
        if sheet_id is None:
            return f"Sheet tab '{sheet_name}' not found in this spreadsheet."

        toolkit.sheets.create_chart(
            spreadsheet_id=actual_id,
            sheet_id=sheet_id,
            chart_type=chart_type,
            data_range=data_range,
            title=chart_title,
            position_row=0,
            position_col=5,
        )
        url = f"https://docs.google.com/spreadsheets/d/{actual_id}"
        return f"✓ Created {chart_type} chart '{chart_title}' in '{sheet_name}'\n\nURL: {url}"
    except Exception as e:
        return f"Error creating chart: {e}"


@mcp.tool()
async def save_resource_alias(
    alias: str = Field(..., description="Alias name (e.g., 'finance_report')"),
    resource_id: str = Field(..., description="Resource ID to save (e.g., Spreadsheet ID)"),
) -> str:
    """Save a user-friendly alias for a resource ID.

    Parameters
    ----------
    alias:
        Short, memorable name.
    resource_id:
        The actual resource identifier (typically a Google Spreadsheet ID).

    Returns
    -------
    str
        Confirmation message.
    """
    toolkit = get_toolkit()
    toolkit.resources.save_alias(alias, resource_id)
    return f"Saved alias '{alias}' → '{resource_id}'."


@mcp.tool()
async def list_resource_aliases() -> str:
    """List all saved resource aliases.

    Returns
    -------
    str
        JSON mapping of alias → resource ID.
    """
    toolkit = get_toolkit()
    return json.dumps(toolkit.resources.list_aliases(), indent=2)


@mcp.tool()
async def prune_drive_files(
    max_files: int = 10,
    older_than_days: int = 30,
    dry_run: bool = True,
) -> str:
    """Free up Drive storage by deleting old Google Sheets/files.

    **Safe by default** — running without arguments lists files that *would*
    be deleted without actually deleting them.

    Parameters
    ----------
    max_files:
        Maximum number of files to delete (guards against mass deletion).
    older_than_days:
        Only target files created more than N days ago.
    dry_run:
        ``True`` → list only.  ``False`` → actually delete.

    Returns
    -------
    str
        List of files (dry run) or deletion report (live run).
    """
    toolkit = get_toolkit()
    try:
        files = toolkit.sheets.list_files(page_size=100)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=older_than_days)

        candidates = []
        for f in files:
            try:
                created = datetime.datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00"))
                if created < cutoff:
                    candidates.append(f)
            except Exception:
                continue

        candidates.sort(key=lambda x: x.get("createdTime", ""))
        targets = candidates[:max_files]

        if not targets:
            return f"No files found older than {older_than_days} days."

        summary = [f"Found {len(targets)} files older than {older_than_days} days:"]
        for f in targets:
            summary.append(f"- {f.get('name')} (ID: {f.get('id')}) — {f.get('createdTime')}")

        if dry_run:
            return "🔍 [DRY RUN] Files **would** be deleted:\n\n" + "\n".join(summary) + "\n\n⚠️ Use `dry_run=False` to actually delete."

        deleted, log = 0, []
        for f in targets:
            try:
                toolkit.sheets.delete_file(f["id"])
                deleted += 1
                log.append(f"✓ Deleted: {f.get('name')}")
            except Exception as e:
                log.append(f"✗ Failed: {f.get('name')}: {e}")

        return f"🗑️ Pruned {deleted} files.\n\n" + "\n".join(log)
    except Exception as e:
        return f"Error pruning files: {e}"


@mcp.tool()
async def read_google_sheet(spreadsheet_id: str, range_name: str) -> str:
    """Read data from a Google Sheet range.

    Parameters
    ----------
    spreadsheet_id:
        Google Sheet ID or saved alias.
    range_name:
        A1 notation range (e.g. ``"Sheet1!A1:B10"``).

    Returns
    -------
    str
        JSON-encoded 2D list of cell values.
    """
    toolkit = get_toolkit()
    actual_id = toolkit.resources.get_id(spreadsheet_id)
    try:
        values = toolkit.sheets.read_sheet(actual_id, range_name)
        return json.dumps(values, indent=2)
    except Exception as e:
        error_type, message, suggestions = toolkit.error_handler.handle_sheets_error(e)
        return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)


@mcp.tool()
async def replicate_data_to_sheet(
    spreadsheet_id: str,
    sheet_name: str,
    query: str | None = None,
) -> str:
    """Execute a Snowflake query and write results to a Google Sheet tab.

    If no query is provided, re-uses the last successfully executed query.

    **Agent guidance:** If the user requests a specific report without providing
    SQL, explore the database schema first (``_list_tables_internal``), generate
    an appropriate SQL query, and pass it here — do NOT ask the user for SQL.

    Parameters
    ----------
    spreadsheet_id:
        Google Sheet ID or alias.
    sheet_name:
        Worksheet tab name.  Created automatically if it doesn't exist.
    query:
        SQL SELECT statement.  Optional — defaults to the last executed query.

    Returns
    -------
    str
        Success message with row count and sheet URL, or error details.
    """
    import time
    toolkit = get_toolkit()

    if not query:
        if toolkit.snowflake.last_executed_query:
            query = toolkit.snowflake.last_executed_query
            logger.info("replicate_data_to_sheet: reusing last query")
        else:
            return "No query provided and no previous query in history. Please provide a SQL query."

    actual_id = toolkit.resources.get_id(spreadsheet_id)
    start = time.time()

    try:
        # Ensure the target tab exists
        available = toolkit.sheets.get_sheet_names(actual_id)
        if sheet_name not in available:
            toolkit.sheets.add_worksheet(actual_id, sheet_name)

        results = toolkit.snowflake.query(query)
        if not results:
            return "No data returned from Snowflake query."

        headers = list(results[0].keys())
        rows = []
        for row in results:
            clean = []
            for val in row.values():
                if hasattr(val, "isoformat"):
                    clean.append(val.isoformat())
                elif hasattr(val, "quantize"):
                    clean.append(float(val))
                else:
                    clean.append(val)
            rows.append(clean)

        write_result = toolkit.sheets.write_sheet(actual_id, f"{sheet_name}!A1", [headers] + rows)
        elapsed = int((time.time() - start) * 1000)

        return (
            f"✅ Replicated {len(rows)} rows to '{sheet_name}' in {elapsed}ms.\n"
            f"URL: https://docs.google.com/spreadsheets/d/{actual_id}"
        )

    except Exception as e:
        if "404" in str(e) or "INVALID_ARGUMENT" in str(e):
            return (
                f"Sheet ID '{spreadsheet_id}' not found.\n\n"
                "Create a new sheet first with `create_new_sheet`, then replicate."
            )
        return f"Error replicating data: {e}"
