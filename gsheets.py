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

SHEET_NAMES = ["Expense", "Bought", "Fridge", "Revenue"]

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

EXPENSE_COLS  = ["Date", "Type", "Description", "Expense"] + EXPENSE_PAYMENT_COLS
BOUGHT_COLS   = ["Date"] + PRODUCTS
FRIDGE_COLS   = ["Date", "Mode"] + PRODUCTS
REVENUE_COLS  = ["Date", "Revenue"]

SHEET_COLS = {
    "Expense": EXPENSE_COLS,
    "Bought":  BOUGHT_COLS,
    "Fridge":  FRIDGE_COLS,
    "Revenue": REVENUE_COLS,
}


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
    try:
        ws = get_spreadsheet().worksheet(sheet_name)
        data = ws.get_all_records(expected_headers=SHEET_COLS[sheet_name])
        df = pd.DataFrame(data, columns=SHEET_COLS[sheet_name])
        for col in SHEET_COLS[sheet_name]:
            if col not in df.columns:
                df[col] = 0
        df = df[SHEET_COLS[sheet_name]]
        if df.empty:
            return df
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        num_cols = [c for c in df.columns if c not in ("Date", "Mode", "Type", "Description")]
        if num_cols:
            df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
        return df
    except Exception as e:
        st.warning(f"Could not load sheet '{sheet_name}': {e}")
        return pd.DataFrame(columns=SHEET_COLS[sheet_name])


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