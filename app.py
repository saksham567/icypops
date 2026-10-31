"""
IcyPops — Inventory & Business Dashboard
Streamlit app connecting to Google Sheets via Service Account.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from gsheets import (
    load_sheet, append_row, ensure_headers, create_spreadsheet_snapshot,
    PRODUCTS, FRIDGE_MODES, SHEET_NAMES,
    EXPENSE_PAYMENT_COLS, EXPENSE_PAYMENT_LABELS, EXPENSE_OPERATIONAL_COL,
    REVENUE_COMMENT_COL, DIV_TOTAL, DIV_SAKSHAM, DIV_DHAIRYA,
)

from metrics import compute_inventory, compute_sold_trend
from styles import inject_app_styles, render_app_header

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IcyPops Dashboard",
    page_icon="🍦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling (st.html — st.markdown strips <style> tags on Streamlit Cloud) ───
inject_app_styles()
render_app_header()

# ── Connect & load ────────────────────────────────────────────────────────────
try:
    ensure_headers()
except Exception as e:
    st.error(f"⚠️ Could not connect to Google Sheets. Check your secrets. Error: {e}")
    st.stop()

@st.cache_data(ttl=30)
def load_all():
    return {s: load_sheet(s) for s in SHEET_NAMES}

data = load_all()

# ── Helper ────────────────────────────────────────────────────────────────────
def kpi(col, label, value, sub="", kind=""):
    col.markdown(
        f'<div class="metric-card {kind}">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-sub">{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

CHART_LAYOUT = dict(
    plot_bgcolor="rgba(17, 24, 39, 0)",
    paper_bgcolor="rgba(17, 24, 39, 0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=12),
    margin=dict(l=10, r=24, t=36, b=10),
    legend=dict(
        bgcolor="rgba(26, 34, 52, 0.9)",
        bordercolor="rgba(148, 163, 184, 0.15)",
        borderwidth=1,
        font=dict(color="#e2e8f0", size=11),
    ),
    hoverlabel=dict(
        bgcolor="#1a2234",
        bordercolor="rgba(56, 189, 248, 0.3)",
        font=dict(family="Inter, sans-serif", color="#f1f5f9", size=12),
    ),
)

def section(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)

# ── Product category helpers ──────────────────────────────────────────────────
PRODS_40 = [p for p in PRODUCTS if "40 ml" in p]
PRODS_80 = [p for p in PRODUCTS if "80 ml" in p]

def _product_group(product: str) -> int:
    if "80 ml" in product:
        return 0
    if "40 ml" in product:
        return 1
    if product == "FAMILY PACK":
        return 2
    return 3


def sort_chart_products(df: pd.DataFrame) -> pd.DataFrame:
    """80 ml (top) → 40 ml → Family Pack (bottom); within each group lowest % unsold at top."""
    sort_df = df.copy()
    sort_df["_group"] = sort_df.index.map(_product_group)
    bought = sort_df["Total Bought"]
    sort_df["_pct_left"] = (bought - sort_df["Sold"]) / bought.where(bought > 0)
    sort_df["_pct_left"] = sort_df["_pct_left"].fillna(0)
    # Plotly h-bar: last row = top; group descending puts 80 ml on top; pct descending puts lowest % on top
    return (
        sort_df.sort_values(["_group", "_pct_left"], ascending=[False, False])
        .drop(columns=["_group", "_pct_left"])
    )


def sort_inventory_rows(df: pd.DataFrame) -> pd.DataFrame:
    """80 ml → 40 ml → Family Pack; within each group by Stock Inside Fridge ascending."""
    stock_col = "Stock Inside Fridge" if "Stock Inside Fridge" in df.columns else None
    sort_df = df.copy()
    sort_df["_group"] = sort_df.index.map(_product_group)
    if stock_col:
        return (
            sort_df.sort_values(["_group", stock_col], ascending=[True, True])
            .drop(columns="_group")
        )
    return sort_df.sort_values("_group").drop(columns="_group")

def expense_by_payment(df_expense: pd.DataFrame) -> dict[str, float]:
    """Sum Expense for rows where each payment-method flag is set."""
    totals = {col: 0.0 for col in EXPENSE_PAYMENT_COLS}
    if df_expense.empty:
        return totals
    for col in EXPENSE_PAYMENT_COLS:
        flag = pd.to_numeric(df_expense.get(col, 0), errors="coerce").fillna(0)
        totals[col] = float(df_expense.loc[flag > 0, "Expense"].sum())
    return totals

PRICE_40, PRICE_80, PRICE_FP = 15, 25, 220


def monthly_expense_pivot(df_expense: pd.DataFrame):
    """Rows: Category > Type. Columns: months + Total."""
    if df_expense.empty:
        return None
    df = df_expense.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        return None
    is_op = pd.to_numeric(df[EXPENSE_OPERATIONAL_COL], errors="coerce").fillna(0) > 0
    df["Category"] = is_op.map({True: "Operational", False: "Non-Operational"})
    df["Type"] = df["Type"].astype(str).str.strip().replace("", "Uncategorised")
    df["MonthKey"] = df["Date"].dt.strftime("%Y-%m")
    pivot = df.pivot_table(index=["Category", "Type"], columns="MonthKey",
                           values="Expense", aggfunc="sum", fill_value=0)
    pivot.columns = [pd.to_datetime(m + "-01").strftime("%b %Y") for m in pivot.columns]
    pivot["Total"] = pivot.sum(axis=1)
    return pivot


def daily_actual_vs_expected(df_revenue: pd.DataFrame, df_fridge_safe: pd.DataFrame) -> pd.DataFrame:
    """Per-day Actual (Revenue sheet), Expected (settled sold units × price), and comments."""
    rev = df_revenue.copy()
    rev["Date"] = pd.to_datetime(rev["Date"], errors="coerce")
    rev = rev.dropna(subset=["Date"])
    actual = rev.groupby("Date")["Revenue"].sum().rename("Actual")
    comments = rev.groupby("Date")[REVENUE_COMMENT_COL].apply(
        lambda s: " | ".join(str(x).strip() for x in s if str(x).strip())
    ).rename("Comment")

    st_df = compute_sold_trend(df_fridge_safe, PRODUCTS)
    if st_df.empty:
        expected = pd.Series(dtype=float, name="Expected")
    else:
        fp = st_df["FAMILY PACK"] if "FAMILY PACK" in st_df.columns else 0
        expected = pd.Series(
            (st_df[PRODS_40].sum(axis=1) * PRICE_40
             + st_df[PRODS_80].sum(axis=1) * PRICE_80
             + fp * PRICE_FP).values,
            index=pd.to_datetime(st_df["Date"]), name="Expected",
        )

    out = pd.concat([actual, expected, comments], axis=1).reset_index()
    out = out.rename(columns={"index": "Date"})
    out["Comment"] = out["Comment"].fillna("")
    return out.sort_values("Date")

MARGIN_40 = 7
MARGIN_80 = 10
MARGIN_FP = 66

tab_dash, tab_entry = st.tabs(["Dashboard", "Data Entry"])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:

    df_bought  = data["Bought"]
    df_fridge  = data["Fridge"]
    df_revenue = data["Revenue"]
    df_expense = data["Expense"]

    if df_bought.empty and df_fridge.empty:
        st.info("No data yet. Use the **Data Entry** tab to start adding records.")

    # Safe fallbacks for empty sheets
    def _empty_bought():
        df = pd.DataFrame(columns=["Date"] + PRODUCTS)
        for p in PRODUCTS: df[p] = 0
        return df

    def _empty_fridge():
        df = pd.DataFrame(columns=["Date", "Mode"] + PRODUCTS)
        for p in PRODUCTS: df[p] = 0
        df["Mode"] = ""
        return df

    df_bought_safe = df_bought if not df_bought.empty else _empty_bought()
    df_fridge_safe = df_fridge if not df_fridge.empty else _empty_fridge()

    inv = compute_inventory(df_bought_safe, df_fridge_safe, PRODUCTS)

    # ── Derived KPI values ────────────────────────────────────────────────────
    total_revenue    = df_revenue["Revenue"].sum() if not df_revenue.empty else 0
    total_expense    = df_expense["Expense"].sum() if not df_expense.empty else 0
    expense_split    = expense_by_payment(df_expense)
    operational_cost = 0.0
    if not df_expense.empty and EXPENSE_OPERATIONAL_COL in df_expense.columns:
        flag = pd.to_numeric(df_expense[EXPENSE_OPERATIONAL_COL], errors="coerce").fillna(0)
        operational_cost = float(df_expense.loc[flag > 0, "Expense"].sum())
    realized_profit = total_revenue - operational_cost
    df_dividend           = data["Dividend"]
    total_dividend        = df_dividend[DIV_TOTAL].sum()   if not df_dividend.empty else 0
    saksham_dividend      = df_dividend[DIV_SAKSHAM].sum() if not df_dividend.empty else 0
    dhairya_dividend      = df_dividend[DIV_DHAIRYA].sum() if not df_dividend.empty else 0
    profit_after_dividend = realized_profit - total_dividend
    net_pnl          = total_revenue - total_expense
    reorder_count    = int(inv["Needs Reorder"].sum())
    fridge_low       = int(inv["Fridge Stock Low"].sum())

    sold_40          = inv.loc[PRODS_40, "Sold"].sum()
    sold_80          = inv.loc[PRODS_80, "Sold"].sum()
    sold_fp          = inv.loc["FAMILY PACK", "Sold"] if "FAMILY PACK" in inv.index else 0
    total_sold       = sold_40 + sold_80 + sold_fp

    expected_rev_40  = sold_40 * 15
    expected_rev_80  = sold_80 * 25
    expected_rev_fp  = sold_fp * 220
    expected_revenue = expected_rev_40 + expected_rev_80 + expected_rev_fp
    revenue_gap      = total_revenue - expected_revenue

    # gross_40         = sold_40 * MARGIN_40
    # gross_80         = sold_80 * MARGIN_80
    # gross_fp         = sold_fp * MARGIN_FP
    # gross_total      = gross_40 + gross_80 + gross_fp

    # ── Revenue KPIs ─────────────────────────────────────────────────────────
    section("Revenue")
    k1, k2, k3 = st.columns(3)
    kpi(k1, "Total Actual Revenue",   f"₹{total_revenue:,.0f}",   "Actual collected",               "good")
    kpi(k2, "Total Expected Revenue", f"₹{expected_revenue:,.0f}", f"{int(total_sold)} units sold",  "neutral")
    kpi(k3, "Revenue Gap",            f"₹{revenue_gap:,.0f}",     "Actual − Expected",               "good" if revenue_gap >= 0 else "alert")

    k4, k5, k6 = st.columns(3)
    kpi(k4, "Expected — 40ml", f"₹{expected_rev_40:,.0f}", f"@ ₹15/unit · {int(sold_40)} units", "neutral")
    kpi(k5, "Expected — 80ml", f"₹{expected_rev_80:,.0f}", f"@ ₹25/unit · {int(sold_80)} units", "neutral")
    kpi(k6, "Expected — FP",   f"₹{expected_rev_fp:,.0f}", f"@ ₹220/unit · {int(sold_fp)} units", "neutral")

    # ── Expense & P&L KPIs ───────────────────────────────────────────────────
    section("Expense & P&L")
    k7, k8 = st.columns(2)
    kpi(k7, "Total Expense", f"₹{total_expense:,.0f}", "Lifetime",         "neutral")
    kpi(k8, "Net P&L",       f"₹{net_pnl:,.0f}",      "Breakeven tracker", "good" if net_pnl >= 0 else "alert")

    ep1, ep2, ep3 = st.columns(3)
    kpi(ep1, EXPENSE_PAYMENT_LABELS["PaidThroughIncomeBank"],
        f"₹{expense_split['PaidThroughIncomeBank']:,.0f}", "Lifetime", "neutral")
    kpi(ep2, EXPENSE_PAYMENT_LABELS["PaidThroughIncomeCash"],
        f"₹{expense_split['PaidThroughIncomeCash']:,.0f}", "Lifetime", "neutral")
    kpi(ep3, EXPENSE_PAYMENT_LABELS["PaidThroughOwnMoney"],
        f"₹{expense_split['PaidThroughOwnMoney']:,.0f}", "Lifetime", "neutral")

    op1, op2 = st.columns(2)
    kpi(op1, "Operation Cost",        f"₹{operational_cost:,.0f}",
        "Expenses flagged as Operational", "neutral")
    kpi(op2, "Total Realized Profit", f"₹{realized_profit:,.0f}",
        "Actual Revenue − Operation Cost", "good" if realized_profit >= 0 else "alert")

    # k9, k10, k11, k12 = st.columns(4)
    # kpi(k9,  "Gross Profit — 40ml", f"₹{gross_40:,.0f}",    f"@ ₹7/unit · {int(sold_40)} units",   "good" if gross_40    >= 0 else "alert")
    # kpi(k10, "Gross Profit — 80ml", f"₹{gross_80:,.0f}",    f"@ ₹10/unit · {int(sold_80)} units",  "good" if gross_80    >= 0 else "alert")
    # kpi(k11, "Gross Profit — FP",   f"₹{gross_fp:,.0f}",    f"@ ₹66/unit · {int(sold_fp)} units", "good" if gross_fp    >= 0 else "alert")
    # kpi(k12, "Gross Profit — Total",f"₹{gross_total:,.0f}", f"Lifetime across all products",        "good" if gross_total >= 0 else "alert")

        # ── Dividend ─────────────────────────────────────────────────────────────
    section("Dividend")
    d1, d2, d3, d4 = st.columns(4)
    kpi(d1, "Total Dividend",   f"₹{total_dividend:,.0f}",   "Lifetime", "neutral")
    kpi(d2, "Dhairya Dividend", f"₹{dhairya_dividend:,.0f}", "Lifetime", "neutral")
    kpi(d3, "Saksham Dividend", f"₹{saksham_dividend:,.0f}", "Lifetime", "neutral")
    kpi(d4, "Realized Profit After Dividend", f"₹{profit_after_dividend:,.0f}",
        "Realized Profit − Total Dividend", "good" if profit_after_dividend >= 0 else "alert")

    # ── Monthly Expense Breakdown ────────────────────────────────────────────
    section("Monthly Expense Breakdown")
    pivot = monthly_expense_pivot(df_expense)
    if pivot is None:
        st.info("No expense data yet.")
    else:
        cat_totals = pivot.groupby(level="Category").sum()
        cat_totals = cat_totals.reindex(
            [c for c in ["Operational", "Non-Operational"] if c in cat_totals.index]
        )
        cat_totals.loc["Total"] = cat_totals.sum()
        st.dataframe(cat_totals.style.format("{:,.0f}"), use_container_width=True)

        for cat in cat_totals.index[:-1]:
            detail = pivot.loc[cat].sort_values("Total", ascending=False)
            detail.loc["Total"] = detail.sum()
            with st.expander(f"{cat} — breakdown by Type", expanded=False):
                st.dataframe(detail.style.format("{:,.0f}"), use_container_width=True)

    # ── Actual vs Expected Revenue ───────────────────────────────────────────
    section("Actual vs Expected Revenue")
    avx = daily_actual_vs_expected(df_revenue, df_fridge_safe)
    if avx.empty:
        st.info("No revenue data yet.")
    else:
        n_days = st.number_input("Show last N days", min_value=1, max_value=3650,
                                 value=20, step=1, key="avx_days")
        end   = avx["Date"].max()
        view  = avx[avx["Date"] >= end - pd.Timedelta(days=int(n_days) - 1)].copy()
        view["Note"] = view["Comment"].apply(lambda c: f"💬 {c}" if c else "")
        short = view[view["Actual"].notna() & view["Expected"].notna()
                     & (view["Actual"] < view["Expected"])].copy()
        short["Shortfall"] = short["Expected"] - short["Actual"]

        fig_avx = go.Figure()
        fig_avx.add_trace(go.Scatter(
            x=view["Date"], y=view["Expected"], mode="lines+markers", name="Expected",
            line=dict(color="#38bdf8", width=2), connectgaps=True,
            hovertemplate="<b>Expected</b><br>%{x|%d %b}<br>₹%{y:,.0f}<extra></extra>",
        ))
        fig_avx.add_trace(go.Scatter(
            x=view["Date"], y=view["Actual"], mode="lines+markers", name="Actual",
            line=dict(color="#34d399", width=2), connectgaps=True,
            customdata=view["Note"],
            hovertemplate="<b>Actual</b><br>%{x|%d %b}<br>₹%{y:,.0f}<br>%{customdata}<extra></extra>",
        ))
        fig_avx.add_trace(go.Scatter(
            x=short["Date"], y=short["Actual"], mode="markers", name="Actual < Expected",
            marker=dict(color="#f87171", size=13, line=dict(color="#ffffff", width=1.5)),
            customdata=short[["Expected", "Shortfall", "Note"]].values,
            hovertemplate=("<b>Below expected</b><br>%{x|%d %b}<br>Actual: ₹%{y:,.0f}"
                           "<br>Expected: ₹%{customdata[0]:,.0f}"
                           "<br>Shortfall: ₹%{customdata[1]:,.0f}"
                           "<br>%{customdata[2]}<extra></extra>"),
        ))
        fig_avx.update_layout(
            **CHART_LAYOUT, height=360,
            xaxis=dict(showgrid=False, showline=False, tickformat="%d %b",
                       **({"dtick": "D1"} if n_days <= 31 else {})),
            yaxis=dict(showgrid=False, title="₹", zeroline=False, showline=False),
        )
        st.plotly_chart(fig_avx, use_container_width=True)
        st.caption(f"{len(short)} day(s) below expected in this window.")

    # ── Alerts ───────────────────────────────────────────────────────────────
    section("Alerts")
    k9, _ = st.columns(2)
    alert_kind = "alert" if (reorder_count + fridge_low) > 0 else "good"
    kpi(k9, "Active Alerts", f"{reorder_count + fridge_low}",
        f"🔴 {reorder_count} reorder · 🟡 {fridge_low} fridge low", alert_kind)

    col_a1, col_a2 = st.columns(2)
    with col_a1:
        section("Reorder Alerts — Stock Left Below Threshold")
        reorder_df = inv[inv["Needs Reorder"]][["Stock Left", "Reorder Threshold", "Total Bought", "Sold"]].copy()
        if reorder_df.empty:
            st.success("✅ All products have sufficient stock.")
        else:
            reorder_df = reorder_df.reset_index()
            reorder_df.columns = ["Product", "Stock Left", "Threshold", "Total Bought", "Sold"]
            reorder_df["Gap"] = reorder_df["Threshold"] - reorder_df["Stock Left"]
            st.dataframe(
                reorder_df.style
                    .background_gradient(subset=["Gap"], cmap="Reds")
                    .format({c: "{:.0f}" for c in ["Stock Left","Threshold","Gap"]}),
                use_container_width=True, hide_index=True,
            )

    with col_a2:
        section("Fridge Stock Alerts — In-Fridge Below Threshold")
        fridge_df = inv[inv["Fridge Stock Low"]][["Stock Inside Fridge", "Fridge Threshold"]].copy()
        if fridge_df.empty:
            st.success("✅ Fridge stock looks healthy.")
        else:
            fridge_df = fridge_df.reset_index()
            fridge_df.columns = ["Product", "In Fridge", "Threshold"]
            fridge_df["Gap"] = fridge_df["Threshold"] - fridge_df["In Fridge"]
            st.dataframe(
                fridge_df.style
                    .background_gradient(subset=["Gap"], cmap="YlOrRd")
                    .format({c: "{:.0f}" for c in ["In Fridge","Threshold","Gap"]}),
                use_container_width=True, hide_index=True,
            )

    # ── Products chart ───────────────────────────────────────────────────────
    section("Products — Units Bought vs Sold")
    chart_inv = sort_chart_products(inv[["Total Bought", "Sold"]])
    display_inv_chart = chart_inv.reset_index()
    display_inv_chart.columns = ["Product", "Total Bought", "Units Sold"]
    display_inv_chart["Difference"] = display_inv_chart["Total Bought"] - display_inv_chart["Units Sold"]

    hover_data = display_inv_chart[["Total Bought", "Units Sold", "Difference"]].values
    y_order = list(display_inv_chart["Product"])

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        y=display_inv_chart["Product"], x=display_inv_chart["Total Bought"],
        name="Total Bought", orientation="h", marker_color="#fbbf24",
        marker_line=dict(width=0),
        customdata=hover_data,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Bought: %{customdata[0]:,.0f}<br>"
            "Sold: %{customdata[1]:,.0f}<br>"
            "Difference: %{customdata[2]:,.0f}"
            "<extra></extra>"
        ),
    ))
    fig2.add_trace(go.Bar(
        y=display_inv_chart["Product"], x=display_inv_chart["Units Sold"],
        name="Units Sold", orientation="h", marker_color="#38bdf8",
        marker_line=dict(width=0),
        customdata=hover_data,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Bought: %{customdata[0]:,.0f}<br>"
            "Sold: %{customdata[1]:,.0f}<br>"
            "Difference: %{customdata[2]:,.0f}"
            "<extra></extra>"
        ),
    ))
    fig2.update_layout(
        **CHART_LAYOUT, barmode="group", height=640,
        xaxis=dict(showgrid=False, title="", zeroline=False, showline=False),
        yaxis=dict(
            tickfont=dict(size=11, color="#cbd5e1"),
            categoryorder="array", categoryarray=y_order,
            showgrid=False, zeroline=False, showline=False,
        ),
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Daily Dispatch Chart ──────────────────────────────────────────────────
    section("Daily Expected Revenue by Category (Settled Days Only)")
    sold_trend = compute_sold_trend(df_fridge_safe, PRODUCTS)

    if sold_trend.empty or sold_trend["Total Sold"].sum() == 0:
        st.info("No settled dispatch data yet. A day is counted only when both 'to vendor' and 'from vendor' entries exist.")
    else:
        # ── Toggle ────────────────────────────────────────────────────────
        view_mode = st.radio(
            "View", ["Daily", "Monthly"],
            horizontal=True, key="dispatch_view",
            label_visibility="collapsed",
        )

        if view_mode == "Daily":
            min_date     = sold_trend["Date"].min().date()
            max_date     = sold_trend["Date"].max().date()
            default_from = max(min_date, max_date - pd.Timedelta(days=14))

            col_from, col_to = st.columns(2)
            from_date = col_from.date_input(
                "From date", value=default_from,
                min_value=min_date, max_value=max_date,
                key="chart_from_date",
            )
            to_date = col_to.date_input(
                "To date", value=max_date,
                min_value=min_date, max_value=max_date,
                key="chart_to_date",
            )
            plot_df = sold_trend[
                (sold_trend["Date"].dt.date >= from_date) &
                (sold_trend["Date"].dt.date <= to_date)
            ].copy()
            x_col      = "Date"
            x_settings = dict(showgrid=False, dtick="D1", tickformat="%d %b", showline=False)

        else:  # Monthly
            monthly = sold_trend.copy()
            monthly["Month"] = monthly["Date"].dt.to_period("M")
            agg_cols = PRODS_40 + PRODS_80 + ["FAMILY PACK",
                        "Rev 40ml", "Rev 80ml", "Rev FP",
                        "Units 40ml", "Units 80ml", "Units FP",
                        "Rev Total", "Units Total", "Gross Profit"]

            # Compute derived columns before aggregating
            monthly["Rev 40ml"]     = monthly[PRODS_40].sum(axis=1) * 15
            monthly["Rev 80ml"]     = monthly[PRODS_80].sum(axis=1) * 25
            monthly["Rev FP"]       = monthly.get("FAMILY PACK", 0) * 220
            monthly["Units 40ml"]   = monthly[PRODS_40].sum(axis=1)
            monthly["Units 80ml"]   = monthly[PRODS_80].sum(axis=1)
            monthly["Units FP"]     = monthly.get("FAMILY PACK", 0)
            monthly["Rev Total"]    = monthly["Rev 40ml"] + monthly["Rev 80ml"] + monthly["Rev FP"]
            monthly["Units Total"]  = monthly["Units 40ml"] + monthly["Units 80ml"] + monthly["Units FP"]
            monthly["Gross Profit"] = (
                monthly["Units 40ml"] * MARGIN_40 +
                monthly["Units 80ml"] * MARGIN_80 +
                monthly.get("FAMILY PACK", 0) * MARGIN_FP
            )

            num_cols = [c for c in agg_cols if c in monthly.columns]
            plot_df  = monthly.groupby("Month")[num_cols].sum().reset_index()
            plot_df["Month"] = plot_df["Month"].dt.strftime("%b %Y")
            x_col      = "Month"
            x_settings = dict(showgrid=False, showline=False)

        # Ensure derived cols exist for daily path (already computed for monthly)
        if view_mode == "Daily":
            plot_df["Rev 40ml"]     = plot_df[PRODS_40].sum(axis=1) * 15
            plot_df["Rev 80ml"]     = plot_df[PRODS_80].sum(axis=1) * 25
            plot_df["Rev FP"]       = plot_df.get("FAMILY PACK", 0) * 220
            plot_df["Units 40ml"]   = plot_df[PRODS_40].sum(axis=1)
            plot_df["Units 80ml"]   = plot_df[PRODS_80].sum(axis=1)
            plot_df["Units FP"]     = plot_df.get("FAMILY PACK", 0)
            plot_df["Rev Total"]    = plot_df["Rev 40ml"] + plot_df["Rev 80ml"] + plot_df["Rev FP"]
            plot_df["Units Total"]  = plot_df["Units 40ml"] + plot_df["Units 80ml"] + plot_df["Units FP"]
            plot_df["Gross Profit"] = (
                plot_df["Units 40ml"] * MARGIN_40 +
                plot_df["Units 80ml"] * MARGIN_80 +
                plot_df.get("FAMILY PACK", 0) * MARGIN_FP
            )

        fig5 = go.Figure()
        for label, rev_col, units_col, color in [
            ("40ml",        "Rev 40ml",  "Units 40ml",  "#38bdf8"),
            ("80ml",        "Rev 80ml",  "Units 80ml",  "#34d399"),
            ("Family Pack", "Rev FP",    "Units FP",    "#fbbf24"),
            ("Total",       "Rev Total", "Units Total", "#a78bfa"),
        ]:
            fig5.add_trace(go.Bar(
                x=plot_df[x_col], y=plot_df[rev_col],
                name=label, marker_color=color,
                customdata=plot_df[units_col],
                hovertemplate=f"<b>{label}</b><br>Revenue: ₹%{{y:,.0f}}<br>Units: %{{customdata}}<extra></extra>",
            ))

        fig5.add_trace(go.Bar(
            x=plot_df[x_col], y=plot_df["Gross Profit"],
            name="Gross Profit", marker_color="#818cf8",
            hovertemplate="<b>Gross Profit</b><br>₹%{y:,.0f}<extra></extra>",
        ))

        fig5.update_layout(
            **CHART_LAYOUT, barmode="group", height=340,
            xaxis=x_settings,
            yaxis=dict(showgrid=False, title="₹", zeroline=False, showline=False),
        )
        st.plotly_chart(fig5, use_container_width=True)

    # ── Full Inventory Grid ───────────────────────────────────────────────────
    section("Full Inventory Snapshot")
    display_inv = sort_inventory_rows(
        inv[["Total Bought", "Stock Inside Fridge", "Sold", "Stock Left", "Needs Reorder", "Fridge Stock Low"]]
    ).reset_index()

    def _color_flags(val):
        if val is True:  return "background-color:rgba(248,113,113,0.15);color:#f87171;font-weight:600"
        if val is False: return "color:#34d399"
        return ""

    st.dataframe(
        display_inv.style
            .map(_color_flags, subset=["Needs Reorder", "Fridge Stock Low"])
            .format({c: "{:.0f}" for c in ["Total Bought", "Stock Inside Fridge", "Sold", "Stock Left"]})
            .set_properties(**{"background-color": "#1a2234", "color": "#e2e8f0"}),
        use_container_width=True, hide_index=True, height=420,
    )

    st.markdown("")
    col_refresh, col_snapshot = st.columns(2)
    with col_refresh:
        if st.button("Refresh Data", type="secondary", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with col_snapshot:
        if st.button("Save Google Sheets Snapshot", type="primary", use_container_width=True):
            try:
                with st.spinner("Creating snapshot in Google Drive…"):
                    snapshot = create_spreadsheet_snapshot()
                st.success(f"Snapshot saved as **{snapshot['name']}**")
                st.markdown(f"[Open snapshot in Google Sheets]({snapshot['url']})")
            except Exception as e:
                st.error(f"Could not create snapshot. Check Drive permissions. Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — DATA ENTRY
# ══════════════════════════════════════════════════════════════════════════════
with tab_entry:

    section("Add a New Record")

    sheet_choice = st.selectbox(
        "Select Sheet",
        SHEET_NAMES,
        format_func=lambda x: {
            "Expense": "💰 Expense — Daily costs",
            "Bought":  "🛒 Bought — Stock purchased from manufacturer",
            "Fridge":  "🧊 Fridge — Stock movement log",
            "Revenue": "📈 Revenue — Daily earnings",
            "Dividend": "🤝 Dividend — Partner payouts",
        }[x],
    )

    st.markdown("")

    with st.form(key=f"entry_form_{sheet_choice}", clear_on_submit=True):
        entry_date = st.date_input("Date", value=date.today())

        # ── EXPENSE ──────────────────────────────────────────────────────────
        if sheet_choice == "Expense":
            c1, c2 = st.columns(2)
            exp_type   = c1.text_input("Type", placeholder="e.g. Product, Repair, Essentials")
            exp_desc   = c2.text_input("Description", placeholder="Brief note")
            exp_amount = st.number_input("Expense Amount (₹)", min_value=0.0, step=1.0)
            pay_method = st.selectbox(
                "Payment Method",
                EXPENSE_PAYMENT_COLS,
                format_func=lambda c: EXPENSE_PAYMENT_LABELS[c],
            )

            is_operational = st.checkbox("Flag as Operational Cost")

            if st.form_submit_button("➕ Add Expense", type="primary"):
                if not exp_type.strip():
                    st.error("Type is required.")
                elif exp_amount <= 0:
                    st.error("Expense must be greater than 0.")
                else:
                    flags = {c: (1 if c == pay_method else 0) for c in EXPENSE_PAYMENT_COLS}
                    append_row("Expense", [
                        str(entry_date), exp_type.strip(), exp_desc.strip(), exp_amount,
                        flags["PaidThroughIncomeBank"],
                        flags["PaidThroughIncomeCash"],
                        flags["PaidThroughOwnMoney"],
                        1 if is_operational else 0,
                    ])

                    st.success(f"✅ Expense of ₹{exp_amount} added for {entry_date}.")

        # ── BOUGHT ───────────────────────────────────────────────────────────
        elif sheet_choice == "Bought":
            st.markdown("Enter quantities purchased from manufacturer. Leave 0 for items not bought.")
            qty = {}
            for label, prods in [("40 ml products", PRODS_40), ("80 ml products", PRODS_80), ("Family Pack", ["FAMILY PACK"])]:
                st.markdown(f"**{label}**")
                cols = st.columns(3)
                for i, p in enumerate(prods):
                    qty[p] = cols[i % 3].number_input(p, min_value=0, step=1, key=f"b_{p}")

            if st.form_submit_button("➕ Add Purchase Record", type="primary"):
                append_row("Bought", [str(entry_date)] + [qty[p] for p in PRODUCTS])
                st.success(f"✅ Purchase record added for {entry_date}. Total units: {sum(qty.values())}")

        # ── FRIDGE ───────────────────────────────────────────────────────────
        elif sheet_choice == "Fridge":
            mode = st.selectbox("Mode", FRIDGE_MODES, format_func=lambda x: {
                "from stock":  "📦 From Stock — Moving into fridge from your own storage",
                "to vendor":   "🚚 To Vendor   — Dispatching to reseller/vendor",
                "from vendor": "↩️  From Vendor — Returns from vendor back to you",
            }[x])
            st.markdown(f"**Enter quantities for mode: `{mode}`**")

            fq = {}
            fridge_prods = [("40 ml products", PRODS_40), ("80 ml products", PRODS_80)]
            for label, prods in fridge_prods:
                st.markdown(f"**{label}**")
                cols = st.columns(3)
                for i, p in enumerate(prods):
                    fq[p] = cols[i % 3].number_input(p, min_value=0, step=1, key=f"f_{p}")

            # Family Pack shown but clarified it doesn't go in fridge
            st.markdown("**Family Pack** *(stock movement only — no fridge tracking)*")
            fq["FAMILY PACK"] = st.number_input("FAMILY PACK", min_value=0, step=1, key="f_fp")

            if st.form_submit_button("➕ Add Fridge Entry", type="primary"):
                append_row("Fridge", [str(entry_date), mode] + [fq[p] for p in PRODUCTS])
                st.success(f"✅ Fridge entry ({mode}) added for {entry_date}. Total units: {sum(fq.values())}")

        # ── REVENUE ──────────────────────────────────────────────────────────
        elif sheet_choice == "Revenue":
            rev_amount  = st.number_input("Revenue Amount (₹)", min_value=0.0, step=1.0)
            rev_comment = st.text_input("Comments (optional)")

            if st.form_submit_button("➕ Add Revenue", type="primary"):
                if rev_amount <= 0:
                    st.error("Revenue must be greater than 0.")
                else:
                    append_row("Revenue", [str(entry_date), rev_amount, rev_comment.strip()])
                    st.success(f"✅ Revenue of ₹{rev_amount} added for {entry_date}.")

        # ── DIVIDEND ─────────────────────────────────────────────────────────
        elif sheet_choice == "Dividend":
            dc1, dc2 = st.columns(2)
            div_s = dc1.number_input("Saksham Dividend (₹)", min_value=0.0, step=1.0)
            div_d = dc2.number_input("Dhairya Dividend (₹)", min_value=0.0, step=1.0)

            if st.form_submit_button("➕ Add Dividend", type="primary"):
                if div_s + div_d <= 0:
                    st.error("Enter a dividend amount.")
                else:
                    append_row("Dividend", [str(entry_date), div_s + div_d, div_s, div_d])
                    st.success(f"✅ Dividend of ₹{div_s + div_d:,.0f} added for {entry_date}.")

    # ── Recent entries preview ────────────────────────────────────────────────
    st.markdown("")
    section(f"🔍 Recent Entries — {sheet_choice}")
    preview_df = data[sheet_choice]
    if preview_df.empty:
        st.info("No records yet.")
    else:
        if sheet_choice in ("Bought", "Fridge"):
            active_products = [c for c in PRODUCTS if c in preview_df.columns and preview_df[c].sum() > 0]
            meta = ["Date"] + (["Mode"] if sheet_choice == "Fridge" else [])
            show_cols = meta + active_products
        else:
            show_cols = preview_df.columns.tolist()
                sort_col = "DATE" if "DATE" in preview_df.columns else "Date"
        st.dataframe(
            preview_df[show_cols].tail(10).sort_values(sort_col, ascending=False),
            use_container_width=True, hide_index=True,
        )