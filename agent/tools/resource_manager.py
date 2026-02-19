"""
agent/tools/resource_manager.py
================================

Manages persistent aliases for Google Sheets (and other resources).

The Problem It Solves
---------------------
Google Sheets IDs look like ``1Sbjtqe0v0BATcBvoQ8B8_VXEoFLMugZS1CtLN6L_lVM``.
These are opaque and hard to reference in conversation.  ``ResourceManager``
lets the agent (and users) refer to sheets by human-friendly names like
``"monthly_sales"`` instead.

Aliases are stored in ``agent/resources.json`` so they survive process restarts.
"""

import json
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)

# Path to the alias store — same directory as this package's parent (agent/)
_RESOURCES_PATH = os.path.join(os.path.dirname(__file__), "..", "resources.json")


class ResourceManager:
    """Persists and resolves human-friendly aliases for resource IDs.

    A resource is typically a Google Spreadsheet, but the system is generic
    enough to store any string-to-string mapping.

    Usage
    -----
    >>> rm = ResourceManager()
    >>> rm.save_alias("q4_report", "1Sbjtqe0v0BAT...")
    >>> rm.get_id("q4_report")
    '1Sbjtqe0v0BAT...'
    >>> rm.get_id("already_an_id")  # pass-through if not found
    'already_an_id'
    """

    def __init__(self):
        """Load the alias store from disk on construction."""
        self.file_path = os.path.normpath(_RESOURCES_PATH)
        self._load_resources()

    def _load_resources(self):
        """Read the JSON alias store from disk."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.resources = json.load(f)
            except Exception as e:
                logger.warning("Could not load resources.json: %s", e)
                self.resources = {}
        else:
            self.resources = {}

    def _save_resources(self):
        """Write the current alias store to disk."""
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.resources, f, indent=2)

    def save_alias(self, alias: str, resource_id: str) -> None:
        """Persist a new alias → resource_id mapping.

        Parameters
        ----------
        alias:
            Short, human-friendly name (e.g. ``"monthly_sales"``).
        resource_id:
            The actual resource identifier (e.g. a Spreadsheet ID).
        """
        self.resources[alias] = resource_id
        self._save_resources()
        logger.debug("Saved alias '%s' → '%s'", alias, resource_id)

    def get_id(self, alias_or_id: str) -> str:
        """Resolve an alias to its resource ID, or return the input unchanged.

        This pass-through behaviour means callers don't need to check whether
        they have an alias or a raw ID — just always call ``get_id()``.

        Parameters
        ----------
        alias_or_id:
            Either a saved alias or a raw resource ID.

        Returns
        -------
        str
            The resolved resource ID.
        """
        return self.resources.get(alias_or_id, alias_or_id)

    def list_aliases(self) -> Dict[str, str]:
        """Return all saved aliases as a dict.

        Returns
        -------
        Dict[str, str]
            ``{alias: resource_id, ...}``
        """
        return self.resources
