"""
data/gsheets_repo.py — Google Sheets backend (service account).

Improvements over the original gsheets.py:
  • writes are mapped by header name, not position — reordering or adding a
    column in the Sheet no longer corrupts rows
  • optional columns (PaidBy, Comments) are created on demand
  • Products / Partners / Settings tabs are read when present
  • one worksheet listing per request (gspread call count matters for quota)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from core import schema as S
from core.catalog import Catalog
from data.base import Repository, canonical_header, record_to_row, required_columns

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsRepository(Repository):
    name = "gsheets"

    def __init__(self, spreadsheet_id: str, service_account_info: dict):
        import gspread
        from google.oauth2.service_account import Credentials

        self.spreadsheet_id = spreadsheet_id
        self._creds = Credentials.from_service_account_info(dict(service_account_info), scopes=SCOPES)
        self._gc = gspread.authorize(self._creds)
        self._ss = self._gc.open_by_key(spreadsheet_id)
        self._ws_cache: dict[str, Any] = {}

    # ── helpers ────────────────────────────────────────────────────────────
    def _worksheets(self) -> dict[str, Any]:
        if not self._ws_cache:
            self._ws_cache = {ws.title: ws for ws in self._ss.worksheets()}
        return self._ws_cache

    def _ws(self, table: str):
        ws = self._worksheets().get(table)
        if ws is None:
            ws = self._ss.add_worksheet(title=table, rows=1000, cols=40)
            self._ws_cache[table] = ws
        return ws

    # ── reads ──────────────────────────────────────────────────────────────
    def tables(self) -> list[str]:
        return list(self._worksheets().keys())

    def read(self, table: str) -> pd.DataFrame:
        ws = self._worksheets().get(table)
        if ws is None:
            return pd.DataFrame()
        values = ws.get_all_values(value_render_option="UNFORMATTED_VALUE",
                                   date_time_render_option="SERIAL_NUMBER")
        if not values or not any(str(v).strip() for v in values[0]):
            return pd.DataFrame()
        headers = [str(h).strip() for h in values[0]]
        width = len(headers)
        rows = [r + [""] * (width - len(r)) for r in values[1:]]
        return pd.DataFrame(rows, columns=headers)

    # ── writes ─────────────────────────────────────────────────────────────
    def ensure_tables(self, cat: Catalog) -> None:
        for table in S.TRANSACTION_TABLES:
            ws = self._ws(table)
            if not ws.get_all_values():
                ws.append_row(required_columns(table, cat), value_input_option="USER_ENTERED")

    def append(self, table: str, record: dict[str, Any], cat: Catalog) -> None:
        ws = self._ws(table)
        headers = [h for h in ws.row_values(1) if str(h).strip()]
        if not headers:
            headers = required_columns(table, cat)
            ws.append_row(headers, value_input_option="USER_ENTERED")
        canon = {canonical_header(table, h, cat) for h in headers}
        for key in record:
            if key not in canon and key in (S.EXPENSE_OPTIONAL + S.REVENUE_OPTIONAL):
                ws.update_cell(1, len(headers) + 1, key)
                headers.append(key)
                canon.add(key)
        row = record_to_row(table, record, headers, cat)
        ws.append_row(row, value_input_option="USER_ENTERED")

    def write_table(self, table: str, df: pd.DataFrame) -> None:
        """Replace a whole (small) table — used by setup script for config tabs."""
        ws = self._ws(table)
        ws.clear()
        values = [list(df.columns)] + df.astype(object).where(df.notna(), "").values.tolist()
        ws.update(values, value_input_option="USER_ENTERED")

    def snapshot(self) -> dict | None:
        from google.auth.transport.requests import AuthorizedSession

        session = AuthorizedSession(self._creds)
        stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        name = f"{self._ss.title} — Snapshot {stamp}"
        meta = session.get(f"https://www.googleapis.com/drive/v3/files/{self.spreadsheet_id}",
                           params={"fields": "parents"})
        meta.raise_for_status()
        body: dict = {"name": name}
        if meta.json().get("parents"):
            body["parents"] = meta.json()["parents"]
        resp = session.post(f"https://www.googleapis.com/drive/v3/files/{self.spreadsheet_id}/copy", json=body)
        resp.raise_for_status()
        cid = resp.json()["id"]
        return {"name": name, "url": f"https://docs.google.com/spreadsheets/d/{cid}/edit"}

    def describe(self) -> str:
        return f"Google Sheets · {self._ss.title}"
