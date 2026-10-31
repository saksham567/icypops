"""ui/state.py — Streamlit caching around settings, repository and data bundle."""
from __future__ import annotations

import streamlit as st

from config.settings import Settings, load_settings
from data import DataBundle, build_repository, load_bundle
from data.base import Repository


def get_settings() -> Settings:
    if "settings" not in st.session_state:
        st.session_state["settings"] = load_settings()
    return st.session_state["settings"]


def _cache_key(s: Settings) -> str:
    return f"{s.data_backend}|{s.spreadsheet_id}|{s.database_url}|{s.local_workbook}|{s.business_file}"


@st.cache_resource(show_spinner=False)
def _repo(key: str) -> Repository:  # key only drives cache identity
    return build_repository(get_settings())


def get_repo() -> Repository:
    return _repo(_cache_key(get_settings()))


@st.cache_data(ttl=30, show_spinner="Loading data…")
def _bundle(key: str) -> DataBundle:
    s = get_settings()
    return load_bundle(_repo(key), s)


def get_bundle() -> DataBundle:
    return _bundle(_cache_key(get_settings()))


def refresh() -> None:
    """Drop cached data (not the connection) so the next run re-reads the backend."""
    _bundle.clear()


def reconnect() -> None:
    _bundle.clear()
    _repo.clear()
    st.session_state.pop("settings", None)
