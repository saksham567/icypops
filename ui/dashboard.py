"""ui/dashboard.py — Owner dashboard (IcyPops Pal).

Three visually distinct zones:
  A  Filtered by the period selector     Business at a glance · Product performance · Expenses
  B  Lifetime / as of today              Investment recovery · Stock & reorder · Partners
  C  Analysis with its own date controls Sales trend · Revenue by weekday · Expected revenue by category
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import schema as S
from core.analytics import (PERIODS, Window, category_mix, days_of_cover, expense_by_type, in_window, make_window,
                            payback_estimate, pct_change, period_stats, product_period_sales, recovery,
                            resample_breakdown, weekday_pattern)
from core.finance import build_expense_grid, daily_actual_vs_expected, dividend_totals, monthly_expense_pivot, partner_capital
from core.inventory import category_breakdown, compute_inventory, compute_sold_trend
from data import DataBundle
from ui import state
from ui.components import (COLORS, chart_title, delta_chip, download_csv, good_or_alert, html_table,
                           kpi, kpi_row, layout, plot, section, split_bar, xaxis, yaxis)

_CAT_RGB = {"Operational": "20,184,166", "Non-Operational": "246,185,59"}
_GRAND_RGB = "99,102,241"


def render(bundle: DataBundle) -> None:
    cat = bundle.catalog
    frames = bundle.frames
    df_bought, df_fridge, df_revenue = frames[S.BOUGHT], frames[S.FRIDGE], frames[S.REVENUE]
    if df_bought.empty and df_fridge.empty and df_revenue.empty:
        st.info("No data yet. Use the **Data Entry** tab to start adding records.")

    inv = compute_inventory(df_bought, df_fridge, cat)
    trend = compute_sold_trend(df_fridge, cat)
    div = dividend_totals(frames[S.DIVIDEND], cat)
    rec = recovery(frames, div[S.DIV_TOTAL])
    data_end = max([d for d in (df_revenue[S.DATE].max() if not df_revenue.empty else None,
                                trend[S.DATE].max() if not trend.empty else None) if pd.notna(d)] or [pd.Timestamp(date.today())])

    # ── Period selector ─────────────────────────────────────────────────────
    pc1, pc2 = st.columns([2, 3])
    with pc1:
        period = st.segmented_control("Period", PERIODS, default="All time", key="period", label_visibility="collapsed") or "All time"
    w = make_window(period, data_end=data_end)
    prev = w.previous()
    now = period_stats(frames, trend, cat, w)
    before = period_stats(frames, trend, cat, prev) if prev else None
    with pc2:
        st.markdown(f'<div class="period-caption">{w.describe()}' + (f" · change shown vs {prev.label}" if prev else "") + "</div>", unsafe_allow_html=True)

    def chip(cur_v, prev_v, invert=False):
        return delta_chip(pct_change(cur_v, prev_v), f"vs {prev.label}", invert) if before else ""

    # ══ ZONE A — follows the period selector ═════════════════════════════════
    with st.container(border=True):
        st.markdown(f'<span class="panel-tag teal">Filtered · {w.label} · the sections below follow the period selector</span>', unsafe_allow_html=True)
        _glance(cat, w, now, before, chip)
        _products(cat, trend, df_bought, w)
        _expenses(cat, frames[S.EXPENSE], w, now, before, chip)

    # ══ ZONE B — lifetime / as of today ══════════════════════════════════════
    with st.container(border=True):
        st.markdown('<span class="panel-tag slate">Lifetime · as of today · not affected by the period selector</span>', unsafe_allow_html=True)
        _recovery(cat, rec, w, now)
        _stock(cat, inv, trend)
        _partners(cat, frames[S.EXPENSE], div, rec)

    # ══ ZONE C — own date controls ═══════════════════════════════════════════
    _analysis(cat, df_revenue, df_fridge, trend, data_end)

    _footer(inv)


# ─────────────────────────────────────────────────────────────────────────────
#  ZONE A
# ─────────────────────────────────────────────────────────────────────────────

def _glance(cat, w: Window, now, before, chip) -> None:
    fx = cat.fmt
    section("Business at a glance", w.label)
    gap_pct = (now.gap / now.expected * 100) if now.expected else 0.0
    kpi_row([
        ("Revenue collected", fx(now.revenue), f"actual collections · {now.revenue_days} selling days", "teal",
         chip(now.revenue, before.revenue if before else None)),
        ("Expected revenue", fx(now.expected), "units sold × list price", "indigo",
         chip(now.expected, before.expected if before else None)),
        ("Collection gap", fx(now.gap), f"collected − expected · {gap_pct:+.1f}%", good_or_alert(now.gap)),
        ("Avg revenue / day", fx(now.avg_daily_revenue), "revenue collected ÷ selling days", "teal",
         chip(now.avg_daily_revenue, before.avg_daily_revenue if before else None)),
        ("Units sold", f"{int(now.units):,}", f"{now.avg_ticket_units:,.0f} units per trading day", "indigo",
         chip(now.units, before.units if before else None)),
        ("Realized profit", fx(now.operating_profit), "revenue collected − operating expenses", good_or_alert(now.operating_profit),
         chip(now.operating_profit, before.operating_profit if before else None)),
    ], max_cols=3)


def _products(cat, trend, df_bought, w: Window) -> None:
    fx, cur = cat.fmt, cat.currency
    section("Product performance", w.label)
    psales = product_period_sales(trend, df_bought, cat, w)
    p1, p2 = st.columns([3, 1.3])
    with p1:
        chart_title("Units sold vs bought per product")
        chart = psales.copy()
        chart["_grp"] = chart.index.map(cat.category_rank)
        chart = chart.sort_values(["_grp", "Units Sold"], ascending=[False, True])
        hover = chart[["Units Sold", "Units Bought", "Revenue", "Share %"]].values
        tmpl = (f"<b>%{{y}}</b><br>Sold: %{{customdata[0]:,.0f}}<br>Bought: %{{customdata[1]:,.0f}}"
                f"<br>Expected revenue: {cur}%{{customdata[2]:,.0f}}<br>Share: %{{customdata[3]:.1f}}%<extra></extra>")
        fig = go.Figure()
        fig.add_trace(go.Bar(y=chart.index, x=chart["Units Bought"], name="Bought", orientation="h",
                             marker_color="rgba(148,163,184,0.30)", customdata=hover, hovertemplate=tmpl))
        fig.add_trace(go.Bar(y=chart.index, x=chart["Units Sold"], name="Sold", orientation="h",
                             marker_color=[cat.category_of(p).color for p in chart.index], customdata=hover, hovertemplate=tmpl))
        fig.update_layout(**layout(barmode="overlay", height=max(380, 26 * len(chart) + 90),
                                   xaxis=yaxis(title="units"), yaxis=xaxis(tickfont=dict(size=11, color="#1B2437"))))
        plot(fig)
    with p2:
        mix = category_mix(psales, cat)
        if mix["Revenue"].sum() > 0:
            chart_title("Expected revenue mix")
            figd = go.Figure(go.Pie(labels=mix["Category"], values=mix["Revenue"], hole=0.62, sort=False,
                                    marker=dict(colors=list(mix["Color"]), line=dict(color="#FFFFFF", width=2)),
                                    textinfo="percent", textfont=dict(size=11, color="#FFFFFF"),
                                    hovertemplate=f"<b>%{{label}}</b><br>{cur}%{{value:,.0f}}<br>%{{percent}}<extra></extra>"))
            figd.update_layout(**layout(height=300, showlegend=True, margin=dict(l=8, r=8, t=16, b=8),
                                        legend=dict(orientation="h", y=-0.1, yanchor="top", x=0.5, xanchor="center", font=dict(size=11, color="#1B2437")),
                                        annotations=[dict(text=fx(mix["Revenue"].sum()), showarrow=False, font=dict(size=14, color="#1B2437"))]))
            plot(figd)
        ranked = psales[psales["Units Sold"] > 0].sort_values("Units Sold", ascending=False)
        st.markdown("**Top sellers**")
        html_table(ranked.head(5)[["Units Sold"]], formats={"Units Sold": "{:,.0f}"}, index=True, max_height=260)
        st.markdown("**Slow movers**")
        slow = psales[psales["Units Bought"] + psales["Units Sold"] > 0].sort_values("Units Sold").head(5)
        html_table(slow[["Units Sold"]], formats={"Units Sold": "{:,.0f}"}, index=True, max_height=260)
    st.caption("Collections are recorded per day, not per product, so product and category splits use expected revenue (units × list price).")


def _expenses(cat, df_expense, w: Window, now, before, chip) -> None:
    fx, cur = cat.fmt, cat.currency
    section("Expenses", w.label)
    exp_w = in_window(df_expense, w)
    paid = ({c: float(exp_w.loc[pd.to_numeric(exp_w[c], errors="coerce").fillna(0) > 0, S.EXP_AMOUNT].sum()) for c in S.PAYMENT_COLS}
            if not exp_w.empty else {c: 0.0 for c in S.PAYMENT_COLS})
    total_exp = now.op_expense + now.capex

    def pct(v):
        return f"{(v / total_exp * 100) if total_exp else 0:.0f}% of total"

    x1, x2 = st.columns([1.3, 3])
    with x1:
        kpi(st, "Total expenses", fx(total_exp), f"{len(exp_w)} entries · " + (w.label.lower() if w.start is not None else "lifetime"), "hero",
            chip(total_exp, (before.op_expense + before.capex) if before else None, invert=True))
    with x2:
        chart_title("What kind of spend?")
        kpi_row([
            ("Operating", fx(now.op_expense), f"{pct(now.op_expense)} · stock, salary, essentials, travel", "teal",
             chip(now.op_expense, before.op_expense if before else None, invert=True)),
            ("One-time investment", fx(now.capex), f"{pct(now.capex)} · cart, freezer, deposits", "amber"),
        ], max_cols=2)
        split_bar([("Operating", now.op_expense, COLORS["teal"]), ("One-time", now.capex, COLORS["amber"])], fx)

    chart_title("Who paid for it?")
    kpi_row([
        ("From business bank", fx(paid[S.PAY_BANK]), pct(paid[S.PAY_BANK]), "indigo"),
        ("From business cash", fx(paid[S.PAY_CASH]), pct(paid[S.PAY_CASH]), "indigo"),
        ("From partners' own money", fx(paid[S.PAY_OWN]), f"{pct(paid[S.PAY_OWN])} · capital put in by partners", "warn" if paid[S.PAY_OWN] else "indigo"),
    ], max_cols=3)
    split_bar([("Business bank", paid[S.PAY_BANK], COLORS["indigo"]), ("Business cash", paid[S.PAY_CASH], "#A5B4FC"),
               ("Partners' own money", paid[S.PAY_OWN], COLORS["coral"])], fx)

    e1, e2 = st.columns([1.3, 3])
    with e1:
        bt = expense_by_type(df_expense, w)
        if bt.empty:
            st.info("No expenses in this period.")
        else:
            chart_title("By type")
            bt = bt.groupby("Type", as_index=False).agg(Amount=("Amount", "sum"), Operational=("Operational", "max")).sort_values("Amount")
            fige = go.Figure(go.Bar(y=bt["Type"], x=bt["Amount"], orientation="h", text=[fx(v) for v in bt["Amount"]], textposition="outside",
                                    textfont=dict(size=10, color="#5B6577"), cliponaxis=False,
                                    marker_color=[COLORS["teal"] if o else COLORS["amber"] for o in bt["Operational"]],
                                    hovertemplate=f"<b>%{{y}}</b><br>{cur}%{{x:,.0f}}<extra></extra>"))
            fige.update_layout(**layout(height=max(260, 30 * len(bt) + 60), margin=dict(l=8, r=80, t=12, b=8), showlegend=False,
                                        xaxis=xaxis(showticklabels=False), yaxis=xaxis(tickfont=dict(size=11, color="#1B2437"))))
            plot(fige)
            st.caption("Teal = operating · Amber = one-time")
    with e2:
        pivot = monthly_expense_pivot(df_expense)
        if pivot is not None:
            chart_title("Month by month (lifetime)")
            grid, kinds, num_cols = build_expense_grid(pivot)
            css = _style_expense_grid(grid, kinds, num_cols)
            html_table(grid, formats={c: (lambda v: "–" if float(v) == 0 else fx(v)) for c in num_cols},
                       cell_style=css, pill_cols=("Category",), max_height=520, first_col_bold=False)
            download_csv(grid, "⬇ Export month-by-month grid", "expense_breakdown.csv", "dl_exp")


# ─────────────────────────────────────────────────────────────────────────────
#  ZONE B
# ─────────────────────────────────────────────────────────────────────────────

def _recovery(cat, rec, w: Window, now) -> None:
    fx = cat.fmt
    section("Investment recovery", "lifetime")
    r1, r2 = st.columns([3, 2])
    with r1:
        pb = payback_estimate(rec, now)
        if rec.remaining <= 0:
            eta = "Investment fully recovered 🎉"
        elif pb is None:
            eta = "Payback not estimable — no realized profit in the selected period"
        else:
            eta = f"Payback in ≈ {pb:,.0f} days at the {w.label.lower()} run rate → {(pd.Timestamp(date.today()) + timedelta(days=int(pb))):%b %Y}"
        st.markdown(f"""
<div class="recovery">
  <div class="row"><span>Recovered <b>{rec.pct:.0f}%</b> of one-time investment (cumulative realized profit)</span><span class="big">{fx(rec.recovered)} / {fx(rec.invested)}</span></div>
  <div class="track"><div class="fill" style="width:{rec.pct:.1f}%"></div></div>
  <div class="row"><span>{eta}</span><span>Remaining {fx(rec.remaining)}</span></div>
</div>""", unsafe_allow_html=True)
    with r2:
        kpi_row([
            ("Net P&L to date", fx(rec.net_pnl), "revenue − all expenses incl. one-time", good_or_alert(rec.net_pnl)),
            ("Distributable profit", fx(rec.distributable), f"realized profit − {fx(rec.dividends)} paid out", good_or_alert(rec.distributable)),
        ], max_cols=2)


def _stock(cat, inv, trend) -> None:
    fx = cat.fmt
    cover = days_of_cover(inv, trend, cat)
    attention = cover[cover["Status"] != "Healthy"]
    section("Stock & reorder", f"as of today · {len(attention)} need attention")
    s1, s2 = st.columns([1, 3])
    with s1:
        only_attention = st.toggle("Needs attention only", value=len(attention) > 0, key="stock_attention")
        urgent = cover[cover["Status"].isin(["Out of stock", "Reorder now"])]
        kpi(st, "Reorder now", f"{len(urgent)}", "products at ≤ 7 days of cover or below threshold", "alert" if len(urgent) else "good")
        kpi(st, "Stock on hand", f"{int(inv['Stock Left'].sum()):,}",
            f"units · worth {fx(float((inv['Stock Left'] * inv['Unit Price']).sum()))} at list price", "indigo")
    with s2:
        tbl = (attention if only_attention else cover).copy()
        tbl["_grp"] = tbl.index.map(cat.category_rank)
        tbl = tbl.sort_values(["Days of cover", "_grp"], na_position="last").drop(columns="_grp")
        tbl["Days of cover"] = tbl["Days of cover"].apply(lambda v: "—" if pd.isna(v) else f"{int(v)}")
        show = tbl.reset_index()[["Product", "Category", "Stock Left", "Avg/day", "Days of cover", "Reorder Threshold", "Status"]]
        if show.empty:
            st.success("✅ Every product has more than two weeks of cover.")
        else:
            html_table(show, formats={"Stock Left": "{:.0f}", "Avg/day": "{:.1f}", "Reorder Threshold": "{:.0f}"}, pill_cols=("Status",), max_height=480)
            st.caption("Avg/day = units sold per trading day over the last 14 settled days · Days of cover = stock left ÷ avg/day.")


def _partners(cat, df_expense, div, rec) -> None:
    if not cat.partners:
        return
    fx = cat.fmt
    section("Partners", "lifetime")
    items = [("Dividends paid", fx(div[S.DIV_TOTAL]), "total payouts to date", "indigo")]
    items += [(p.name, fx(div.get(p.name, 0)), f"{p.share_pct:g}% share · fair share {fx(div[S.DIV_TOTAL] * p.share_pct / 100)}", "teal") for p in cat.partners]
    items.append(("Available to distribute", fx(rec.distributable), "realized profit − dividends paid", good_or_alert(rec.distributable)))
    kpi_row(items, max_cols=min(4, len(items)))
    capital = partner_capital(df_expense, cat)
    if capital is not None:
        html_table(capital, formats={c: fx for c in ["Contributed", "Fair share", "Over / (Under)"]})
        st.caption("Own-money contributions vs each partner's share. Positive = that partner has put in more than their share.")
    else:
        st.caption("Tip: record *who* paid when an expense is paid with own money and this section will show each partner's capital balance.")


# ─────────────────────────────────────────────────────────────────────────────
#  ZONE C
# ─────────────────────────────────────────────────────────────────────────────

def _analysis(cat, df_revenue, df_fridge, trend, data_end) -> None:
    fx, cur = cat.fmt, cat.currency
    st.markdown("")
    with st.container(border=True):
        st.markdown('<span class="panel-tag indigo">Analysis · own date controls below · not affected by the period selector</span>', unsafe_allow_html=True)

        section("Sales trend", "actual collections vs expected from units sold")
        avx_all = daily_actual_vs_expected(df_revenue, df_fridge, cat).dropna(subset=[S.DATE])
        if avx_all.empty:
            st.info("No revenue data yet.")
        else:
            max_days = max(7, int(avx_all[S.DATE].nunique()))
            n_days = st.slider("Days shown", min_value=7, max_value=max_days, value=min(20, max_days), step=1, key="trend_days")
            end = avx_all[S.DATE].max()
            view = avx_all[avx_all[S.DATE] >= end - pd.Timedelta(days=n_days - 1)].copy()
            view["Note"] = view["Comment"].apply(lambda c: f"💬 {c}" if c else "")
            short = view[view["Actual"].notna() & view["Expected"].notna() & (view["Actual"] < view["Expected"])].copy()
            short["Shortfall"] = short["Expected"] - short["Actual"]
            t1, t2 = st.columns([3, 1.2])
            with t1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=view[S.DATE], y=view["Expected"], mode="lines+markers", name="Expected",
                                         line=dict(color=COLORS["slate"], width=2, dash="dot"), marker=dict(size=5), connectgaps=True,
                                         hovertemplate=f"<b>Expected</b><br>%{{x|%a %d %b}}<br>{cur}%{{y:,.0f}}<extra></extra>"))
                fig.add_trace(go.Scatter(x=view[S.DATE], y=view["Actual"], mode="lines+markers", name="Collected",
                                         line=dict(color=COLORS["teal_dark"], width=2.5), marker=dict(size=6),
                                         fill="tozeroy", fillcolor="rgba(20,184,166,0.10)", connectgaps=True, customdata=view["Note"],
                                         hovertemplate=f"<b>Collected</b><br>%{{x|%a %d %b}}<br>{cur}%{{y:,.0f}}<br>%{{customdata}}<extra></extra>"))
                fig.add_trace(go.Scatter(x=short[S.DATE], y=short["Actual"], mode="markers", name="Below expected",
                                         marker=dict(color=COLORS["coral_dark"], size=11, line=dict(color="#FFFFFF", width=1.5)),
                                         customdata=short[["Expected", "Shortfall", "Note"]].values,
                                         hovertemplate=(f"<b>Below expected</b><br>%{{x|%a %d %b}}<br>Collected: {cur}%{{y:,.0f}}"
                                                        f"<br>Expected: {cur}%{{customdata[0]:,.0f}}<br>Short: {cur}%{{customdata[1]:,.0f}}<br>%{{customdata[2]}}<extra></extra>")))
                fig.update_layout(**layout(height=340, xaxis=xaxis(tickformat="%d %b", **({"dtick": "D1"} if n_days <= 31 else {})),
                                           yaxis=yaxis(title=cur)))
                plot(fig)
                st.caption(f"{len(short)} of {len(view)} days below expected · cumulative gap {fx(float(view['Gap'].fillna(0).sum()))} in this window.")
            with t2:
                chart_title("Average revenue by weekday (all time)")
                wk = weekday_pattern(df_revenue, make_window("All time", data_end=data_end))
                best = wk.loc[wk["Avg Revenue"].idxmax(), "Weekday"] if wk["Avg Revenue"].sum() else "—"
                figw = go.Figure(go.Bar(x=wk["Weekday"], y=wk["Avg Revenue"], text=[fx(v) for v in wk["Avg Revenue"]], textposition="outside",
                                        textfont=dict(size=10, color="#5B6577"), cliponaxis=False,
                                        marker_color=[COLORS["emerald"] if d == best else "rgba(20,184,166,0.45)" for d in wk["Weekday"]],
                                        customdata=wk["Days"], hovertemplate=f"<b>%{{x}}</b><br>Avg {cur}%{{y:,.0f}}<br>%{{customdata}} days<extra></extra>"))
                figw.update_layout(**layout(height=340, margin=dict(l=8, r=8, t=28, b=8), showlegend=False,
                                            xaxis=xaxis(), yaxis=xaxis(showticklabels=False)))
                plot(figw)

        section("Expected revenue by category", "settled days only")
        if trend.empty or trend["Total Sold"].sum() == 0:
            st.info("No settled dispatch data yet.")
        else:
            bd = category_breakdown(trend, cat)
            c0, c1, c2 = st.columns([1.2, 1, 1])
            view_mode = c0.radio("View", ["Daily", "Monthly"], horizontal=True, key="cat_view", label_visibility="collapsed")
            if view_mode == "Daily":
                min_d, max_d = bd[S.DATE].min().date(), bd[S.DATE].max().date()
                d_from = c1.date_input("From date", value=max(min_d, max_d - timedelta(days=14)), min_value=min_d, max_value=max_d, key="cat_from")
                d_to = c2.date_input("To date", value=max_d, min_value=min_d, max_value=max_d, key="cat_to")
                plot_df = bd[(bd[S.DATE].dt.date >= d_from) & (bd[S.DATE].dt.date <= d_to)].copy()
                x_col, x_settings = S.DATE, xaxis(dtick="D1", tickformat="%d %b")
            else:
                plot_df, x_col = resample_breakdown(bd, "M")
                x_settings = xaxis()
            fig5 = go.Figure()
            for c in cat.categories_sorted():
                fig5.add_trace(go.Bar(x=plot_df[x_col], y=plot_df[f"Rev {c.label}"], name=c.label, marker_color=c.color,
                                      customdata=plot_df[f"Units {c.label}"],
                                      hovertemplate=f"<b>{c.label}</b><br>{cur}%{{y:,.0f}} · %{{customdata:,.0f}} units<extra></extra>"))
            fig5.add_trace(go.Bar(x=plot_df[x_col], y=plot_df["Rev Total"], name="Total", marker_color=COLORS["indigo"],
                                  customdata=plot_df["Units Total"],
                                  hovertemplate=f"<b>Total</b><br>{cur}%{{y:,.0f}} · %{{customdata:,.0f}} units<extra></extra>"))
            fig5.add_trace(go.Scatter(x=plot_df[x_col], y=plot_df["Gross Profit"], name="Gross profit", mode="lines+markers",
                                      line=dict(color=COLORS["emerald"], width=2.5), marker=dict(size=6),
                                      hovertemplate=f"<b>Gross profit</b><br>{cur}%{{y:,.0f}}<extra></extra>"))
            fig5.update_layout(**layout(barmode="group", height=360, xaxis=x_settings, yaxis=yaxis(title=cur)))
            plot(fig5)


# ─────────────────────────────────────────────────────────────────────────────

def _footer(inv) -> None:
    st.markdown("")
    f1, f2, f3 = st.columns(3)
    with f1:
        if st.button("↻ Refresh data", type="secondary", width="stretch"):
            state.refresh()
            st.rerun()
    with f2:
        download_csv(inv.reset_index(), "⬇ Export inventory (CSV)", "inventory_snapshot.csv", "dl_inv")
    with f3:
        if st.button("💾 Save backup snapshot", type="primary", width="stretch"):
            try:
                with st.spinner("Creating snapshot…"):
                    snap = state.get_repo().snapshot()
                if snap is None:
                    st.info("Snapshots are not supported for this backend — use your database provider's backups.")
                else:
                    st.success(f"Snapshot saved as **{snap['name']}**" + (f" · {snap['path']}" if snap.get("path") else ""))
                    if snap.get("url"):
                        st.markdown(f"[Open snapshot]({snap['url']})")
            except Exception as e:
                st.error(f"Could not create snapshot. {e}")


def _style_expense_grid(grid: pd.DataFrame, kinds: list[str], num_cols: list[str]) -> pd.DataFrame:
    css = pd.DataFrame("", index=grid.index, columns=grid.columns)
    month_cols = num_cols[:-1]
    detail_idx = [i for i, k in enumerate(kinds) if k in _CAT_RGB]
    vmax = float(grid.iloc[detail_idx][month_cols].to_numpy().max()) if detail_idx and month_cols else 0.0
    for i, kind in enumerate(kinds):
        if kind in _CAT_RGB:
            rgb = _CAT_RGB[kind]
            for c in month_cols:
                v = float(grid.iloc[i][c])
                css.at[i, c] = (f"background-color: rgba({rgb},{0.10 + 0.45 * v / vmax:.2f})" if v > 0 and vmax > 0 else "color: #8A94A6")
            css.at[i, "Total"] = "font-weight: 700"
        elif kind.startswith("subtotal:"):
            rgb = _CAT_RGB[kind.split(":", 1)[1]]
            css.iloc[i, :] = f"background-color: rgba({rgb},0.30); font-weight: 700"
        else:
            css.iloc[i, :] = f"background-color: rgba({_GRAND_RGB},0.18); font-weight: 700"
    return css
