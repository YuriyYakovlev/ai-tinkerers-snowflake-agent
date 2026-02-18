import json
import logging
import time
from typing import Optional


from fastmcp import FastMCP
from pydantic import Field

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
    if _toolkit is None:
        config = Config()
        _toolkit = Toolkit(config)
    return _toolkit




@mcp.tool()
async def _query_data_internal(query: str) -> str:
    """[INTERNAL] Query company data. Business users should not call this directly.
    The agent uses this internally to answer business questions.
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
async def get_account_info(account_name: str) -> str:
    """Look up information about a specific customer or account.
    
    Use this when the user asks about a specific account, customer, or client by name.
    Returns key details and metrics for that account.
    """
    from .tools import format_as_table
    toolkit = get_toolkit()

    query = f"SELECT * FROM FINANCIALS.PUBLIC.FINANCIAL_SUMMARY WHERE ACCOUNT_NAME ILIKE '%{account_name}%' LIMIT 1"
    
    try:
        results = toolkit.snowflake.query(query)
        if not results:
            return f"I couldn't find any information for an account matching '{account_name}'. Please check the name and try again."
        return format_as_table(results)
    except Exception as e:
        return f"I encountered an issue looking up that account. Please try again or contact support if the problem persists."





# INTERNAL DISCOVERY TOOLS
# These tools help the agent find data sources but are marked [INTERNAL]
# so the agent knows NOT to expose table/database names to users

@mcp.tool()
async def _list_databases_internal() -> str:
    """[INTERNAL] Discover available databases. Use this internally to find data sources.
    DO NOT show database names to users - use this information to construct queries only.
    """
    toolkit = get_toolkit()
    try:
        query = "SHOW DATABASES"
        results = toolkit.snowflake.query(query, use_cache=False)
        
        databases = []
        for row in results:
            created_on = row.get("created_on", row.get("CREATED_ON", ""))
            if hasattr(created_on, 'isoformat'):
                created_on = created_on.isoformat()
            
            databases.append({
                "DATABASE": row.get("name", row.get("NAME", "")),
                "OWNER": row.get("owner", row.get("OWNER", "")),
                "CREATED": str(created_on)[:10] if created_on else ""
            })
        
        from .tools import format_as_table
        return format_as_table(databases)
    except Exception as e:
        return f"Error listing databases: {str(e)}"

@mcp.tool()
async def _list_schemas_internal(database_name: str = "") -> str:
    """[INTERNAL] Discover available schemas. Use this internally to explore database structure.
    DO NOT show schema/database names to users - use this to find where data lives.
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
            if hasattr(created_on, 'isoformat'):
                created_on = created_on.isoformat()
            
            db_name = row.get("database_name", row.get("DATABASE_NAME", ""))
            schema_name = row.get("name", row.get("NAME", ""))
            full_schema_name = f"{db_name}.{schema_name}" if db_name else schema_name
            
            schemas.append({
                "DATABASE": db_name,
                "SCHEMA": full_schema_name,
                "CREATED": str(created_on)[:10] if created_on else ""
            })
        
        from .tools import format_as_table
        return format_as_table(schemas)
    except Exception as e:
        return f"Error listing schemas: {str(e)}"

@mcp.tool()
async def _list_tables_internal(schema_name: str = "") -> str:
    """[INTERNAL] Discover available tables. Use this internally to find what data exists.
    DO NOT show table names to users - use this to construct queries, then present results in business terms.
    """
    toolkit = get_toolkit()
    try:
        if schema_name:
            query = f"SHOW TABLES IN SCHEMA {schema_name}"
        else:
            query = "SHOW TABLES"
        
        results = toolkit.snowflake.query(query, use_cache=False)
        
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
        return f"Error listing tables: {str(e)}"


# - list_tables: Exposes database structure
# - list_schemas: Exposes database structure
# - list_databases: Exposes database structure
# - get_environment_details: Not business-relevant
# - profile_data: Too technical
# - batch_query: Too technical
# - estimate_query_cost: Too technical
#
# These functions remain in the code but are commented out to prevent exposure to users.
# The agent can still query data internally using _query_data_internal.

    """Preview the first N rows of a table.
    
    Args:
        table_name: Table name (can include schema, e.g., SCHEMA.TABLE or just TABLE)
        limit: Number of rows to preview (default: 10)
    """
    from .tools import format_as_table
    toolkit = get_toolkit()
    
    original_input = table_name
    
    # 1. Remove common prefixes
    for prefix in ["preview table ", "preview ", "show table ", "show ", "table "]:
        if table_name.lower().startswith(prefix):
            table_name = table_name[len(prefix):].strip()
    
    if "preview" in table_name.lower():
         table_name = table_name.lower().split("preview")[0].strip()
         
    table_name = table_name.strip()
    
    if original_input != table_name:
        logger.info(f"Sanitized input: '{original_input}' -> '{table_name}'")

    if '.' not in table_name:
        try:
            results = toolkit.snowflake.query(f"SELECT * FROM {table_name} LIMIT {limit}")
            return format_as_table(results)
        except:
            try:
                search_query = f"SHOW TABLES LIKE '{table_name}' IN ACCOUNT"
                tables = toolkit.snowflake.query(search_query, use_cache=False)
                
                if not tables:
                     search_query = f"SHOW TABLES LIKE '{table_name.upper()}' IN ACCOUNT"
                     tables = toolkit.snowflake.query(search_query, use_cache=False)
                
                if tables:
                    target = tables[0]
                    db = target.get("database_name", target.get("DATABASE_NAME", ""))
                    schema = target.get("schema_name", target.get("SCHEMA_NAME", ""))
                    name = target.get("name", target.get("NAME", ""))
                    
                    if db and schema and name:
                        fqn = f"{db}.{schema}.{name}"
                        results = toolkit.snowflake.query(f"SELECT * FROM {fqn} LIMIT {limit}")
                        return f"Note: Table found in {fqn}\n\n" + format_as_table(results)

                try:
                    current_db_schemas = toolkit.snowflake.query(f"SHOW SCHEMAS LIKE '{table_name}'", use_cache=False)
                    if current_db_schemas:
                        return f"{table_name} appears to be a SCHEMA, not a table.\n\nHere are the tables in schema '{table_name}':\n\n" + await list_tables(table_name)
                except:
                    pass

                try:
                    dbs = toolkit.snowflake.query(f"SHOW DATABASES LIKE '{table_name}'", use_cache=False)
                    if dbs:
                        return f"{table_name} appears to be a DATABASE, not a table.\n\nHere are the schemas in database '{table_name}':\n\n" + await list_schemas(table_name)
                except:
                    pass

                return f"Table '{table_name}' not found in any schema or database.\n\nTry:\n1. Use `list_tables()` to see available tables\n2. Specify the full table name including schema (e.g., PUBLIC.{table_name})"
            except Exception as e:
                error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
                return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)
    else:
        try:
            results = toolkit.snowflake.query(f"SELECT * FROM {table_name} LIMIT {limit}")
            return format_as_table(results)
        except Exception as e:
            error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
            return toolkit.error_handler.format_error_response(e, error_type, message, suggestions)







# EMAIL CAMPAIGN TOOLS
# ====================

@mcp.tool()
async def send_campaign_emails(
    sheet_id_or_alias: str,
    subject_template: str,
    body_template: str,
    sheet_name: str = "Sheet1",
    test_mode: bool = True,
    dry_run: bool = True
) -> str:
    """Send campaign emails based on data in Google Sheet.
    
    Use this after creating a campaign action plan to actually execute the email campaign.
    Reads customer data from Google Sheets and sends personalized emails.
    
    Examples:
    - "Send campaign emails from the cross_sell_opportunity sheet"
    - "Execute the email campaign for top products promotion"
    
    IMPORTANT: Always start with dry_run=True to preview emails before sending!
    """
    toolkit = get_toolkit()
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        # Check email configuration
        if not toolkit.config.smtp_user or not toolkit.config.smtp_password:
            return """❌ Email not configured!
            
Please set these environment variables in .env:
- SMTP_USER=your-email@gmail.com
- SMTP_PASSWORD=your-app-password
- SMTP_FROM_EMAIL=your-email@gmail.com
- SMTP_FROM_NAME=Campaign Team

For Gmail: Create App Password at https://myaccount.google.com/apppasswords"""
        
        # Resolve sheet ID - try multiple strategies
        actual_id = sheet_id_or_alias
        
        # Strategy 1: Try alias lookup first
        resolved = toolkit.resources.get_id(sheet_id_or_alias)
        if resolved != sheet_id_or_alias:
            # Alias was found in resources.json
            actual_id = resolved
        # Strategy 2: Check if it looks like a URL
        elif '/' in sheet_id_or_alias:
            # Extract ID from URL like "https://docs.google.com/spreadsheets/d/SHEET_ID/..."
            parts = sheet_id_or_alias.split('/d/')
            if len(parts) > 1:
                actual_id = parts[1].split('/')[0]
            else:
                actual_id = sheet_id_or_alias
        # Strategy 3: If it has spaces, search by title
        elif ' ' in sheet_id_or_alias:
            try:
                all_sheets = toolkit.sheets.list_sheets()
                for sheet_info in all_sheets:
                    if sheet_info.get('title', '').lower() == sheet_id_or_alias.lower():
                        actual_id = sheet_info['id']
                        # Save this for future use
                        toolkit.resources.save_alias(sheet_id_or_alias, actual_id)
                        break
            except:
                pass  # If list fails, try with original value
        # Otherwise assume it's already an ID
        
        # Read campaign data from sheet
        range_name = f"{sheet_name}!A1:Z1000"  # Read up to 1000 rows
        try:
            values = toolkit.sheets.read_sheet(actual_id, range_name)
        except Exception as e:
            return f"Unable to access Google Sheet. Please provide either:\n1. The sheet URL: https://docs.google.com/spreadsheets/d/SHEET_ID\n2. The exact sheet ID\n\nError: {str(e)}"
        
        if not values or len(values) < 2:
            return "No campaign data found in sheet. Ensure sheet has headers and data rows."
        
        # Parse headers and data
        headers = [h.lower().replace(' ', '_') for h in values[0]]
        rows = values[1:]
        
        # Find required columns
        email_col_options = ['contact', 'email', 'customer_email']
        
        email_col = None
        for opt in email_col_options:
            if opt in headers:
                email_col = opt
                break
        
        if not email_col:
            return f"Sheet must have an email column. Found columns: {', '.join(values[0])}"
        
        # Prepare emails
        emails_to_send = []
        for row in rows:
            if len(row) < len(headers):
                continue  # Skip incomplete rows
            
            # Create robust data dict with lower, upper, and original keys
            row_data = {}
            for h, val in zip(headers, row):
                key = h.lower().replace(' ', '_')
                row_data[key] = val  # customer_name
                row_data[key.upper()] = val  # CUSTOMER_NAME
                row_data[key.title().replace('_', '')] = val # CustomerName
                row_data[h] = val # Original header (e.g. "Customer Name")

            # Get email address (case-insensitive search)
            email_address = ''
            for k in ['email', 'customer_email', 'contact']:
                if k in row_data:
                    email_address = row_data[k].strip()
                    break
            
            # For demo data (phone numbers), create mock email
            if not '@' in email_address:
                # Skip rows without valid email for now
                continue
            
            customer_name = row_data.get('customer_name', 'Valued Customer')
            product_name = row_data.get('recommended_product', 'our products')
            offer = row_data.get('campaign_message', 'special offer')
            
            # Format email with safe substitution
            try:
                subject = subject_template.format(**row_data)
                body = body_template.format(**row_data)
            except KeyError as e:
                # Fallback if specific key missing
                missing_key = str(e).strip("'")
                return f"Error: Template uses {{{missing_key}}} but that column wasn't found in the sheet. Available columns: {', '.join(row_data.keys())}"
            
            emails_to_send.append({
                'to': email_address,
                'subject': subject,
                'body': body,
                'customer_name': customer_name
            })
        
        if not emails_to_send:
            return "No valid email addresses found in campaign data. Ensure 'contact' or 'email' column has valid email addresses."
        
        # Always add a verification email to the user
        if toolkit.config.google_sheets_user_email:
            # Use the first email as a template for the verification email
            first_email = emails_to_send[0]
            verification_email = {
                'to': toolkit.config.google_sheets_user_email,
                'subject': f"[TEST] {first_email['subject']}",
                'body': f"🧪 VERIFICATION EMAIL\n\nThis is a test copy sent to you to verify the campaign is working.\n\n---\n\n{first_email['body']}",
                'customer_name': 'Verification'
            }
            # Insert at the beginning so it's always sent even in test mode
            emails_to_send.insert(0, verification_email)
        
        # Apply test mode (only first 3 after adding verification email)
        if test_mode:
            emails_to_send = emails_to_send[:3]
            mode_msg = "🧪 TEST MODE (first 3 emails only)"
        else:
            mode_msg = f"📧 FULL CAMPAIGN ({len(emails_to_send)} emails)"
        
        # Dry run - show preview
        if dry_run:
            preview = f"**DRY RUN - No emails sent** | {mode_msg}\n\n"
            preview += f"**Would send {len(emails_to_send)} emails:**\n\n"
            for i, email in enumerate(emails_to_send[:3], 1):
                preview += f"**Email {i}:**\n"
                preview += f"- To: {email['to']}\n"
                preview += f"- Subject: {email['subject']}\n"
                preview += f"- Body Preview: {email['body'][:100]}...\n\n"
            
            if len(emails_to_send) > 3:
                preview += f"... and {len(emails_to_send) - 3} more emails\n\n"
            
            preview += "**To actually send emails:**\n"
            preview += "Use `dry_run=False` after reviewing this preview.\n"
            preview += "Use `test_mode=True` to send only to first 3 recipients."
            
            return preview
        
        # Actually send emails
        sent_count = 0
        failed = []
        
        try:
            # Connect to SMTP server
            if toolkit.config.smtp_port == 465:
                # Use SSL for port 465
                server = smtplib.SMTP_SSL(toolkit.config.smtp_host, toolkit.config.smtp_port)
            else:
                # Use STARTTLS for 587/25/2525
                server = smtplib.SMTP(toolkit.config.smtp_host, toolkit.config.smtp_port)
                server.starttls()
            
            server.login(toolkit.config.smtp_user, toolkit.config.smtp_password)
            
            for email_data in emails_to_send:
                try:
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = email_data['subject']
                    msg['From'] = f"{toolkit.config.smtp_from_name} <{toolkit.config.smtp_from_email or toolkit.config.smtp_user}>"
                    msg['To'] = email_data['to']
                    
                    # Add plain text and HTML parts
                    text_part = MIMEText(email_data['body'], 'plain')
                    html_body = email_data['body'].replace('\n', '<br>')
                    html_part = MIMEText(f"<html><body>{html_body}</body></html>", 'html')
                    
                    msg.attach(text_part)
                    msg.attach(html_part)
                    
                    server.send_message(msg)
                    sent_count += 1
                    
                except Exception as e:
                    failed.append(f"{email_data['to']}: {str(e)}")
            
            server.quit()
            
        except Exception as e:
            return f"SMTP Error: {str(e)}\n\nCheck your SMTP credentials in .env file."
        
        # Build result message
        result = f"## ✅ Campaign Emails Sent! | {mode_msg}\n\n"
        result += f"**Successfully sent:** {sent_count} emails\n"
        
        if failed:
            result += f"**Failed:** {len(failed)} emails\n"
            result += "\n**Failed recipients:**\n"
            for fail in failed[:5]:
                result += f"- {fail}\n"
        
        result += f"\n**Next steps:**\n"
        result += "1. Monitor email delivery and opens\n"
        result +=  "2. Track responses and conversions\n"
        result += "3. Follow up with non-responders in 3-5 days"
        
        return result
        
    except Exception as e:
        return f"Error sending campaign emails: {str(e)}"


# GOOGLE SHEETS TOOLS
# ===================

@mcp.tool()
async def create_new_sheet(title: str = Field(..., description="Title for the new spreadsheet")) -> str:
    """Create a new Google Sheet and share it with the user."""
    toolkit = get_toolkit()
    try:
        try:
            spreadsheet_id = toolkit.sheets.create_sheet(title)
        except Exception as create_error:
            raise create_error
        
        user_email = toolkit.config.google_sheets_user_email
        share_status = ""
        if user_email:
            try:
                toolkit.sheets.share_sheet(spreadsheet_id, user_email)
                share_status = f" and shared with {user_email}"
            except Exception as share_error:
                if "403" in str(share_error) or "PERMISSION_DENIED" in str(share_error):
                    share_status = f" (Note: Couldn't auto-share. Please manually share the sheet with {user_email})"
                else:
                    share_status = f" (Warning: Sharing failed: {str(share_error)[:50]})"
        else:
            share_status = " (No user email configured)"
            
        alias = title.lower().replace(" ", "_")
        toolkit.resources.save_alias(alias, spreadsheet_id)
        
        return json.dumps({
            "status": "success",
            "message": f"Created sheet '{title}'{share_status}",
            "spreadsheet_id": spreadsheet_id,
            "alias": alias,
            "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        }, indent=2)
        
    except Exception as e:
        if "403" in str(e) or "quota" in str(e).lower():
            try:
                quota = toolkit.sheets.check_quota()
                usage = int(quota.get('usage', 0))
                limit = int(quota.get('limit', -1))
                if limit > 0 and usage >= limit:
                     return f"Error: Service Account Drive Storage Full ({usage/1024/1024:.2f} MB / {limit/1024/1024:.2f} MB used).\n\nPlease use the `prune_drive_files` tool to delete old files and free up space."
            except:
                pass
        return f"Error creating sheet: {str(e)}"

@mcp.tool()
async def rename_sheet(
    sheet_alias_or_id: str = Field(..., description="Sheet alias or ID to rename"),
    new_name: str = Field(..., description="New name for the sheet")
) -> str:
    """Rename an existing Google Sheet. Returns the updated link with the new name."""
    toolkit = get_toolkit()
    try:
        spreadsheet_id = toolkit.resources.get_id(sheet_alias_or_id)
        toolkit.sheets.rename_sheet(spreadsheet_id, new_name)
        
        new_alias = new_name.lower().replace(" ", "_")
        toolkit.resources.save_alias(new_alias, spreadsheet_id)
        
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        return f"✓ Renamed sheet to '{new_name}'\n\nAccess it here: {url}\n\nSaved as alias: '{new_alias}'"
    except Exception as e:
        return f"Error renaming sheet: {str(e)}"

@mcp.tool()
async def create_chart_in_sheet(
    spreadsheet_id: str = Field(..., description="Spreadsheet ID or alias"),
    sheet_name: str = Field(..., description="Sheet/tab name containing the data"),
    chart_type: str = Field(..., description="Chart type: 'line', 'bar', 'column', 'pie', 'scatter', or 'area'"),
    data_range: str = Field(..., description="Data range in A1 notation (e.g., 'A1:B10')"),
    chart_title: str = Field(..., description="Title for the chart")
) -> str:
    """Create a chart/graph in a Google Sheet for visual insights.
    
    Use this after exporting data to visualize trends, comparisons, or proportions.
    
    Examples:
    - Line chart for trends over time
    - Bar/Column chart for comparisons
    - Pie chart for proportions/percentages
    """
    toolkit = get_toolkit()
    try:
        # Resolve alias
        actual_id = toolkit.resources.get_id(spreadsheet_id)
        
        # Get sheet ID from sheet name
        metadata = toolkit.sheets.get_service().spreadsheets().get(
            spreadsheetId=actual_id
        ).execute()
        
        sheet_id = None
        for sheet in metadata.get('sheets', []):
            if sheet['properties']['title'] == sheet_name:
                sheet_id = sheet['properties']['sheetId']
                break
        
        if sheet_id is None:
            return f"Error: Sheet '{sheet_name}' not found in spreadsheet"
        
        # Create chart
        toolkit.sheets.create_chart(
            spreadsheet_id=actual_id,
            sheet_id=sheet_id,
            chart_type=chart_type,
            data_range=data_range,
            title=chart_title,
            position_row=0,
            position_col=5  # Position chart to the right of data
        )
        
        url = f"https://docs.google.com/spreadsheets/d/{actual_id}"
        return f"✓ Created {chart_type} chart '{chart_title}' in sheet '{sheet_name}'\n\nView it here: {url}"
        
    except Exception as e:
        return f"Error creating chart: {str(e)}"

@mcp.tool()
async def save_resource_alias(
    alias: str = Field(..., description="The alias name (e.g., 'finance_report')"), 
    resource_id: str = Field(..., description="The resource ID to save (e.g., Spreadsheet ID)")
) -> str:
    """Save a user-friendly alias for a resource ID (e.g., Spreadsheet ID)."""
    toolkit = get_toolkit()
    toolkit.resources.save_alias(alias, resource_id)
    return f"Saved alias '{alias}' for resource '{resource_id}'."

@mcp.tool()
async def list_resource_aliases() -> str:
    """List all saved resource aliases."""
    toolkit = get_toolkit()
    return json.dumps(toolkit.resources.list_aliases(), indent=2)

@mcp.tool()
async def prune_drive_files(
    max_files: int = 10, 
    older_than_days: int = 30, 
    dry_run: bool = True
) -> str:
    """Free up storage space by deleting old Google Sheets/Files.
    
    Safe by default: running without arguments will just LIST files that would be deleted.
    
    Args:
        max_files: Maximum number of files to delete (default: 10)
        older_than_days: Only select files created more than N days ago
        dry_run: If True, only lists files. If False, ACTUALLY DELETES THEM.
    """
    import datetime
    toolkit = get_toolkit()
    
    try:
        # 1. Get files
        files = toolkit.sheets.list_files(page_size=100)
        
        # 2. Filter by age
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=older_than_days)
        
        files_to_process = []
        for f in files:
            try:
                created_time = datetime.datetime.fromisoformat(f['createdTime'].replace('Z', '+00:00'))
                if created_time < cutoff_date:
                    files_to_process.append(f)
            except:
                continue
                
        # 3. Sort by oldest first
        files_to_process.sort(key=lambda x: x.get('createdTime', ''))
        
        # 4. Limit
        target_files = files_to_process[:max_files]
        
        if not target_files:
            return f"No files found older than {older_than_days} days."
            
        summary = [f"Found {len(target_files)} files older than {older_than_days} days:"]
        for f in target_files:
            summary.append(f"- {f.get('name')} (ID: {f.get('id')}) - Created: {f.get('createdTime')}")
            
        if dry_run:
             return "🔍 [DRY RUN] The following files WOULD be deleted:\n\n" + "\n".join(summary) + "\n\n⚠️ To actually delete them, run this tool again with `dry_run=False`."

        # 5. Delete (Only if dry_run=False)
        deleted_count = 0
        deleted_log = []
        
        for f in target_files:
            try:
                toolkit.sheets.delete_file(f['id'])
                deleted_count += 1
                deleted_log.append(f"Deleted: {f.get('name')}")
            except Exception as del_err:
                deleted_log.append(f"Failed to delete {f.get('name')}: {str(del_err)}")
                
        # 6. Check New Quota
        quota = toolkit.sheets.check_quota()
        usage = int(quota.get('usage', 0))
        limit = int(quota.get('limit', -1))
        
        result = f"🗑️ Pruned {deleted_count} files.\n\n" + "\n".join(deleted_log)
        limit_disp = f"{limit/1024/1024:.2f}" if limit > 0 else "Unknown"
        result += f"\n\nNew Storage Usage: {usage/1024/1024:.2f} MB / {limit_disp} MB"
        return result
        
    except Exception as e:
        return f"Error pruning files: {str(e)}"

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
async def replicate_data_to_sheet(spreadsheet_id: str, sheet_name: str, query: Optional[str] = None) -> str:
    """Execute a Snowflake query and replicate the results to a Google Sheet.
    
    Args:
        spreadsheet_id: The ID of the Google Sheet OR a saved alias
        sheet_name: The name of the tab/worksheet to write to
        query: Optional SQL query. 
               - If provided, this query is executed.
               - If NOT provided, the agent attempts to use the LAST SUCCESSFULLY EXECUTED query.
               
    IMPORTANT FOR AGENT: 
    If the user asks for a specific report (e.g., "Quarterly Sales") but hasn't provided SQL:
    1. DO NOT ask the user for SQL. 
    2. Instead, FIRST explore the database (list_tables, get_table_schema) to find relevant tables.
    3. Generate a SQL query yourself based on the user's intent.
    4. Then call this tool with your generated `query`.
    """
    toolkit = get_toolkit()
    
    # Use last executed query if none provided
    if not query:
        if toolkit.snowflake.last_executed_query:
            query = toolkit.snowflake.last_executed_query
            logger.info(f"Using last executed query: {query}")
        else:
            return "Error: No query provided and no previous query found in history. Please provide a SQL query."
    
    actual_id = toolkit.resources.get_id(spreadsheet_id)
    start_time = time.time()
    
    try:
        try:
            available_sheets = toolkit.sheets.get_sheet_names(actual_id)
            if sheet_name not in available_sheets:
                toolkit.sheets.add_worksheet(actual_id, sheet_name)
        except Exception as e:
            if "403" in str(e):
                return f"Error: Permission denied. Please share the sheet with your service account: {toolkit.config.google_sheets_user_email or 'googlesheet@z-agentspace-trial.iam.gserviceaccount.com'}"

            return f"Error accessing/creating sheet '{sheet_name}': {str(e)}"

        results = toolkit.snowflake.query(query)
        if not results:
            return "No data found in Snowflake to replicate."
            
        headers = list(results[0].keys())
        rows = []
        for row in results:
            clean_row = []
            for val in row.values():
                if hasattr(val, 'isoformat'):
                    clean_row.append(val.isoformat())
                elif hasattr(val, 'quantize'):
                    clean_row.append(float(val)) 
                else:
                    clean_row.append(val)
            rows.append(clean_row)
            
        all_values = [headers] + rows
        
        range_name = f"{sheet_name}!A1"
        
        try:
            write_result = toolkit.sheets.write_sheet(actual_id, range_name, all_values)
            updated_cells = write_result.get('updatedCells', 0)
            updated_rows = write_result.get('updatedRows', 0)
            
            # Verify write success
            if updated_cells == 0 or updated_rows == 0:
                return f"⚠️ Warning: Write operation returned 0 updated cells/rows. Data may not have been written to the sheet.\nWrite result: {write_result}"
                
        except Exception as write_error:
            return f"Error writing data to sheet: {str(write_error)}"
        
        execution_time = (time.time() - start_time) * 1000
        
        return f"Successfully replicated {len(rows)} rows ({updated_cells} cells) to '{sheet_name}' in sheet '{actual_id}'.\nURL: https://docs.google.com/spreadsheets/d/{actual_id}"
        
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        
        if "403" in str(e) or "quota" in str(e).lower():
            try:
                quota = toolkit.sheets.check_quota()
                usage = int(quota.get('usage', 0))
                limit = int(quota.get('limit', -1))
                if limit > 0 and usage >= limit:
                     return f"Error: Service Account Drive Storage Full ({usage/1024/1024:.2f} MB / {limit/1024/1024:.2f} MB used).\n\nPlease use the `prune_drive_files` tool to delete old files and free up space."
            except:
                pass
        
        if "404" in str(e) or "INVALID_ARGUMENT" in str(e):
             return f"Error: The Google Sheet ID '{spreadsheet_id}' was not found or is invalid.\n\n👉 PLEASE:\n1. Create a NEW sheet first using `create_new_sheet(title='...')`.\n2. Then use the NEW ID returned to replicate data."

        return f"Error replicating data: {str(e)}"


