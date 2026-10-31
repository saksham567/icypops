"""
core/finance.py — Revenue, expense, P&L and partner computations (pure pandas).

  Operational Cost       = Σ Expense where OperationalCost == 1
  Realized Profit        = Actual Revenue − Operational Cost
  Net P&L (breakeven)    = Actual Revenue − Total Expense (incl. capex like cart/freezer)
  Profit After Dividend  = Realized Profit − Total Dividend
  Expected Revenue       = Σ units sold (settled) × unit price
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core import schema as S
from core.catalog import Catalog
from core.inventory import compute_sold_trend, category_breakdown


def _dates(df: pd.DataFrame, col: str = S.DATE) -> pd.DataFrame:
    out = df.copy()
    out[col] = pd.to_datetime(out[col], errors="coerce").dt.normalize()
    return out.dropna(subset=[col])


def _flag(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0) > 0


# ── Expenses ─────────────────────────────────────────────────────────────────

def total_expense(df: pd.DataFrame) -> float:
    return float(pd.to_numeric(df[S.EXP_AMOUNT], errors="coerce").fillna(0).sum()) if not df.empty else 0.0


def operational_cost(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    amt = pd.to_numeric(df[S.EXP_AMOUNT], errors="coerce").fillna(0)
    return float(amt[_flag(df, S.EXP_OPERATIONAL)].sum())


def expense_by_payment(df: pd.DataFrame) -> dict[str, float]:
    totals = {c: 0.0 for c in S.PAYMENT_COLS}
    if df.empty:
        return totals
    amt = pd.to_numeric(df[S.EXP_AMOUNT], errors="coerce").fillna(0)
    for c in S.PAYMENT_COLS:
        totals[c] = float(amt[_flag(df, c)].sum())
    return totals


def partner_capital(df: pd.DataFrame, cat: Catalog) -> pd.DataFrame | None:
    """
    Own-money contributions per partner (requires the optional PaidBy column).
    Returns None when the column is absent or never filled, so the UI can hide the section.
    """
    if df.empty or S.EXP_PAID_BY not in df.columns:
        return None
    own = df[_flag(df, S.PAY_OWN)].copy()
    own[S.EXP_PAID_BY] = own[S.EXP_PAID_BY].astype(str).str.strip()
    own = own[own[S.EXP_PAID_BY] != ""]
    if own.empty:
        return None
    own[S.EXP_AMOUNT] = pd.to_numeric(own[S.EXP_AMOUNT], errors="coerce").fillna(0)
    contrib = own.groupby(S.EXP_PAID_BY)[S.EXP_AMOUNT].sum()
    rows = []
    total = float(contrib.sum())
    for p in cat.partners:
        paid = float(contrib.get(p.name, 0.0))
        fair = total * p.share_pct / (sum(x.share_pct for x in cat.partners) or 100)
        rows.append({"Partner": p.name, "Contributed": paid, "Fair share": fair, "Over / (Under)": paid - fair})
    for name, paid in contrib.items():
        if name not in cat.partner_names:
            rows.append({"Partner": name, "Contributed": float(paid), "Fair share": 0.0, "Over / (Under)": float(paid)})
    return pd.DataFrame(rows)


def monthly_expense_pivot(df: pd.DataFrame) -> pd.DataFrame | None:
    """Rows: Category (Operational / Non-Operational) › Type. Columns: months + Total."""
    if df.empty:
        return None
    d = _dates(df)
    if d.empty:
        return None
    d["Category"] = _flag(d, S.EXP_OPERATIONAL).map({True: "Operational", False: "Non-Operational"})
    d["Type"] = d[S.EXP_TYPE].astype(str).str.strip().replace("", "Uncategorised")
    d["MonthKey"] = d[S.DATE].dt.strftime("%Y-%m")
    d[S.EXP_AMOUNT] = pd.to_numeric(d[S.EXP_AMOUNT], errors="coerce").fillna(0)
    pivot = d.pivot_table(index=["Category", "Type"], columns="MonthKey",
                          values=S.EXP_AMOUNT, aggfunc="sum", fill_value=0)
    pivot = pivot[sorted(pivot.columns)]
    pivot.columns = [pd.to_datetime(m + "-01").strftime("%b %Y") for m in pivot.columns]
    pivot["Total"] = pivot.sum(axis=1)
    return pivot


def build_expense_grid(pivot: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Flatten Category › Type pivot into: Category | Type | months… | Total, with row kinds."""
    num_cols = list(pivot.columns)
    cats_present = set(pivot.index.get_level_values("Category"))
    rows, kinds = [], []
    for cat_name in ["Operational", "Non-Operational"]:
        if cat_name not in cats_present:
            continue
        detail = pivot.loc[cat_name].sort_values("Total", ascending=False)
        for typ, r in detail.iterrows():
            rows.append([cat_name, typ] + r[num_cols].tolist())
            kinds.append(cat_name)
        rows.append([cat_name, "Subtotal"] + detail[num_cols].sum().tolist())
        kinds.append("subtotal:" + cat_name)
    rows.append(["Total", ""] + pivot[num_cols].sum().tolist())
    kinds.append("grand")
    return pd.DataFrame(rows, columns=["Category", "Type"] + num_cols), kinds, num_cols


# ── Revenue ──────────────────────────────────────────────────────────────────

def total_revenue(df: pd.DataFrame) -> float:
    return float(pd.to_numeric(df[S.REV_AMOUNT], errors="coerce").fillna(0).sum()) if not df.empty else 0.0


def daily_actual_vs_expected(df_revenue: pd.DataFrame, df_fridge: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """Per-day Actual (Revenue table), Expected (settled sold units × price) and comments."""
    if df_revenue.empty:
        actual = pd.Series(dtype=float, name="Actual")
        comments = pd.Series(dtype=str, name="Comment")
    else:
        rev = _dates(df_revenue)
        rev[S.REV_AMOUNT] = pd.to_numeric(rev[S.REV_AMOUNT], errors="coerce").fillna(0)
        actual = rev.groupby(S.DATE)[S.REV_AMOUNT].sum().rename("Actual")
        if S.COMMENTS in rev.columns:
            comments = rev.groupby(S.DATE)[S.COMMENTS].apply(
                lambda s: " | ".join(str(x).strip() for x in s if str(x).strip() and str(x) != "nan")
            ).rename("Comment")
        else:
            comments = pd.Series("", index=actual.index, name="Comment")

    trend = compute_sold_trend(df_fridge, cat)
    if trend.empty:
        expected = pd.Series(dtype=float, name="Expected")
    else:
        bd = category_breakdown(trend, cat)
        expected = pd.Series(bd["Rev Total"].values, index=pd.to_datetime(bd[S.DATE]), name="Expected")

    out = pd.concat([actual, expected, comments], axis=1).reset_index().rename(columns={"index": S.DATE})
    out["Comment"] = out["Comment"].fillna("")
    out["Gap"] = out["Actual"] - out["Expected"]
    return out.sort_values(S.DATE).reset_index(drop=True)


# ── Dividends ────────────────────────────────────────────────────────────────

def dividend_totals(df: pd.DataFrame, cat: Catalog) -> dict[str, float]:
    """{'Total': x, '<Partner>': y, …} lifetime payouts."""
    out = {S.DIV_TOTAL: 0.0, **{p.name: 0.0 for p in cat.partners}}
    if df.empty:
        return out
    if S.DIV_TOTAL in df.columns:
        out[S.DIV_TOTAL] = float(pd.to_numeric(df[S.DIV_TOTAL], errors="coerce").fillna(0).sum())
    for p in cat.partners:
        if p.column in df.columns:
            out[p.name] = float(pd.to_numeric(df[p.column], errors="coerce").fillna(0).sum())
    if out[S.DIV_TOTAL] == 0 and cat.partners:
        out[S.DIV_TOTAL] = sum(out[p.name] for p in cat.partners)
    return out


# ── Summary bundle ───────────────────────────────────────────────────────────

@dataclass
class FinanceSummary:
    total_revenue: float = 0.0
    expected_revenue: float = 0.0
    total_expense: float = 0.0
    operational_cost: float = 0.0
    realized_profit: float = 0.0
    net_pnl: float = 0.0
    total_dividend: float = 0.0
    profit_after_dividend: float = 0.0
    gross_profit: float = 0.0
    payment_split: dict = field(default_factory=dict)
    dividends: dict = field(default_factory=dict)

    @property
    def revenue_gap(self) -> float:
        return self.total_revenue - self.expected_revenue


def summarize(frames: dict[str, pd.DataFrame], inv: pd.DataFrame, cat: Catalog) -> FinanceSummary:
    rev = total_revenue(frames[S.REVENUE])
    exp = total_expense(frames[S.EXPENSE])
    opex = operational_cost(frames[S.EXPENSE])
    div = dividend_totals(frames[S.DIVIDEND], cat)
    by_cat = pd.DataFrame()
    expected = gross = 0.0
    if not inv.empty:
        from core.inventory import expected_revenue_by_category
        by_cat = expected_revenue_by_category(inv, cat)
        expected = float(by_cat["Expected Revenue"].sum())
        gross = float(by_cat["Gross Profit"].sum())
    realized = rev - opex
    return FinanceSummary(
        total_revenue=rev, expected_revenue=expected, total_expense=exp, operational_cost=opex,
        realized_profit=realized, net_pnl=rev - exp, total_dividend=div[S.DIV_TOTAL],
        profit_after_dividend=realized - div[S.DIV_TOTAL], gross_profit=gross,
        payment_split=expense_by_payment(frames[S.EXPENSE]), dividends=div,
    )
