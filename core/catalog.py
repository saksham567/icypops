"""
core/catalog.py — The business catalog (what this franchise sells, who owns it).

A ``Catalog`` is built once per load from, in order of precedence:
  1. Products / Partners / Settings tables in the data backend (if present & non-empty)
  2. config/business.json (always present — the onboarding template)

Everything downstream (metrics, charts, forms) only asks the Catalog, so onboarding
a new franchise owner is: edit three small tables. No code changes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

from core import schema as S

_PALETTE = ["#14B8A6", "#F97066", "#F6B93B", "#6366F1", "#0EA5E9", "#A855F7", "#22C55E", "#F97316"]


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    sell_price: float
    unit_margin: float
    fridge_tracked: bool = True
    sort_order: int = 99
    color: str = "#38bdf8"


@dataclass(frozen=True)
class Product:
    name: str
    category: str
    sell_price: float
    unit_margin: float
    reorder_threshold: float
    fridge_threshold: float
    fridge_tracked: bool = True
    active: bool = True
    sort_order: int = 0


@dataclass(frozen=True)
class Partner:
    name: str
    share_pct: float

    @property
    def column(self) -> str:
        """Canonical Dividend column for this partner."""
        return f"{self.name.upper()}_DIVIDEND"


@dataclass(frozen=True)
class Business:
    name: str = "My Business"
    tagline: str = "Inventory & Business Intelligence"
    logo_emoji: str = "🏪"
    currency_symbol: str = "₹"
    locale: str = "en-IN"
    app_name: str = ""

    def __post_init__(self):
        if not self.app_name:
            object.__setattr__(self, "app_name", f"{self.name} Pal")


@dataclass
class Catalog:
    business: Business
    categories: list[Category]
    products: list[Product]
    partners: list[Partner]
    expense_types: list[str] = field(default_factory=list)
    source: str = "business.json"

    # ── Convenience accessors ──────────────────────────────────────────────
    @property
    def product_names(self) -> list[str]:
        return [p.name for p in self.products if p.active]

    @property
    def all_product_names(self) -> list[str]:
        return [p.name for p in self.products]

    @property
    def partner_names(self) -> list[str]:
        return [p.name for p in self.partners]

    @property
    def currency(self) -> str:
        return self.business.currency_symbol

    def category(self, key: str) -> Category:
        for c in self.categories:
            if c.key == key:
                return c
        raise KeyError(key)

    def category_of(self, product_name: str) -> Category:
        return self.category(self.product(product_name).category)

    def product(self, name: str) -> Product:
        for p in self.products:
            if p.name == name:
                return p
        raise KeyError(name)

    def products_in(self, category_key: str, active_only: bool = True) -> list[str]:
        return [p.name for p in self.products
                if p.category == category_key and (p.active or not active_only)]

    def categories_sorted(self) -> list[Category]:
        return sorted(self.categories, key=lambda c: (c.sort_order, c.label))

    def category_rank(self, product_name: str) -> int:
        """Rank used for grouping rows/bars (lower = shown first / on top)."""
        try:
            return self.category_of(product_name).sort_order
        except KeyError:
            return 999

    def price(self, product_name: str) -> float:
        return self.product(product_name).sell_price

    def margin(self, product_name: str) -> float:
        return self.product(product_name).unit_margin

    def price_series(self) -> pd.Series:
        return pd.Series({p.name: p.sell_price for p in self.products})

    def margin_series(self) -> pd.Series:
        return pd.Series({p.name: p.unit_margin for p in self.products})

    def thresholds(self) -> tuple[pd.Series, pd.Series]:
        return (pd.Series({p.name: p.reorder_threshold for p in self.products}),
                pd.Series({p.name: p.fridge_threshold for p in self.products}))

    def partner(self, name: str) -> Partner:
        for p in self.partners:
            if p.name.lower() == name.lower():
                return p
        raise KeyError(name)

    def split_dividend(self, total: float) -> dict[str, float]:
        """Suggested per-partner split of ``total`` by share_pct (rounded to whole units)."""
        if not self.partners:
            return {}
        total_pct = sum(p.share_pct for p in self.partners) or 100.0
        split = {p.name: round(total * p.share_pct / total_pct) for p in self.partners}
        # push rounding remainder to the largest shareholder
        diff = round(total) - sum(split.values())
        if diff and split:
            biggest = max(self.partners, key=lambda p: p.share_pct).name
            split[biggest] += diff
        return split

    def fmt(self, amount: float, decimals: int = 0) -> str:
        """Format a currency amount with the business' symbol (Indian grouping for en-IN)."""
        try:
            v = float(amount)
        except (TypeError, ValueError):
            return "–"
        sign = "-" if v < 0 else ""
        v = abs(v)
        if self.business.locale == "en-IN":
            s = _indian_group(v, decimals)
        else:
            s = f"{v:,.{decimals}f}"
        return f"{sign}{self.currency}{s}"


def _indian_group(v: float, decimals: int) -> str:
    whole, _, frac = f"{v:.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{whole}.{frac}" if decimals else whole


# ══════════════════════════════════════════════════════════════════════════════
#  Builders
# ══════════════════════════════════════════════════════════════════════════════

def _truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "1.0"}


def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return default if pd.isna(f) else f
    except (TypeError, ValueError):
        return default


def catalog_from_json(path: Path) -> Catalog:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return _build(
        business=raw.get("business", {}),
        categories=raw.get("categories", []),
        products=raw.get("products", []),
        partners=raw.get("partners", []),
        expense_types=raw.get("expense_types", []),
        source=str(path.name),
    )


def catalog_from_frames(products: pd.DataFrame | None,
                        partners: pd.DataFrame | None,
                        settings: pd.DataFrame | None,
                        fallback: Catalog) -> Catalog:
    """Overlay Products/Partners/Settings tables on top of a fallback catalog."""
    fb = fallback

    # Settings → business + expense types ------------------------------------
    kv: dict[str, str] = {}
    if settings is not None and not settings.empty and {"Key", "Value"} <= set(settings.columns):
        kv = {str(k).strip(): str(v).strip() for k, v in zip(settings["Key"], settings["Value"]) if str(k).strip()}
    business = {
        "name": kv.get("business_name", fb.business.name),
        "tagline": kv.get("tagline", fb.business.tagline),
        "logo_emoji": kv.get("logo_emoji", fb.business.logo_emoji),
        "currency_symbol": kv.get("currency_symbol", fb.business.currency_symbol),
        "locale": kv.get("locale", fb.business.locale),
        "app_name": kv.get("app_name", fb.business.app_name),
    }
    expense_types = fb.expense_types
    if kv.get("expense_types"):
        expense_types = [t.strip() for t in kv["expense_types"].split(",") if t.strip()]

    # Category defaults may be given in Settings as  category.<key>.<field> = value
    cat_overrides: dict[str, dict] = {}
    for k, v in kv.items():
        if k.startswith("category."):
            parts = k.split(".")
            if len(parts) == 3:
                cat_overrides.setdefault(parts[1], {})[parts[2]] = v

    # Products ---------------------------------------------------------------
    used_tables = []
    if products is not None and not products.empty and "Name" in products.columns:
        prods = []
        for i, r in products.iterrows():
            name = str(r.get("Name", "")).strip()
            if not name:
                continue
            prods.append({
                "name": name,
                "category": str(r.get("Category", "")).strip() or "default",
                "sell_price": r.get("SellPrice"),
                "unit_margin": r.get("UnitMargin"),
                "reorder_threshold": _num(r.get("ReorderThreshold"), 0),
                "fridge_threshold": _num(r.get("FridgeThreshold"), 0),
                "fridge_tracked": r.get("FridgeTracked"),
                "active": _truthy(r.get("Active", 1)) if str(r.get("Active", "")).strip() != "" else True,
                "sort_order": int(_num(r.get("SortOrder"), i)),
            })
        used_tables.append("Products")
    else:
        prods = [p.__dict__ for p in fb.products]

    # Categories: when the Products table drives the catalog, derive categories from it
    # (fallback categories only apply when products themselves come from the fallback).
    cats = {} if "Products" in used_tables else {c.key: c.__dict__.copy() for c in fb.categories}
    for p in prods:
        key = p["category"]
        if key not in cats:
            cats[key] = {"key": key, "label": key, "sell_price": 0, "unit_margin": 0,
                         "fridge_tracked": True, "sort_order": len(cats) + 1}
    for key, ov in cat_overrides.items():
        cats.setdefault(key, {"key": key, "label": key, "sell_price": 0, "unit_margin": 0,
                              "fridge_tracked": True, "sort_order": len(cats) + 1}).update(ov)

    # Partners ---------------------------------------------------------------
    if partners is not None and not partners.empty and "Name" in partners.columns:
        parts = [{"name": str(r["Name"]).strip(), "share_pct": _num(r.get("SharePct"), 0)}
                 for _, r in partners.iterrows() if str(r.get("Name", "")).strip()]
        used_tables.append("Partners")
    else:
        parts = [p.__dict__ for p in fb.partners]
    if kv:
        used_tables.append("Settings")

    source = ("tables: " + ", ".join(used_tables)) if used_tables else fb.source
    return _build(business, list(cats.values()), prods, parts, expense_types, source)


def _build(business: dict, categories: Iterable[dict], products: Iterable[dict],
           partners: Iterable[dict], expense_types: Iterable[str], source: str) -> Catalog:
    cats: list[Category] = []
    for i, c in enumerate(categories):
        cats.append(Category(
            key=str(c["key"]), label=str(c.get("label", c["key"])),
            sell_price=_num(c.get("sell_price"), 0), unit_margin=_num(c.get("unit_margin"), 0),
            fridge_tracked=_truthy(c.get("fridge_tracked", True)),
            sort_order=int(_num(c.get("sort_order"), i + 1)),
            color=c.get("color") or _PALETTE[i % len(_PALETTE)],
        ))
    cat_by_key = {c.key: c for c in cats}

    prods: list[Product] = []
    for i, p in enumerate(products):
        cat = cat_by_key.get(str(p.get("category")), None)
        price = p.get("sell_price")
        margin = p.get("unit_margin")
        tracked = p.get("fridge_tracked")
        prods.append(Product(
            name=str(p["name"]),
            category=cat.key if cat else str(p.get("category", "default")),
            sell_price=_num(price, cat.sell_price if cat else 0) if price not in (None, "") else (cat.sell_price if cat else 0),
            unit_margin=_num(margin, cat.unit_margin if cat else 0) if margin not in (None, "") else (cat.unit_margin if cat else 0),
            reorder_threshold=_num(p.get("reorder_threshold"), 0),
            fridge_threshold=_num(p.get("fridge_threshold"), 0),
            fridge_tracked=_truthy(tracked) if tracked not in (None, "") else (cat.fridge_tracked if cat else True),
            active=bool(p.get("active", True)),
            sort_order=int(_num(p.get("sort_order"), i)),
        ))

    parts = [Partner(name=str(p["name"]), share_pct=_num(p.get("share_pct"), 0)) for p in partners]

    return Catalog(
        business=Business(**{k: v for k, v in business.items() if k in Business.__dataclass_fields__}),
        categories=cats,
        products=prods,
        partners=parts,
        expense_types=list(expense_types),
        source=source,
    )


def catalog_to_frames(cat: Catalog) -> dict[str, pd.DataFrame]:
    """Serialise a catalog into the three config tables (used by setup scripts)."""
    products = pd.DataFrame([{
        "Name": p.name, "Category": p.category, "SellPrice": p.sell_price, "UnitMargin": p.unit_margin,
        "ReorderThreshold": p.reorder_threshold, "FridgeThreshold": p.fridge_threshold,
        "FridgeTracked": int(p.fridge_tracked), "Active": int(p.active), "SortOrder": p.sort_order,
    } for p in cat.products], columns=S.PRODUCTS_COLS)
    partners = pd.DataFrame([{"Name": p.name, "SharePct": p.share_pct} for p in cat.partners],
                            columns=S.PARTNERS_COLS)
    rows = [
        ("business_name", cat.business.name), ("tagline", cat.business.tagline),
        ("logo_emoji", cat.business.logo_emoji), ("currency_symbol", cat.business.currency_symbol),
        ("locale", cat.business.locale), ("app_name", cat.business.app_name), ("expense_types", ", ".join(cat.expense_types)),
    ]
    for c in cat.categories:
        rows += [(f"category.{c.key}.label", c.label), (f"category.{c.key}.sell_price", c.sell_price),
                 (f"category.{c.key}.unit_margin", c.unit_margin),
                 (f"category.{c.key}.fridge_tracked", int(c.fridge_tracked)),
                 (f"category.{c.key}.sort_order", c.sort_order)]
    settings = pd.DataFrame(rows, columns=S.SETTINGS_COLS)
    return {S.PRODUCTS: products, S.PARTNERS: partners, S.SETTINGS: settings}
