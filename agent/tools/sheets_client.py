"""
agent/tools/sheets_client.py
=============================

Google Sheets and Google Drive API wrappers.

Authentication Flow
-------------------
The client supports two auth modes, tried in order:

1. **User OAuth Token** (``token.json``) — Used when the agent needs to act
   on behalf of a human user (e.g., create sheets in the user's Drive, share
   with their email).  The token file is written by ``setup_google_user_auth.py``
   in the ``scripts/`` directory.

2. **Service Account** (``GOOGLE_SERVICE_ACCOUNT_PATH``) — Used in production
   (Vertex AI Reasoning Engine) where a human isn't available to complete the
   OAuth flow.  Service accounts have their own Drive storage quota.

Why separate ``_service`` and ``_drive_service``?
--------------------------------------------------
Google exposes Sheets operations (read, write, create, share) through two
different APIs:

- ``sheets`` v4 — Cell-level read/write, metadata, formatting.
- ``drive`` v3 — File management (share, delete, list, quota check).

Both are lazy-initialised and cached to avoid redundant authentication calls.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ..config import Config

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetsClient:
    """Wraps the Google Sheets v4 and Drive v3 APIs.

    Parameters
    ----------
    config:
        Populated ``Config`` instance with Google auth paths.
    """

    def __init__(self, config: Config):
        self.config = config
        self._service = None       # Sheets API service
        self._drive_service = None  # Drive API service

    # ── Auth helpers ──────────────────────────────────────────────────────────

    def get_service(self):
        """Return the Google Sheets API service (lazy init).

        Tries User OAuth token first, falls back to service account.
        """
        if self._service:
            return self._service

        # Attempt 1: User OAuth token
        if self.config.google_token_path and os.path.exists(self.config.google_token_path):
            try:
                with open(self.config.google_token_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                creds = Credentials.from_authorized_user_info(info)
                self._service = build("sheets", "v4", credentials=creds)
                logger.info("Sheets service initialised via User OAuth token.")
                return self._service
            except Exception as e:
                logger.warning("User token auth failed: %s — falling back to service account.", e)

        # Attempt 2: Service account
        if not self.config.google_service_account_path:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_PATH not set and valid User Token not found. "
                "Run scripts/setup_google_user_auth.py to create a token."
            )
        creds = service_account.Credentials.from_service_account_file(
            self.config.google_service_account_path, scopes=_SCOPES
        )
        self._service = build("sheets", "v4", credentials=creds)
        logger.info("Sheets service initialised via Service Account.")
        return self._service

    def get_drive_service(self):
        """Return the Google Drive API service (lazy init).

        Used for file operations not available in the Sheets API:
        sharing, deletion, quota checks, and listing.
        """
        if self._drive_service:
            return self._drive_service

        if self.config.google_token_path and os.path.exists(self.config.google_token_path):
            try:
                with open(self.config.google_token_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                creds = Credentials.from_authorized_user_info(info)
                self._drive_service = build("drive", "v3", credentials=creds)
                logger.info("Drive service initialised via User OAuth token.")
                return self._drive_service
            except Exception as e:
                logger.warning("User token Drive auth failed: %s — falling back to service account.", e)

        if not self.config.google_service_account_path:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_PATH not set.")
        creds = service_account.Credentials.from_service_account_file(
            self.config.google_service_account_path, scopes=_SCOPES
        )
        self._drive_service = build("drive", "v3", credentials=creds)
        return self._drive_service

    # ── Sheets operations ─────────────────────────────────────────────────────

    def read_sheet(self, spreadsheet_id: str, range_name: str) -> List[List[str]]:
        """Read a range from a Google Sheet.

        Parameters
        ----------
        spreadsheet_id:
            The 44-character Sheet ID from the URL.
        range_name:
            A1 notation range, e.g. ``"Sheet1!A1:Z100"``.

        Returns
        -------
        List[List[str]]
            2D list of cell values (empty cells may be omitted by the API).
        """
        service = self.get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name
        ).execute()
        return result.get("values", [])

    def write_sheet(
        self, spreadsheet_id: str, range_name: str, values: List[List[Any]]
    ) -> Dict[str, Any]:
        """Write data to a Google Sheet.

        Parameters
        ----------
        spreadsheet_id:
            Target Sheet ID.
        range_name:
            Top-left anchor cell in A1 notation (e.g., ``"Sheet1!A1"``).
        values:
            2D list of cell values.  The first sub-list is treated as headers.

        Returns
        -------
        Dict[str, Any]
            API response dict with ``updatedCells``, ``updatedRows``, etc.

        Raises
        ------
        ValueError
            If the API confirms 0 cells were updated (likely a permissions issue).
        """
        service = self.get_service()
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

        updated_cells = result.get("updatedCells", 0)
        if updated_cells == 0:
            raise ValueError(f"Write operation returned 0 updated cells. Response: {result}")
        return result

    def create_sheet(self, title: str) -> str:
        """Create a new Google Spreadsheet.

        Parameters
        ----------
        title:
            Display name for the new spreadsheet.

        Returns
        -------
        str
            The new spreadsheet's ID.
        """
        service = self.get_service()
        spreadsheet = service.spreadsheets().create(
            body={"properties": {"title": title}},
            fields="spreadsheetId",
        ).execute()
        return spreadsheet.get("spreadsheetId")

    def rename_sheet(self, spreadsheet_id: str, new_title: str) -> str:
        """Rename an existing spreadsheet.

        Parameters
        ----------
        spreadsheet_id:
            The Sheet ID to rename.
        new_title:
            New display name.

        Returns
        -------
        str
            Confirmation message.
        """
        service = self.get_service()
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [{
                    "updateSpreadsheetProperties": {
                        "properties": {"title": new_title},
                        "fields": "title",
                    }
                }]
            },
        ).execute()
        return f"Renamed spreadsheet to '{new_title}'"

    def share_sheet(self, spreadsheet_id: str, email: str, role: str = "writer") -> None:
        """Share a spreadsheet with a user via the Drive API.

        Parameters
        ----------
        spreadsheet_id:
            Sheet ID to share.
        email:
            Gmail or Google Workspace email to grant access to.
        role:
            Drive role: ``"reader"``, ``"writer"``, or ``"owner"``.
        """
        drive_service = self.get_drive_service()
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body={"type": "user", "role": role, "emailAddress": email},
            fields="id",
        ).execute()

    def get_sheet_names(self, spreadsheet_id: str) -> List[str]:
        """Return the tab names of all sheets in a spreadsheet.

        Parameters
        ----------
        spreadsheet_id:
            Target Sheet ID.

        Returns
        -------
        List[str]
            Ordered list of worksheet tab names.
        """
        service = self.get_service()
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        return [sheet["properties"]["title"] for sheet in metadata.get("sheets", [])]

    def add_worksheet(self, spreadsheet_id: str, title: str) -> int:
        """Add a new worksheet tab to an existing spreadsheet.

        Parameters
        ----------
        spreadsheet_id:
            Target spreadsheet ID.
        title:
            Title for the new tab.

        Returns
        -------
        int
            The numeric sheet ID of the new tab (needed for chart requests).
        """
        service = self.get_service()
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ).execute()
        return response["replies"][0]["addSheet"]["properties"]["sheetId"]

    def create_chart(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        chart_type: str,
        data_range: str,
        title: str,
        position_row: int = 0,
        position_col: int = 0,
    ) -> Dict[str, Any]:
        """Create a chart in an existing sheet.

        Parameters
        ----------
        spreadsheet_id:
            Target spreadsheet ID.
        sheet_id:
            Numeric ID of the tab that contains the data (not the name).
        chart_type:
            One of ``"line"``, ``"bar"``, ``"column"``, ``"pie"``,
            ``"scatter"``, ``"area"``.
        data_range:
            A1 notation range including headers (e.g. ``"A1:B10"``).
        title:
            Chart title.
        position_row / position_col:
            Top-left anchor cell (row/column index) for the chart overlay.

        Returns
        -------
        Dict[str, Any]
            Raw API batchUpdate response.
        """
        service = self.get_service()

        chart_type_map = {
            "line": "LINE", "bar": "BAR", "column": "COLUMN",
            "pie": "PIE", "scatter": "SCATTER", "area": "AREA",
        }
        google_chart_type = chart_type_map.get(chart_type.lower(), "LINE")

        # Parse A1 range into row/column indices
        match = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", data_range.upper())
        if not match:
            raise ValueError(f"Invalid data range format: {data_range}")

        def col_to_index(col: str) -> int:
            result = 0
            for char in col:
                result = result * 26 + (ord(char) - ord("A") + 1)
            return result - 1

        start_col = col_to_index(match.group(1))
        start_row = int(match.group(2)) - 1
        end_col = col_to_index(match.group(3)) + 1
        end_row = int(match.group(4))

        def _src(sc, sr, ec, er):
            return {"sheetId": sheet_id, "startRowIndex": sr, "endRowIndex": er,
                    "startColumnIndex": sc, "endColumnIndex": ec}

        if google_chart_type == "PIE":
            spec = {
                "title": title,
                "pieChart": {
                    "legendPosition": "RIGHT_LEGEND",
                    "domain": {"sourceRange": {"sources": [_src(start_col, start_row, start_col + 1, end_row)]}},
                    "series": {"sourceRange": {"sources": [_src(start_col + 1, start_row, end_col, end_row)]}},
                },
            }
        else:
            spec = {
                "title": title,
                "basicChart": {
                    "chartType": google_chart_type,
                    "legendPosition": "RIGHT_LEGEND",
                    "axis": [{"position": "BOTTOM_AXIS"}, {"position": "LEFT_AXIS"}],
                    "domains": [{"domain": {"sourceRange": {"sources": [_src(start_col, start_row, start_col + 1, end_row)]}}}],
                    "series": [{"series": {"sourceRange": {"sources": [_src(start_col + 1, start_row, end_col, end_row)]}}, "targetAxis": "LEFT_AXIS"}],
                    "headerCount": 1,
                },
            }

        return service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [{
                    "addChart": {
                        "chart": {
                            "spec": spec,
                            "position": {"overlayPosition": {"anchorCell": {
                                "sheetId": sheet_id, "rowIndex": position_row, "columnIndex": position_col,
                            }}},
                        }
                    }
                }]
            },
        ).execute()

    # ── Drive operations ──────────────────────────────────────────────────────

    def check_quota(self) -> Dict[str, Any]:
        """Return the Drive storage quota for the authenticated account.

        Returns
        -------
        Dict[str, Any]
            Dict with keys ``usage`` and ``limit`` (bytes as strings).
        """
        drive_service = self.get_drive_service()
        about = drive_service.about().get(fields="storageQuota").execute()
        return about.get("storageQuota", {})

    def list_files(self, mime_type: Optional[str] = None, page_size: int = 10) -> List[Dict[str, Any]]:
        """List files in the user's/service-account's Drive.

        Parameters
        ----------
        mime_type:
            Optional MIME type filter (e.g., ``"application/vnd.google-apps.spreadsheet"``).
        page_size:
            Maximum number of files to return.

        Returns
        -------
        List[Dict[str, Any]]
            List of file metadata dicts.
        """
        drive_service = self.get_drive_service()
        query = "trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
        results = drive_service.files().list(
            q=query,
            pageSize=page_size,
            fields="nextPageToken, files(id, name, mimeType, createdTime, size)",
            orderBy="createdTime",
        ).execute()
        return results.get("files", [])

    def delete_file(self, file_id: str) -> None:
        """Permanently delete a file from Drive.

        Parameters
        ----------
        file_id:
            The Drive file ID to delete.

        .. warning::
            This is irreversible.  Always call ``list_files`` first and
            confirm with ``dry_run=True`` in the ``prune_drive_files`` tool.
        """
        drive_service = self.get_drive_service()
        drive_service.files().delete(fileId=file_id).execute()
