# IcyPops Pal — Franchise Operations Dashboard

Inventory, revenue, expense and partner tracking for a franchise cart/kiosk business.
Built for IcyPops; configurable for any owner of the same franchise without code changes.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py            # no secrets → demo mode on sample_data/IcyPops.xlsx
pytest -q                       # 10 tests
```

To connect your Google Sheet: `cp .streamlit/secrets.toml.example .streamlit/secrets.toml` and fill it in.
Same service-account setup as before; the sheet needs no changes to work.
To unlock the config tabs (recommended — see `docs/SHEET_CHANGES.md`): `python scripts/setup_sheet.py`.

## Theme note

The look is self-contained: tables are rendered as styled HTML, charts ignore Streamlit's theme, and widgets are explicitly styled, so the app looks right even if a viewer has Streamlit's dark theme selected. Still commit `.streamlit/config.toml` (light base) and, on Streamlit Cloud, set **⋮ → Settings → Theme → Light** once so native pop-ups (date pickers, dropdown menus) match perfectly.

## Layout

| Folder | What lives there | Streamlit? |
|---|---|---|
| `config/` | `settings.py` (secrets → env → defaults), `business.json` (default catalog & onboarding template) | no |
| `core/` | `schema.py` column names · `catalog.py` products/partners/branding · `inventory.py` · `finance.py` · `entries.py` validation | **no** — reusable from Django, scripts, tests |
| `data/` | `Repository` interface and three backends: `gsheets_repo.py`, `sql_repo.py`, `local_repo.py` | no |
| `ui/` | `dashboard.py`, `entry.py`, `components.py`, `styles.py`, `state.py` (caching) | yes |
| `scripts/` | `setup_sheet.py` (config tabs), `migrate_to_db.py` (any backend → SQL) | no |
| `docs/` | `SHEET_CHANGES.md`, `ROADMAP_STEP2.md` | — |

Rule of thumb: **anything in `core/` is the product; `ui/` is just today's screen for it.**
When Step 2 happens, `core/` moves into the Django project unchanged.

## Choosing a backend

`data_backend` in secrets (or `DATA_BACKEND` env var):

| value | reads/writes | use for |
|---|---|---|
| `gsheets` | the live Google Sheet | today's production |
| `sql` | `database_url` (SQLite file or Postgres) | Step 2 bridge; `python scripts/migrate_to_db.py --to sqlite:///data/icypops.db` |
| `local` | an `.xlsx` with the same tabs | demos, offline, tests |

All three return identical frames to the UI (verified on the real data: ₹4,51,595 expected revenue, 16,987 units on every backend).

## Onboarding another franchise owner

1. `python scripts/setup_sheet.py --xlsx owner.xlsx --business owners/owner.json` (or run against their Google Sheet).
2. They edit three small tabs — **Products**, **Partners**, **Settings** — flavours, prices, margins, thresholds, partner shares, brand name, currency.
3. Point `secrets.toml` at their sheet. Every form, KPI and chart rebuilds from those tables.


## What changed from the original (functional behaviour preserved)

**Kept**: all formulas, the settled-day rule, every dashboard section and chart, the dark theme, the Google Sheet as-is.

**Generalised**: product list, categories (40 ml / 80 ml / Family Pack), unit prices and margins, thresholds, partner names and shares, brand, currency — all come from the catalog instead of code.

**Dashboard (v3, light theme)** — teal / coral / amber palette on a milk-white base. Global period control (All time · This month · This week) with change vs last month / last week. Sections: *Business at a glance* (revenue collected, expected, collection gap, avg revenue/day, units sold, realized profit) · *Investment recovery* with payback estimate · *Product performance* · *Stock & reorder* with days of cover · *Expenses* (total, operating vs one-time, who paid — each as cards + 100% split bar) · *Partners*. A visually separate **Analysis** panel has its own date controls: sales trend (days slider), revenue by weekday, expected revenue by category (daily from/to or monthly; grouped bars + gross-profit line). Actual collections are used wherever possible; per-product/category splits use expected revenue.

**Added**
- Partner capital table when the optional `PaidBy` column is used ("who paid from own money", vs their share).
- Sell-through % per product; gross-profit KPI; CSV export of inventory and expense grid.
- Demo mode without credentials; header-mapped writes (reordering sheet columns no longer corrupts rows); optional columns auto-created; expense-type picker; dividend auto-split by share.
- SQL backend + migration script; tests.

**Fixed**: crash in *Recent Entries* for Bought/Fridge (`sort_col` undefined); dashboard not refreshing after a save; Indian number grouping (₹12,34,567).
