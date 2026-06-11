"""
IcyPops — Inventory & Business Dashboard
Streamlit app connecting to Google Sheets via Service Account.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

from gsheets import (
    load_sheet, append_row, ensure_headers,
    PRODUCTS, FRIDGE_MODES, SHEET_NAMES
)
from metrics import (
    compute_inventory, compute_daily_revenue_expense,
    compute_sold_trend, compute_expense_breakdown,
    compute_top_products, load_thresholds,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IcyPops Dashboard",
    page_icon="🍦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  :root {
    --ice-teal:  #00b4d8; --ice-green: #06d6a0; --ice-yellow: #ffd166;
    --ice-dark:  #0d1b2a; --ice-card:  #1a2f45; --ice-text:   #e0f4ff;
    --ice-muted: #7faacc; --red-alert: #ff4d6d; --amber:      #fca311;
  }
  .stApp { background-color: var(--ice-dark); color: var(--ice-text); }

  .metric-card {
    background: var(--ice-card); border-radius: 12px;
    padding: 18px 20px; border-left: 4px solid var(--ice-teal); margin-bottom: 8px;
  }
  .metric-card.alert { border-left-color: var(--red-alert); }
  .metric-card.warn  { border-left-color: var(--amber); }
  .metric-card.good  { border-left-color: var(--ice-green); }
  .metric-value { font-size: 2rem; font-weight: 700; color: var(--ice-teal); }
  .metric-label { font-size: 0.85rem; color: var(--ice-muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .metric-sub   { font-size: 0.8rem; color: var(--ice-muted); margin-top: 4px; }

  .section-header {
    font-size: 1.1rem; font-weight: 600; color: var(--ice-teal);
    border-bottom: 1px solid #1e3a52; padding-bottom: 6px; margin: 20px 0 12px 0;
  }
  .stTabs [data-baseweb="tab-list"] { gap: 8px; }
  .stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0; padding: 8px 24px;
    background: var(--ice-card); color: var(--ice-muted); font-weight: 600;
  }
  .stTabs [aria-selected="true"] { background: var(--ice-teal) !important; color: #fff !important; }
  .stNumberInput input, .stTextInput input, .stSelectbox > div { background: var(--ice-card) !important; }
  .stDataFrame { border-radius: 10px; overflow: hidden; }
  #MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 9])
with col_logo:
    st.markdown("<div style='font-size:3rem;padding-top:8px'>🍦</div>", unsafe_allow_html=True)
with col_title:
    st.markdown("<h1 style='margin:0;color:#00b4d8;font-size:2rem'>IcyPops</h1>", unsafe_allow_html=True)
    st.markdown("<p style='margin:0;color:#7faacc;font-size:0.85rem'>Inventory & Business Dashboard</p>", unsafe_allow_html=True)

st.markdown("---")

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
    plot_bgcolor="#1a2f45", paper_bgcolor="#1a2f45",
    font_color="#e0f4ff", margin=dict(l=10, r=10, t=20, b=10),
    legend=dict(bgcolor="#1a2f45"),
)

def section(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)

# ── Product category helpers ──────────────────────────────────────────────────
PRODS_40 = [p for p in PRODUCTS if "40 ml" in p]
PRODS_80 = [p for p in PRODUCTS if "80 ml" in p]

MARGIN_40 = 8
MARGIN_80 = 15
MARGIN_FP = 154

tab_dash, tab_entry = st.tabs(["📊  Dashboard", "✏️  Data Entry"])


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

    inv  = compute_inventory(df_bought_safe, df_fridge_safe, PRODUCTS)
    pnl  = compute_daily_revenue_expense(df_revenue, df_expense)

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
    section("💰 Revenue")
    k1, k2, k3 = st.columns(3)
    kpi(k1, "Total Actual Revenue",   f"₹{total_revenue:,.0f}",   "Actual collected",               "good")
    kpi(k2, "Total Expected Revenue", f"₹{expected_revenue:,.0f}", f"{int(total_sold)} units sold",  "")
    kpi(k3, "Revenue Gap",            f"₹{revenue_gap:,.0f}",     "Actual − Expected",               "good" if revenue_gap >= 0 else "alert")

    k4, k5, k6 = st.columns(3)
    kpi(k4, "Expected — 40ml", f"₹{expected_rev_40:,.0f}", f"@ ₹15/unit · {int(sold_40)} units", "")
    kpi(k5, "Expected — 80ml", f"₹{expected_rev_80:,.0f}", f"@ ₹25/unit · {int(sold_80)} units", "")
    kpi(k6, "Expected — FP",   f"₹{expected_rev_fp:,.0f}", f"@ ₹220/unit · {int(sold_fp)} units","")

    # ── Expense & P&L KPIs ───────────────────────────────────────────────────
    section("🧾 Expense & P&L")
    k7, k8 = st.columns(2)
    kpi(k7, "Total Expense", f"₹{total_expense:,.0f}", "Lifetime",         "")
    kpi(k8, "Net P&L",       f"₹{net_pnl:,.0f}",      "Breakeven tracker", "good" if net_pnl >= 0 else "alert")

    k9, k10, k11, k12 = st.columns(4)
    kpi(k9,  "Gross Profit — 40ml", f"₹{gross_40:,.0f}",    f"@ ₹8/unit · {int(sold_40)} units",   "good" if gross_40    >= 0 else "alert")
    kpi(k10, "Gross Profit — 80ml", f"₹{gross_80:,.0f}",    f"@ ₹15/unit · {int(sold_80)} units",  "good" if gross_80    >= 0 else "alert")
    kpi(k11, "Gross Profit — FP",   f"₹{gross_fp:,.0f}",    f"@ ₹154/unit · {int(sold_fp)} units", "good" if gross_fp    >= 0 else "alert")
    kpi(k12, "Gross Profit — Total",f"₹{gross_total:,.0f}", f"Lifetime across all products",        "good" if gross_total >= 0 else "alert")

    # ── Alerts ───────────────────────────────────────────────────────────────
    section("🚨 Alerts")
    k9, _ = st.columns(2)
    alert_kind = "alert" if (reorder_count + fridge_low) > 0 else "good"
    kpi(k9, "Active Alerts", f"{reorder_count + fridge_low}",
        f"🔴 {reorder_count} reorder · 🟡 {fridge_low} fridge low", alert_kind)

    col_a1, col_a2 = st.columns(2)
    with col_a1:
        section("🔴 Reorder Alerts — Stock Left Below Threshold")
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
        section("🟡 Fridge Stock Alerts — In-Fridge Below Threshold")
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

    # ── Top Products ─────────────────────────────────────────────────────────
    section("🏆 Products — Units Bought vs Sold")
    display_inv_chart = inv[["Total Bought", "Sold"]].reset_index()
    display_inv_chart.columns = ["Product", "Total Bought", "Units Sold"]
    display_inv_chart = display_inv_chart.sort_values("Units Sold", ascending=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        y=display_inv_chart["Product"], x=display_inv_chart["Total Bought"],
        name="Total Bought", orientation="h", marker_color="#ffd166",
        hovertemplate="<b>%{y}</b><br>Bought: %{x}<extra></extra>",
    ))
    fig2.add_trace(go.Bar(
        y=display_inv_chart["Product"], x=display_inv_chart["Units Sold"],
        name="Units Sold", orientation="h", marker_color="#00b4d8",
        hovertemplate="<b>%{y}</b><br>Sold: %{x}<extra></extra>",
    ))
    fig2.update_layout(
        **CHART_LAYOUT, barmode="group", height=600,
        xaxis=dict(gridcolor="#1e3a52", title="Units"),
        yaxis=dict(tickfont=dict(size=11)),
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Daily Dispatch Chart ──────────────────────────────────────────────────
    section("📦 Daily Expected Revenue by Category (Settled Days Only)")
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
            ("40ml",        "Rev 40ml",  "Units 40ml",  "#00b4d8"),
            ("80ml",        "Rev 80ml",  "Units 80ml",  "#06d6a0"),
            ("Family Pack", "Rev FP",    "Units FP",    "#ffd166"),
            ("Total",       "Rev Total", "Units Total", "#f72585"),
        ]:
            fig5.add_trace(go.Bar(
                x=sold_trend["Date"], y=sold_trend[rev_col],
                name=label, marker_color=color,
                customdata=sold_trend[units_col],
                hovertemplate=f"<b>{label}</b><br>Revenue: ₹%{{y:,.0f}}<br>Units: %{{customdata}}<extra></extra>",
            ))

        fig5.add_trace(go.Bar(
            x=sold_trend["Date"], y=sold_trend["Gross Profit"],
            name="Gross Profit", marker_color="#a855f7",
            hovertemplate="<b>Gross Profit</b><br>₹%{y:,.0f}<extra></extra>",
        ))

        fig5.update_layout(
            **CHART_LAYOUT, barmode="group", height=320,
            xaxis=dict(showgrid=False, dtick="D1", tickformat="%d %b"),
            yaxis=dict(gridcolor="#1e3a52", title="₹"),
        )
        st.plotly_chart(fig5, use_container_width=True)

    # ── Full Inventory Grid ───────────────────────────────────────────────────
    section("📋 Full Inventory Snapshot")
    display_inv = inv[["Total Bought", "Stock Outside Fridge", "Stock Inside Fridge",
                        "Sold", "Stock Left", "Needs Reorder", "Fridge Stock Low"]].reset_index()

    def _color_flags(val):
        if val is True:  return "background-color:#ff4d6d33;color:#ff4d6d;font-weight:600"
        if val is False: return "color:#06d6a0"
        return ""

    st.dataframe(
        display_inv.style
            .map(_color_flags, subset=["Needs Reorder", "Fridge Stock Low"])
            .format({c: "{:.0f}" for c in ["Total Bought", "Stock Outside Fridge",
                                            "Stock Inside Fridge", "Sold", "Stock Left"]})
            .set_properties(**{"background-color": "#1a2f45", "color": "#e0f4ff"}),
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

    section("✏️ Add a New Record")

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