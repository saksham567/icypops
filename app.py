"""
IcyPops — Inventory & Business Dashboard
Streamlit app connecting to Google Sheets via Service Account.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from gsheets import (
    load_sheet, append_row, ensure_headers,
    PRODUCTS, FRIDGE_MODES, SHEET_NAMES
)
from metrics import compute_inventory, compute_sold_trend

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IcyPops Dashboard",
    page_icon="🍦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-base:     #080c14;
    --bg-surface:  #111827;
    --bg-elevated: #1a2234;
    --border:      rgba(148, 163, 184, 0.12);
    --border-strong: rgba(148, 163, 184, 0.22);
    --text-primary:   #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted:     #64748b;
    --accent:      #38bdf8;
    --accent-soft: rgba(56, 189, 248, 0.12);
    --success:     #34d399;
    --warning:     #fbbf24;
    --danger:      #f87171;
    --radius:      14px;
    --shadow:      0 4px 24px rgba(0, 0, 0, 0.35);
  }

  html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  }

  .stApp {
    background: linear-gradient(165deg, #080c14 0%, #0f172a 45%, #0a1628 100%);
    color: var(--text-primary);
  }

  .block-container { padding-top: 1.5rem; max-width: 1400px; }

  .app-header {
    background: linear-gradient(135deg, var(--bg-elevated) 0%, rgba(26, 34, 52, 0.6) 100%);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem 1.75rem;
    margin-bottom: 0.5rem;
    box-shadow: var(--shadow);
    display: flex;
    align-items: center;
    gap: 1.25rem;
  }
  .app-logo {
    width: 52px; height: 52px;
    background: linear-gradient(135deg, #38bdf8 0%, #818cf8 100%);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.6rem;
    box-shadow: 0 4px 16px rgba(56, 189, 248, 0.25);
  }
  .app-title {
    margin: 0; font-size: 1.65rem; font-weight: 700; letter-spacing: -0.02em;
    background: linear-gradient(90deg, #f1f5f9 0%, #94a3b8 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }
  .app-subtitle { margin: 0.15rem 0 0 0; font-size: 0.875rem; color: var(--text-secondary); }
  .app-badge {
    margin-left: auto; padding: 0.35rem 0.85rem;
    background: var(--accent-soft); border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 999px; font-size: 0.72rem; font-weight: 600;
    color: var(--accent); letter-spacing: 0.06em; text-transform: uppercase;
  }

  .metric-card {
    background: var(--bg-elevated); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 1.15rem 1.25rem; margin-bottom: 0.65rem;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2); position: relative; overflow: hidden;
  }
  .metric-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: var(--accent); opacity: 0.85;
  }
  .metric-card.alert::before { background: linear-gradient(90deg, var(--danger), #fb7185); }
  .metric-card.warn::before  { background: linear-gradient(90deg, var(--warning), #f59e0b); }
  .metric-card.good::before  { background: linear-gradient(90deg, var(--success), #6ee7b7); }
  .metric-card.neutral::before { background: linear-gradient(90deg, #64748b, #94a3b8); opacity: 0.5; }

  .metric-label {
    font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase;
    letter-spacing: 0.08em; font-weight: 600; margin-bottom: 0.35rem;
  }
  .metric-value {
    font-size: 1.75rem; font-weight: 700; color: var(--text-primary);
    letter-spacing: -0.02em; line-height: 1.2;
  }
  .metric-card.good .metric-value  { color: var(--success); }
  .metric-card.alert .metric-value { color: var(--danger); }
  .metric-card.warn .metric-value  { color: var(--warning); }
  .metric-sub { font-size: 0.78rem; color: var(--text-secondary); margin-top: 0.4rem; }

  .section-header {
    font-size: 0.95rem; font-weight: 600; color: var(--text-primary);
    letter-spacing: -0.01em; padding: 0.5rem 0 0.65rem 0;
    margin: 1.75rem 0 0.85rem 0; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 0.5rem;
  }
  .section-header::before {
    content: ''; width: 4px; height: 1rem;
    background: linear-gradient(180deg, var(--accent), #818cf8); border-radius: 2px;
  }

  .stTabs [data-baseweb="tab-list"] {
    gap: 6px; background: var(--bg-surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 5px;
  }
  .stTabs [data-baseweb="tab"] {
    border-radius: 8px; padding: 0.55rem 1.35rem; background: transparent;
    color: var(--text-muted); font-weight: 600; font-size: 0.875rem; border: none;
  }
  .stTabs [aria-selected="true"] {
    background: var(--bg-elevated) !important; color: var(--accent) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
  }

  .stNumberInput input, .stTextInput input, .stSelectbox > div,
  .stDateInput input, .stTextArea textarea {
    background: var(--bg-elevated) !important; border-color: var(--border) !important;
    color: var(--text-primary) !important; border-radius: 10px !important;
  }
  .stButton > button { border-radius: 10px; font-weight: 600; }
  .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #38bdf8 0%, #6366f1 100%);
    border: none; box-shadow: 0 4px 14px rgba(56, 189, 248, 0.3);
  }
  .stButton > button[kind="secondary"] {
    background: var(--bg-elevated); border: 1px solid var(--border-strong); color: var(--text-secondary);
  }

  .stDataFrame { border-radius: var(--radius); overflow: hidden; border: 1px solid var(--border); }
  .stAlert { border-radius: 12px; border: 1px solid var(--border); }
  hr { border-color: var(--border) !important; margin: 1rem 0 !important; }
  #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <div class="app-logo">🍦</div>
  <div>
    <h1 class="app-title">IcyPops</h1>
    <p class="app-subtitle">Inventory & Business Intelligence</p>
  </div>
  <span class="app-badge">Live Dashboard</span>
</div>
""", unsafe_allow_html=True)

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
    """80 ml (top) → 40 ml → Family Pack (bottom); within each group smallest (Bought − Sold) diff at top."""
    sort_df = df.copy()
    sort_df["_group"] = sort_df.index.map(_product_group)
    sort_df["_diff"] = sort_df["Total Bought"] - sort_df["Sold"]
    # Plotly h-bar: last row = top; group descending puts 80 ml on top; diff descending puts smallest diff on top
    return (
        sort_df.sort_values(["_group", "_diff"], ascending=[False, False])
        .drop(columns=["_group", "_diff"])
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

    gross_40         = sold_40 * MARGIN_40
    gross_80         = sold_80 * MARGIN_80
    gross_fp         = sold_fp * MARGIN_FP
    gross_total      = gross_40 + gross_80 + gross_fp

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

    k9, k10, k11, k12 = st.columns(4)
    kpi(k9,  "Gross Profit — 40ml", f"₹{gross_40:,.0f}",    f"@ ₹7/unit · {int(sold_40)} units",   "good" if gross_40    >= 0 else "alert")
    kpi(k10, "Gross Profit — 80ml", f"₹{gross_80:,.0f}",    f"@ ₹10/unit · {int(sold_80)} units",  "good" if gross_80    >= 0 else "alert")
    kpi(k11, "Gross Profit — FP",   f"₹{gross_fp:,.0f}",    f"@ ₹66/unit · {int(sold_fp)} units", "good" if gross_fp    >= 0 else "alert")
    kpi(k12, "Gross Profit — Total",f"₹{gross_total:,.0f}", f"Lifetime across all products",        "good" if gross_total >= 0 else "alert")

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
        sold_trend["Rev 40ml"]     = sold_trend[PRODS_40].sum(axis=1) * 15
        sold_trend["Rev 80ml"]     = sold_trend[PRODS_80].sum(axis=1) * 25
        sold_trend["Rev FP"]       = sold_trend.get("FAMILY PACK", 0) * 220
        sold_trend["Units 40ml"]   = sold_trend[PRODS_40].sum(axis=1)
        sold_trend["Units 80ml"]   = sold_trend[PRODS_80].sum(axis=1)
        sold_trend["Units FP"]     = sold_trend.get("FAMILY PACK", 0)
        sold_trend["Rev Total"]    = sold_trend["Rev 40ml"] + sold_trend["Rev 80ml"] + sold_trend["Rev FP"]
        sold_trend["Units Total"]  = sold_trend["Units 40ml"] + sold_trend["Units 80ml"] + sold_trend["Units FP"]
        sold_trend["Gross Profit"] = (
            sold_trend["Units 40ml"] * MARGIN_40 +
            sold_trend["Units 80ml"] * MARGIN_80 +
            sold_trend.get("FAMILY PACK", 0) * MARGIN_FP
        )

        fig5 = go.Figure()
        for label, rev_col, units_col, color in [
            ("40ml",        "Rev 40ml",  "Units 40ml",  "#38bdf8"),
            ("80ml",        "Rev 80ml",  "Units 80ml",  "#34d399"),
            ("Family Pack", "Rev FP",    "Units FP",    "#fbbf24"),
            ("Total",       "Rev Total", "Units Total", "#a78bfa"),
        ]:
            fig5.add_trace(go.Bar(
                x=sold_trend["Date"], y=sold_trend[rev_col],
                name=label, marker_color=color,
                customdata=sold_trend[units_col],
                hovertemplate=f"<b>{label}</b><br>Revenue: ₹%{{y:,.0f}}<br>Units: %{{customdata}}<extra></extra>",
            ))

        fig5.add_trace(go.Bar(
            x=sold_trend["Date"], y=sold_trend["Gross Profit"],
            name="Gross Profit", marker_color="#818cf8",
            hovertemplate="<b>Gross Profit</b><br>₹%{y:,.0f}<extra></extra>",
        ))

        fig5.update_layout(
            **CHART_LAYOUT, barmode="group", height=340,
            xaxis=dict(showgrid=False, dtick="D1", tickformat="%d %b", showline=False),
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
    if st.button("🔄 Refresh Data", type="secondary"):
        st.cache_data.clear()
        st.rerun()


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

            if st.form_submit_button("➕ Add Expense", type="primary"):
                if not exp_type.strip():
                    st.error("Type is required.")
                elif exp_amount <= 0:
                    st.error("Expense must be greater than 0.")
                else:
                    append_row("Expense", [str(entry_date), exp_type.strip(), exp_desc.strip(), exp_amount])
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
            rev_amount = st.number_input("Revenue Amount (₹)", min_value=0.0, step=1.0)

            if st.form_submit_button("➕ Add Revenue", type="primary"):
                if rev_amount <= 0:
                    st.error("Revenue must be greater than 0.")
                else:
                    append_row("Revenue", [str(entry_date), rev_amount])
                    st.success(f"✅ Revenue of ₹{rev_amount} added for {entry_date}.")

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
        st.dataframe(
            preview_df[show_cols].tail(10).sort_values("Date", ascending=False),
            use_container_width=True, hide_index=True,
        )