"""
agent/tool_definitions/query_tools.py
======================================

╔══════════════════════════════════════════════════════════════════════╗
║          HYBRID ARCHITECTURE: DETERMINISTIC + GENERATIVE TOOLS       ║
╚══════════════════════════════════════════════════════════════════════╝

This file is the architectural centrepiece of the Snowflake BI Agent.
It implements TWO complementary strategies for answering data questions:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRATEGY 1 — DETERMINISTIC (Hardcoded SQL)    →  get_account_info()
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• The SQL is written by a human engineer, reviewed, and frozen.
• The LLM only supplies the *parameter* (account name), not the query.
• Outcome is GUARANTEED: same input always produces the same query.
• Best for: high-frequency, mission-critical, SLA-sensitive lookups.
• Trade-off: inflexible — adding a new column requires a code change.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRATEGY 2 — GENERATIVE (Text-to-SQL)         →  _query_data_internal()
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• The LLM writes the SQL at *runtime* from the user's natural language.
• Can answer questions that were never anticipated at development time.
• Best for: exploratory, ad-hoc, one-off analytical queries.
• Trade-off: the LLM can make SQL mistakes — guardrails are essential.
  Guardrails here: all queries are READ-ONLY (SELECT only; INSERT/UPDATE
  /DELETE are rejected by the system prompt and Snowflake role).

WHY BOTH?
---------
A BI agent that only uses hardcoded SQL is brittle — every new question
requires a developer.  A BI agent that only uses Text-to-SQL is risky —
critical lookups may fail due to LLM hallucinations or schema drift.
The hybrid approach gives us stability where it matters and flexibility
everywhere else.
"""

import logging

from .registry import mcp
from ..tools.toolkit import Toolkit
from ..tools.formatters import format_as_table
from ..config import Config

logger = logging.getLogger(__name__)

# ── Toolkit singleton (lazy init) ─────────────────────────────────────────────
_toolkit: Toolkit | None = None


def get_toolkit() -> Toolkit:
    """Return the shared Toolkit instance, creating it on first call.

    The singleton pattern ensures only ONE Snowflake connection is opened
    per agent session, regardless of how many tool calls are made.
    """
    global _toolkit
    if _toolkit is None:
        _toolkit = Toolkit(Config.from_env())
    return _toolkit


# ════════════════════════════════════════════════════════════════════════
# STRATEGY 1 — DETERMINISTIC: Hardcoded SQL tool
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_account_info(account_name: str) -> str:
    """Look up information about a specific customer or account.

    Use this when the user asks about a specific account, customer, or client
    by name.  Returns key details and metrics for that account.

    **Why hardcoded SQL?**
    This is the most frequent query in the BI workflow and the one where
    errors would be most visible to clients.  By hardcoding the SQL pattern,
    we guarantee consistent results regardless of how the LLM interprets
    the user's question.

    Parameters
    ----------
    account_name:
        The name (or partial name) of the account to look up.

    Returns
    -------
    str
        Markdown table of account details, or a not-found message.
    """
    toolkit = get_toolkit()
    query = (
        f"SELECT * FROM FINANCIALS.PUBLIC.FINANCIAL_SUMMARY "
        f"WHERE ACCOUNT_NAME ILIKE '%{account_name}%' LIMIT 1"
    )
    try:
        results = toolkit.snowflake.query(query)
        if not results:
            return (
                f"I couldn't find any information for an account matching '{account_name}'. "
                f"Please check the name and try again."
            )
        return format_as_table(results)
    except Exception:
        return "I encountered an issue looking up that account. Please try again or contact support."


# ════════════════════════════════════════════════════════════════════════
# STRATEGY 2 — GENERATIVE: Text-to-SQL tool
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def _query_data_internal(query: str) -> str:
    """[INTERNAL] Execute a Snowflake SQL query and return results.

    Business users should not call this directly.  The agent uses this
    internally to answer exploratory, ad-hoc questions that don't have a
    dedicated hardcoded tool.

    **Why [INTERNAL]?**
    The ``[INTERNAL]`` prefix in the name signals to the LLM (via the system
    prompt) that this tool is infrastructure — it should never say "I'm using
    _query_data_internal" in a response.  The user should only ever see the
    *results*, expressed in business language.

    **Safety guardrails:**
    - The Snowflake role used has SELECT-only privileges (no writes).
    - The system prompt explicitly forbids generating DML (INSERT/UPDATE/DELETE).
    - Parameterised values aren't used here because Snowflake DDL names can't
      be parameterised; instead, the system prompt enforces READ-ONLY.

    Parameters
    ----------
    query:
        Valid Snowflake SQL SELECT statement.  Constructed by the LLM from
        the user's natural language question.

    Returns
    -------
    str
        Markdown table of results, or a user-friendly error message.
    """
    toolkit = get_toolkit()
    try:
        results = toolkit.snowflake.query(query)
        return format_as_table(results)
    except Exception as e:
        error_type, message, suggestions = toolkit.error_handler.handle_snowflake_error(e)
        return toolkit.error_handler.format_error_response(e, error_type, message, suggestions, query)
