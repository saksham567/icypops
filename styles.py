"""Dashboard CSS — injected via st.html (not st.markdown) for Streamlit Cloud compatibility."""

import streamlit as st

APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

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

/* Hide the zero-height style injector container */
div[data-testid="stHtml"]:has(style) { display: none; height: 0; margin: 0; padding: 0; }
"""

APP_HEADER_HTML = """
<div class="app-header">
  <div class="app-logo">🍦</div>
  <div>
    <h1 class="app-title">IcyPops</h1>
    <p class="app-subtitle">Inventory & Business Intelligence</p>
  </div>
  <span class="app-badge">Live Dashboard</span>
</div>
"""


def inject_app_styles() -> None:
    """Inject CSS into the page. Must use st.html — st.markdown strips <style> on Cloud."""
    st.html(f"<style>{APP_CSS}</style>")


def render_app_header() -> None:
    st.html(APP_HEADER_HTML)