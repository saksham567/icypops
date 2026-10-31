"""ui/setup.py — Setup & Help tab: how this business is configured and how numbers are computed."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from config.settings import Settings
from core import schema as S
from core.catalog import catalog_to_frames
from core.inventory import compute_inventory, unsettled_dates
from data import DataBundle
from ui import state
from ui.components import pills, section

GLOSSARY = [
    ("Settled day", "A date with both a 'to vendor' and a 'from vendor' entry. Only settled days count towards Sold, Stock Left and Expected Revenue, so an in-progress day never looks like a sell-out."),
    ("Sold", "to vendor − from vendor (settled days)."),
    ("Stock Outside Fridge", "Total Bought − from stock. Units still in storage/boxes."),
    ("Stock Inside Fridge", "from stock − to vendor + from vendor (settled). Negative means units were dispatched without a 'from stock' entry."),
    ("Stock Left", "Total Bought + from vendor − to vendor (settled) = Outside + Inside."),
    ("Expected Revenue", "Σ units sold × unit price (from the Products table / business.json)."),
    ("Revenue Gap", "Actual collected − Expected. Persistent negative gaps point at leakage, discounts or free samples."),
    ("Gross Profit", "Σ units sold × unit margin. Does not include fixed costs."),
    ("Operational Cost", "Expenses flagged Operational (stock, salary, essentials, travel). Capex like the cart or freezer stays non-operational."),
    ("Realized Profit", "Actual Revenue − Operational Cost."),
    ("Net P&L (breakeven)", "Actual Revenue − Total Expense including capex. Turns positive once the initial investment is recovered."),
    ("Profit After Dividend", "Realized Profit − total partner payouts."),
    ("Reorder alert", "Stock Left < ReorderThreshold for that product."),
    ("Fridge-low alert", "Stock Inside Fridge < FridgeThreshold, only for fridge-tracked products."),
]


def render(bundle: DataBundle, settings: Settings) -> None:
    cat = bundle.catalog

    section("Connection")
    c1, c2, c3 = st.columns(3)
    c1.metric("Data backend", settings.backend_label)
    c2.metric("Source", bundle.backend)
    c3.metric("Catalog loaded from", cat.source)
    if settings.demo_mode:
        st.info("You are in **demo mode** on the bundled sample workbook. Entries you add are written to that file. "
                "To connect your own Google Sheet, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in.")
    for w in bundle.warnings:
        st.warning(w)
    present = state.get_repo().tables()
    pills([(t, "green" if t in present else "red") for t in S.TRANSACTION_TABLES]
          + [(t, "green" if t in present else "amber") for t in S.CONFIG_TABLES])
    st.caption("Green = table found · Amber = optional config table missing (defaults from business.json are used) · Red = required table missing (created on first write).")

    section("Business profile")
    b = cat.business
    st.markdown(f"**{b.logo_emoji} {b.name}** — {b.tagline} · currency `{b.currency_symbol}` · locale `{b.locale}`")
    st.markdown("**Partners:** " + (", ".join(f"{p.name} ({p.share_pct:g}%)" for p in cat.partners) or "none configured"))
    st.markdown("**Expense types:** " + ", ".join(cat.expense_types))

    section("Product catalog", f"{len(cat.product_names)} active products · {len(cat.categories)} categories")
    cats = pd.DataFrame([{"Category": c.label, "Key": c.key, "Default price": c.sell_price, "Default margin": c.unit_margin,
                          "Fridge tracked": c.fridge_tracked, "Display order": c.sort_order} for c in cat.categories_sorted()])
    st.dataframe(cats, width="stretch", hide_index=True)
    prods = pd.DataFrame([{"Product": p.name, "Category": cat.category(p.category).label, "Price": p.sell_price,
                           "Margin": p.unit_margin, "Reorder at": p.reorder_threshold, "Fridge low at": p.fridge_threshold,
                           "Fridge tracked": p.fridge_tracked, "Active": p.active} for p in cat.products])
    st.dataframe(prods, width="stretch", hide_index=True, height=min(60 + 36 * len(prods), 520))

    section("Onboard another franchise owner")
    st.markdown(
        '<p class="note">1. Make a copy of the Google Sheet template (or run <code>scripts/setup_sheet.py</code>).<br>'
        '2. Fill the three config tabs — <b>Products</b>, <b>Partners</b>, <b>Settings</b> — with their flavours, prices, thresholds, partners and branding. '
        'No code changes are needed; the app rebuilds every form, KPI and chart from those tables.<br>'
        '3. Share the sheet with the service-account email and point <code>secrets.toml</code> at it.</p>',
        unsafe_allow_html=True)
    frames = catalog_to_frames(cat)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in frames.items():
            df.to_excel(xw, sheet_name=name, index=False)
        for t in S.TRANSACTION_TABLES:
            pd.DataFrame(columns=bundle[t].columns).to_excel(xw, sheet_name=t, index=False)
    st.download_button("⬇ Download onboarding template (xlsx: config tabs + empty data tabs)", buf.getvalue(),
                       file_name=f"{b.name}_template.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_tpl")

    section("How the numbers are computed")
    st.markdown('<dl class="glossary">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in GLOSSARY) + "</dl>", unsafe_allow_html=True)

    section("Data checks")
    inv = compute_inventory(bundle[S.BOUGHT], bundle[S.FRIDGE], cat)
    open_days = unsettled_dates(bundle[S.FRIDGE])
    neg = inv[inv["Fridge Tracked"] & (inv["Stock Inside Fridge"] < 0)]
    d1, d2 = st.columns(2)
    d1.metric("Open days (dispatch without return)", len(open_days),
              help="These days are excluded from Sold until a 'from vendor' entry exists.")
    d2.metric("Products with negative in-fridge stock", len(neg),
              help="Units were dispatched without a matching 'from stock' entry. Stock Left is unaffected.")
    if open_days:
        st.caption("Open: " + ", ".join(d.strftime("%d %b %Y") for d in open_days))

    section("Maintenance")
    m1, m2 = st.columns(2)
    if m1.button("↻ Reload data", width="stretch"):
        state.refresh()
        st.rerun()
    if m2.button("⟲ Reconnect backend", width="stretch", help="Re-read secrets and rebuild the connection"):
        state.reconnect()
        st.rerun()
