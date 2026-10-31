"""
app.py — Franchise operations dashboard (Streamlit entry point).

Layers:
    config/   settings & default business catalog
    core/     pure business logic (pandas) — reusable from Django / scripts / tests
    data/     storage backends behind one Repository interface (Google Sheets · SQL · local workbook)
    ui/       Streamlit tabs & components

Run:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from ui import dashboard, entry, state
from ui.styles import inject_app_styles, render_app_header

settings = state.get_settings()

st.set_page_config(page_title="IcyPops Pal", page_icon="🍦", layout="wide", initial_sidebar_state="collapsed")
inject_app_styles()

try:
    bundle = state.get_bundle()
except Exception as e:  # connection-level failure (bad credentials, sheet not shared, DB down)
    st.error(f"⚠️ Could not connect to the data backend ({settings.backend_label}). {e}")
    st.info("Check `.streamlit/secrets.toml`, or remove it to run in demo mode on the sample workbook.")
    if st.button("Retry"):
        state.reconnect()
        st.rerun()
    st.stop()

render_app_header(bundle.catalog, settings.backend_label, settings.demo_mode)
for note in bundle.warnings:
    st.caption(f"ℹ️ {note}")

tab_dash, tab_entry = st.tabs(["Dashboard", "Data Entry"])
with tab_dash:
    dashboard.render(bundle)
with tab_entry:
    entry.render(bundle)
