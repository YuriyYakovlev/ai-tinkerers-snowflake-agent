"""
agent/tools/formatters.py
==========================

Shared output formatting utilities.

Why a separate module?
----------------------
Multiple tool functions need to present query results in the same way.
Centralising ``format_as_table`` here prevents duplication and ensures
consistent output across all tools.
"""

from typing import Any, Dict, List


def format_as_table(data: List[Dict[str, Any]], max_rows: int = 100) -> str:
    """Format a list of row-dicts as a Markdown table.

    The agent's system prompt instructs it to present data in clean tables.
    This function converts raw Snowflake query results (list of dicts) into
    GitHub-flavoured Markdown table syntax that renders neatly in most
    chat interfaces.

    Parameters
    ----------
    data:
        List of row dictionaries.  All dicts must have the same keys.
    max_rows:
        Safety cap on rendered rows.  Large result sets risk hitting Gemini's
        context window limit; this guard keeps responses manageable.

    Returns
    -------
    str
        Markdown-formatted table string, including a footer with row count.
        Returns ``"No data returned"`` for empty inputs.

    Example
    -------
    >>> rows = [{"name": "Acme", "revenue": 125000}]
    >>> print(format_as_table(rows))
    | name | revenue |
    |------|---------|
    | Acme | 125000  |

    *1 rows*
    """
    if not data:
        return "No data returned"

    display_data = data[:max_rows]
    total_rows = len(data)
    columns = list(display_data[0].keys())

    header = "| " + " | ".join(str(col) for col in columns) + " |"
    separator = "|" + "|".join("------" for _ in columns) + "|"

    rows = []
    for row in display_data:
        values = []
        for col in columns:
            val = row.get(col, "")
            val_str = str(val) if val is not None else ""
            # Truncate very long values to keep the table readable
            if len(val_str) > 50:
                val_str = val_str[:47] + "..."
            values.append(val_str)
        rows.append("| " + " | ".join(values) + " |")

    table = "\n".join([header, separator] + rows)

    if total_rows > max_rows:
        table += f"\n\n*Showing {max_rows} of {total_rows} rows*"
    else:
        table += f"\n\n*{total_rows} rows*"

    return table
