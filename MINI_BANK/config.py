"""
Configuration module for MINI BANK.
Loads settings from environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "database" / "mini_bank.db"))
TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Moscow")

# Economy defaults (can be overridden via admin panel / DB settings)
DEFAULT_DAILY_BONUS: int = 1000  # in kopecks (10.00 ₽)
DEFAULT_INITIAL_BALANCE: int = 5000  # 50.00 ₽
MAX_TRANSFER_AMOUNT: int = 1_000_000_00  # 1 000 000.00 ₽

# Task limits
DEFAULT_DAILY_TASK_LIMIT: int = 20
DEFAULT_TASK_STREAK_BONUS: int = 500  # kopecks

# Savings
DEFAULT_SAVINGS_RATE: float = 0.01  # 1% per period
DEFAULT_SAVINGS_PERIOD_HOURS: int = 24

# Security
ADMIN_SESSION_TIMEOUT_MINUTES: int = 30
MAX_LOGIN_ATTEMPTS: int = 5
LOCKOUT_MINUTES: int = 15
TOTP_WINDOW: int = 1

# Paths
BACKUPS_DIR = BASE_DIR / "backups"
BACKUPS_DIR.mkdir(exist_ok=True)

def validate_config() -> None:
    """Validate critical configuration on startup."""
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and set a valid token."
        )
    if OWNER_ID <= 0:
        raise RuntimeError(
            "OWNER_ID is not set or invalid. Set your Telegram user ID in .env"
        )
