"""
data/__init__.py — Backend factory and the single "load everything" entry point.

    repo   = build_repository(settings)
    bundle = load_bundle(repo, settings)      # → DataBundle(catalog, frames, warnings)

The UI only ever imports from here. Streamlit caching lives in ui/state.py so
this module stays importable from scripts and tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config.settings import Settings
from core import schema as S
from core.catalog import Catalog, catalog_from_frames, catalog_from_json
from data.base import Repository, normalize


def build_repository(settings: Settings) -> Repository:
    if settings.data_backend == "gsheets":
        from data.gsheets_repo import GoogleSheetsRepository
        return GoogleSheetsRepository(settings.spreadsheet_id, settings.gcp_service_account)  # type: ignore[arg-type]
    if settings.data_backend == "sql":
        from data.sql_repo import SqlRepository
        return SqlRepository(settings.database_url)
    from data.local_repo import LocalWorkbookRepository
    return LocalWorkbookRepository(settings.local_workbook)


@dataclass
class DataBundle:
    catalog: Catalog
    frames: dict[str, pd.DataFrame]
    warnings: list[str] = field(default_factory=list)
    backend: str = ""

    def __getitem__(self, table: str) -> pd.DataFrame:
        return self.frames[table]


def load_catalog(repo: Repository, settings: Settings) -> Catalog:
    fallback = catalog_from_json(settings.business_file)
    present = set(repo.tables())

    def _cfg(table: str) -> pd.DataFrame | None:
        if table not in present:
            return None
        try:
            raw = repo.read(table)
            return normalize(table, raw, fallback) if not raw.empty else None
        except Exception:
            return None

    return catalog_from_frames(_cfg(S.PRODUCTS), _cfg(S.PARTNERS), _cfg(S.SETTINGS), fallback)


def load_bundle(repo: Repository, settings: Settings) -> DataBundle:
    warnings: list[str] = list(settings.notes)
    cat = load_catalog(repo, settings)
    try:
        repo.ensure_tables(cat)
    except Exception as e:  # non-fatal: read-only credentials etc.
        warnings.append(f"Could not verify table headers: {e}")

    frames: dict[str, pd.DataFrame] = {}
    for table in S.TRANSACTION_TABLES:
        try:
            frames[table] = normalize(table, repo.read(table), cat)
        except Exception as e:
            warnings.append(f"Could not load '{table}': {e}")
            frames[table] = normalize(table, pd.DataFrame(), cat)

    for table in S.TRANSACTION_TABLES:
        n_undated = int(frames[table][S.DATE].isna().sum()) if S.DATE in frames[table].columns else 0
        if n_undated:
            warnings.append(f"'{table}': {n_undated} row(s) have an unreadable date — counted in totals, hidden from charts.")

    # Products present in data but missing from the catalog → surface, don't crash
    known = set(cat.all_product_names)
    for table in (S.BOUGHT, S.FRIDGE):
        extra = [c for c in frames[table].columns if c not in known and c not in (S.DATE, S.MODE)]
        if extra:
            warnings.append(f"'{table}' has columns not in the product catalog (ignored): {', '.join(map(str, extra))}")

    return DataBundle(catalog=cat, frames=frames, warnings=warnings, backend=repo.describe())
