"""
Google Sheets Manager
Handles all read/write operations for expense tracking
Sheet structure:
  - "Engineers" sheet: telegram_id, name, initial_deposit, balance, currency, project
  - "Transactions" sheet: id, date, engineer_id, engineer_name, vendor, amount, currency, category, description, balance_after
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional
import gspread
from google.oauth2.service_account import Credentials
from config import Config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CATEGORY_RU = {
    "transport": "Транспорт",
    "purchase": "Закупка",
    "components": "Комплектующие",
    "other": "Другое",
}


class SheetsManager:
    def __init__(self):
        # On Railway: load credentials from env variable
        # Locally: load from credentials.json file
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            creds_info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(
                Config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
            )
        self.client = gspread.authorize(creds)
        self._spreadsheet = None
        self._engineers_sheet = None
        self._transactions_sheet = None

    @property
    def spreadsheet(self):
        if not self._spreadsheet:
            self._spreadsheet = self.client.open_by_key(Config.SPREADSHEET_ID)
        return self._spreadsheet

    @property
    def engineers_sheet(self):
        if not self._engineers_sheet:
            try:
                self._engineers_sheet = self.spreadsheet.worksheet("Engineers")
            except gspread.WorksheetNotFound:
                self._engineers_sheet = self._create_engineers_sheet()
        return self._engineers_sheet

    @property
    def transactions_sheet(self):
        if not self._transactions_sheet:
            try:
                self._transactions_sheet = self.spreadsheet.worksheet("Transactions")
            except gspread.WorksheetNotFound:
                self._transactions_sheet = self._create_transactions_sheet()
        return self._transactions_sheet

    def _create_engineers_sheet(self):
        ws = self.spreadsheet.add_worksheet("Engineers", rows=100, cols=10)
        ws.append_row([
            "telegram_id", "name", "project", "initial_deposit",
            "balance", "currency", "added_date", "notes"
        ])
        # Format header
        ws.format("A1:H1", {
            "backgroundColor": {"red": 0.2, "green": 0.5, "blue": 0.8},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
        })
        return ws

    def _create_transactions_sheet(self):
        ws = self.spreadsheet.add_worksheet("Transactions", rows=5000, cols=12)
        ws.append_row([
            "id", "timestamp", "date", "engineer_id", "engineer_name",
            "vendor", "amount", "currency", "category", "category_ru",
            "description", "balance_after"
        ])
        ws.format("A1:L1", {
            "backgroundColor": {"red": 0.15, "green": 0.65, "blue": 0.45},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
        })
        return ws

    # ── READ OPERATIONS ──────────────────────────────────────────────────────

    def get_engineer(self, telegram_id: str) -> Optional[dict]:
        """Get engineer data by Telegram ID."""
        try:
            records = self.engineers_sheet.get_all_records()
            for r in records:
                if str(r.get("telegram_id")) == str(telegram_id):
                    return r
            return None
        except Exception as e:
            logger.error(f"get_engineer error: {e}")
            return None

    def get_all_engineers(self) -> list:
        """Get all engineers."""
        try:
            return self.engineers_sheet.get_all_records()
        except Exception as e:
            logger.error(f"get_all_engineers error: {e}")
            return []

    def get_transactions(self, engineer_id: str = None, limit: int = 50) -> list:
        """Get transactions, optionally filtered by engineer."""
        try:
            records = self.transactions_sheet.get_all_records()
            if engineer_id:
                records = [r for r in records if str(r.get("engineer_id")) == str(engineer_id)]
            # Sort by timestamp descending
            records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return records[:limit]
        except Exception as e:
            logger.error(f"get_transactions error: {e}")
            return []

    def get_total_spent(self, engineer_id: str) -> float:
        """Calculate total spent by engineer."""
        transactions = self.get_transactions(engineer_id, limit=9999)
        return sum(float(str(t.get("amount", 0)).replace(",", ".")) for t in transactions)

    # ── WRITE OPERATIONS ─────────────────────────────────────────────────────

    def add_engineer(self, telegram_id: str, name: str, project: str,
                     initial_deposit: float, currency: str = "AED", notes: str = "") -> bool:
        """Add new engineer to the system."""
        try:
            # Check if already exists
            existing = self.get_engineer(telegram_id)
            if existing:
                return False
            
            self.engineers_sheet.append_row([
                str(telegram_id),
                name,
                project,
                initial_deposit,
                initial_deposit,  # balance = initial
                currency,
                datetime.now().strftime("%Y-%m-%d"),
                notes
            ])
            logger.info(f"Added engineer: {name} ({telegram_id})")
            return True
        except Exception as e:
            logger.error(f"add_engineer error: {e}")
            return False

    def update_balance(self, telegram_id: str, new_balance: float) -> bool:
        """Update engineer's balance."""
        try:
            records = self.engineers_sheet.get_all_records()
            for i, r in enumerate(records, start=2):  # row 1 is header
                if str(r.get("telegram_id")) == str(telegram_id):
                    # Column E is balance (index 5)
                    self.engineers_sheet.update_cell(i, 5, new_balance)
                    return True
            return False
        except Exception as e:
            logger.error(f"update_balance error: {e}")
            return False

    def top_up_balance(self, telegram_id: str, amount: float) -> Optional[float]:
        """Add funds to engineer deposit. Returns new balance."""
        engineer = self.get_engineer(telegram_id)
        if not engineer:
            return None
        new_balance = float(engineer.get("balance", 0)) + amount
        if self.update_balance(telegram_id, new_balance):
            return new_balance
        return None

    def add_transaction(self, data: dict) -> bool:
        """Record a new expense transaction."""
        try:
            transaction_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{data['user_id'][-4:]}"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self.transactions_sheet.append_row([
                transaction_id,
                timestamp,
                data.get("date", datetime.now().strftime("%Y-%m-%d")),
                str(data["user_id"]),
                data.get("engineer_name", ""),
                data.get("vendor", ""),
                round(float(str(data["amount"]).replace(",", ".")), 2),
                data.get("currency", "AED"),
                data.get("category", "other"),
                CATEGORY_RU.get(data.get("category", "other"), "Другое"),
                data.get("description", ""),
                round(float(str(data.get("new_balance", 0)).replace(",", ".")), 2),
            ])
            logger.info(f"Transaction recorded: {transaction_id} - {data['amount']} {data.get('currency')}")
            return True
        except Exception as e:
            logger.error(f"add_transaction error: {e}")
            return False

    def update_engineer(self, telegram_id: str, **kwargs) -> bool:
        """Update engineer fields."""
        try:
            records = self.engineers_sheet.get_all_records()
            headers = self.engineers_sheet.row_values(1)
            
            for i, r in enumerate(records, start=2):
                if str(r.get("telegram_id")) == str(telegram_id):
                    for field, value in kwargs.items():
                        if field in headers:
                            col = headers.index(field) + 1
                            self.engineers_sheet.update_cell(i, col, value)
                    return True
            return False
        except Exception as e:
            logger.error(f"update_engineer error: {e}")
            return False
