#!/usr/bin/env python
"""
scripts/setup_sheet.py — Prepare a Google Sheet (or local workbook) as a backend.

  • creates the five data tabs with headers if missing
  • writes Products / Partners / Settings tabs from config/business.json
    (or from --business <file> for a new franchise owner)
  • never touches existing data rows

Usage
    python scripts/setup_sheet.py                       # uses secrets.toml (Google Sheet)
    python scripts/setup_sheet.py --xlsx new_owner.xlsx --business owners/ramesh.json
    python scripts/setup_sheet.py --force               # overwrite existing config tabs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import load_settings  # noqa: E402
from core import schema as S  # noqa: E402
from core.catalog import catalog_from_json, catalog_to_frames  # noqa: E402
from data import build_repository  # noqa: E402
from data.local_repo import LocalWorkbookRepository  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xlsx", help="Write to this workbook instead of the configured Google Sheet")
    ap.add_argument("--business", help="business.json to seed config tabs from (default: config/business.json)")
    ap.add_argument("--force", action="store_true", help="Overwrite config tabs even if they already exist")
    args = ap.parse_args()

    settings = load_settings()
    cat = catalog_from_json(Path(args.business) if args.business else settings.business_file)
    repo = LocalWorkbookRepository(Path(args.xlsx)) if args.xlsx else build_repository(settings)
    print(f"Target: {repo.describe()}")

    repo.ensure_tables(cat)
    print("Data tabs verified:", ", ".join(S.TRANSACTION_TABLES))

    existing = set(repo.tables())
    for table, df in catalog_to_frames(cat).items():
        if table in existing and not args.force:
            print(f"  {table}: exists — skipped (use --force to overwrite)")
            continue
        if hasattr(repo, "write_table"):
            repo.write_table(table, df)
        else:  # local workbook
            from openpyxl import load_workbook
            wb = load_workbook(repo.path)
            if table in wb.sheetnames:
                del wb[table]
            ws = wb.create_sheet(table)
            ws.append(list(df.columns))
            for row in df.itertuples(index=False):
                ws.append(list(row))
            wb.save(repo.path)
        print(f"  {table}: written ({len(df)} rows)")
    print("Done. Reload the app — the catalog will now come from the sheet.")


if __name__ == "__main__":
    main()
