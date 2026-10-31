"""
core/entries.py — Build & validate records for the transactional tables (no Streamlit).

Each ``build_*`` returns ``(record, errors)``; ``record`` uses canonical column
names from core/schema.py and is accepted by every Repository.append().
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from core import schema as S
from core.catalog import Catalog


def _d(value: date) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def build_expense(entry_date: date, exp_type: str, description: str, amount: float, pay_method: str,
                  is_operational: bool, paid_by: str | None = None, comments: str = "") -> tuple[dict, list[str]]:
    errors = []
    if not str(exp_type).strip():
        errors.append("Type is required.")
    if amount is None or float(amount) <= 0:
        errors.append("Expense amount must be greater than 0.")
    if pay_method not in S.PAYMENT_COLS:
        errors.append("Choose a payment method.")
    if pay_method == S.PAY_OWN and paid_by is not None and not str(paid_by).strip():
        errors.append("Select which partner paid.")
    rec = {
        S.DATE: _d(entry_date), S.EXP_TYPE: str(exp_type).strip(), S.EXP_DESC: str(description).strip(),
        S.EXP_AMOUNT: float(amount or 0), **{c: int(c == pay_method) for c in S.PAYMENT_COLS},
        S.EXP_OPERATIONAL: int(bool(is_operational)),
        S.EXP_PAID_BY: str(paid_by).strip() if pay_method == S.PAY_OWN and paid_by else "",
        S.COMMENTS: str(comments or "").strip(),
    }
    return rec, errors


def build_quantities(entry_date: date, qty: dict[str, float], cat: Catalog, mode: str | None = None,
                     allow_empty: bool = False) -> tuple[dict, list[str]]:
    errors = []
    clean = {p: int(float(qty.get(p, 0) or 0)) for p in cat.all_product_names}
    if any(v < 0 for v in clean.values()):
        errors.append("Quantities cannot be negative.")
    if not allow_empty and sum(clean.values()) == 0:
        errors.append("Enter at least one quantity.")
    if mode is not None and mode not in S.FRIDGE_MODES:
        errors.append("Invalid movement mode.")
    rec = {S.DATE: _d(entry_date), **({S.MODE: mode} if mode is not None else {}), **clean}
    return rec, errors


def build_revenue(entry_date: date, amount: float, comments: str = "") -> tuple[dict, list[str]]:
    errors = [] if amount and float(amount) > 0 else ["Revenue must be greater than 0."]
    return {S.DATE: _d(entry_date), S.REV_AMOUNT: float(amount or 0), S.COMMENTS: str(comments or "").strip()}, errors


def build_dividend(entry_date: date, per_partner: dict[str, float], cat: Catalog) -> tuple[dict, list[str]]:
    errors = []
    amounts = {p: float(per_partner.get(p.name, 0) or 0) for p in cat.partners}
    total = sum(amounts.values())
    if total <= 0:
        errors.append("Enter a dividend amount.")
    if any(v < 0 for v in amounts.values()):
        errors.append("Amounts cannot be negative.")
    rec = {S.DATE: _d(entry_date), S.DIV_TOTAL: total, **{p.column: amounts[p] for p in cat.partners}}
    return rec, errors


def last_returns(df_fridge: pd.DataFrame, cat: Catalog) -> tuple[pd.Timestamp | None, dict[str, int]]:
    """Most recent 'from vendor' quantities — what is carried over into today's dispatch."""
    if df_fridge.empty:
        return None, {}
    fv = df_fridge[df_fridge[S.MODE] == S.MODE_FROM_VENDOR]
    if fv.empty:
        return None, {}
    last_date = fv[S.DATE].max()
    rows = fv[fv[S.DATE] == last_date]
    return last_date, {p: int(pd.to_numeric(rows[p], errors="coerce").fillna(0).sum()) for p in cat.all_product_names if p in rows.columns}


def expense_type_options(cat: Catalog, df_expense: pd.DataFrame) -> list[str]:
    seen: list[str] = []
    for t in list(cat.expense_types) + (df_expense[S.EXP_TYPE].dropna().astype(str).tolist() if not df_expense.empty else []):
        t = t.strip()
        if t and t not in seen:
            seen.append(t)
    return seen
