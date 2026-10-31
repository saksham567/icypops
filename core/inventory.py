"""
core/inventory.py — Inventory computations (pure pandas, no Streamlit).

Definitions (per product, lifetime cumulative):
  Total Bought         = sum of Bought quantities
  from_stock           = sum of Fridge rows where Mode == 'from stock'
  to_vendor            = sum of Fridge rows where Mode == 'to vendor'   (settled days only)
  from_vendor          = sum of Fridge rows where Mode == 'from vendor' (settled days only)

  A day is "settled" only when BOTH 'to vendor' AND 'from vendor' entries exist for that date.
  Unsettled 'to vendor' rows are excluded from Sold, Stock Left and Stock Inside Fridge —
  otherwise a day that is still in progress would look like everything was sold.

  Stock Outside Fridge = Total Bought  - from_stock
  Stock Inside Fridge  = from_stock    - to_vendor  + from_vendor    (settled only)
  Sold                 = to_vendor     - from_vendor                  (settled only)
  Stock Left           = Total Bought  + from_vendor - to_vendor      (settled only)
                       = Stock Outside Fridge + Stock Inside Fridge
"""
from __future__ import annotations

import pandas as pd

from core import schema as S
from core.catalog import Catalog


# ── helpers ──────────────────────────────────────────────────────────────────

def _numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0) if c in out.columns else 0
    return out


def _with_dates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out[S.DATE] = pd.to_datetime(out[S.DATE], errors="coerce").dt.normalize()
    return out


def settled_dates(df_fridge: pd.DataFrame) -> set:
    """Dates that have both a 'to vendor' and a 'from vendor' entry."""
    if df_fridge.empty:
        return set()
    df = _with_dates(df_fridge)
    tv = set(df.loc[df[S.MODE] == S.MODE_TO_VENDOR, S.DATE].dropna())
    fv = set(df.loc[df[S.MODE] == S.MODE_FROM_VENDOR, S.DATE].dropna())
    return tv & fv


def unsettled_dates(df_fridge: pd.DataFrame) -> list[pd.Timestamp]:
    """Dates with a dispatch ('to vendor') but no return ('from vendor') yet — day not closed."""
    if df_fridge.empty:
        return []
    df = _with_dates(df_fridge)
    tv = set(df.loc[df[S.MODE] == S.MODE_TO_VENDOR, S.DATE].dropna())
    fv = set(df.loc[df[S.MODE] == S.MODE_FROM_VENDOR, S.DATE].dropna())
    return sorted(tv - fv)


def _sum_mode(df: pd.DataFrame, mode: str, products: list[str], dates: set | None = None) -> pd.Series:
    mask = df[S.MODE] == mode
    if dates is not None:
        mask &= df[S.DATE].isin(dates)
    sub = _numeric(df.loc[mask], products)
    return sub[products].sum() if not sub.empty else pd.Series(0.0, index=products)


# ── public API ───────────────────────────────────────────────────────────────

def compute_inventory(df_bought: pd.DataFrame, df_fridge: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """Per-product inventory summary, indexed by product name."""
    products = cat.product_names
    bought = _numeric(df_bought, products)
    fridge = _with_dates(_numeric(df_fridge, products)) if not df_fridge.empty else df_fridge

    total_bought = bought[products].sum() if not bought.empty else pd.Series(0.0, index=products)

    if fridge.empty:
        zero = pd.Series(0.0, index=products)
        from_stock, to_vendor, from_vendor = zero, zero, zero
    else:
        settled = settled_dates(fridge)
        from_stock = _sum_mode(fridge, S.MODE_FROM_STOCK, products)
        to_vendor = _sum_mode(fridge, S.MODE_TO_VENDOR, products, settled)
        from_vendor = _sum_mode(fridge, S.MODE_FROM_VENDOR, products, settled)

    inv = pd.DataFrame({
        "Product": products,
        "Category": [cat.category_of(p).label for p in products],
        "Total Bought": total_bought.reindex(products).values,
        "Stock Outside Fridge": (total_bought - from_stock).reindex(products).values,
        "Stock Inside Fridge": (from_stock - to_vendor + from_vendor).reindex(products).values,
        "Sold": (to_vendor - from_vendor).reindex(products).values,
        "Stock Left": (total_bought + from_vendor - to_vendor).reindex(products).values,
    }).set_index("Product")

    reorder_thr, fridge_thr = cat.thresholds()
    inv["Reorder Threshold"] = inv.index.map(reorder_thr).fillna(0)
    inv["Fridge Threshold"] = inv.index.map(fridge_thr).fillna(0)
    inv["Fridge Tracked"] = [cat.product(p).fridge_tracked for p in products]
    inv["Needs Reorder"] = inv["Stock Left"] < inv["Reorder Threshold"]
    inv["Fridge Stock Low"] = inv["Fridge Tracked"] & (inv["Stock Inside Fridge"] < inv["Fridge Threshold"])
    inv["Sell-through %"] = (inv["Sold"] / inv["Total Bought"].where(inv["Total Bought"] > 0) * 100).fillna(0).round(1)
    inv["Unit Price"] = inv.index.map(cat.price_series())
    inv["Unit Margin"] = inv.index.map(cat.margin_series())
    return inv


def compute_sold_trend(df_fridge: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """Daily net units sold per product (to_vendor − from_vendor), settled days only."""
    products = cat.product_names
    if df_fridge.empty:
        return pd.DataFrame(columns=[S.DATE] + products + ["Total Sold"])
    df = _with_dates(_numeric(df_fridge, products))
    settled = settled_dates(df)
    tv = df[(df[S.MODE] == S.MODE_TO_VENDOR) & df[S.DATE].isin(settled)].groupby(S.DATE)[products].sum()
    fv = df[(df[S.MODE] == S.MODE_FROM_VENDOR) & df[S.DATE].isin(settled)].groupby(S.DATE)[products].sum()
    sold = tv.subtract(fv, fill_value=0).reset_index()
    sold["Total Sold"] = sold[products].sum(axis=1)
    return sold.sort_values(S.DATE).reset_index(drop=True)


def category_breakdown(sold: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """
    Add per-category Units / Revenue columns plus totals & gross profit to a
    sold-trend frame (daily or monthly). Column names: 'Units <label>', 'Rev <label>'.
    """
    out = sold.copy()
    units_cols, rev_cols = [], []
    gross = pd.Series(0.0, index=out.index)
    for c in cat.categories_sorted():
        prods = [p for p in cat.products_in(c.key) if p in out.columns]
        units = out[prods].sum(axis=1) if prods else pd.Series(0.0, index=out.index)
        rev = sum((out[p] * cat.price(p) for p in prods), pd.Series(0.0, index=out.index)) if prods else pd.Series(0.0, index=out.index)
        gross = gross + sum((out[p] * cat.margin(p) for p in prods), pd.Series(0.0, index=out.index))
        out[f"Units {c.label}"] = units
        out[f"Rev {c.label}"] = rev
        units_cols.append(f"Units {c.label}")
        rev_cols.append(f"Rev {c.label}")
    out["Units Total"] = out[units_cols].sum(axis=1) if units_cols else 0
    out["Rev Total"] = out[rev_cols].sum(axis=1) if rev_cols else 0
    out["Gross Profit"] = gross
    return out


def expected_revenue_by_category(inv: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """Lifetime expected revenue per category from units Sold × unit price."""
    rows = []
    for c in cat.categories_sorted():
        prods = [p for p in cat.products_in(c.key) if p in inv.index]
        units = float(inv.loc[prods, "Sold"].sum()) if prods else 0.0
        revenue = float(sum(inv.loc[p, "Sold"] * cat.price(p) for p in prods)) if prods else 0.0
        gross = float(sum(inv.loc[p, "Sold"] * cat.margin(p) for p in prods)) if prods else 0.0
        rows.append({"Category": c.label, "Units Sold": units, "Expected Revenue": revenue,
                     "Gross Profit": gross, "Unit Price": c.sell_price, "Color": c.color})
    return pd.DataFrame(rows)


def sort_for_chart(inv: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """Category rank first, then lowest % unsold at top (matches original behaviour)."""
    df = inv.copy()
    df["_grp"] = df.index.map(cat.category_rank)
    bought = df["Total Bought"]
    df["_pct_left"] = ((bought - df["Sold"]) / bought.where(bought > 0)).fillna(0)
    # Plotly horizontal bars draw the last row at the top → sort descending.
    return df.sort_values(["_grp", "_pct_left"], ascending=[False, False]).drop(columns=["_grp", "_pct_left"])


def sort_for_grid(inv: pd.DataFrame, cat: Catalog) -> pd.DataFrame:
    """Category rank first, then Stock Inside Fridge ascending (lowest fridge stock first)."""
    df = inv.copy()
    df["_grp"] = df.index.map(cat.category_rank)
    return df.sort_values(["_grp", "Stock Inside Fridge"], ascending=[True, True]).drop(columns="_grp")
