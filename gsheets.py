"""
gsheets.py — Google Sheets read/write helper for IcyPops dashboard.

Authentication uses a Google Service Account key stored in
Streamlit secrets (st.secrets["gcp_service_account"]).
"""

import streamlit as st
import gspread
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_NAMES = ["Expense", "Bought", "Fridge", "Revenue", "Dividend"]

PRODUCTS = [
    "Kala Khatta - 40 ml", "Kachhi Keri - 40 ml", "Mango Bango - 40 ml",
    "Tangy Orange - 40 ml", "STRAWBERRY LOVE - 40 ml", "Guava Delight - 40 ml",
    "ZESTY LEMON - 40 ml", "REFRESHING ROSE - 40 ml", "Tasty Mix Fruit - 40 ml",
    "Spicy Jeera - 40 ml", "CHATPATTI IMLI - 40 ml",
    "Kala Khatta - 80 ml", "Kachhi Keri - 80 ml", "Mango Bango - 80 ml",
    "Tangy Orange - 80 ml", "STRAWBERRY LOVE - 80 ml", "Guava Delight - 80 ml",
    "ZESTY LEMON - 80 ml", "REFRESHING ROSE - 80 ml", "Tasty Mix Fruit - 80 ml",
    "Spicy Jeera - 80 ml", "CHATPATTI IMLI - 80 ml", "FAMILY PACK",
]

FRIDGE_MODES = ["from stock", "to vendor", "from vendor"]

EXPENSE_PAYMENT_COLS = ["PaidThroughIncomeBank", "PaidThroughIncomeCash", "PaidThroughOwnMoney"]

EXPENSE_PAYMENT_LABELS = {
    "PaidThroughIncomeBank": "Expense Paid through Income from Account",
    "PaidThroughIncomeCash": "Expense Paid through Income in Cash",
    "PaidThroughOwnMoney":   "Expense Paid by Personal Money",
}

EXPENSE_OPERATIONAL_COL = "OperationalCost"

EXPENSE_COLS  = ["Date", "Type", "Description", "Expense"] + EXPENSE_PAYMENT_COLS + [EXPENSE_OPERATIONAL_COL]
BOUGHT_COLS   = ["Date"] + PRODUCTS
FRIDGE_COLS   = ["Date", "Mode"] + PRODUCTS
REVENUE_COLS  = ["Date", "Revenue"]
REVENUE_COMMENT_COL = "Comments"          # optional column in the Revenue sheet

# Dividend sheet headers exactly as in your sheet (note: DIVIDENT spelling)
DIVIDEND_COLS = ["DATE", "TOTAL_DIVIDEND", "SAKSHAM_DIVIDEND", "DHAIRYA_DIVIDENT"]
DIV_TOTAL, DIV_SAKSHAM, DIV_DHAIRYA = DIVIDEND_COLS[1:]

SHEET_COLS = {
    "Expense":  EXPENSE_COLS,
    "Bought":   BOUGHT_COLS,
    "Fridge":   FRIDGE_COLS,
    "Revenue":  REVENUE_COLS,
    "Dividend": DIVIDEND_COLS,
}

SHEET_OPTIONAL_COLS = {"Revenue": [REVENUE_COMMENT_COL]}
TEXT_COLS = {"Date", "DATE", "Mode", "Type", "Description", REVENUE_COMMENT_COL}


@st.cache_resource(ttl=60)
def get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)


def get_spreadsheet():
    gc = get_client()
    return gc.open_by_key(st.secrets["spreadsheet_id"])


@st.cache_data(ttl=30)
def load_sheet(sheet_name: str) -> pd.DataFrame:
    """Load a sheet as a DataFrame. Returns empty DF with correct columns on error."""
    required = SHEET_COLS[sheet_name]
    all_cols = required + SHEET_OPTIONAL_COLS.get(sheet_name, [])
    try:
        ws = get_spreadsheet().worksheet(sheet_name)
        data = ws.get_all_records(expected_headers=required)
        df = pd.DataFrame(data)
        for col in all_cols:
            if col not in df.columns:
                df[col] = "" if col in TEXT_COLS else 0
        df = df[all_cols]
        if df.empty:
            return df
        date_col = "DATE" if "DATE" in df.columns else "Date"
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        num_cols = [c for c in df.columns if c not in TEXT_COLS]
        if num_cols:
            df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
        return df
    except Exception as e:
        st.warning(f"Could not load sheet '{sheet_name}': {e}")
        return pd.DataFrame(columns=all_cols)


def append_row(sheet_name: str, row: list):
    """Append a single row to the given sheet."""
    ws = get_spreadsheet().worksheet(sheet_name)
    ws.append_row(row, value_input_option="USER_ENTERED")
    load_sheet.clear()


def ensure_headers():
    """Write header row to any sheet that is completely empty."""
    ss = get_spreadsheet()
    for name, cols in SHEET_COLS.items():
        ws = ss.worksheet(name)
        existing = ws.get_all_values()
        if not existing:
            ws.append_row(cols, value_input_option="USER_ENTERED")


def create_spreadsheet_snapshot() -> dict:
    """Copy the live spreadsheet into the same Drive folder with a timestamped name."""
    spreadsheet_id = st.secrets["spreadsheet_id"]
    ss = get_spreadsheet()
    timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    snapshot_name = f"{ss.title} — Snapshot {timestamp}"

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    session = AuthorizedSession(creds)

    meta_resp = session.get(
        f"https://www.googleapis.com/drive/v3/files/{spreadsheet_id}",
        params={"fields": "parents"},
    )
    meta_resp.raise_for_status()
    parents = meta_resp.json().get("parents", [])

    copy_body: dict = {"name": snapshot_name}
    if parents:
        copy_body["parents"] = parents

    copy_resp = session.post(
        f"https://www.googleapis.com/drive/v3/files/{spreadsheet_id}/copy",
        json=copy_body,
    )
    copy_resp.raise_for_status()
    copy_id = copy_resp.json()["id"]

    return {
        "id": copy_id,
        "name": snapshot_name,
        "url": f"https://docs.google.com/spreadsheets/d/{copy_id}/edit",
    }