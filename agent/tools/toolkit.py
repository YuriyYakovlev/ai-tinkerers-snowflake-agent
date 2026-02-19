"""
agent/tools/toolkit.py
========================

Dependency Injection (DI) container for all infrastructure clients.

Why Dependency Injection?
-------------------------
Tool functions (in ``tool_definitions/``) need access to Snowflake, Google
Sheets, the resource alias store, and the error handler.  Without DI, each
tool would construct its own clients, leading to:

- Multiple redundant Snowflake connections per request.
- Config objects scattered across the codebase.
- Hard-to-test code (you can't swap out a real DB for a mock).

``Toolkit`` solves this by creating **one instance of each client** and passing
it as a single object to every tool via the ``get_toolkit()`` singleton pattern
in ``tool_definitions/registry.py``.

This is the classic **Service Locator / Dependency Container** pattern adapted
for a lightweight Python codebase.
"""

import logging

from ..config import Config
from .error_handler import ErrorHandler
from .resource_manager import ResourceManager
from .sheets_client import SheetsClient
from .snowflake_client import SnowflakeClient

logger = logging.getLogger(__name__)


class Toolkit:
    """Wires all infrastructure clients together into one injectable container.

    Parameters
    ----------
    config:
        A fully populated ``Config`` instance.

    Attributes
    ----------
    config:
        Application configuration (shared across all clients).
    snowflake:
        Lazy-connected Snowflake client.
    sheets:
        Google Sheets + Drive API client.
    resources:
        Alias-to-ID persistent store.
    error_handler:
        Stateless error classification and formatting utility.
    """

    def __init__(self, config: Config):
        self.config = config
        self.snowflake = SnowflakeClient(config)
        self.sheets = SheetsClient(config)
        self.resources = ResourceManager()
        self.error_handler = ErrorHandler()
        logger.debug("Toolkit initialised with config for account: %s", config.snowflake_account)
