"""Run with:  pytest -q"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from config.settings import PROJECT_ROOT, Settings
from core import schema as S
from core.catalog import catalog_from_frames, catalog_from_json
from core.entries import build_dividend, build_expense, build_quantities
from core.finance import daily_actual_vs_expected, monthly_expense_pivot, summarize, total_expense
from core.inventory import compute_inventory, compute_sold_trend, settled_dates, unsettled_dates
from data import build_repository, load_bundle
from data.base import normalize

SAMPLE = PROJECT_ROOT / "sample_data" / "IcyPops.xlsx"


@pytest.fixture(scope="module")
def cat():
    return catalog_from_json(PROJECT_ROOT / "config" / "business.json")


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    wb = tmp_path_factory.mktemp("wb") / "sample.xlsx"
    wb.write_bytes(SAMPLE.read_bytes())
    s = Settings(data_backend="local", local_workbook=wb)
    return load_bundle(build_repository(s), s)


def test_inventory_identities(bundle):
    inv = compute_inventory(bundle[S.BOUGHT], bundle[S.FRIDGE], bundle.catalog)
    assert len(inv) == 23
    assert ((inv["Stock Outside Fridge"] + inv["Stock Inside Fridge"] - inv["Stock Left"]).abs() < 1e-9).all()
    assert (inv["Sold"] >= 0).all()
    assert inv["Total Bought"].sum() == pd.to_numeric(bundle[S.BOUGHT][bundle.catalog.product_names].stack()).sum()


def test_settlement_rules(cat):
    f = pd.DataFrame([
        {S.DATE: "2026-01-01", S.MODE: S.MODE_TO_VENDOR, "Kala Khatta - 80 ml": 10},
        {S.DATE: "2026-01-01", S.MODE: S.MODE_FROM_VENDOR, "Kala Khatta - 80 ml": 4},
        {S.DATE: "2026-01-02", S.MODE: S.MODE_TO_VENDOR, "Kala Khatta - 80 ml": 20},   # open day
    ])
    f = normalize(S.FRIDGE, f, cat)
    b = normalize(S.BOUGHT, pd.DataFrame([{S.DATE: "2025-12-31", "Kala Khatta - 80 ml": 100}]), cat)
    assert settled_dates(f) == {pd.Timestamp("2026-01-01")}
    assert unsettled_dates(f) == [pd.Timestamp("2026-01-02")]
    inv = compute_inventory(b, f, cat)
    assert inv.loc["Kala Khatta - 80 ml", "Sold"] == 6           # open day excluded
    assert inv.loc["Kala Khatta - 80 ml", "Stock Left"] == 94
    trend = compute_sold_trend(f, cat)
    assert list(trend["Total Sold"]) == [6]


def test_all_zero_return_row_settles_day(cat):
    f = normalize(S.FRIDGE, pd.DataFrame([
        {S.DATE: "2026-01-01", S.MODE: S.MODE_TO_VENDOR, "FAMILY PACK": 2},
        {S.DATE: "2026-01-01", S.MODE: S.MODE_FROM_VENDOR, "FAMILY PACK": 0},
    ]), cat)
    assert settled_dates(f) == {pd.Timestamp("2026-01-01")}


def test_header_tolerance_dividend(cat):
    raw = pd.DataFrame({"DATE": ["2026-10-02"], "TOTAL_DIVIDEND": [30000],
                        "SAKSHAM_DIVIDENT": [10500], "DHAIRYA_DIVIDEND": [19500]})
    df = normalize(S.DIVIDEND, raw, cat)
    assert list(df.columns[:2]) == [S.DATE, S.DIV_TOTAL]
    assert df["SAKSHAM_DIVIDEND"].iloc[0] == 10500 and df["DHAIRYA_DIVIDEND"].iloc[0] == 19500


def test_excel_serial_dates(cat):
    df = normalize(S.REVENUE, pd.DataFrame({"Date": [46176.0], "Revenue": [3020]}), cat)
    assert df[S.DATE].iloc[0] == pd.Timestamp("2026-06-03")


def test_finance_summary(bundle):
    inv = compute_inventory(bundle[S.BOUGHT], bundle[S.FRIDGE], bundle.catalog)
    f = summarize(bundle.frames, inv, bundle.catalog)
    assert f.total_revenue == 451423
    assert f.total_expense == 621120
    assert f.net_pnl == f.total_revenue - f.total_expense
    assert f.profit_after_dividend == f.realized_profit - 30000
    assert f.dividends["Saksham"] == 10500
    pivot = monthly_expense_pivot(bundle[S.EXPENSE])
    assert pivot["Total"].sum() == total_expense(bundle[S.EXPENSE])
    avx = daily_actual_vs_expected(bundle[S.REVENUE], bundle[S.FRIDGE], bundle.catalog)
    assert {"Actual", "Expected", "Gap"} <= set(avx.columns)


def test_catalog_overlay_from_tables(cat):
    products = pd.DataFrame([{"Name": "Cone", "Category": "cone", "SellPrice": 30, "UnitMargin": 10,
                              "ReorderThreshold": 5, "FridgeThreshold": 1, "FridgeTracked": 1, "Active": 1, "SortOrder": 0}])
    partners = pd.DataFrame([{"Name": "A", "SharePct": 70}, {"Name": "B", "SharePct": 30}])
    settings = pd.DataFrame([{"Key": "business_name", "Value": "Frosty"}, {"Key": "currency_symbol", "Value": "$"},
                             {"Key": "category.cone.label", "Value": "Cones"}])
    c = catalog_from_frames(products, partners, settings, cat)
    assert c.business.name == "Frosty" and c.currency == "$"
    assert [x.label for x in c.categories] == ["Cones"]          # fallback categories must not leak
    assert c.product_names == ["Cone"] and c.price("Cone") == 30
    assert c.split_dividend(1000) == {"A": 700, "B": 300}


def test_indian_number_format(cat):
    assert cat.fmt(1234567) == "₹12,34,567"
    assert cat.fmt(-999) == "-₹999"


def test_entry_validation(cat):
    rec, errs = build_expense(date(2026, 1, 1), "", "x", 0, S.PAY_BANK, True)
    assert "Type is required." in errs and any("greater than 0" in e for e in errs)
    rec, errs = build_expense(date(2026, 1, 1), "Salary", "x", 100, S.PAY_OWN, True, "Saksham")
    assert not errs and rec[S.PAY_OWN] == 1 and rec[S.PAY_BANK] == 0 and rec[S.EXP_PAID_BY] == "Saksham"
    rec, errs = build_quantities(date(2026, 1, 1), {}, cat, mode=S.MODE_TO_VENDOR)
    assert errs
    rec, errs = build_dividend(date(2026, 1, 1), {"Saksham": 350, "Dhairya": 650}, cat)
    assert not errs and rec[S.DIV_TOTAL] == 1000 and rec["SAKSHAM_DIVIDEND"] == 350


def test_sql_roundtrip(tmp_path, bundle):
    from data.sql_repo import SqlRepository
    repo = SqlRepository(f"sqlite:///{tmp_path / 't.db'}")
    cat = bundle.catalog
    repo.append(S.FRIDGE, {S.DATE: "2026-01-01", S.MODE: S.MODE_TO_VENDOR, "FAMILY PACK": 3}, cat)
    repo.append(S.FRIDGE, {S.DATE: "2026-01-01", S.MODE: S.MODE_FROM_VENDOR}, cat)   # all-zero return
    repo.append(S.EXPENSE, {S.DATE: "2026-01-01", S.EXP_TYPE: "Rent", S.EXP_AMOUNT: 500, S.PAY_CASH: 1, S.EXP_OPERATIONAL: 1}, cat)
    repo.append(S.DIVIDEND, {S.DATE: "2026-01-02", S.DIV_TOTAL: 100, "SAKSHAM_DIVIDEND": 35, "DHAIRYA_DIVIDEND": 65}, cat)
    fridge = normalize(S.FRIDGE, repo.read(S.FRIDGE), cat)
    assert settled_dates(fridge) == {pd.Timestamp("2026-01-01")}
    exp = normalize(S.EXPENSE, repo.read(S.EXPENSE), cat)
    assert exp[S.PAY_CASH].iloc[0] == 1 and exp[S.PAY_BANK].iloc[0] == 0
    div = normalize(S.DIVIDEND, repo.read(S.DIVIDEND), cat)
    assert div[S.DIV_TOTAL].iloc[0] == 100 and div["DHAIRYA_DIVIDEND"].iloc[0] == 65
