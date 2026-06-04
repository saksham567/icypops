"""
metrics.py — All inventory computations for IcyPops dashboard.

Definitions (per product, lifetime cumulative):
  Total Bought       = sum of Bought sheet quantities
  from_stock         = sum of Fridge rows where Mode == 'from stock'
  to_vendor          = sum of Fridge rows where Mode == 'to vendor'
  from_vendor        = sum of Fridge rows where Mode == 'from vendor'

  Stock Outside Fridge = Total Bought  - from_stock
  Stock Inside Fridge  = from_stock    - to_vendor  + from_vendor
  Sold                 = to_vendor     - from_vendor
  Stock Left           = Total Bought  + from_vendor - to_vendor
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path

THRESHOLDS_PATH = Path(__file__).parent / "thresholds.json"

def load_thresholds():
    with open(THRESHOLDS_PATH) as f:
        return json.load(f)


def compute_inventory(df_bought: pd.DataFrame, df_fridge: pd.DataFrame, products: list) -> pd.DataFrame:
    """Return a per-product inventory summary DataFrame."""

    def _sum_mode(df, mode):
        sub = df[df["Mode"] == mode][products].copy()
        for c in products:
            sub[c] = pd.to_numeric(sub[c], errors="coerce").fillna(0)
        return sub.sum()

    total_bought  = pd.Series({p: pd.to_numeric(df_bought[p], errors="coerce").fillna(0).sum() for p in products})
    from_stock_s  = _sum_mode(df_fridge, "from stock")
    to_vendor_s   = _sum_mode(df_fridge, "to vendor")
    from_vendor_s = _sum_mode(df_fridge, "from vendor")

    inv = pd.DataFrame({
        "Product":              products,
        "Total Bought":         total_bought.values,
        "from_stock":           from_stock_s.values,
        "to_vendor":            to_vendor_s.values,
        "from_vendor":          from_vendor_s.values,
        "Stock Outside Fridge": (total_bought - from_stock_s).values,
        "Stock Inside Fridge":  (from_stock_s - to_vendor_s + from_vendor_s).values,
        "Sold":                 (to_vendor_s - from_vendor_s).values,
        "Stock Left":           (total_bought + from_vendor_s - to_vendor_s).values,
    })
    inv = inv.set_index("Product")

    thresholds = load_thresholds()
    inv["Reorder Threshold"]      = inv.index.map(lambda p: thresholds["reorder_threshold"].get(p, 0))
    inv["Fridge Threshold"]       = inv.index.map(lambda p: thresholds["fridge_threshold"].get(p, 0))
    inv["Needs Reorder"]          = inv["Stock Left"]          < inv["Reorder Threshold"]
    inv["Fridge Stock Low"]       = inv["Stock Inside Fridge"] < inv["Fridge Threshold"]

    return inv


def compute_daily_revenue_expense(df_revenue: pd.DataFrame, df_expense: pd.DataFrame) -> pd.DataFrame:
    """Return daily net P&L."""
    rev = df_revenue.copy()
    exp = df_expense.copy()

    rev["Revenue"] = pd.to_numeric(rev["Revenue"], errors="coerce").fillna(0)
    exp["Expense"] = pd.to_numeric(exp["Expense"], errors="coerce").fillna(0)

    rev["Date"] = pd.to_datetime(rev["Date"], errors="coerce")
    exp["Date"] = pd.to_datetime(exp["Date"], errors="coerce")

    rev_daily = rev.groupby("Date")["Revenue"].sum().reset_index()
    exp_daily = exp.groupby("Date")["Expense"].sum().reset_index()

    pnl = pd.merge(rev_daily, exp_daily, on="Date", how="outer").fillna(0)
    pnl = pnl.sort_values("Date")
    pnl["Net"] = pnl["Revenue"] - pnl["Expense"]
    pnl["Cumulative Net"] = pnl["Net"].cumsum()
    return pnl


def compute_sold_trend(df_fridge: pd.DataFrame, products: list) -> pd.DataFrame:
    """Daily net sold (to_vendor - from_vendor) per product."""
    df = df_fridge.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for p in products:
        df[p] = pd.to_numeric(df[p], errors="coerce").fillna(0)

    tv = df[df["Mode"] == "to vendor"].groupby("Date")[products].sum()
    fv = df[df["Mode"] == "from vendor"].groupby("Date")[products].sum()
    sold = tv.subtract(fv, fill_value=0).reset_index()
    sold["Total Sold"] = sold[products].sum(axis=1)
    return sold


def compute_expense_breakdown(df_expense: pd.DataFrame) -> pd.DataFrame:
    """Expense grouped by Type."""
    df = df_expense.copy()
    df["Expense"] = pd.to_numeric(df["Expense"], errors="coerce").fillna(0)
    return df.groupby("Type")["Expense"].sum().reset_index().sort_values("Expense", ascending=False)


def compute_top_products(inv: pd.DataFrame, n=5) -> pd.DataFrame:
    return inv["Sold"].sort_values(ascending=False).head(n).reset_index()
