"""ui/entry.py — Data Entry tab: one form per table."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import schema as S
from core.catalog import Catalog
from core.entries import build_dividend, build_expense, build_quantities, build_revenue, expense_type_options
from data import DataBundle
from ui import state
from ui.components import fmt_date, html_table, section

OTHER = "Other (type below)"


def render(bundle: DataBundle) -> None:
    repo = state.get_repo()

    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
        st.toast("Saved ✓")

    choice = st.selectbox(
        "What do you want to record?",
        S.TRANSACTION_TABLES,
        format_func=lambda x: S.TABLE_LABELS[x],
    )
    st.markdown("")

    if choice == S.EXPENSE:
        _expense(bundle, repo)
    elif choice == S.BOUGHT:
        _quantities(bundle, repo, S.BOUGHT)
    elif choice == S.FRIDGE:
        _quantities(bundle, repo, S.FRIDGE)
    elif choice == S.REVENUE:
        _revenue(bundle, repo)
    elif choice == S.DIVIDEND:
        _dividend(bundle, repo)

    _recent(bundle, choice)


# ── helpers ──────────────────────────────────────────────────────────────────

def _submit(repo, cat: Catalog, writes: list[tuple[str, dict]], success_msg: str) -> None:
    try:
        for table, record in writes:
            repo.append(table, record, cat)
    except Exception as e:
        st.error(f"Could not save. {e}")
        return
    state.refresh()
    st.session_state["flash"] = success_msg
    st.rerun()  # re-render so the Dashboard reflects the new entry immediately


def _qty_grid(cat: Catalog, key_prefix: str, defaults: dict[str, int] | None = None,
              only_fridge_tracked: bool = False, note_untracked: bool = False) -> dict[str, int]:
    """Number inputs grouped by category, 3 per row. Returns {product: qty}."""
    out: dict[str, int] = {}
    defaults = defaults or {}
    for c in cat.categories_sorted():
        prods = cat.products_in(c.key)
        if not prods:
            continue
        label = f"**{c.label}**"
        if note_untracked and not c.fridge_tracked:
            label += " *(stock movement only — not kept in the fridge)*"
        st.markdown(label)
        cols = st.columns(3)
        for i, p in enumerate(prods):
            out[p] = cols[i % 3].number_input(p, min_value=0, step=1, value=int(defaults.get(p, 0)), key=f"{key_prefix}_{p}")
    return out


# ── forms ────────────────────────────────────────────────────────────────────

def _expense(bundle: DataBundle, repo) -> None:
    cat = bundle.catalog
    section("Add Expense")
    types = expense_type_options(cat, bundle[S.EXPENSE])
    with st.form("expense", clear_on_submit=True):
        entry_date = st.date_input("Date", value=date.today())
        c1, c2 = st.columns(2)
        pick = c1.selectbox("Type", types + [OTHER])
        custom = c1.text_input("New type", placeholder="only if 'Other' selected")
        desc = c2.text_input("Description", placeholder="Brief note")
        amount = c2.number_input(f"Amount ({cat.currency})", min_value=0.0, step=1.0)
        c3, c4 = st.columns(2)
        pay = c3.selectbox("Paid from", S.PAYMENT_COLS, format_func=lambda c: S.PAYMENT_LABELS[c])
        paid_by = c4.selectbox("Paid by (if own money)", ["—"] + cat.partner_names) if cat.partners else "—"
        is_op = st.checkbox("Operational cost (recurring cost of running the business — stock, salary, essentials)",
                            value=True, help="Leave unticked for one-time investments such as the cart or freezer.")
        comments = st.text_input("Comments (optional)")
        if st.form_submit_button("➕ Add Expense", type="primary"):
            exp_type = custom if pick == OTHER else pick
            pb = None if paid_by == "—" else paid_by
            rec, errors = build_expense(entry_date, exp_type, desc, amount, pay, is_op, pb, comments)
            if pay == S.PAY_OWN and cat.partners and pb is None:
                errors.append("Select which partner paid from their own money.")
            if errors:
                for e in errors:
                    st.error(e)
            else:
                _submit(repo, cat, [(S.EXPENSE, rec)], f"Expense of {cat.fmt(amount)} added for {fmt_date(entry_date)}.")


def _quantities(bundle: DataBundle, repo, table: str) -> None:
    cat = bundle.catalog
    is_fridge = table == S.FRIDGE
    section("Add Purchase Record" if not is_fridge else "Add Fridge Movement")
    with st.form(f"form_{table}", clear_on_submit=True):
        entry_date = st.date_input("Date", value=date.today())
        mode = None
        if is_fridge:
            mode = st.selectbox("Mode", S.FRIDGE_MODES, format_func=lambda m: S.MODE_LABELS[m])
        else:
            st.markdown("Enter quantities purchased from the manufacturer. Leave 0 for items not bought.")
        qty = _qty_grid(cat, f"q_{table}", note_untracked=is_fridge)
        if st.form_submit_button("➕ Save", type="primary"):
            rec, errors = build_quantities(entry_date, qty, cat, mode=mode)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                total = sum(rec[p] for p in cat.all_product_names)
                _submit(repo, cat, [(table, rec)], f"{table} record added for {fmt_date(entry_date)} · {total} units.")


def _revenue(bundle: DataBundle, repo) -> None:
    cat = bundle.catalog
    section("Add Revenue")
    with st.form("revenue", clear_on_submit=True):
        entry_date = st.date_input("Date", value=date.today())
        amount = st.number_input(f"Revenue Amount ({cat.currency})", min_value=0.0, step=1.0)
        comment = st.text_input("Comments (optional)")
        if st.form_submit_button("➕ Add Revenue", type="primary"):
            rec, errors = build_revenue(entry_date, amount, comment)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                _submit(repo, cat, [(S.REVENUE, rec)], f"Revenue of {cat.fmt(amount)} added for {fmt_date(entry_date)}.")


def _dividend(bundle: DataBundle, repo) -> None:
    cat = bundle.catalog
    section("Add Dividend / Partner Payout")
    if not cat.partners:
        st.info("No partners configured. Add them in the Partners table or config/business.json.")
        return
    shares = " · ".join(f"{p.name} {p.share_pct:g}%" for p in cat.partners)
    st.caption(f"Profit share: {shares}. Enter a total to see the suggested split, then adjust per partner if needed.")
    total = st.number_input(f"Total payout ({cat.currency})", min_value=0.0, step=100.0, key="div_total")
    suggested = cat.split_dividend(total) if total else {p.name: 0 for p in cat.partners}
    with st.form("dividend", clear_on_submit=True):
        entry_date = st.date_input("Date", value=date.today())
        cols = st.columns(len(cat.partners))
        per = {p.name: cols[i].number_input(f"{p.name} ({cat.currency})", min_value=0.0, step=1.0,
                                             value=float(suggested.get(p.name, 0)), key=f"div_{p.name}_{total}")
               for i, p in enumerate(cat.partners)}
        if st.form_submit_button("➕ Add Dividend", type="primary"):
            rec, errors = build_dividend(entry_date, per, cat)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                _submit(repo, cat, [(S.DIVIDEND, rec)], f"Dividend of {cat.fmt(rec[S.DIV_TOTAL])} recorded for {fmt_date(entry_date)}.")


# ── recent entries ───────────────────────────────────────────────────────────

def _recent(bundle: DataBundle, table: str) -> None:
    cat = bundle.catalog
    st.markdown("")
    section(f"Recent Entries — {table}", "last 10")
    df = bundle[table]
    if df.empty:
        st.info("No records yet.")
        return
    if table in (S.BOUGHT, S.FRIDGE):
        active = [c for c in cat.all_product_names if c in df.columns and pd.to_numeric(df[c], errors="coerce").fillna(0).sum() > 0]
        show = [S.DATE] + ([S.MODE] if table == S.FRIDGE else []) + active
    else:
        show = [c for c in df.columns if c in df.columns]
    recent = df.tail(10).sort_values(S.DATE, ascending=False)[show].copy()
    html_table(recent, max_height=420, first_col_bold=False)
