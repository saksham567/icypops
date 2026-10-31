"""
data/base.py — Repository interface + normalization shared by every backend.

A Repository knows how to read a table as a raw DataFrame and append one record.
It does NOT know about business rules. ``normalize()`` turns whatever a backend
returns into the canonical shape in core/schema.py, tolerating header
misspellings (``SAKSHAM_DIVIDENT``), case, extra whitespace and missing optional
columns — so the same code works on the current Google Sheet, a local workbook
or a SQL database.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any

import pandas as pd

from core import schema as S
from core.catalog import Catalog


class Repository(ABC):
    """Storage-agnostic access to the business tables."""

    name: str = "base"

    @abstractmethod
    def tables(self) -> list[str]:
        """Table names that physically exist in this backend."""

    @abstractmethod
    def read(self, table: str) -> pd.DataFrame:
        """Raw frame with the backend's own headers (may be empty)."""

    @abstractmethod
    def append(self, table: str, record: dict[str, Any], cat: Catalog) -> None:
        """Append one record. Keys are canonical column names."""

    def ensure_tables(self, cat: Catalog) -> None:  # noqa: B027 — optional hook
        """Create missing transactional tables / headers. Default: no-op."""

    def snapshot(self) -> dict | None:
        """Create a point-in-time backup. Returns {'name','url'|'path'} or None if unsupported."""
        return None

    def describe(self) -> str:
        return self.name

    def has(self, table: str) -> bool:
        return table in self.tables()


# ══════════════════════════════════════════════════════════════════════════════
#  Header tolerance
# ══════════════════════════════════════════════════════════════════════════════

def canonical_header(table: str, raw: str, cat: Catalog) -> str:
    """Map a backend header onto the canonical column name (or return it stripped)."""
    h = str(raw).strip()
    up = h.upper()
    if up == "DATE":
        return S.DATE
    if table == S.DIVIDEND:
        if up.startswith("TOTAL"):
            return S.DIV_TOTAL
        for p in cat.partners:
            if up.startswith(p.name.upper()):
                return p.column
        return h
    if table == S.EXPENSE:
        for c in S.EXPENSE_REQUIRED + S.EXPENSE_OPTIONAL:
            if up == c.upper():
                return c
        if up in {"AMOUNT", "COST"}:
            return S.EXP_AMOUNT
        return h
    if table == S.REVENUE:
        if up in {"REVENUE", "AMOUNT", "SALES"}:
            return S.REV_AMOUNT
        if up in {"COMMENT", "COMMENTS", "NOTE", "NOTES"}:
            return S.COMMENTS
        return h
    if table == S.FRIDGE and up == "MODE":
        return S.MODE
    if table in (S.BOUGHT, S.FRIDGE):
        # product headers: match case-insensitively against the catalog
        for name in cat.all_product_names:
            if up == name.upper():
                return name
        return h
    if table in S.CONFIG_TABLES:
        cols = {S.PRODUCTS: S.PRODUCTS_COLS, S.PARTNERS: S.PARTNERS_COLS, S.SETTINGS: S.SETTINGS_COLS}[table]
        for c in cols:
            if up == c.upper():
                return c
    return h


def required_columns(table: str, cat: Catalog) -> list[str]:
    products = cat.all_product_names
    return {
        S.EXPENSE: S.EXPENSE_REQUIRED,
        S.BOUGHT: [S.DATE] + products,
        S.FRIDGE: [S.DATE, S.MODE] + products,
        S.REVENUE: S.REVENUE_REQUIRED,
        S.DIVIDEND: [S.DATE, S.DIV_TOTAL] + [p.column for p in cat.partners],
        S.PRODUCTS: S.PRODUCTS_COLS,
        S.PARTNERS: S.PARTNERS_COLS,
        S.SETTINGS: S.SETTINGS_COLS,
    }[table]


def optional_columns(table: str) -> list[str]:
    return {S.EXPENSE: S.EXPENSE_OPTIONAL, S.REVENUE: S.REVENUE_OPTIONAL}.get(table, [])


def all_columns(table: str, cat: Catalog) -> list[str]:
    return required_columns(table, cat) + optional_columns(table)


def empty_frame(table: str, cat: Catalog) -> pd.DataFrame:
    cols = all_columns(table, cat)
    df = pd.DataFrame(columns=cols)
    for c in cols:
        df[c] = df[c].astype(object if c in S.TEXT_COLS else float)
    return df


def normalize(table: str, raw: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """Canonical headers, required columns present, numeric coercion, parsed dates."""
    if raw is None or raw.empty:
        return empty_frame(table, cat)

    df = raw.copy()
    df.columns = [canonical_header(table, c, cat) for c in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]

    # Drop fully blank rows (Sheets often returns trailing empties)
    df = df.replace({"": pd.NA}).dropna(how="all")
    if df.empty:
        return empty_frame(table, cat)

    for col in all_columns(table, cat):
        if col not in df.columns:
            df[col] = pd.NA

    # Keep canonical columns first, then any extra columns the user added
    extras = [c for c in df.columns if c not in all_columns(table, cat)]
    df = df[all_columns(table, cat) + extras]

    if S.DATE in df.columns:
        df[S.DATE] = _parse_dates(df[S.DATE])

    for c in df.columns:
        if c in S.TEXT_COLS or c == S.DATE:
            if c != S.DATE:
                df[c] = df[c].astype(object).where(df[c].notna(), "").astype(str).str.strip()
                df[c] = df[c].replace({"nan": "", "None": "", "<NA>": ""})
        else:
            df[c] = coerce_number(df[c])

    if table in S.TRANSACTION_TABLES:
        # Rows with an unreadable date are KEPT (they still count in totals, as in the original app);
        # they simply don't appear in date-based charts. load_bundle reports how many there are.
        df = df.sort_values(S.DATE, kind="stable", na_position="last")
    return df.reset_index(drop=True)


_TRUTHY = {"true": 1, "yes": 1, "y": 1, "x": 1, "✓": 1, "false": 0, "no": 0, "n": 0, "": 0}


def coerce_number(s: pd.Series) -> pd.Series:
    """Numbers from anything a spreadsheet may display: '₹49,236.00', 'TRUE', '1,25,000', ' 12 '."""
    if pd.api.types.is_bool_dtype(s):
        return s.astype(int).astype(float)
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0).astype(float)
    txt = s.astype(object).where(s.notna(), "").astype(str).str.strip()
    lowered = txt.str.lower()
    out = pd.to_numeric(txt, errors="coerce")
    mask = out.isna()
    if mask.any():
        out.loc[mask] = lowered[mask].map(_TRUTHY)
    mask = out.isna()
    if mask.any():
        cleaned = txt[mask].str.replace(r"[^\d.\-]", "", regex=True).replace({"": None, "-": None, ".": None})
        out.loc[mask] = pd.to_numeric(cleaned, errors="coerce")
    return out.fillna(0).astype(float)


def _parse_dates(s: pd.Series) -> pd.Series:
    """Parse ISO / d-m-Y / Excel-serial dates robustly."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s).dt.normalize()
    num = pd.to_numeric(s, errors="coerce")
    serial_mask = num.notna() & (num > 20000) & (num < 80000)          # Excel / Sheets serial dates
    text = s.astype(object).where(~serial_mask, None)
    # ISO first; anything else is treated day-first (dd/mm/yyyy — the Indian / Sheets default)
    out = pd.to_datetime(text, errors="coerce", format="%Y-%m-%d")
    rest = out.isna() & text.notna()
    if rest.any():
        out.loc[rest] = pd.to_datetime(text[rest], errors="coerce", format="mixed", dayfirst=True)
    if serial_mask.any():
        out = out.astype("datetime64[ns]")
        out.loc[serial_mask] = pd.to_datetime(num[serial_mask], unit="D", origin="1899-12-30")
    return out.dt.normalize()


def record_to_row(table: str, record: dict[str, Any], headers: list[str], cat: Catalog) -> list:
    """Order a canonical record according to the backend's header row (missing → blank)."""
    canon = [canonical_header(table, h, cat) for h in headers]
    row = []
    for c in canon:
        v = record.get(c, "")
        row.append(_cell(v))
    return row


def _cell(v: Any):
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    if v is None:
        return ""
    if isinstance(v, bool):
        return int(v)
    return v


def to_long(table: str, df: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """Wide product frame → long (Date, [Mode], Product, Qty). Used for SQL & exports."""
    products = [p for p in cat.all_product_names if p in df.columns]
    id_vars = [S.DATE] + ([S.MODE] if table == S.FRIDGE else [])
    long = df.melt(id_vars=id_vars, value_vars=products, var_name="Product", value_name="Qty")
    long["Qty"] = pd.to_numeric(long["Qty"], errors="coerce").fillna(0)
    return long[long["Qty"] != 0].reset_index(drop=True)
