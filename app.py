"""
IcyPops — Inventory & Business Dashboard
Streamlit app connecting to Google Sheets via Service Account.
"""

import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime

from gsheets import (
    load_sheet, append_row, ensure_headers,
    PRODUCTS, FRIDGE_MODES, SHEET_NAMES,
)
from metrics import (
    compute_inventory, compute_daily_revenue_expense,
    compute_sold_trend, compute_expense_breakdown,
    compute_top_products, load_thresholds,
)

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IcyPops Dashboard",
    page_icon="🍦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Styling ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Palette */
  :root {
    --ice-teal:   #00b4d8;
    --ice-pink:   #f72585;
    --ice-yellow: #ffd166;
    --ice-green:  #06d6a0;
    --ice-dark:   #0d1b2a;
    --ice-card:   #1a2f45;
    --ice-text:   #e0f4ff;
    --ice-muted:  #7faacc;
    --red-alert:  #ff4d6d;
    --amber:      #fca311;
  }
  .stApp { background-color: var(--ice-dark); color: var(--ice-text); }

  /* Metric cards */
  .metric-card {
    background: var(--ice-card);
    border-radius: 12px;
    padding: 18px 20px;
    border-left: 4px solid var(--ice-teal);
    margin-bottom: 8px;
  }
  .metric-card.alert { border-left-color: var(--red-alert); }
  .metric-card.warn  { border-left-color: var(--amber); }
  .metric-card.good  { border-left-color: var(--ice-green); }
  .metric-value { font-size: 2rem; font-weight: 700; color: var(--ice-teal); }
  .metric-label { font-size: 0.85rem; color: var(--ice-muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .metric-sub   { font-size: 0.8rem; color: var(--ice-muted); margin-top: 4px; }

  /* Alert badges */
  .badge-red    { background:#ff4d6d22; color:#ff4d6d; border:1px solid #ff4d6d55; border-radius:6px; padding:2px 8px; font-size:0.75rem; }
  .badge-amber  { background:#fca31122; color:#fca311; border:1px solid #fca31155; border-radius:6px; padding:2px 8px; font-size:0.75rem; }
  .badge-green  { background:#06d6a022; color:#06d6a0; border:1px solid #06d6a055; border-radius:6px; padding:2px 8px; font-size:0.75rem; }

  /* Section headers */
  .section-header {
    font-size: 1.1rem; font-weight: 600; color: var(--ice-teal);
    border-bottom: 1px solid #1e3a52; padding-bottom: 6px; margin: 20px 0 12px 0;
  }

  /* Tab tweaks */
  .stTabs [data-baseweb="tab-list"] { gap: 8px; }
  .stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 8px 24px;
    background: var(--ice-card);
    color: var(--ice-muted);
    font-weight: 600;
  }
  .stTabs [aria-selected="true"] { background: var(--ice-teal) !important; color: #fff !important; }

  /* Form inputs */
  .stNumberInput input, .stTextInput input, .stSelectbox > div { background: var(--ice-card) !important; }

  /* Dataframe */
  .stDataFrame { border-radius: 10px; overflow: hidden; }

  /* Hide hamburger & footer */
  #MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ─── Header ──────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 9])
with col_logo:
    st.markdown("<div style='font-size:3rem;padding-top:8px'>🍦</div>", unsafe_allow_html=True)
with col_title:
    st.markdown("<h1 style='margin:0;color:#00b4d8;font-size:2rem'>IcyPops</h1>", unsafe_allow_html=True)
    st.markdown("<p style='margin:0;color:#7faacc;font-size:0.85rem'>Inventory & Business Dashboard</p>", unsafe_allow_html=True)

st.markdown("---")

# ─── Ensure Google Sheet has headers ─────────────────────────────────────────
try:
    ensure_headers()
except Exception as e:
    st.error(f"⚠️ Could not connect to Google Sheets. Check your secrets. Error: {e}")
    st.stop()

# ─── Load all data ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_all():
    return {
        "Expense": load_sheet("Expense"),
        "Bought":  load_sheet("Bought"),
        "Fridge":  load_sheet("Fridge"),
        "Revenue": load_sheet("Revenue"),
    }

data = load_all()

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_dash, tab_entry = st.tabs(["📊  Dashboard", "✏️  Data Entry"])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:

    df_bought  = data["Bought"]
    df_fridge  = data["Fridge"]
    df_revenue = data["Revenue"]
    df_expense = data["Expense"]

    # Compute inventory — always build safe fallbacks
    if df_bought.empty and df_fridge.empty:
        st.info("No data yet. Use the **Data Entry** tab to start adding records.")

    if df_bought.empty:
        df_bought_safe = pd.DataFrame(columns=["Date"] + PRODUCTS)
        for p in PRODUCTS:
            df_bought_safe[p] = 0
    else:
        df_bought_safe = df_bought

    if df_fridge.empty:
        df_fridge_safe = pd.DataFrame(columns=["Date", "Mode"] + PRODUCTS)
        for p in PRODUCTS:
            df_fridge_safe[p] = 0
        df_fridge_safe["Mode"] = ""
    else:
        df_fridge_safe = df_fridge

    inv = compute_inventory(df_bought_safe, df_fridge_safe, PRODUCTS)
    pnl = compute_daily_revenue_expense(df_revenue, df_expense)
    thresholds = load_thresholds()

    # ── KPI Strip ─────────────────────────────────────────────────────────────
    total_revenue  = df_revenue["Revenue"].sum() if not df_revenue.empty else 0
    total_expense  = df_expense["Expense"].sum() if not df_expense.empty else 0
    net_pnl        = total_revenue - total_expense
    total_sold     = int(inv["Sold"].sum())
    reorder_count  = int(inv["Needs Reorder"].sum())
    fridge_low     = int(inv["Fridge Stock Low"].sum())

    k1, k2, k3, k4, k5 = st.columns(5)

    def kpi(col, label, value, sub="", kind=""):
        css = f"metric-card {kind}"
        col.markdown(
            f"""<div class="{css}">
              <div class="metric-label">{label}</div>
              <div class="metric-value">{value}</div>
              <div class="metric-sub">{sub}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    kpi(k1, "Total Revenue", f"₹{total_revenue:,.0f}", "Lifetime", "good")
    kpi(k2, "Total Expense", f"₹{total_expense:,.0f}", "Lifetime")
    kpi(k3, "Net P&L",       f"₹{net_pnl:,.0f}",      "Breakeven tracker", "good" if net_pnl >= 0 else "alert")
    kpi(k4, "Units Sold",    f"{total_sold:,}",         "Lifetime total")
    kpi(k5, "Alerts",        f"{reorder_count + fridge_low}", f"🔴 {reorder_count} reorder · 🟡 {fridge_low} fridge low", "alert" if (reorder_count + fridge_low) > 0 else "good")

    st.markdown("")

    # ── Alert Tables ──────────────────────────────────────────────────────────
    col_a1, col_a2 = st.columns(2)

    with col_a1:
        st.markdown('<div class="section-header">🔴 Reorder Alerts — Stock Left Below Threshold</div>', unsafe_allow_html=True)
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
                    .format({"Stock Left": "{:.0f}", "Threshold": "{:.0f}", "Gap": "{:.0f}"}),
                use_container_width=True, hide_index=True,
            )

    with col_a2:
        st.markdown('<div class="section-header">🟡 Fridge Stock Alerts — In-Fridge Below Threshold</div>', unsafe_allow_html=True)
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
                    .format({"In Fridge": "{:.0f}", "Threshold": "{:.0f}", "Gap": "{:.0f}"}),
                use_container_width=True, hide_index=True,
            )

    st.markdown("")

    # ── Row 2: Charts ─────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="section-header">📈 Cumulative P&L — Breakeven Tracker</div>', unsafe_allow_html=True)
        if pnl.empty:
            st.info("No revenue/expense data yet.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=pnl["Date"], y=pnl["Cumulative Net"],
                fill="tozeroy",
                line=dict(color="#00b4d8", width=2),
                fillcolor="rgba(0,180,216,0.15)",
                name="Cumulative Net",
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#ff4d6d", annotation_text="Break Even")
            fig.update_layout(
                plot_bgcolor="#1a2f45", paper_bgcolor="#1a2f45",
                font_color="#e0f4ff", margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1e3a52"),
                height=280,
            )
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown('<div class="section-header">🏆 Top Products by Units Sold</div>', unsafe_allow_html=True)
        top = compute_top_products(inv, n=10)
        if top.empty or top["Sold"].sum() == 0:
            st.info("No sales data yet.")
        else:
            fig2 = px.bar(
                top, x="Sold", y="Product", orientation="h",
                color="Sold", color_continuous_scale="teal",
                labels={"Sold": "Units Sold"},
            )
            fig2.update_layout(
                plot_bgcolor="#1a2f45", paper_bgcolor="#1a2f45",
                font_color="#e0f4ff", margin=dict(l=10, r=10, t=10, b=10),
                coloraxis_showscale=False, height=280,
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── Row 3 ─────────────────────────────────────────────────────────────────
    c3, c4 = st.columns(2)

    with c3:
        st.markdown('<div class="section-header">💸 Daily Revenue vs Expense</div>', unsafe_allow_html=True)
        if pnl.empty:
            st.info("No data yet.")
        else:
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(x=pnl["Date"], y=pnl["Revenue"], name="Revenue", marker_color="#06d6a0"))
            fig3.add_trace(go.Bar(x=pnl["Date"], y=pnl["Expense"], name="Expense", marker_color="#f72585"))
            fig3.update_layout(
                barmode="group",
                plot_bgcolor="#1a2f45", paper_bgcolor="#1a2f45",
                font_color="#e0f4ff", margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1e3a52"),
                height=280, legend=dict(bgcolor="#1a2f45"),
            )
            st.plotly_chart(fig3, use_container_width=True)

    with c4:
        st.markdown('<div class="section-header">🧾 Expense Breakdown by Type</div>', unsafe_allow_html=True)
        exp_br = compute_expense_breakdown(df_expense)
        if exp_br.empty or exp_br["Expense"].sum() == 0:
            st.info("No expense data yet.")
        else:
            fig4 = px.pie(
                exp_br, values="Expense", names="Type",
                color_discrete_sequence=px.colors.sequential.Teal,
                hole=0.45,
            )
            fig4.update_layout(
                plot_bgcolor="#1a2f45", paper_bgcolor="#1a2f45",
                font_color="#e0f4ff", margin=dict(l=10, r=10, t=10, b=10),
                height=280, legend=dict(bgcolor="#1a2f45"),
                showlegend=True,
            )
            st.plotly_chart(fig4, use_container_width=True)

    # ── Row 4: Sold trend ─────────────────────────────────────────────────────
    st.markdown('<div class="section-header">📦 Daily Units Dispatched to Vendor (Sold Net)</div>', unsafe_allow_html=True)
    sold_trend = compute_sold_trend(df_fridge_safe, PRODUCTS)
    if sold_trend.empty or sold_trend["Total Sold"].sum() == 0:
        st.info("No fridge dispatch data yet.")
    else:
        fig5 = go.Figure()
        fig5.add_trace(go.Scatter(
            x=sold_trend["Date"], y=sold_trend["Total Sold"],
            mode="lines+markers",
            line=dict(color="#ffd166", width=2),
            marker=dict(size=5),
            fill="tozeroy",
            fillcolor="rgba(255,209,102,0.1)",
            name="Total Sold",
        ))
        fig5.update_layout(
            plot_bgcolor="#1a2f45", paper_bgcolor="#1a2f45",
            font_color="#e0f4ff", margin=dict(l=10, r=10, t=20, b=10),
            xaxis=dict(showgrid=False, dtick="D1", tickformat="%d %b"), yaxis=dict(gridcolor="#1e3a52"),
            height=220,
        )
        st.plotly_chart(fig5, use_container_width=True)

    # ── Row 5: Full Inventory Grid ─────────────────────────────────────────────
    st.markdown('<div class="section-header">📋 Full Inventory Snapshot</div>', unsafe_allow_html=True)
    display_inv = inv[["Total Bought", "Stock Outside Fridge", "Stock Inside Fridge",
                        "Sold", "Stock Left", "Needs Reorder", "Fridge Stock Low"]].copy()
    display_inv = display_inv.reset_index()

    def color_flags(val):
        if val is True:
            return "background-color:#ff4d6d33;color:#ff4d6d;font-weight:600"
        if val is False:
            return "color:#06d6a0"
        return ""

    styled = display_inv.style\
        .map(color_flags, subset=["Needs Reorder", "Fridge Stock Low"])\
        .format({c: "{:.0f}" for c in ["Total Bought","Stock Outside Fridge",
                                        "Stock Inside Fridge","Sold","Stock Left"]})\
        .set_properties(**{"background-color": "#1a2f45", "color": "#e0f4ff"})

    st.dataframe(styled, use_container_width=True, hide_index=True, height=400)

    # ── Refresh button ─────────────────────────────────────────────────────────
    st.markdown("")
    if st.button("🔄 Refresh Data", type="secondary"):
        st.cache_data.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — DATA ENTRY
# ══════════════════════════════════════════════════════════════════════════════
with tab_entry:

    st.markdown('<div class="section-header">✏️ Add a New Record</div>', unsafe_allow_html=True)

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

        # ── EXPENSE ───────────────────────────────────────────────────────────
        if sheet_choice == "Expense":
            col1, col2 = st.columns(2)
            with col1:
                exp_type = st.text_input("Type", placeholder="e.g. Product, Repair, Essentials")
            with col2:
                exp_desc = st.text_input("Description", placeholder="Brief note")
            exp_amount = st.number_input("Expense Amount (₹)", min_value=0.0, step=1.0)

            submitted = st.form_submit_button("➕ Add Expense", type="primary")
            if submitted:
                if not exp_type.strip():
                    st.error("Type is required.")
                elif exp_amount <= 0:
                    st.error("Expense must be greater than 0.")
                else:
                    append_row("Expense", [str(entry_date), exp_type.strip(), exp_desc.strip(), exp_amount])
                    st.success(f"✅ Expense of ₹{exp_amount} added for {entry_date}.")

        # ── BOUGHT ────────────────────────────────────────────────────────────
        elif sheet_choice == "Bought":
            st.markdown("Enter quantities purchased from manufacturer today. Leave 0 for items not bought.")
            st.markdown("**40 ml products**")
            cols_40 = st.columns(3)
            qty_40 = {}
            prods_40 = [p for p in PRODUCTS if "40 ml" in p]
            for i, p in enumerate(prods_40):
                with cols_40[i % 3]:
                    qty_40[p] = st.number_input(p, min_value=0, step=1, key=f"b40_{p}")

            st.markdown("**80 ml products**")
            cols_80 = st.columns(3)
            qty_80 = {}
            prods_80 = [p for p in PRODUCTS if "80 ml" in p]
            for i, p in enumerate(prods_80):
                with cols_80[i % 3]:
                    qty_80[p] = st.number_input(p, min_value=0, step=1, key=f"b80_{p}")

            st.markdown("**Family Pack**")
            fp_qty = st.number_input("FAMILY PACK", min_value=0, step=1, key="b_fp")

            submitted = st.form_submit_button("➕ Add Purchase Record", type="primary")
            if submitted:
                all_qty = {**qty_40, **qty_80, "FAMILY PACK": fp_qty}
                row = [str(entry_date)] + [all_qty[p] for p in PRODUCTS]
                append_row("Bought", row)
                total = sum(all_qty.values())
                st.success(f"✅ Purchase record added for {entry_date}. Total units: {total}")

        # ── FRIDGE ────────────────────────────────────────────────────────────
        elif sheet_choice == "Fridge":
            mode = st.selectbox(
                "Mode",
                FRIDGE_MODES,
                format_func=lambda x: {
                    "from stock":   "📦 From Stock — Moving into fridge from your own storage",
                    "to vendor":    "🚚 To Vendor   — Dispatching to reseller/vendor",
                    "from vendor":  "↩️  From Vendor — Returns from vendor back to you",
                }[x],
            )
            st.markdown(f"**Enter quantities for mode: `{mode}`**")

            st.markdown("**40 ml products**")
            fc_40 = st.columns(3)
            fq_40 = {}
            prods_40 = [p for p in PRODUCTS if "40 ml" in p]
            for i, p in enumerate(prods_40):
                with fc_40[i % 3]:
                    fq_40[p] = st.number_input(p, min_value=0, step=1, key=f"f40_{p}")

            st.markdown("**80 ml products**")
            fc_80 = st.columns(3)
            fq_80 = {}
            prods_80 = [p for p in PRODUCTS if "80 ml" in p]
            for i, p in enumerate(prods_80):
                with fc_80[i % 3]:
                    fq_80[p] = st.number_input(p, min_value=0, step=1, key=f"f80_{p}")

            st.markdown("**Family Pack**")
            ffp = st.number_input("FAMILY PACK", min_value=0, step=1, key="f_fp")

            submitted = st.form_submit_button("➕ Add Fridge Entry", type="primary")
            if submitted:
                all_qty = {**fq_40, **fq_80, "FAMILY PACK": ffp}
                row = [str(entry_date), mode] + [all_qty[p] for p in PRODUCTS]
                append_row("Fridge", row)
                total = sum(all_qty.values())
                st.success(f"✅ Fridge entry ({mode}) added for {entry_date}. Total units: {total}")

        # ── REVENUE ───────────────────────────────────────────────────────────
        elif sheet_choice == "Revenue":
            rev_amount = st.number_input("Revenue Amount (₹)", min_value=0.0, step=1.0)

            submitted = st.form_submit_button("➕ Add Revenue", type="primary")
            if submitted:
                if rev_amount <= 0:
                    st.error("Revenue must be greater than 0.")
                else:
                    append_row("Revenue", [str(entry_date), rev_amount])
                    st.success(f"✅ Revenue of ₹{rev_amount} added for {entry_date}.")

    # ── Recent entries preview ─────────────────────────────────────────────────
    st.markdown("")
    st.markdown(f'<div class="section-header">🔍 Recent Entries — {sheet_choice}</div>', unsafe_allow_html=True)
    preview_df = data[sheet_choice]
    if preview_df.empty:
        st.info("No records yet.")
    else:
        show_cols = preview_df.columns.tolist()
        # For Bought/Fridge, only show non-zero product columns to keep it readable
        if sheet_choice in ("Bought", "Fridge"):
            product_cols = [c for c in PRODUCTS if c in preview_df.columns and preview_df[c].sum() > 0]
            meta_cols = ["Date"] + (["Mode"] if sheet_choice == "Fridge" else [])
            show_cols = meta_cols + product_cols
        st.dataframe(
            preview_df[show_cols].tail(10).sort_values("Date", ascending=False),
            use_container_width=True, hide_index=True,
        )