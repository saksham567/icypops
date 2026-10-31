"""
data/local_repo.py — .xlsx workbook backend.

Mirrors the Google Sheet tab-for-tab so the exported workbook *is* a valid
backend. Used for demo mode, offline work and tests. Appends are written back
with openpyxl so the Data Entry tab works end-to-end in a walkthrough.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook, load_workbook

from core import schema as S
from core.catalog import Catalog
from data.base import Repository, canonical_header, record_to_row, required_columns


class LocalWorkbookRepository(Repository):
    name = "local"

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            Workbook().save(self.path)

    # ── reads ──────────────────────────────────────────────────────────────
    def tables(self) -> list[str]:
        wb = load_workbook(self.path, read_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()

    def read(self, table: str) -> pd.DataFrame:
        if table not in self.tables():
            return pd.DataFrame()
        return pd.read_excel(self.path, sheet_name=table)

    # ── writes ─────────────────────────────────────────────────────────────
    def ensure_tables(self, cat: Catalog) -> None:
        wb = load_workbook(self.path)
        changed = False
        for table in S.TRANSACTION_TABLES:
            if table not in wb.sheetnames:
                ws = wb.create_sheet(table)
                ws.append(required_columns(table, cat))
                changed = True
        if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1 and wb["Sheet"].max_row <= 1:
            del wb["Sheet"]
            changed = True
        if changed:
            wb.save(self.path)

    def append(self, table: str, record: dict[str, Any], cat: Catalog) -> None:
        wb = load_workbook(self.path)
        if table not in wb.sheetnames:
            ws = wb.create_sheet(table)
            ws.append(required_columns(table, cat))
        ws = wb[table]
        headers = [c.value for c in ws[1] if c.value is not None]
        if not headers:
            headers = required_columns(table, cat)
            ws.append(headers)
        # add optional canonical columns that the record carries but the sheet lacks
        canon = {canonical_header(table, h, cat) for h in headers}
        for key in record:
            if key not in canon and key in (S.EXPENSE_OPTIONAL + S.REVENUE_OPTIONAL):
                ws.cell(row=1, column=len(headers) + 1, value=key)
                headers.append(key)
                canon.add(key)
        row = record_to_row(table, record, headers, cat)
        # store real dates as dates so Excel formats them
        for i, h in enumerate(headers):
            if canonical_header(table, h, cat) == S.DATE and row[i]:
                row[i] = datetime.strptime(str(row[i]), "%Y-%m-%d")
        ws.append(row)
        wb.save(self.path)

    def snapshot(self) -> dict | None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest = self.path.with_name(f"{self.path.stem}_snapshot_{stamp}{self.path.suffix}")
        shutil.copy2(self.path, dest)
        return {"name": dest.name, "path": str(dest)}

    def describe(self) -> str:
        return f"Local workbook · {self.path.name}"
