"""
config/settings.py — Runtime settings.

Resolution order for every setting:  Streamlit secrets  →  environment variable  →  default.

Supported backends (``data_backend`` / ``DATA_BACKEND``):
    gsheets  — live Google Sheet (needs ``spreadsheet_id`` + ``gcp_service_account`` secrets)
    sql      — any SQLAlchemy URL in ``database_url`` (sqlite:///…, postgresql://…)
    local    — an .xlsx workbook with the same tab structure (demo / offline / tests)

If nothing is configured the app silently runs in **demo mode** against
``sample_data/IcyPops.xlsx`` so a walkthrough never depends on credentials.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUSINESS_FILE = PROJECT_ROOT / "config" / "business.json"
DEFAULT_LOCAL_WORKBOOK = PROJECT_ROOT / "sample_data" / "IcyPops.xlsx"
DEFAULT_SQLITE_URL = f"sqlite:///{PROJECT_ROOT / 'data' / 'icypops.db'}"


def _streamlit_secrets() -> Mapping[str, Any]:
    """Return st.secrets as a plain mapping, or {} when unavailable (tests, scripts)."""
    try:
        import streamlit as st  # imported lazily so scripts can use settings without Streamlit
        return st.secrets  # type: ignore[return-value]
    except Exception:
        return {}


def _get(key: str, default: Any = None) -> Any:
    secrets = _streamlit_secrets()
    try:
        if key in secrets:
            return secrets[key]
    except Exception:
        pass
    return os.environ.get(key.upper(), default)


@dataclass(frozen=True)
class Settings:
    data_backend: str = "local"
    spreadsheet_id: str | None = None
    gcp_service_account: Mapping[str, Any] | None = None
    database_url: str = DEFAULT_SQLITE_URL
    local_workbook: Path = DEFAULT_LOCAL_WORKBOOK
    business_file: Path = DEFAULT_BUSINESS_FILE
    cache_ttl_seconds: int = 30
    demo_mode: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def backend_label(self) -> str:
        return {"gsheets": "Google Sheets", "sql": "Database", "local": "Local workbook"}.get(
            self.data_backend, self.data_backend
        )


def load_settings() -> Settings:
    backend = str(_get("data_backend", "") or "").strip().lower()
    notes: list[str] = []

    spreadsheet_id = _get("spreadsheet_id")
    sa = _get("gcp_service_account")
    database_url = str(_get("database_url", DEFAULT_SQLITE_URL))
    local_workbook = Path(str(_get("local_workbook", DEFAULT_LOCAL_WORKBOOK)))
    business_file = Path(str(_get("business_file", DEFAULT_BUSINESS_FILE)))
    ttl = int(_get("cache_ttl_seconds", 30) or 30)

    # Infer a backend when none is declared explicitly.
    if not backend:
        if spreadsheet_id and sa:
            backend = "gsheets"
        elif _get("database_url"):
            backend = "sql"
        else:
            backend = "local"
            notes.append("No data backend configured — running in demo mode on the sample workbook.")

    demo = backend == "local" and local_workbook == DEFAULT_LOCAL_WORKBOOK

    if backend == "gsheets" and not (spreadsheet_id and sa):
        notes.append("Backend is 'gsheets' but spreadsheet_id / gcp_service_account are missing — falling back to demo mode.")
        backend, demo = "local", True

    return Settings(
        data_backend=backend,
        spreadsheet_id=spreadsheet_id,
        gcp_service_account=sa,
        database_url=database_url,
        local_workbook=local_workbook,
        business_file=business_file,
        cache_ttl_seconds=ttl,
        demo_mode=demo,
        notes=notes,
    )
