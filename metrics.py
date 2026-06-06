"""
metrics.py — All inventory computations for IcyPops dashboard.

Definitions (per product, lifetime cumulative):
  Total Bought         = sum of Bought sheet quantities
  from_stock           = sum of Fridge rows where Mode == 'from stock'
  to_vendor            = sum of Fridge rows where Mode == 'to vendor'   (settled days only)
  from_vendor          = sum of Fridge rows where Mode == 'from vendor' (settled days only)

  A day is "settled" only when BOTH 'to vendor' AND 'from vendor' entries exist for that date.
  Unsettled to_vendor rows are excluded from Sold, Stock Left, and Stock Inside Fridge.

  Stock Outside Fridge = Total Bought  - from_stock
  Stock Inside Fridge  = from_stock    - to_vendor  + from_vendor    (settled only)
  Sold                 = to_vendor     - from_vendor                  (settled only)
  Stock Left           = Total Bought  + from_vendor - to_vendor      (settled only)
"""

import json
import pandas as pd
from pathlib import Path

THRESHOLDS_PATH = Path(__file__).parent / "thresholds.json"


def load_thresholds() -> dict:
    with open(THRESHOLDS_PATH) as f:
        return json.load(f)


def _coerce_products(df: pd.DataFrame, products: list) -> pd.DataFrame:
    """In-place numeric coercion for product columns."""
    for p in products:
        if p in df.columns:
            df[p] = pd.to_numeric(df[p], errors="coerce").fillna(0)
    return df


def _settled_dates(df_fridge: pd.DataFrame) -> set:
    """Return dates where both 'to vendor' and 'from vendor' entries exist."""
    dates_tv = set(df_fridge[df_fridge["Mode"] == "to vendor"]["Date"].dropna().unique())
    dates_fv = set(df_fridge[df_fridge["Mode"] == "from vendor"]["Date"].dropna().unique())
    return dates_tv & dates_fv


def _sum_mode(df: pd.DataFrame, mode: str, products: list, dates=None) -> pd.Series:
    """Sum product quantities for a given mode, optionally filtered to specific dates."""
    mask = df["Mode"] == mode
    if dates is not None:
        mask &= df["Date"].isin(dates)
    sub = df[mask][products].copy()
    return _coerce_products(sub, products).sum()


def compute_inventory(df_bought: pd.DataFrame, df_fridge: pd.DataFrame, products: list) -> pd.DataFrame:
    """Return a per-product inventory summary DataFrame."""

    df_fridge = df_fridge.copy()
    df_fridge["Date"] = pd.to_datetime(df_fridge["Date"], errors="coerce")

    settled = _settled_dates(df_fridge)

    total_bought  = pd.Series({p: pd.to_numeric(df_bought[p], errors="coerce").fillna(0).sum() for p in products})
    from_stock_s  = _sum_mode(df_fridge, "from stock",  products)
    to_vendor_s   = _sum_mode(df_fridge, "to vendor",   products, dates=settled)
    from_vendor_s = _sum_mode(df_fridge, "from vendor", products, dates=settled)

    inv = pd.DataFrame({
        "Product":              products,
        "Total Bought":         total_bought.values,
        "Stock Outside Fridge": (total_bought - from_stock_s).values,
        "Stock Inside Fridge":  (from_stock_s - to_vendor_s + from_vendor_s).values,
        "Sold":                 (to_vendor_s - from_vendor_s).values,
        "Stock Left":           (total_bought + from_vendor_s - to_vendor_s).values,
    }).set_index("Product")

    thresholds = load_thresholds()
    inv["Reorder Threshold"] = inv.index.map(lambda p: thresholds["reorder_threshold"].get(p, 0))
    inv["Fridge Threshold"]  = inv.index.map(lambda p: thresholds["fridge_threshold"].get(p, 0))
    inv["Needs Reorder"]     = inv["Stock Left"]          < inv["Reorder Threshold"]
    inv["Fridge Stock Low"] = inv["Stock Inside Fridge"] < inv["Fridge Threshold"]
    return inv


def compute_daily_revenue_expense(df_revenue: pd.DataFrame, df_expense: pd.DataFrame) -> pd.DataFrame:
    """Return daily and cumulative P&L."""
    def _prep(df, col):
        df = df.copy()
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df[col]    = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df.groupby("Date")[col].sum().reset_index()

    pnl = pd.merge(_prep(df_revenue, "Revenue"), _prep(df_expense, "Expense"),
                   on="Date", how="outer").fillna(0).sort_values("Date")
    pnl["Net"]            = pnl["Revenue"] - pnl["Expense"]
    pnl["Cumulative Net"] = pnl["Net"].cumsum()
    return pnl


def compute_sold_trend(df_fridge: pd.DataFrame, products: list) -> pd.DataFrame:
    """Daily net sold (to_vendor - from_vendor) for settled days only."""
    df = df_fridge.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = _coerce_products(df, products)

    settled = _settled_dates(df)
    tv   = df[(df["Mode"] == "to vendor")   & df["Date"].isin(settled)].groupby("Date")[products].sum()
    fv   = df[(df["Mode"] == "from vendor") & df["Date"].isin(settled)].groupby("Date")[products].sum()
    sold = tv.subtract(fv, fill_value=0).reset_index()
    sold["Total Sold"] = sold[products].sum(axis=1)
    return sold


def compute_expense_breakdown(df_expense: pd.DataFrame) -> pd.DataFrame:
    """Expense totals grouped by Type, descending."""
    df = df_expense.copy()
    df["Expense"] = pd.to_numeric(df["Expense"], errors="coerce").fillna(0)
    return df.groupby("Type")["Expense"].sum().reset_index().sort_values("Expense", ascending=False)


def compute_top_products(inv: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    return inv["Sold"].sort_values(ascending=False).head(n).reset_index()