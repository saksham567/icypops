"""
core/schema.py — Canonical table & column names.

Every backend (Google Sheets, SQL, local workbook) returns DataFrames in this
shape, and the UI/metrics only ever talk in these names. Changing a sheet header
means changing it here (and in the backend's header-tolerance map) — nowhere else.

Transactional tables  (one row = one event):
    EXPENSE   Date | Type | Description | Expense | PaidThroughIncomeBank | PaidThroughIncomeCash | PaidThroughOwnMoney | OperationalCost | PaidBy | Comments
    BOUGHT    Date | <one column per product>                       (wide — units purchased from manufacturer)
    FRIDGE    Date | Mode | <one column per product>                (wide — stock movement log)
    REVENUE   Date | Revenue | Comments
    DIVIDEND  Date | Total | <one column per partner>

Configuration tables (optional — fall back to config/business.json):
    PRODUCTS  Name | Category | SellPrice | UnitMargin | ReorderThreshold | FridgeThreshold | FridgeTracked | Active | SortOrder
    PARTNERS  Name | SharePct
    SETTINGS  Key | Value
"""

# ── Table names ──────────────────────────────────────────────────────────────
EXPENSE = "Expense"
BOUGHT = "Bought"
FRIDGE = "Fridge"
REVENUE = "Revenue"
DIVIDEND = "Dividend"
PRODUCTS = "Products"
PARTNERS = "Partners"
SETTINGS = "Settings"

TRANSACTION_TABLES = [EXPENSE, BOUGHT, FRIDGE, REVENUE, DIVIDEND]
CONFIG_TABLES = [PRODUCTS, PARTNERS, SETTINGS]
ALL_TABLES = TRANSACTION_TABLES + CONFIG_TABLES

TABLE_LABELS = {
    EXPENSE: "💰 Expense — costs & purchases paid",
    BOUGHT: "🛒 Bought — stock purchased from manufacturer",
    FRIDGE: "🧊 Fridge — stock movement log",
    REVENUE: "📈 Revenue — daily collections",
    DIVIDEND: "🤝 Dividend — partner payouts",
}

# ── Common columns ───────────────────────────────────────────────────────────
DATE = "Date"
MODE = "Mode"
COMMENTS = "Comments"

# ── Expense ──────────────────────────────────────────────────────────────────
EXP_TYPE = "Type"
EXP_DESC = "Description"
EXP_AMOUNT = "Expense"
PAY_BANK = "PaidThroughIncomeBank"
PAY_CASH = "PaidThroughIncomeCash"
PAY_OWN = "PaidThroughOwnMoney"
EXP_OPERATIONAL = "OperationalCost"
EXP_PAID_BY = "PaidBy"          # optional: which partner paid when PAY_OWN == 1

PAYMENT_COLS = [PAY_BANK, PAY_CASH, PAY_OWN]
PAYMENT_LABELS = {
    PAY_BANK: "Paid from business bank account",
    PAY_CASH: "Paid from business cash",
    PAY_OWN: "Paid with a partner's own money",
}
PAYMENT_SHORT = {PAY_BANK: "Bank", PAY_CASH: "Cash", PAY_OWN: "Own money"}

EXPENSE_REQUIRED = [DATE, EXP_TYPE, EXP_DESC, EXP_AMOUNT] + PAYMENT_COLS + [EXP_OPERATIONAL]
EXPENSE_OPTIONAL = [EXP_PAID_BY, COMMENTS]

# ── Fridge ───────────────────────────────────────────────────────────────────
MODE_FROM_STOCK = "from stock"
MODE_TO_VENDOR = "to vendor"
MODE_FROM_VENDOR = "from vendor"
FRIDGE_MODES = [MODE_FROM_STOCK, MODE_TO_VENDOR, MODE_FROM_VENDOR]
MODE_LABELS = {
    MODE_FROM_STOCK: "📦 From Stock — moving stock from storage into the fridge/cart",
    MODE_TO_VENDOR: "🚚 To Vendor — handed to the vendor/cart for the day",
    MODE_FROM_VENDOR: "↩️ From Vendor — unsold units returned at day end",
}

# ── Revenue ──────────────────────────────────────────────────────────────────
REV_AMOUNT = "Revenue"
REVENUE_REQUIRED = [DATE, REV_AMOUNT]
REVENUE_OPTIONAL = [COMMENTS]

# ── Dividend ─────────────────────────────────────────────────────────────────
DIV_TOTAL = "Total"             # partner columns are added dynamically from the catalog

# ── Config tables ────────────────────────────────────────────────────────────
PRODUCTS_COLS = ["Name", "Category", "SellPrice", "UnitMargin", "ReorderThreshold",
                 "FridgeThreshold", "FridgeTracked", "Active", "SortOrder"]
PARTNERS_COLS = ["Name", "SharePct"]
SETTINGS_COLS = ["Key", "Value"]

# Text columns that must never be coerced to numbers.
TEXT_COLS = {DATE, MODE, EXP_TYPE, EXP_DESC, COMMENTS, EXP_PAID_BY,
             "Name", "Category", "Key", "Value"}
