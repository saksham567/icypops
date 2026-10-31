"""ui/styles.py — Light theme ("IcyPops Pal"). Injected via st.html; st.markdown strips <style> on Cloud.

Palette
  base      #F5F7FA   surface #FFFFFF   border #E5E9F0
  text      #1B2437 / #5B6577 / #8A94A6
  teal      #0F766E (primary) · #14B8A6 (bright)      → revenue, operating, positive accents
  coral     #D64E31 (text) · #F97066 (fill)            → negatives, shortfalls
  amber     #D97706 (text) · #F6B93B (fill)            → one-time spend, caution
  emerald   #16A34A                                    → profit / healthy
  indigo    #6366F1                                    → totals / neutral highlight
"""
from __future__ import annotations

import html

import streamlit as st

from core.catalog import Catalog

APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
  --bg-base: #F5F7FA; --bg-surface: #FFFFFF; --bg-soft: #F0F3F8;
  --border: #E5E9F0; --border-strong: #D5DBE5;
  --text-primary: #1B2437; --text-secondary: #5B6577; --text-muted: #8A94A6;
  --teal: #0F766E; --teal-bright: #14B8A6; --teal-soft: rgba(20,184,166,0.12);
  --coral: #D64E31; --coral-soft: rgba(249,112,102,0.14);
  --amber: #D97706; --amber-soft: rgba(246,185,59,0.18);
  --emerald: #16A34A; --emerald-soft: rgba(22,163,74,0.12);
  --indigo: #6366F1; --indigo-soft: rgba(99,102,241,0.12);
  --radius: 14px; --shadow: 0 1px 2px rgba(27,36,55,0.04), 0 6px 20px rgba(27,36,55,0.06);
}

html, body, [class*="css"] { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
.stApp { background: var(--bg-base); color: var(--text-primary); }
.block-container { padding-top: 1.25rem; max-width: 1440px; }
h1, h2, h3, h4, p, li, label, .stMarkdown { color: var(--text-primary); }

/* ── Header ─────────────────────────────────────────────────────────────── */
.app-header {
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 1.1rem 1.5rem; margin-bottom: 0.75rem; box-shadow: var(--shadow);
  display: flex; align-items: center; gap: 1.1rem;
}
.app-logo {
  width: 48px; height: 48px; flex: 0 0 48px; border-radius: 13px; font-size: 1.5rem;
  background: linear-gradient(135deg, #14B8A6 0%, #0F766E 100%);
  display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 16px rgba(15,118,110,0.25);
}
.app-title { margin: 0; font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; color: var(--text-primary); }
.app-subtitle { margin: 0.1rem 0 0 0; font-size: 0.84rem; color: var(--text-secondary); }
.app-badges { margin-left: auto; display: flex; gap: 0.5rem; flex-wrap: wrap; justify-content: flex-end; }
.app-badge {
  padding: 0.3rem 0.8rem; border-radius: 999px; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  background: var(--teal-soft); color: var(--teal); border: 1px solid rgba(20,184,166,0.3);
}
.app-badge.demo  { background: var(--amber-soft); color: var(--amber); border-color: rgba(217,119,6,0.3); }
.app-badge.muted { background: var(--bg-soft); color: var(--text-secondary); border-color: var(--border-strong); }

/* ── KPI cards ──────────────────────────────────────────────────────────── */
.metric-card {
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 1.05rem 1.2rem 1rem; margin-bottom: 0.7rem; box-shadow: var(--shadow);
  position: relative; overflow: hidden; min-height: 112px;
}
.metric-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--border-strong); }
.metric-card.good::before    { background: var(--emerald); }
.metric-card.alert::before   { background: var(--coral); }
.metric-card.warn::before    { background: var(--amber); }
.metric-card.teal::before    { background: var(--teal-bright); }
.metric-card.amber::before   { background: #F6B93B; }
.metric-card.indigo::before  { background: var(--indigo); }
.metric-card.hero { background: linear-gradient(135deg, #0F766E 0%, #14B8A6 100%); border: none; }
.metric-card.hero::before { display: none; }
.metric-card.hero .metric-label { color: rgba(255,255,255,0.8); }
.metric-card.hero .metric-value { color: #fff; font-size: 2rem; }
.metric-card.hero .metric-sub   { color: rgba(255,255,255,0.85); }
.metric-label { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; margin-bottom: 0.4rem; }
.metric-value { font-size: 1.7rem; font-weight: 800; color: var(--text-primary); letter-spacing: -0.02em; line-height: 1.15; }
.metric-card.good  .metric-value { color: var(--emerald); }
.metric-card.alert .metric-value { color: var(--coral); }
.metric-card.warn  .metric-value { color: var(--amber); }
.metric-card.teal  .metric-value { color: var(--teal); }
.metric-card.amber .metric-value { color: var(--amber); }
.metric-sub { font-size: 0.77rem; color: var(--text-secondary); margin-top: 0.45rem; display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
.metric-delta { font-size: 0.68rem; font-weight: 700; padding: 0.1rem 0.5rem; border-radius: 999px; border: 1px solid transparent; white-space: nowrap; }
.metric-delta.up   { color: var(--emerald); background: var(--emerald-soft); border-color: rgba(22,163,74,0.3); }
.metric-delta.down { color: var(--coral); background: var(--coral-soft); border-color: rgba(214,78,49,0.3); }
.metric-delta.flat { color: var(--text-muted); background: var(--bg-soft); border-color: var(--border-strong); }

/* ── Section headers ────────────────────────────────────────────────────── */
.section-header {
  font-size: 1rem; font-weight: 700; color: var(--text-primary); letter-spacing: -0.01em;
  padding: 0.4rem 0 0.6rem 0; margin: 1.6rem 0 0.8rem 0; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 0.55rem;
}
.section-header::before { content: ''; width: 4px; height: 1.05rem; background: linear-gradient(180deg, var(--teal-bright), var(--teal)); border-radius: 2px; }
.section-header .hint { margin-left: auto; font-size: 0.74rem; font-weight: 600; color: var(--text-muted); }
.chart-title { font-size: 0.86rem; font-weight: 700; color: var(--text-secondary); margin: 0.2rem 0 0; }

/* ── Split bar (100% stacked) ───────────────────────────────────────────── */
.split { margin: -0.1rem 0 0.9rem; }
.split .bar { display: flex; height: 12px; border-radius: 999px; overflow: hidden; background: var(--bg-soft); }
.split .seg { height: 100%; }
.split .legend { display: flex; flex-wrap: wrap; gap: 0.4rem 1.2rem; margin-top: 0.45rem; font-size: 0.76rem; color: var(--text-secondary); }
.split .legend .dot { display: inline-block; width: 9px; height: 9px; border-radius: 3px; margin-right: 0.4rem; vertical-align: -1px; }
.split .legend b { color: var(--text-primary); }

/* ── Recovery bar ───────────────────────────────────────────────────────── */
.recovery { background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.1rem 1.25rem; margin-bottom: 0.7rem; box-shadow: var(--shadow); min-height: 112px; }
.recovery .track { height: 10px; border-radius: 999px; background: var(--bg-soft); overflow: hidden; margin: 0.65rem 0 0.5rem; }
.recovery .fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--teal-bright), var(--emerald)); }
.recovery .row { display: flex; justify-content: space-between; font-size: 0.78rem; color: var(--text-secondary); gap: 1rem; }
.recovery .big { font-size: 1.2rem; font-weight: 800; color: var(--text-primary); letter-spacing: -0.02em; }

/* ── Zones: which sections follow the period filter ─────────────────────── */
.panel-tag {
  display: inline-block; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 0.28rem 0.75rem; border-radius: 999px; margin: 0.1rem 0 0.2rem;
}
.panel-tag.teal   { color: var(--teal);   background: var(--teal-soft);   border: 1px solid rgba(20,184,166,0.35); }
.panel-tag.slate  { color: #475569;       background: #EEF2F7;            border: 1px solid #CBD5E1; }
.panel-tag.indigo { color: var(--indigo); background: var(--indigo-soft); border: 1px solid rgba(99,102,241,0.35); }
div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-tag) { border-radius: var(--radius); padding: 0.8rem 1.1rem 0.4rem; background: var(--bg-surface); }
div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-tag.teal)   { border: 1.5px solid rgba(20,184,166,0.55) !important; background: linear-gradient(180deg, #FFFFFF 0%, #F7FCFB 100%); }
div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-tag.slate)  { border: 1.5px solid #D5DBE5 !important; background: #FBFCFD; }
div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-tag.indigo) { border: 1.5px dashed rgba(99,102,241,0.5) !important; background: linear-gradient(180deg, #FCFCFF 0%, #F5F5FC 100%); }
div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-tag) .section-header:first-of-type { margin-top: 0.8rem; }

/* ── HTML tables ────────────────────────────────────────────────────────── */
.tbl-wrap { overflow: auto; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-surface); box-shadow: var(--shadow); margin-bottom: 0.6rem; }
table.tbl { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.82rem; }
table.tbl th { position: sticky; top: 0; z-index: 1; background: var(--bg-soft); color: var(--text-secondary); text-transform: uppercase; font-size: 0.66rem; letter-spacing: 0.06em; font-weight: 700; padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
table.tbl td { padding: 0.5rem 0.8rem; border-bottom: 1px solid var(--border); color: var(--text-primary); white-space: nowrap; background: var(--bg-surface); }
table.tbl tr:last-child td { border-bottom: none; }
table.tbl td.num, table.tbl th.num { text-align: right; font-variant-numeric: tabular-nums; }
table.tbl td.lead { font-weight: 600; }
table.tbl td.empty { text-align: center; color: var(--text-muted); padding: 1.2rem; }
table.tbl tbody tr:hover td { filter: brightness(0.985); }
.pill-cell { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; font-size: 0.72rem; font-weight: 700; }

/* ── Streamlit widgets — hardened so the look does not depend on the Streamlit theme ── */
.stApp, .stApp p, .stApp label, .stApp li, .stApp span, .stMarkdown, [data-testid="stWidgetLabel"] p { color: var(--text-primary); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--text-muted) !important; }
.stApp a { color: var(--teal); }

/* segmented control (period) */
div[data-testid="stSegmentedControl"] div[data-baseweb="button-group"] { gap: 6px; }
div[data-testid="stSegmentedControl"] button {
  background: var(--bg-surface) !important; color: var(--text-secondary) !important;
  border: 1px solid var(--border-strong) !important; border-radius: 10px !important; font-weight: 600; box-shadow: none !important;
}
div[data-testid="stSegmentedControl"] button:hover { border-color: var(--teal-bright) !important; color: var(--teal) !important; }
div[data-testid="stSegmentedControl"] button[kind="segmented_controlActive"],
div[data-testid="stSegmentedControl"] button[aria-checked="true"], div[data-testid="stSegmentedControl"] button[aria-pressed="true"] {
  background: var(--teal) !important; color: #FFFFFF !important; border-color: var(--teal) !important;
}
div[data-testid="stSegmentedControl"] button p, div[data-testid="stSegmentedControl"] button span { color: inherit !important; }

/* inputs */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
  background: var(--bg-surface) !important; border-color: var(--border-strong) !important; color: var(--text-primary) !important; border-radius: 10px !important;
}
[data-baseweb="input"] input, [data-baseweb="select"] input, [data-baseweb="select"] div, textarea { color: var(--text-primary) !important; background: transparent !important; -webkit-text-fill-color: var(--text-primary) !important; }
[data-baseweb="select"] svg, [data-baseweb="input"] svg { fill: var(--text-secondary) !important; }
.stNumberInput button, .stNumberInput [data-testid="stNumberInputStepDown"], .stNumberInput [data-testid="stNumberInputStepUp"] {
  background: var(--bg-soft) !important; color: var(--text-primary) !important; border-left: 1px solid var(--border-strong) !important;
}
.stNumberInput button:hover { background: var(--teal-soft) !important; color: var(--teal) !important; }
.stNumberInput button svg { fill: currentColor !important; }
/* dropdown menus & calendars (rendered in a portal) */
div[data-baseweb="popover"], div[data-baseweb="popover"] > div, ul[data-baseweb="menu"], div[data-baseweb="menu"], div[data-baseweb="calendar"], [data-baseweb="datepicker"] {
  background: var(--bg-surface) !important; color: var(--text-primary) !important; border-radius: 12px !important; box-shadow: 0 12px 32px rgba(27,36,55,0.14) !important;
}
ul[data-baseweb="menu"] li, li[role="option"] { background: var(--bg-surface) !important; color: var(--text-primary) !important; }
ul[data-baseweb="menu"] li:hover, li[role="option"]:hover, li[aria-selected="true"] { background: var(--teal-soft) !important; color: var(--teal) !important; }
div[data-baseweb="calendar"] *, [data-baseweb="datepicker"] * { color: var(--text-primary); }
div[data-baseweb="calendar"] [aria-selected="true"] { background: var(--teal) !important; color: #fff !important; }
/* radio / toggle / checkbox / slider */
.stRadio [role="radiogroup"] label, .stCheckbox label, [data-testid="stToggle"] label { color: var(--text-primary) !important; }
.stRadio [role="radiogroup"] label > div:first-child { border-color: var(--border-strong) !important; background: var(--bg-surface) !important; }
.stSlider [data-baseweb="slider"] [role="slider"] { background: var(--teal) !important; border: 2px solid #fff !important; box-shadow: 0 2px 6px rgba(15,118,110,0.35) !important; }
.stSlider [data-testid="stSliderThumbValue"], .stSlider [data-testid="stTickBar"] div { color: var(--text-secondary) !important; }
.stSlider [data-baseweb="slider"] > div > div { background: var(--border-strong); }
.stSlider [data-baseweb="slider"] > div > div > div { background: var(--teal-bright); }
/* forms, alerts, expanders */
[data-testid="stForm"] { background: var(--bg-surface); border: 1px solid var(--border) !important; border-radius: var(--radius); padding: 1rem 1.2rem; box-shadow: var(--shadow); }
[data-testid="stAlert"], .stAlert > div { background: var(--bg-soft) !important; color: var(--text-primary) !important; border: 1px solid var(--border) !important; border-radius: 12px !important; }
[data-testid="stAlert"] p { color: var(--text-primary) !important; }
[data-testid="stToast"] { background: var(--text-primary) !important; color: #fff !important; }
[data-testid="stSpinner"] p { color: var(--text-secondary) !important; }
[data-testid="stTooltipIcon"] svg { fill: var(--text-muted); }
div[data-testid="stDecoration"] { display: none; }

.stTabs [data-baseweb="tab-list"] { gap: 6px; background: var(--bg-surface); border: 1px solid var(--border); border-radius: 12px; padding: 5px; box-shadow: var(--shadow); }
.stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 0.5rem 1.3rem; background: transparent; color: var(--text-muted); font-weight: 600; font-size: 0.875rem; border: none; }
.stTabs [aria-selected="true"] { background: var(--teal-soft) !important; color: var(--teal) !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }

div[data-testid="stSegmentedControl"] button { border-radius: 8px !important; font-weight: 600; }
.period-caption { font-size: 0.78rem; color: var(--text-muted); margin-top: 0.4rem; }

.stNumberInput input, .stTextInput input, .stSelectbox > div, .stDateInput input, .stTextArea textarea {
  background: var(--bg-surface) !important; border-color: var(--border-strong) !important; color: var(--text-primary) !important; border-radius: 10px !important;
}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button { border-radius: 10px; font-weight: 600; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] { background: linear-gradient(135deg, #14B8A6 0%, #0F766E 100%); border: none; color: #fff; box-shadow: 0 4px 14px rgba(15,118,110,0.25); }
.stButton > button[kind="secondary"], .stDownloadButton > button { background: var(--bg-surface); border: 1px solid var(--border-strong); color: var(--text-secondary); }
.stDataFrame { border-radius: var(--radius); overflow: hidden; border: 1px solid var(--border); box-shadow: var(--shadow); }
.stAlert { border-radius: 12px; }
hr { border-color: var(--border) !important; margin: 1rem 0 !important; }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
div[data-testid="stHtml"]:has(style) { display: none; height: 0; margin: 0; padding: 0; }
"""


def inject_app_styles() -> None:
    st.html(f"<style>{APP_CSS}</style>")


def render_app_header(cat: Catalog, backend_label: str, demo: bool) -> None:
    b = cat.business
    badges = [f'<span class="app-badge muted">{html.escape(backend_label)}</span>']
    badges.append('<span class="app-badge demo">Demo mode</span>' if demo else '<span class="app-badge">Live</span>')
    st.html(f"""
<div class="app-header">
  <div class="app-logo">{html.escape(b.logo_emoji)}</div>
  <div>
    <h1 class="app-title">{html.escape(b.app_name)}</h1>
    <p class="app-subtitle">{html.escape(b.name)} · {html.escape(b.tagline)}</p>
  </div>
  <div class="app-badges">{''.join(badges)}</div>
</div>""")
