"""
Configuration — заполни свои данные здесь или через переменные окружения
"""
import os

class Config:
    # ── TELEGRAM BOT ──────────────────────────────────────────────
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")

    # ── ANTHROPIC (Claude Vision для чтения чеков) ────────────────
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY_HERE")

    # ── GOOGLE SHEETS ──────────────────────────────────────────────
    GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "YOUR_SPREADSHEET_ID_HERE")

    # ── ADMIN ──────────────────────────────────────────────────────
    ADMIN_TELEGRAM_IDS = [
        int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",") if x.strip()
    ]

    # ── DASHBOARD AUTH ─────────────────────────────────────────────
    DASHBOARD_USER = os.getenv("DASHBOARD_USER", "furni")
    DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "")  # пустой = без пароля

    # ── НАСТРОЙКИ ──────────────────────────────────────────────────
    DEFAULT_CURRENCY = "AED"
    LOW_BALANCE_THRESHOLD = 500
