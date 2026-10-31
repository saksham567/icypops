"""
core/analytics.py — Owner-facing analytics on top of inventory/finance (pure pandas).

Everything here is either *period-scoped* (takes a Window) or explicitly lifetime.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from core import schema as S
from core.catalog import Catalog
from core.finance import _flag
from core.inventory import category_breakdown, compute_sold_trend


# ── Periods ───────────────────────────────────────────────────────────────────

PERIODS = ["All time", "This month", "This week"]


@dataclass(frozen=True)
class Window:
    start: pd.Timestamp | None       # None = open-ended
    end: pd.Timestamp
    label: str

    @property
    def days(self) -> int | None:
        return None if self.start is None else int((self.end - self.start).days) + 1

    def previous(self) -> "Window | None":
        """Comparable earlier window: previous calendar month / week, else same length before."""
        if self.start is None:
            return None
        if self.label == "This month":
            last_prev = self.start - timedelta(days=1)
            return Window(last_prev.replace(day=1), last_prev, "last month")
        if self.label == "This week":
            return Window(self.start - timedelta(days=7), self.start - timedelta(days=1), "last week")
        n = self.days or 0
        return Window(self.start - timedelta(days=n), self.start - timedelta(days=1), f"previous {n} days")

    def mask(self, dates: pd.Series) -> pd.Series:
        m = dates <= self.end
        if self.start is not None:
            m &= dates >= self.start
        return m.fillna(False)

    def describe(self) -> str:
        if self.start is None:
            return f"All data up to {self.end:%d %b %Y}"
        return f"{self.start:%d %b %Y} – {self.end:%d %b %Y} · {self.days} days"


def make_window(period: str, today: date | None = None, custom: tuple[date, date] | None = None,
                data_end: pd.Timestamp | None = None) -> Window:
    today_ts = pd.Timestamp(today or date.today()).normalize()
    end = today_ts
    if period == "This month":
        return Window(end.replace(day=1), end, period)
    if period == "This week":                       # Monday → today
        return Window(end - timedelta(days=end.dayofweek), end, period)
    if period == "Custom" and custom:
        return Window(pd.Timestamp(custom[0]), pd.Timestamp(custom[1]), period)
    return Window(None, max(end, data_end) if data_end is not None else end, "All time")


def in_window(df: pd.DataFrame, w: Window) -> pd.DataFrame:
    if df.empty or S.DATE not in df.columns:
        return df
    return df[w.mask(df[S.DATE])]


def pct_change(cur: float, prev: float) -> float | None:
    if prev in (0, None) or pd.isna(prev):
        return None
    return (cur - prev) / abs(prev) * 100


# ── Period summary ────────────────────────────────────────────────────────────

@dataclass
class PeriodStats:
    revenue: float = 0.0
    expected: float = 0.0
    units: float = 0.0
    gross_profit: float = 0.0
    op_expense: float = 0.0
    capex: float = 0.0
    trading_days: int = 0
    revenue_days: int = 0

    @property
    def operating_profit(self) -> float:
        return self.revenue - self.op_expense

    @property
    def gap(self) -> float:
        return self.revenue - self.expected

    @property
    def avg_daily_revenue(self) -> float:
        return self.revenue / self.revenue_days if self.revenue_days else 0.0

    @property
    def avg_ticket_units(self) -> float:
        return self.units / self.trading_days if self.trading_days else 0.0


def period_stats(frames: dict[str, pd.DataFrame], sold_trend: pd.DataFrame, cat: Catalog, w: Window) -> PeriodStats:
    ps = PeriodStats()
    rev = in_window(frames[S.REVENUE], w)
    if not rev.empty:
        ps.revenue = float(rev[S.REV_AMOUNT].sum())
        ps.revenue_days = int(rev[S.DATE].dropna().nunique())
    exp = in_window(frames[S.EXPENSE], w)
    if not exp.empty:
        op = _flag(exp, S.EXP_OPERATIONAL)
        ps.op_expense = float(exp.loc[op, S.EXP_AMOUNT].sum())
        ps.capex = float(exp.loc[~op, S.EXP_AMOUNT].sum())
    st = in_window(sold_trend, w)
    if not st.empty:
        bd = category_breakdown(st, cat)
        ps.units = float(bd["Units Total"].sum())
        ps.expected = float(bd["Rev Total"].sum())
        ps.gross_profit = float(bd["Gross Profit"].sum())
        ps.trading_days = int(st[S.DATE].nunique())
    return ps


# ── Lifetime: investment recovery ─────────────────────────────────────────────

@dataclass
class Recovery:
    invested: float            # non-operational (capex) spend, lifetime
    recovered: float           # cumulative realized profit (revenue − operational cost)
    dividends: float

    @property
    def remaining(self) -> float:
        return max(self.invested - self.recovered, 0.0)

    @property
    def pct(self) -> float:
        return min(max(self.recovered / self.invested * 100, 0.0), 100.0) if self.invested > 0 else 100.0

    @property
    def net_pnl(self) -> float:
        return self.recovered - self.invested

    @property
    def distributable(self) -> float:
        return self.recovered - self.dividends


def recovery(frames: dict[str, pd.DataFrame], total_dividend: float) -> Recovery:
    exp = frames[S.EXPENSE]
    rev = frames[S.REVENUE]
    op = _flag(exp, S.EXP_OPERATIONAL) if not exp.empty else pd.Series(dtype=bool)
    invested = float(exp.loc[~op, S.EXP_AMOUNT].sum()) if not exp.empty else 0.0
    opex = float(exp.loc[op, S.EXP_AMOUNT].sum()) if not exp.empty else 0.0
    revenue = float(rev[S.REV_AMOUNT].sum()) if not rev.empty else 0.0
    return Recovery(invested=invested, recovered=revenue - opex, dividends=total_dividend)


def payback_estimate(rec: Recovery, recent: PeriodStats) -> float | None:
    """Days until investment is recovered at the recent operating-profit run rate."""
    if rec.remaining <= 0:
        return 0
    if not recent.revenue_days or recent.operating_profit <= 0:
        return None
    daily = recent.operating_profit / recent.revenue_days
    return rec.remaining / daily


# ── Product analytics ─────────────────────────────────────────────────────────

def product_period_sales(sold_trend: pd.DataFrame, bought: pd.DataFrame, cat: Catalog, w: Window) -> pd.DataFrame:
    """Per product within the window: Units Sold, Units Bought, Revenue, Gross Profit, Share %."""
    products = cat.product_names
    st = in_window(sold_trend, w)
    sold = st[products].sum() if not st.empty else pd.Series(0.0, index=products)
    bt = in_window(bought, w)
    bought_s = bt[products].sum() if not bt.empty else pd.Series(0.0, index=products)
    df = pd.DataFrame({
        "Product": products,
        "Category": [cat.category_of(p).label for p in products],
        "Units Sold": sold.reindex(products).values,
        "Units Bought": bought_s.reindex(products).values,
    }).set_index("Product")
    df["Revenue"] = df.index.map(lambda p: sold.get(p, 0) * cat.price(p)).astype(float)
    df["Gross Profit"] = df.index.map(lambda p: sold.get(p, 0) * cat.margin(p)).astype(float)
    total_rev = df["Revenue"].sum()
    df["Share %"] = (df["Revenue"] / total_rev * 100).fillna(0) if total_rev else 0.0
    return df


def days_of_cover(inv: pd.DataFrame, sold_trend: pd.DataFrame, cat: Catalog, lookback_days: int = 14) -> pd.DataFrame:
    """Stock Left ÷ average daily units sold over the last N settled days."""
    products = cat.product_names
    out = inv[["Category", "Stock Left", "Reorder Threshold", "Needs Reorder"]].copy()
    if sold_trend.empty:
        out["Avg/day"] = 0.0
    else:
        end = sold_trend[S.DATE].max()
        recent = sold_trend[sold_trend[S.DATE] > end - timedelta(days=lookback_days)]
        n = max(int(recent[S.DATE].nunique()), 1)
        out["Avg/day"] = (recent[products].sum() / n).reindex(out.index).fillna(0).values
    out["Days of cover"] = (out["Stock Left"] / out["Avg/day"].where(out["Avg/day"] > 0)).round(0)
    out["Status"] = out.apply(_stock_status, axis=1)
    return out


def _stock_status(r) -> str:
    if r["Stock Left"] <= 0:
        return "Out of stock"
    if r["Needs Reorder"] or (pd.notna(r["Days of cover"]) and r["Days of cover"] <= 7):
        return "Reorder now"
    if pd.notna(r["Days of cover"]) and r["Days of cover"] <= 14:
        return "Watch"
    return "Healthy"


def category_mix(psales: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    g = psales.groupby("Category")[["Units Sold", "Revenue", "Gross Profit"]].sum().reset_index()
    order = {c.label: c.sort_order for c in cat.categories}
    colors = {c.label: c.color for c in cat.categories}
    g["_o"] = g["Category"].map(order)
    g["Color"] = g["Category"].map(colors)
    return g.sort_values("_o").drop(columns="_o").reset_index(drop=True)


# ── Revenue patterns ──────────────────────────────────────────────────────────

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def weekday_pattern(revenue: pd.DataFrame, w: Window) -> pd.DataFrame:
    rev = in_window(revenue, w).dropna(subset=[S.DATE])
    if rev.empty:
        return pd.DataFrame({"Weekday": WEEKDAYS, "Avg Revenue": 0.0, "Days": 0})
    daily = rev.groupby(S.DATE)[S.REV_AMOUNT].sum().reset_index()
    daily["Weekday"] = daily[S.DATE].dt.dayofweek.map(dict(enumerate(WEEKDAYS)))
    g = daily.groupby("Weekday")[S.REV_AMOUNT].agg(["mean", "count"]).reindex(WEEKDAYS).fillna(0).reset_index()
    g.columns = ["Weekday", "Avg Revenue", "Days"]
    return g


def expense_by_type(expense: pd.DataFrame, w: Window) -> pd.DataFrame:
    exp = in_window(expense, w)
    if exp.empty:
        return pd.DataFrame(columns=["Type", "Amount", "Operational"])
    e = exp.copy()
    e["Type"] = e[S.EXP_TYPE].astype(str).str.strip().replace("", "Uncategorised")
    e["Operational"] = _flag(e, S.EXP_OPERATIONAL)
    g = e.groupby(["Type", "Operational"])[S.EXP_AMOUNT].sum().reset_index().rename(columns={S.EXP_AMOUNT: "Amount"})
    return g.sort_values("Amount", ascending=False).reset_index(drop=True)


def resample_breakdown(bd: pd.DataFrame, freq: str) -> tuple[pd.DataFrame, str]:
    """Daily category breakdown → 'D' | 'W' | 'M' buckets. Returns (df, x column)."""
    if freq == "D":
        return bd, S.DATE
    d = bd.copy()
    d["Bucket"] = d[S.DATE].dt.to_period("W" if freq == "W" else "M")
    num = [c for c in d.columns if c not in (S.DATE, "Bucket")]
    g = d.groupby("Bucket")[num].sum().reset_index()
    g["Bucket"] = g["Bucket"].dt.start_time if freq == "W" else g["Bucket"].dt.strftime("%b %Y")
    return g, "Bucket"


def sold_trend_for(frames: dict[str, pd.DataFrame], cat: Catalog) -> pd.DataFrame:
    return compute_sold_trend(frames[S.FRIDGE], cat)
