"""
agent/tool_definitions/email_tools.py
=======================================

Email campaign execution tool.

This module contains tools for sending personalised email campaigns based on
data stored in Google Sheets (typically populated by ``replicate_data_to_sheet``
from ``sheets_tools.py``).

Campaign Workflow
-----------------
The intended workflow is:

1. The agent queries Snowflake for a target customer list.
2. Results are exported to Google Sheets via ``replicate_data_to_sheet``.
3. The agent (or user) calls ``send_campaign_emails`` to send personalised
   emails to each row in the sheet.

Safety Defaults
---------------
- **``dry_run=True``** (default): shows a preview of what *would* be sent.
  No emails are transmitted.  Always review before setting ``dry_run=False``.
- **``test_mode=True``** (default): even when ``dry_run=False``, only the
  first 3 recipients are emailed.  Set both to ``False`` for a full campaign.
- A **verification copy** is always sent to ``GOOGLE_SHEETS_USER_EMAIL`` so
  the sender can confirm content and formatting before recipients see it.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
async def send_campaign_emails(
    sheet_id_or_alias: str,
    subject_template: str,
    body_template: str,
    sheet_name: str = "Sheet1",
    test_mode: bool = True,
    dry_run: bool = True,
) -> str:
    """Send personalised campaign emails from a Google Sheet.

    Reads customer data from a Google Sheet and sends an email to each row
    that has a valid email address.  Subject and body templates use Python
    ``str.format()`` syntax with column names as keys.

    **ALWAYS start with dry_run=True** to preview the emails before sending!

    Example Templates
    -----------------
    - subject: ``"Exclusive offer for {customer_name}!"``
    - body: ``"Hi {customer_name}, we'd love to offer you {recommended_product}."``

    Parameters
    ----------
    sheet_id_or_alias:
        Google Sheet ID or saved alias (see ``save_resource_alias``).
        Also accepts a full Sheet URL.
    subject_template:
        Email subject line with ``{column_name}`` placeholders.
    body_template:
        Email body with ``{column_name}`` placeholders (plain text).
    sheet_name:
        Worksheet tab name containing the campaign data.
    test_mode:
        If ``True``, only sends to the first 3 recipients (after dry run).
    dry_run:
        If ``True`` (default), shows a preview only — no emails are sent.
        Set to ``False`` to actually send.

    Returns
    -------
    str
        Preview summary (dry run) or delivery report (live run).
    """
    toolkit = get_toolkit()

    # ── Validate SMTP configuration ───────────────────────────────────────────
    if not toolkit.config.smtp_user or not toolkit.config.smtp_password:
        return """❌ Email not configured!

Please set these environment variables in .env:
- SMTP_USER=your-email@gmail.com
- SMTP_PASSWORD=your-app-password
- SMTP_FROM_EMAIL=your-email@gmail.com
- SMTP_FROM_NAME=Campaign Team

For Gmail: Create an App Password at https://myaccount.google.com/apppasswords"""

    # ── Resolve sheet ID ──────────────────────────────────────────────────────
    actual_id = toolkit.resources.get_id(sheet_id_or_alias)

    # Handle Sheet URLs
    if "/" in actual_id and "/d/" in actual_id:
        actual_id = actual_id.split("/d/")[1].split("/")[0]

    # ── Read sheet data ───────────────────────────────────────────────────────
    try:
        values = toolkit.sheets.read_sheet(actual_id, f"{sheet_name}!A1:Z1000")
    except Exception as e:
        return (
            f"Unable to access Google Sheet.\n"
            f"Provide the sheet URL or sheet ID.\n\nError: {e}"
        )

    if not values or len(values) < 2:
        return "No campaign data found. Ensure the sheet has a header row and at least one data row."

    headers = [h.lower().replace(" ", "_") for h in values[0]]
    rows = values[1:]

    # ── Locate the email column ───────────────────────────────────────────────
    email_col = next((h for h in headers if h in ("contact", "email", "customer_email")), None)
    if not email_col:
        return f"Sheet must have an email/contact column. Found: {', '.join(values[0])}"

    # ── Build email list ──────────────────────────────────────────────────────
    emails_to_send = []
    for row in rows:
        if len(row) < len(headers):
            continue

        row_data: dict = {}
        for h, val in zip(headers, row):
            row_data[h] = val
            row_data[h.upper()] = val
            row_data[h.title().replace("_", "")] = val

        email_address = row_data.get("email", row_data.get("contact", row_data.get("customer_email", ""))).strip()
        if "@" not in email_address:
            continue

        try:
            subject = subject_template.format(**row_data)
            body = body_template.format(**row_data)
        except KeyError as e:
            missing = str(e).strip("'")
            return (
                f"Template error: column {{{missing}}} not found in sheet.\n"
                f"Available columns: {', '.join(row_data.keys())}"
            )

        emails_to_send.append({
            "to": email_address,
            "subject": subject,
            "body": body,
        })

    if not emails_to_send:
        return "No valid email addresses found in campaign data."

    # ── Add verification copy to sender ──────────────────────────────────────
    if toolkit.config.google_sheets_user_email and emails_to_send:
        first = emails_to_send[0]
        emails_to_send.insert(0, {
            "to": toolkit.config.google_sheets_user_email,
            "subject": f"[TEST] {first['subject']}",
            "body": f"🧪 VERIFICATION EMAIL\n\nThis copy is sent to you to verify the campaign.\n\n---\n\n{first['body']}",
        })

    # ── Apply test mode ───────────────────────────────────────────────────────
    if test_mode:
        emails_to_send = emails_to_send[:3]
        mode_label = "🧪 TEST MODE (first 3 emails only)"
    else:
        mode_label = f"📧 FULL CAMPAIGN ({len(emails_to_send)} emails)"

    # ── Dry run preview ───────────────────────────────────────────────────────
    if dry_run:
        preview = f"**DRY RUN — No emails sent** | {mode_label}\n\n"
        preview += f"**Would send {len(emails_to_send)} emails:**\n\n"
        for i, email in enumerate(emails_to_send[:3], 1):
            preview += f"**Email {i}:**\n"
            preview += f"- To: {email['to']}\n"
            preview += f"- Subject: {email['subject']}\n"
            preview += f"- Body Preview: {email['body'][:100]}...\n\n"
        if len(emails_to_send) > 3:
            preview += f"... and {len(emails_to_send) - 3} more emails\n\n"
        preview += "**To send:** Use `dry_run=False` after reviewing this preview."
        return preview

    # ── Live send ─────────────────────────────────────────────────────────────
    sent_count = 0
    failed = []

    try:
        if toolkit.config.smtp_port == 465:
            server = smtplib.SMTP_SSL(toolkit.config.smtp_host, toolkit.config.smtp_port)
        else:
            server = smtplib.SMTP(toolkit.config.smtp_host, toolkit.config.smtp_port)
            server.starttls()
        server.login(toolkit.config.smtp_user, toolkit.config.smtp_password)

        for email_data in emails_to_send:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = email_data["subject"]
                msg["From"] = (
                    f"{toolkit.config.smtp_from_name} "
                    f"<{toolkit.config.smtp_from_email or toolkit.config.smtp_user}>"
                )
                msg["To"] = email_data["to"]
                msg.attach(MIMEText(email_data["body"], "plain"))
                html_body = email_data["body"].replace("\n", "<br>")
                msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html"))
                server.send_message(msg)
                sent_count += 1
            except Exception as e:
                failed.append(f"{email_data['to']}: {e}")

        server.quit()
    except Exception as e:
        return f"SMTP Error: {e}\n\nCheck your SMTP credentials in .env."

    result = f"## ✅ Campaign Sent! | {mode_label}\n\n"
    result += f"**Sent:** {sent_count} emails\n"
    if failed:
        result += f"**Failed:** {len(failed)}\n"
        for fail in failed[:5]:
            result += f"- {fail}\n"
    result += "\n**Next steps:**\n1. Monitor delivery\n2. Track responses\n3. Follow up in 3–5 days"
    return result
