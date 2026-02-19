import json
import logging
from typing import Optional


from fastmcp import FastMCP

from .config import Config
from .tools import Toolkit

# Configure logging
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Snowflake Agent")

# Global instances
_toolkit: Toolkit | None = None

def get_toolkit() -> Toolkit:
    """Get or create the toolkit singleton."""
    global _toolkit
    if _toolkit is None:
        config = Config()
        # Initialize toolkit (lazy loading of connections)
        _toolkit = Toolkit(config)
    return _toolkit

# ========================================
# CORE QUERY TOOLS
# ========================================

@mcp.tool()
async def search_snowflake(query: str) -> str:
    """Execute a SQL query against Snowflake.
    
    Use this tool to look up data, find accounts, or retrieve metrics.
    Ensure strict SQL syntax.
    """
    from .tools import format_as_table
    
    toolkit = get_toolkit()
    
    try:
        results = toolkit.snowflake.query(query)
        return format_as_table(results)
    except Exception as e:
        error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
        return toolkit.error_handler.format_error_response(e, error_type, message, suggestions, query)


@mcp.tool()
async def fetch_account_details(account_name: str) -> str:
    """Fetch detailed information for a specific account from Snowflake.
    This is a helper tool that queries the FINANCIAL_SUMMARY table.
    """
    query = f"SELECT * FROM FINANCIALS.PUBLIC.FINANCIAL_SUMMARY WHERE ACCOUNT_NAME ILIKE '%{account_name}%' LIMIT 1"
    return await search_snowflake(query)

# ========================================
# DATA PREVIEW & EXPLORATION TOOLS
# ========================================

@mcp.tool()
async def preview_table(table_name: str, limit: int = 10) -> str:
    """Preview the first N rows of a table.
    
    Args:
        table_name: Table name (can include schema, e.g., SCHEMA.TABLE or just TABLE)
        limit: Number of rows to preview (default: 10)
    """
    from .tools import format_as_table
    toolkit = get_toolkit()
    
    # If table_name doesn't include schema, try to find it
    if '.' not in table_name:
        # Try current schema first
        try:
            results = toolkit.snowflake.query(f"SELECT * FROM {table_name} LIMIT {limit}")
            return format_as_table(results)
        except:
            # Search for the table in other schemas
            try:
                # Get all schemas in current database
                schemas_result = toolkit.snowflake.query("SHOW SCHEMAS", use_cache=False)
                
                # Try each schema
                for row in schemas_result:
                    schema = row.get("name", row.get("NAME", ""))
                    if schema and schema != "INFORMATION_SCHEMA":
                        try:
                            qualified_table = f"{schema}.{table_name}"
                            results = toolkit.snowflake.query(f"SELECT * FROM {qualified_table} LIMIT {limit}")
                            return format_as_table(results)
                        except:
                            continue
                            
                # If we get here, table wasn't found
                return f"❌ Table '{table_name}' not found in any schema.\n\nTry:\n1. Use `list_tables()` to see available tables\n2. Specify the full table name including schema (e.g., PUBLIC.{table_name})"
            except Exception as e:
                error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
                return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)
    else:
        # Table name includes schema, use it directly
        try:
            results = toolkit.snowflake.query(f"SELECT * FROM {table_name} LIMIT {limit}")
            return format_as_table(results)
        except Exception as e:
            error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
            return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)



@mcp.tool()
async def get_table_schema(table_name: str) -> str:
    """Get column information for a table.
    
    Args:
        table_name: Table name (can include schema)
    """
    toolkit = get_toolkit()
    try:
        info = toolkit.snowflake.get_table_info(table_name)
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
        return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)

@mcp.tool()
async def get_table_stats(table_name: str) -> str:
    """Get statistics about a table (row count, size, etc.).
    
    Args:
        table_name: Table name (can include schema)
    """
    query = f"SELECT COUNT(*) as row_count FROM {table_name}"
    return await search_snowflake(query)

@mcp.tool()
async def list_tables(schema_name: str = "") -> str:
    """List all tables in the current schema or a specified schema.
    
    Args:
        schema_name: Optional schema name. If empty, uses current schema from config.
    
    Returns:
        Clean formatted list of tables
    """
    toolkit = get_toolkit()
    try:
        if schema_name:
            query = f"SHOW TABLES IN SCHEMA {schema_name}"
        else:
            # Use current database and schema from config
            query = "SHOW TABLES"
        
        results = toolkit.snowflake.query(query, use_cache=False)
        
        # Snowflake SHOW TABLES returns multiple columns; extract relevant ones
        tables = []
        for row in results:
            tables.append({
                "SCHEMA": row.get("schema_name", row.get("SCHEMA_NAME", "")),
                "TABLE": row.get("name", row.get("NAME", "")),
                "TYPE": row.get("kind", row.get("KIND", "TABLE")),
                "ROWS": row.get("rows", row.get("ROWS", 0))
            })
        
        from .tools import format_as_table
        return format_as_table(tables)
    except Exception as e:
        error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
        return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)

@mcp.tool()
async def list_schemas(database_name: str = "") -> str:
    """List all schemas in the current database or a specified database.
    
    Args:
        database_name: Optional database name. If empty, uses current database from config.
    
    Returns:
        Clean formatted list of schemas
    """
    toolkit = get_toolkit()
    try:
        if database_name:
            query = f"SHOW SCHEMAS IN DATABASE {database_name}"
        else:
            query = "SHOW SCHEMAS"
        
        results = toolkit.snowflake.query(query, use_cache=False)
        
        schemas = []
        for row in results:
            created_on = row.get("created_on", row.get("CREATED_ON", ""))
            # Convert datetime to string if needed
            if hasattr(created_on, 'isoformat'):
                created_on = created_on.isoformat()
            
            db_name = row.get("database_name", row.get("DATABASE_NAME", ""))
            schema_name = row.get("name", row.get("NAME", ""))
            
            # Construct fully qualified name if database is known
            full_schema_name = f"{db_name}.{schema_name}" if db_name else schema_name
            
            schemas.append({
                "DATABASE": db_name,
                "SCHEMA": full_schema_name, # Return fully qualified name
                "CREATED": str(created_on)[:10] if created_on else ""  # Just the date
            })
        
        from .tools import format_as_table
        return format_as_table(schemas)
    except Exception as e:
        error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
        return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)

@mcp.tool()
async def list_databases() -> str:
    """List all databases accessible to the current user.
    
    Returns:
        Clean formatted list of databases
    """
    toolkit = get_toolkit()
    try:
        query = "SHOW DATABASES"
        results = toolkit.snowflake.query(query, use_cache=False)
        
        databases = []
        for row in results:
            created_on = row.get("created_on", row.get("CREATED_ON", ""))
            # Convert datetime to string if needed
            if hasattr(created_on, 'isoformat'):
                created_on = created_on.isoformat()
            
            databases.append({
                "DATABASE": row.get("name", row.get("NAME", "")),
                "OWNER": row.get("owner", row.get("OWNER", "")),
                "CREATED": str(created_on)[:10] if created_on else ""  # Just the date
            })
        
        from .tools import format_as_table
        return format_as_table(databases)
    except Exception as e:
        error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
        return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)



@mcp.tool()
async def profile_data(query: str) -> str:
    """Get statistical profile of query results (count, nulls, distinct values).
    
    This tool analyzes each column in the result set.
    
    Args:
        query: SQL query to profile
    """
    toolkit = get_toolkit()
    try:
        # Execute the query
        results = toolkit.snowflake.query(query)
        
        if not results:
            return "No data to profile"
        
        # Analyze each column
        profile = {
            "total_rows": len(results),
            "columns": {}
        }
        
        # Get column names
        if results:
            for col_name in results[0].keys():
                values = [row.get(col_name) for row in results]
                non_null_values = [v for v in values if v is not None]
                
                profile["columns"][col_name] = {
                    "non_null_count": len(non_null_values),
                    "null_count": len(values) - len(non_null_values),
                    "null_percentage": round((len(values) - len(non_null_values)) / len(values) * 100, 2),
                    "distinct_count": len(set(str(v) for v in non_null_values)),
                    "sample_values": list(set(str(v) for v in non_null_values))[:5]
                }
        
        return json.dumps(profile, indent=2)
    except Exception as e:
        return f"Error profiling data: {str(e)}"

# ========================================
# EXPORT TOOLS
# ========================================

@mcp.tool()
async def export_to_excel(query: str, filename: str) -> str:
    """Execute a query and save results to a local Excel (.xlsx) file.
    
    Args:
        query: The SQL query to execute
        filename: The name of the file to save (e.g., 'report.xlsx')
    """
    toolkit = get_toolkit()
    try:
        results = toolkit.snowflake.query(query)
        if not results:
            return "No data found."
            
        path = toolkit.export_to_excel(results, filename)
        return f"Successfully saved Excel file to: {path}"
    except Exception as e:
        return f"Error creating Excel: {str(e)}"

@mcp.tool()
async def export_to_csv(query: str, filename: str) -> str:
    """Execute a query and save results to a CSV file.
    
    Args:
        query: The SQL query to execute
        filename: The name of the file to save (e.g., 'report.csv')
    """
    toolkit = get_toolkit()
    try:
        results = toolkit.snowflake.query(query)
        if not results:
            return "No data found."
            
        path = toolkit.export_to_csv(results, filename)
        return f"Successfully saved CSV file to: {path}"
    except Exception as e:
        return f"Error creating CSV: {str(e)}"

@mcp.tool()
async def export_to_json(query: str, filename: str) -> str:
    """Execute a query and save results to a JSON file.
    
    Args:
        query: The SQL query to execute
        filename: The name of the file to save (e.g., 'report.json')
    """
    toolkit = get_toolkit()
    try:
        results = toolkit.snowflake.query(query)
        if not results:
            return "No data found."
            
        path = toolkit.export_to_json(results, filename)
        return f"Successfully saved JSON file to: {path}"
    except Exception as e:
        return f"Error creating JSON: {str(e)}"

# ========================================
# BATCH OPERATIONS
# ========================================

@mcp.tool()
async def batch_query(queries: str) -> str:
    """Execute multiple queries in batch (provide as JSON array).
    
    Args:
        queries: JSON array of SQL queries, e.g., '["SELECT 1", "SELECT 2"]'
    
    Returns:
        JSON array of results, one per query
    """
    toolkit = get_toolkit()
    
    try:
        query_list = json.loads(queries)
    except json.JSONDecodeError:
        return "Error: queries must be a valid JSON array"
    
    results = []
    for i, query in enumerate(query_list):
        try:
            result = toolkit.snowflake.query(query)
            results.append({
                "query_index": i,
                "status": "success",
                "row_count": len(result),
                "data": result[:10]  # Only return first 10 rows per query
            })
        except Exception as e:
            results.append({
                "query_index": i,
                "status": "error",
                "error": str(e)
            })
    
    return json.dumps(results, indent=2, default=str)

# ========================================
# COST ESTIMATION
# ========================================

@mcp.tool()
async def estimate_query_cost(query: str) -> str:
    """Estimate the cost/complexity of a query before execution.
    
    Shows the query execution plan to help understand resource usage.
    
    Args:
        query: SQL query to analyze
    """
    toolkit = get_toolkit()
    try:
        plan = toolkit.snowflake.explain_query(query)
        return f"Query Execution Plan:\n\n{plan}\n\nNote: Use this plan to estimate complexity. Large scans and joins may incur higher costs."
    except Exception as e:
        return f"Error getting query plan: {str(e)}"

# ========================================
# GOOGLE SHEETS TOOLS
# ========================================

@mcp.tool()
async def save_resource_alias(alias: str, resource_id: str) -> str:
    """Save a user-friendly alias for a resource ID (e.g., Spreadsheet ID).
    
    Example: save_resource_alias("finance_report", "1Bxi...")
    """
    toolkit = get_toolkit()
    toolkit.resources.save_alias(alias, resource_id)
    return f"Saved alias '{alias}' for resource '{resource_id}'."

@mcp.tool()
async def list_resource_aliases() -> str:
    """List all saved resource aliases."""
    toolkit = get_toolkit()
    return json.dumps(toolkit.resources.list_aliases(), indent=2)

@mcp.tool()
async def read_google_sheet(spreadsheet_id: str, range_name: str) -> str:
    """Read data from a Google Sheet.
    
    Args:
        spreadsheet_id: The ID of the Google Sheet OR a saved alias
        range_name: The A1 notation of the range to read (e.g., 'Sheet1!A1:B10')
    """
    toolkit = get_toolkit()
    # Resolve alias
    actual_id = toolkit.resources.get_id(spreadsheet_id)
    
    try:
        values = toolkit.sheets.read_sheet(actual_id, range_name)
        return json.dumps(values, indent=2)
    except Exception as e:
        error_type, message, suggestions = toolkit.error_handler.handle_sheets_error(e)
        return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)

@mcp.tool()
async def replicate_data_to_sheet(query: str, spreadsheet_id: str, sheet_name: str) -> str:
    """Execute a Snowflake query and replicate the results to a Google Sheet.
    Includes smart error handling for missing sheets.
    """
    toolkit = get_toolkit()
    # Resolve alias
    actual_id = toolkit.resources.get_id(spreadsheet_id)
    start_time = time.time()
    
    try:
        # Check sheet name validity first
        try:
            available_sheets = toolkit.sheets.get_sheet_names(actual_id)
            if sheet_name not in available_sheets:
                # If only one sheet exists, default to it
                if len(available_sheets) == 1:
                    logger.info(f"Sheet '{sheet_name}' not found. Defaulting to '{available_sheets[0]}'.")
                    sheet_name = available_sheets[0]
                else:
                    return f"Error: Sheet '{sheet_name}' not found. Available sheets: {', '.join(available_sheets)}"
        except Exception as e:
             if "403" in str(e):
                 return f"Error: Permission denied. Please share the sheet with your service account."
             return f"Error accessing sheet metadata: {str(e)}"

        # 1. Get data from Snowflake
        results = toolkit.snowflake.query(query)
        if not results:
            return "No data found in Snowflake to replicate."
            
        # 2. Prepare data
        headers = list(results[0].keys())
        rows = [list(row.values()) for row in results]
        all_values = [headers] + rows
        
        # 3. Write to Sheets
        range_name = f"{sheet_name}!A1"
        toolkit.sheets.write_sheet(actual_id, range_name, all_values)
        
        execution_time = (time.time() - start_time) * 1000
        
        # Log to audit
        toolkit.audit.log_operation(
            tool_name='replicate_data_to_sheet',
            parameters={'query': query[:200], 'spreadsheet_id': actual_id, 'sheet_name': sheet_name},
            status='success',
            execution_time_ms=execution_time,
            result_summary={'row_count': len(rows)}
        )
        
        return f"Successfully replicated {len(rows)} rows to '{sheet_name}' in sheet '{actual_id}'."
        
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        toolkit.audit.log_operation(
            tool_name='replicate_data_to_sheet',
            parameters={'query': query[:200], 'spreadsheet_id': actual_id, 'sheet_name': sheet_name},
            status='error',
            execution_time_ms=execution_time,
            error=str(e)
        )
        return f"Error replicating data: {str(e)}"


