# Recommended changes to the Google Sheet

The app works on the sheet **exactly as it is today**. Nothing below is required to run.
Items are ordered by value-for-effort. Items 1–4 take fifteen minutes and are what make the
app sellable; items 5–7 prepare the data for the database move.

## 1. Add three config tabs (do this first)

Run `python scripts/setup_sheet.py` once. It adds:

| Tab | Columns | Purpose |
|---|---|---|
| `Products` | Name, Category, SellPrice, UnitMargin, ReorderThreshold, FridgeThreshold, FridgeTracked, Active, SortOrder | Replaces `thresholds.json` and the hard-coded prices/margins. New flavour = new row. Discontinued flavour = `Active = 0` (history kept). |
| `Partners` | Name, SharePct | Replaces the Saksham/Dhairya columns in code. Drives dividend split and labels. |
| `Settings` | Key, Value | `business_name`, `tagline`, `logo_emoji`, `currency_symbol`, `locale`, `expense_types`, and `category.<key>.label / sell_price / unit_margin / fridge_tracked / sort_order` |

This is the whole onboarding story for another owner: copy the sheet, edit these tabs.

## 2. Add `PaidBy` to `Expense`

A text column (partner name) filled whenever `PaidThroughOwnMoney = 1`. The app creates it
automatically on the first such entry, but back-fill the 20-odd historical own-money rows
(₹3.74 L of capital). It unlocks the *partner capital* table: who has put in how much vs their
share — the single most useful number in a two-person partnership.

## 3. Standardise `Type` values in `Expense`

Today they are free text (`Bought [Stock]`, `Essentials`, `Salary`…). Keep that list in
`Settings → expense_types` and pick from it in the form (the app already offers a picker with an
*Other* escape hatch). Consistent types make the monthly breakdown grid trustworthy.

## 4. Fix the `Dividend` headers (cosmetic)

`SAKSHAM_DIVIDENT` / `DHAIRYA_DIVIDEND` → the app maps them either way, but for a new owner's
sheet use `<PARTNERNAME>_DIVIDEND` consistently, or any header that starts with the partner's name.

## 5. Record "from stock" movements consistently

21 of 23 products show **negative in-fridge stock** in the real data. That means units were
dispatched (`to vendor`) that were never moved into the fridge (`from stock`). Stock Left is
still correct (it doesn't depend on `from stock`), but fridge-low alerts are meaningless until
this is fixed. Two options:

- keep logging `from stock` every time a box goes into the freezer (strict, better for theft/spoilage detection), or
- stop tracking the fridge split altogether: set `FridgeTracked = 0` for all products and the app hides fridge alerts.

Pick one and tell the other owners which one is the franchise standard.

## 6. Think "long" for the database (no sheet change needed)

The `Bought` and `Fridge` tabs are *wide* (one column per flavour). That is great for a human
typing into a sheet and terrible for a database: adding a flavour = schema change. The SQL
backend already stores these as **long** tables — `purchases(date, product, qty)` and
`stock_movements(date, mode, product, qty)` — and `scripts/migrate_to_db.py` converts wide → long.
Keep the sheet wide for data entry; the conversion is handled.

## 7. Add stable identifiers once writes move to the app

When the app becomes the only writer (Step 2), every row gets `id`, `created_at`, `created_by`
and a `batch_id` grouping the rows of one Day Close. The SQL schema already has these. In the
sheet era, resist the urge to add them manually.

## Data-quality checks the app now surfaces

- Unsettled days (dispatch without return) — shown as a warning and excluded from Sold.
- Negative in-fridge stock — shown as a data-health count.
- Product columns in the sheet that are not in the catalog — shown as an info note, ignored in metrics.
- Revenue gap (actual − expected) per day — red markers on the chart; cumulative gap in the caption.
