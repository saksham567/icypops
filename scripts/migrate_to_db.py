#!/usr/bin/env python
"""
scripts/migrate_to_db.py — Copy every table from the current backend into a SQL database.

Examples
    # Google Sheet (uses .streamlit/secrets.toml) → local SQLite
    python scripts/migrate_to_db.py --to sqlite:///data/icypops.db

    # Local workbook → Postgres (Neon / Supabase / Railway…)
    python scripts/migrate_to_db.py --from-xlsx sample_data/IcyPops.xlsx --to postgresql+psycopg://user:pass@host/db

The destination tables are emptied first (idempotent). The catalog (Products /
Partners / Settings) is written too, from the source tables or business.json.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import sqlalchemy as sa  # noqa: E402

from config.settings import load_settings  # noqa: E402
from core import schema as S  # noqa: E402
from core.catalog import catalog_to_frames  # noqa: E402
from data import build_repository, load_bundle  # noqa: E402
from data.local_repo import LocalWorkbookRepository  # noqa: E402
from data.sql_repo import PAID_VIA, SqlRepository  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", required=True, help="SQLAlchemy URL of the destination database")
    ap.add_argument("--from-xlsx", help="Read from this workbook instead of the configured backend")
    args = ap.parse_args()

    settings = load_settings()
    src = LocalWorkbookRepository(Path(args.from_xlsx)) if args.from_xlsx else build_repository(settings)
    bundle = load_bundle(src, settings)
    cat = bundle.catalog
    print(f"Source: {src.describe()}  ·  catalog from {cat.source}")

    dst = SqlRepository(args.to)
    for table, df in catalog_to_frames(cat).items():
        dst.write_table(table, df)
    print(f"Catalog: {len(cat.products)} products, {len(cat.partners)} partners")

    exp = bundle[S.EXPENSE]
    via = pd.Series([None] * len(exp), index=exp.index, dtype=object)
    for flag, code in PAID_VIA.items():
        via[pd.to_numeric(exp[flag], errors="coerce").fillna(0) > 0] = code
    expenses = pd.DataFrame({
        "date": exp[S.DATE].dt.date, "type": exp[S.EXP_TYPE], "description": exp[S.EXP_DESC],
        "amount": exp[S.EXP_AMOUNT].astype(float), "paid_via": via,
        "is_operational": pd.to_numeric(exp[S.EXP_OPERATIONAL], errors="coerce").fillna(0) > 0,
        "paid_by": exp[S.EXP_PAID_BY].replace("", None), "comments": exp[S.COMMENTS].replace("", None),
    })

    def long_rows(table: str) -> pd.DataFrame:
        df = bundle[table].copy()
        df["batch_id"] = [f"m{i:06d}" for i in range(len(df))]
        id_vars = [S.DATE, "batch_id"] + ([S.MODE] if table == S.FRIDGE else [])
        products = [p for p in cat.all_product_names if p in df.columns]
        long = df.melt(id_vars=id_vars, value_vars=products, var_name="product", value_name="qty")
        long["qty"] = pd.to_numeric(long["qty"], errors="coerce").fillna(0)
        nonzero = long[long["qty"] != 0]
        # An all-zero row (e.g. "from vendor" with nothing returned) still settles the day — keep one placeholder.
        missing = set(long["batch_id"]) - set(nonzero["batch_id"])
        placeholders = long[long["batch_id"].isin(missing)].drop_duplicates("batch_id")
        long = pd.concat([nonzero, placeholders]).sort_values("batch_id", kind="stable")
        out = pd.DataFrame({"date": long[S.DATE].dt.date, "product": long["product"], "qty": long["qty"].astype(float),
                            "batch_id": long["batch_id"]})
        if table == S.FRIDGE:
            out["mode"] = long[S.MODE].values
        return out

    purchases = long_rows(S.BOUGHT)
    moves = long_rows(S.FRIDGE)
    rev = bundle[S.REVENUE]
    revenue = pd.DataFrame({"date": rev[S.DATE].dt.date, "amount": rev[S.REV_AMOUNT].astype(float),
                            "comments": rev[S.COMMENTS].replace("", None)})
    div = bundle[S.DIVIDEND].copy()
    div["batch_id"] = [f"d{i:06d}" for i in range(len(div))]
    payouts = []
    for _, r in div.iterrows():
        for p in cat.partners:
            amt = float(r.get(p.column, 0) or 0)
            if amt:
                payouts.append({"date": r[S.DATE].date(), "partner": p.name, "amount": amt, "batch_id": r["batch_id"]})
    payouts = pd.DataFrame(payouts, columns=["date", "partner", "amount", "batch_id"])

    with dst.engine.begin() as con:
        for t in (dst.t_expenses, dst.t_purchases, dst.t_moves, dst.t_revenue, dst.t_payouts):
            con.execute(t.delete())
        for t, df in ((dst.t_expenses, expenses), (dst.t_purchases, purchases), (dst.t_moves, moves),
                      (dst.t_revenue, revenue), (dst.t_payouts, payouts)):
            if not df.empty:
                con.execute(t.insert(), df.astype(object).where(df.notna(), None).to_dict("records"))
            print(f"  {t.name:16s} {len(df):6d} rows")

    with dst.engine.connect() as con:
        n = con.execute(sa.text("select count(*) from stock_movements")).scalar()
    print(f"Done → {args.to}  (stock_movements={n})")


if __name__ == "__main__":
    main()
