"""ui/components.py — Small reusable presentation helpers (light theme)."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

COLORS = {
    "teal": "#14B8A6", "teal_dark": "#0F766E", "coral": "#F97066", "coral_dark": "#D64E31",
    "amber": "#F6B93B", "amber_dark": "#D97706", "emerald": "#16A34A", "indigo": "#6366F1",
    "slate": "#94A3B8", "navy": "#1B2437", "grid": "rgba(27,36,55,0.06)",
}

CHART_LAYOUT = dict(
    template="plotly_white",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#5B6577", size=12),
    title_font=dict(color="#1B2437"),
    margin=dict(l=8, r=16, t=48, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                bgcolor="rgba(0,0,0,0)", font=dict(color="#1B2437", size=11)),
    hoverlabel=dict(bgcolor="#1B2437", bordercolor="#1B2437", font=dict(family="Inter, sans-serif", color="#FFFFFF", size=12)),
    colorway=["#14B8A6", "#F97066", "#F6B93B", "#6366F1", "#0EA5E9", "#A855F7"],
)
X_AXIS = dict(showgrid=False, showline=False, zeroline=False, tickfont=dict(color="#5B6577"), title_font=dict(color="#5B6577"))


def layout(**overrides) -> dict:
    """CHART_LAYOUT with per-chart overrides (nested legend/margin dicts are merged)."""
    base = {k: (dict(v) if isinstance(v, dict) else v) for k, v in CHART_LAYOUT.items()}
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base
Y_AXIS = dict(showgrid=True, gridcolor=COLORS["grid"], showline=False, zeroline=False, tickfont=dict(color="#5B6577"), title_font=dict(color="#5B6577"))


def xaxis(**kw) -> dict:
    d = dict(X_AXIS); d.update(kw); return d


def yaxis(**kw) -> dict:
    d = dict(Y_AXIS); d.update(kw); return d


def plot(fig) -> None:
    """Render a Plotly figure with Streamlit's theme switched OFF so our colours always apply."""
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


def delta_chip(pct: float | None, suffix: str = "vs previous period", invert: bool = False) -> str:
    if pct is None:
        return ""
    up = pct >= 0
    good = (not up) if invert else up
    return f'<span class="metric-delta {"up" if good else "down"}">{"▲" if up else "▼"} {abs(pct):.0f}% {html.escape(suffix)}</span>'


def kpi(col, label: str, value: str, sub: str = "", kind: str = "", delta_html: str = "") -> None:
    col.markdown(
        f'<div class="metric-card {kind}">'
        f'<div class="metric-label">{html.escape(str(label))}</div>'
        f'<div class="metric-value">{html.escape(str(value))}</div>'
        f'<div class="metric-sub">{html.escape(str(sub))}{(" " + delta_html) if delta_html else ""}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def kpi_row(items: list[tuple], max_cols: int = 4) -> None:
    """items: (label, value, sub, kind[, delta_html]) rendered in rows of max_cols."""
    for i in range(0, len(items), max_cols):
        chunk = items[i:i + max_cols]
        cols = st.columns(len(chunk))
        for c, item in zip(cols, chunk):
            kpi(c, *item)


def split_bar(segments: list[tuple[str, float, str]], fmt) -> None:
    """100% stacked bar. segments: (label, value, color)."""
    total = sum(v for _, v, _ in segments) or 1.0
    bar = "".join(f'<div class="seg" style="width:{v / total * 100:.2f}%;background:{c}"></div>' for _, v, c in segments if v > 0)
    leg = "".join(f'<span><span class="dot" style="background:{c}"></span>{html.escape(l)} <b>{html.escape(fmt(v))}</b> · {v / total * 100:.0f}%</span>'
                  for l, v, c in segments)
    st.markdown(f'<div class="split"><div class="bar">{bar}</div><div class="legend">{leg}</div></div>', unsafe_allow_html=True)


def section(title: str, hint: str = "") -> None:
    hint_html = f'<span class="hint">{html.escape(hint)}</span>' if hint else ""
    st.markdown(f'<div class="section-header">{html.escape(title)}{hint_html}</div>', unsafe_allow_html=True)


def chart_title(text: str) -> None:
    st.markdown(f'<p class="chart-title">{html.escape(text)}</p>', unsafe_allow_html=True)


def good_or_alert(v: float) -> str:
    return "good" if v >= 0 else "alert"


def download_csv(df: pd.DataFrame, label: str, filename: str, key: str) -> None:
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name=filename, mime="text/csv", key=key, width="stretch")


def status_style(val: str) -> str:
    return {
        "Out of stock": "background-color:rgba(214,78,49,0.16);color:#B4321A;font-weight:700",
        "Reorder now": "background-color:rgba(249,112,102,0.16);color:#D64E31;font-weight:600",
        "Watch": "background-color:rgba(246,185,59,0.22);color:#B45309;font-weight:600",
        "Healthy": "color:#16A34A;font-weight:600",
    }.get(val, "")


def flag_style(val):
    if val is True:
        return "background-color:rgba(214,78,49,0.12);color:#D64E31;font-weight:600"
    if val is False:
        return "color:#16A34A"
    return ""


def fmt_date(ts) -> str:
    try:
        return pd.Timestamp(ts).strftime("%d %b %Y")
    except Exception:
        return str(ts)


# ── HTML tables (theme-independent; st.dataframe is a canvas that follows Streamlit's theme) ──

PILL_STYLES = {
    "Out of stock": "background:rgba(214,78,49,0.16);color:#B4321A",
    "Reorder now": "background:rgba(249,112,102,0.18);color:#D64E31",
    "Watch": "background:rgba(246,185,59,0.25);color:#B45309",
    "Healthy": "background:rgba(22,163,74,0.12);color:#15803D",
    "Operational": "background:rgba(20,184,166,0.16);color:#0F766E",
    "Non-Operational": "background:rgba(246,185,59,0.25);color:#B45309",
}


def _cell_text(v, fmt) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return ""
    if fmt is not None:
        try:
            return fmt(v) if callable(fmt) else fmt.format(v)
        except Exception:
            pass
    if isinstance(v, (pd.Timestamp,)):
        return v.strftime("%d %b %Y")
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float):
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def html_table(df: pd.DataFrame, formats: dict | None = None, cell_style: pd.DataFrame | None = None,
               row_style: list[str] | None = None, pill_cols: tuple = (), max_height: int = 460,
               first_col_bold: bool = True, index: bool = False) -> None:
    """Light-themed HTML table. formats: {col: callable | "{:.0f}"}; cell_style: same-shape frame of CSS."""
    formats = formats or {}
    d = df.reset_index() if index else df
    cols = list(d.columns)
    numeric = {c for c in cols if pd.api.types.is_numeric_dtype(d[c]) and c not in pill_cols}
    head = "".join(f'<th class="{"num" if c in numeric else ""}">{html.escape(str(c))}</th>' for c in cols)
    rows = []
    for i, (_, r) in enumerate(d.iterrows()):
        tds = []
        for j, c in enumerate(cols):
            v = r[c]
            txt = html.escape(_cell_text(v, formats.get(c)))
            style = ""
            if cell_style is not None:
                try:
                    style = str(cell_style.iloc[i, j]) or ""
                except Exception:
                    style = ""
            if c in pill_cols and str(v) in PILL_STYLES:
                txt = f'<span class="pill-cell" style="{PILL_STYLES[str(v)]}">{txt}</span>'
            cls = ("num" if c in numeric else "") + (" lead" if (j == 0 and first_col_bold) else "")
            tds.append(f'<td class="{cls}" style="{html.escape(style, quote=True)}">{txt}</td>')
        rs = f' style="{html.escape(row_style[i], quote=True)}"' if row_style and i < len(row_style) and row_style[i] else ""
        rows.append(f"<tr{rs}>{''.join(tds)}</tr>")
    body = "".join(rows) or f'<tr><td colspan="{len(cols)}" class="empty">No rows</td></tr>'
    st.markdown(f'<div class="tbl-wrap" style="max-height:{max_height}px"><table class="tbl"><thead><tr>{head}</tr></thead>'
                f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
