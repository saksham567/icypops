"""
data/sql_repo.py — SQLAlchemy backend (SQLite locally, PostgreSQL in production).

Schema is deliberately *normalized* (one row per product per movement) because
that is what the Django models in docs/ROADMAP_STEP2.md will look like. The
repository pivots to the wide canonical frames on read, and melts on write, so
nothing above this layer notices.

Tables
  products, partners, settings            — configuration
  expenses(date, type, description, amount, paid_via, is_operational, paid_by, comments)
  purchases(date, product, qty)
  stock_movements(date, mode, product, qty)
  revenue(date, amount, comments)
  payouts(date, partner, amount)
"""
from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa

from core import schema as S
from core.catalog import Catalog
from data.base import Repository

PAID_VIA = {S.PAY_BANK: "bank", S.PAY_CASH: "cash", S.PAY_OWN: "own"}
PAID_VIA_INV = {v: k for k, v in PAID_VIA.items()}

TABLE_MAP = {  # canonical table → physical table
    S.EXPENSE: "expenses", S.BOUGHT: "purchases", S.FRIDGE: "stock_movements",
    S.REVENUE: "revenue", S.DIVIDEND: "payouts",
    S.PRODUCTS: "products", S.PARTNERS: "partners", S.SETTINGS: "settings",
}


class SqlRepository(Repository):
    name = "sql"

    def __init__(self, database_url: str):
        self.url = database_url
        if database_url.startswith("sqlite:///"):
            Path(database_url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
        self.engine = sa.create_engine(database_url, future=True)
        self.meta = sa.MetaData()
        self._define()
        self.meta.create_all(self.engine)

    # ── schema ─────────────────────────────────────────────────────────────
    def _define(self) -> None:
        m = self.meta
        self.t_products = sa.Table("products", m,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(120), unique=True, nullable=False),
            sa.Column("category", sa.String(60), nullable=False),
            sa.Column("sell_price", sa.Float), sa.Column("unit_margin", sa.Float),
            sa.Column("reorder_threshold", sa.Float), sa.Column("fridge_threshold", sa.Float),
            sa.Column("fridge_tracked", sa.Boolean, default=True),
            sa.Column("active", sa.Boolean, default=True), sa.Column("sort_order", sa.Integer, default=0))
        self.t_partners = sa.Table("partners", m,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(80), unique=True, nullable=False),
            sa.Column("share_pct", sa.Float, default=0))
        self.t_settings = sa.Table("settings", m,
            sa.Column("key", sa.String(80), primary_key=True), sa.Column("value", sa.Text))
        self.t_expenses = sa.Table("expenses", m,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("date", sa.Date, nullable=False, index=True),
            sa.Column("type", sa.String(80)), sa.Column("description", sa.Text),
            sa.Column("amount", sa.Float, nullable=False),
            sa.Column("paid_via", sa.String(10)), sa.Column("is_operational", sa.Boolean, default=False),
            sa.Column("paid_by", sa.String(80)), sa.Column("comments", sa.Text),
            sa.Column("created_at", sa.DateTime, default=datetime.utcnow))
        self.t_purchases = sa.Table("purchases", m,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("date", sa.Date, nullable=False, index=True),
            sa.Column("product", sa.String(120), nullable=False), sa.Column("qty", sa.Float, nullable=False),
            sa.Column("batch_id", sa.String(40)), sa.Column("created_at", sa.DateTime, default=datetime.utcnow))
        self.t_moves = sa.Table("stock_movements", m,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("date", sa.Date, nullable=False, index=True),
            sa.Column("mode", sa.String(20), nullable=False),
            sa.Column("product", sa.String(120), nullable=False), sa.Column("qty", sa.Float, nullable=False),
            sa.Column("batch_id", sa.String(40)), sa.Column("created_at", sa.DateTime, default=datetime.utcnow))
        self.t_revenue = sa.Table("revenue", m,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("date", sa.Date, nullable=False, index=True),
            sa.Column("amount", sa.Float, nullable=False), sa.Column("comments", sa.Text),
            sa.Column("created_at", sa.DateTime, default=datetime.utcnow))
        self.t_payouts = sa.Table("payouts", m,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("date", sa.Date, nullable=False, index=True),
            sa.Column("partner", sa.String(80), nullable=False), sa.Column("amount", sa.Float, nullable=False),
            sa.Column("batch_id", sa.String(40)), sa.Column("created_at", sa.DateTime, default=datetime.utcnow))

    # ── reads ──────────────────────────────────────────────────────────────
    def tables(self) -> list[str]:
        existing = set(sa.inspect(self.engine).get_table_names())
        return [canon for canon, phys in TABLE_MAP.items() if phys in existing]

    def _df(self, table: sa.Table) -> pd.DataFrame:
        with self.engine.connect() as con:
            return pd.read_sql(sa.select(table), con)

    def read(self, table: str) -> pd.DataFrame:
        if table == S.EXPENSE:
            df = self._df(self.t_expenses)
            if df.empty:
                return pd.DataFrame()
            out = pd.DataFrame({
                S.DATE: df["date"], S.EXP_TYPE: df["type"], S.EXP_DESC: df["description"],
                S.EXP_AMOUNT: df["amount"], S.EXP_OPERATIONAL: df["is_operational"].astype(int),
                S.EXP_PAID_BY: df["paid_by"].fillna(""), S.COMMENTS: df["comments"].fillna(""),
            })
            for flag, code in PAID_VIA.items():
                out[flag] = (df["paid_via"] == code).astype(int)
            return out[S.EXPENSE_REQUIRED + S.EXPENSE_OPTIONAL]
        if table == S.BOUGHT:
            df = self._df(self.t_purchases)
            if df.empty:
                return pd.DataFrame()
            wide = df.pivot_table(index=["date", "batch_id"], columns="product", values="qty",
                                  aggfunc="sum", fill_value=0).reset_index().drop(columns="batch_id")
            return wide.rename(columns={"date": S.DATE})
        if table == S.FRIDGE:
            df = self._df(self.t_moves)
            if df.empty:
                return pd.DataFrame()
            wide = df.pivot_table(index=["date", "mode", "batch_id"], columns="product", values="qty",
                                  aggfunc="sum", fill_value=0).reset_index().drop(columns="batch_id")
            return wide.rename(columns={"date": S.DATE, "mode": S.MODE})
        if table == S.REVENUE:
            df = self._df(self.t_revenue)
            if df.empty:
                return pd.DataFrame()
            return pd.DataFrame({S.DATE: df["date"], S.REV_AMOUNT: df["amount"], S.COMMENTS: df["comments"].fillna("")})
        if table == S.DIVIDEND:
            df = self._df(self.t_payouts)
            if df.empty:
                return pd.DataFrame()
            wide = df.pivot_table(index=["date", "batch_id"], columns="partner", values="amount",
                                  aggfunc="sum", fill_value=0).reset_index().drop(columns="batch_id")
            partners = [c for c in wide.columns if c != "date"]
            wide[S.DIV_TOTAL] = wide[partners].sum(axis=1)
            wide = wide.rename(columns={"date": S.DATE, **{p: f"{p.upper()}_DIVIDEND" for p in partners}})
            return wide
        if table == S.PRODUCTS:
            df = self._df(self.t_products)
            return df.rename(columns={"name": "Name", "category": "Category", "sell_price": "SellPrice",
                                      "unit_margin": "UnitMargin", "reorder_threshold": "ReorderThreshold",
                                      "fridge_threshold": "FridgeThreshold", "fridge_tracked": "FridgeTracked",
                                      "active": "Active", "sort_order": "SortOrder"}).drop(columns="id", errors="ignore")
        if table == S.PARTNERS:
            return self._df(self.t_partners).rename(columns={"name": "Name", "share_pct": "SharePct"}).drop(columns="id", errors="ignore")
        if table == S.SETTINGS:
            return self._df(self.t_settings).rename(columns={"key": "Key", "value": "Value"})
        return pd.DataFrame()

    # ── writes ─────────────────────────────────────────────────────────────
    @staticmethod
    def _d(v) -> date:
        return pd.Timestamp(v).date()

    def append(self, table: str, record: dict[str, Any], cat: Catalog) -> None:
        batch = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        with self.engine.begin() as con:
            if table == S.EXPENSE:
                via = next((PAID_VIA[c] for c in S.PAYMENT_COLS if int(record.get(c, 0) or 0) == 1), None)
                con.execute(self.t_expenses.insert().values(
                    date=self._d(record[S.DATE]), type=record.get(S.EXP_TYPE, ""),
                    description=record.get(S.EXP_DESC, ""), amount=float(record[S.EXP_AMOUNT]),
                    paid_via=via, is_operational=bool(int(record.get(S.EXP_OPERATIONAL, 0) or 0)),
                    paid_by=record.get(S.EXP_PAID_BY) or None, comments=record.get(S.COMMENTS) or None))
            elif table in (S.BOUGHT, S.FRIDGE):
                t = self.t_purchases if table == S.BOUGHT else self.t_moves
                rows = []
                for p in cat.all_product_names:
                    q = float(record.get(p, 0) or 0)
                    if q:
                        r = {"date": self._d(record[S.DATE]), "product": p, "qty": q, "batch_id": batch}
                        if table == S.FRIDGE:
                            r["mode"] = record[S.MODE]
                        rows.append(r)
                if not rows:  # keep an explicit zero row so the day shows up as recorded
                    r = {"date": self._d(record[S.DATE]), "product": cat.all_product_names[0], "qty": 0, "batch_id": batch}
                    if table == S.FRIDGE:
                        r["mode"] = record[S.MODE]
                    rows.append(r)
                con.execute(t.insert(), rows)
            elif table == S.REVENUE:
                con.execute(self.t_revenue.insert().values(
                    date=self._d(record[S.DATE]), amount=float(record[S.REV_AMOUNT]),
                    comments=record.get(S.COMMENTS) or None))
            elif table == S.DIVIDEND:
                rows = [{"date": self._d(record[S.DATE]), "partner": p.name,
                         "amount": float(record.get(p.column, 0) or 0), "batch_id": batch}
                        for p in cat.partners if float(record.get(p.column, 0) or 0)]
                if rows:
                    con.execute(self.t_payouts.insert(), rows)
            else:
                raise ValueError(f"append not supported for {table}")

    def write_table(self, table: str, df: pd.DataFrame) -> None:
        """Replace a config table from a canonical frame (used by setup/migration)."""
        t = {S.PRODUCTS: self.t_products, S.PARTNERS: self.t_partners, S.SETTINGS: self.t_settings}[table]
        colmap = {
            S.PRODUCTS: {"Name": "name", "Category": "category", "SellPrice": "sell_price", "UnitMargin": "unit_margin",
                         "ReorderThreshold": "reorder_threshold", "FridgeThreshold": "fridge_threshold",
                         "FridgeTracked": "fridge_tracked", "Active": "active", "SortOrder": "sort_order"},
            S.PARTNERS: {"Name": "name", "SharePct": "share_pct"},
            S.SETTINGS: {"Key": "key", "Value": "value"},
        }[table]
        rows = df.rename(columns=colmap)[list(colmap.values())].to_dict("records")
        for r in rows:
            for k in ("fridge_tracked", "active"):
                if k in r:
                    r[k] = bool(int(float(r[k]))) if str(r[k]).strip() != "" else True
            if "value" in r:
                r["value"] = str(r["value"])
        with self.engine.begin() as con:
            con.execute(t.delete())
            if rows:
                con.execute(t.insert(), rows)

    def snapshot(self) -> dict | None:
        if self.url.startswith("sqlite:///"):
            src = Path(self.url.replace("sqlite:///", "", 1))
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            dest = src.with_name(f"{src.stem}_snapshot_{stamp}{src.suffix}")
            shutil.copy2(src, dest)
            return {"name": dest.name, "path": str(dest)}
        return None  # use pg_dump / managed backups for Postgres

    def describe(self) -> str:
        return f"Database · {self.engine.url.get_backend_name()}"
