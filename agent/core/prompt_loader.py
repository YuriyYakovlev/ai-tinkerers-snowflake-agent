"""
prompt_loader.py
================

Single-responsibility module: load the agent's system prompt from disk.

**Why is the prompt in a file (not hard-coded)?**

Keeping the prompt in ``prompts.md`` rather than inside Python source achieves
three things:

1. **No-code updates** — A product manager or prompt engineer can iterate on
   the agent's behaviour without touching Python.
2. **Version control clarity** — Prompt changes appear as Markdown diffs, not
   buried inside Python string literals.
3. **Testability** — The prompt file can be swapped at runtime for A/B testing
   or different deployment environments.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve the path relative to this file so it works regardless of where
# the process is launched from.
_PROMPT_PATH = Path(__file__).parent.parent / "prompts.md"


def load_prompt() -> str:
    """Read and return the agent system prompt from ``prompts.md``.

    Falls back to a minimal default prompt if the file is missing so the agent
    can still start (useful during local development before the full prompt is
    written).

    Returns
    -------
    str
        The full text of the system prompt.
    """
    try:
        text = _PROMPT_PATH.read_text(encoding="utf-8")
        logger.info("System prompt loaded from %s (%d chars)", _PROMPT_PATH, len(text))
        return text
    except FileNotFoundError:
        logger.warning("prompts.md not found at %s — using fallback prompt.", _PROMPT_PATH)
        return "You are a helpful business intelligence assistant."
