"""
SQLite database connection and initialization for MINI BANK.
All monetary values are stored as INTEGER (kopecks).
"""

from __future__ import annotations

import aiosqlite
from pathlib import Path
from typing import Optional

from config import DATABASE_PATH

_db: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    """Return the shared database connection."""
    global _db
    if _db is None:
        raise RuntimeError("Database is not initialized. Call init_db() first.")
    return _db


async def init_db() -> aiosqlite.Connection:
    """Initialize database connection and create tables if needed."""
    global _db
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(str(db_path))
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA foreign_keys = ON")
    await _db.execute("PRAGMA journal_mode = WAL")
    await _db.execute("PRAGMA synchronous = NORMAL")

    await _create_tables(_db)
    await _db.commit()
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _create_tables(db: aiosqlite.Connection) -> None:
    """Create all required tables."""
    await db.executescript(
        """
        -- Users
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id     INTEGER NOT NULL UNIQUE,
            username        TEXT,
            full_name       TEXT NOT NULL,
            card_number     TEXT NOT NULL UNIQUE,
            is_blocked      INTEGER NOT NULL DEFAULT 0,
            is_admin_setup  INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            last_active     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_users_card_number ON users(card_number);

        -- Accounts (main + savings balances in kopecks)
        CREATE TABLE IF NOT EXISTS accounts (
            user_id             INTEGER PRIMARY KEY,
            main_balance        INTEGER NOT NULL DEFAULT 0 CHECK (main_balance >= 0),
            savings_balance     INTEGER NOT NULL DEFAULT 0 CHECK (savings_balance >= 0),
            wins                INTEGER NOT NULL DEFAULT 0,
            losses              INTEGER NOT NULL DEFAULT 0,
            tasks_completed     INTEGER NOT NULL DEFAULT 0,
            last_interest_at    TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- Transactions history
        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            type            TEXT NOT NULL,
            amount          INTEGER NOT NULL,
            balance_after   INTEGER,
            related_user_id INTEGER,
            description     TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (related_user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);

        -- Games
        CREATE TABLE IF NOT EXISTS games (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            description     TEXT,
            prize           INTEGER NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'created'
                            CHECK (status IN ('created', 'open', 'running', 'finished', 'cancelled')),
            winner_id       INTEGER,
            created_by      INTEGER NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            started_at      TEXT,
            finished_at     TEXT,
            FOREIGN KEY (winner_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS game_participants (
            game_id     INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            joined_at   TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (game_id, user_id),
            FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- Math tasks configuration & attempts
        CREATE TABLE IF NOT EXISTS task_settings (
            id                  INTEGER PRIMARY KEY CHECK (id = 1),
            daily_limit         INTEGER NOT NULL DEFAULT 20,
            streak_bonus        INTEGER NOT NULL DEFAULT 500,
            reward_beginner     INTEGER NOT NULL DEFAULT 50,
            reward_easy         INTEGER NOT NULL DEFAULT 100,
            reward_medium       INTEGER NOT NULL DEFAULT 200,
            reward_advanced     INTEGER NOT NULL DEFAULT 400,
            reward_hard         INTEGER NOT NULL DEFAULT 700,
            reward_expert       INTEGER NOT NULL DEFAULT 1200,
            timer_seconds       INTEGER NOT NULL DEFAULT 60
        );

        INSERT OR IGNORE INTO task_settings (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS task_attempts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            level           TEXT NOT NULL,
            expression      TEXT NOT NULL,
            correct_answer  TEXT NOT NULL,
            user_answer     TEXT,
            is_correct      INTEGER,
            reward          INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_task_attempts_user_date
            ON task_attempts(user_id, created_at);

        -- Daily bonuses
        CREATE TABLE IF NOT EXISTS daily_bonuses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount      INTEGER NOT NULL,
            claimed_at  TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_bonus_user_day
            ON daily_bonuses(user_id, date(claimed_at));

        -- Economy settings
        CREATE TABLE IF NOT EXISTS economy_settings (
            id                      INTEGER PRIMARY KEY CHECK (id = 1),
            daily_bonus_amount      INTEGER NOT NULL DEFAULT 1000,
            initial_balance         INTEGER NOT NULL DEFAULT 5000,
            savings_rate            REAL NOT NULL DEFAULT 0.01,
            savings_period_hours    INTEGER NOT NULL DEFAULT 24,
            max_transfer            INTEGER NOT NULL DEFAULT 100000000
        );

        INSERT OR IGNORE INTO economy_settings (id) VALUES (1);

        -- Admin security
        CREATE TABLE IF NOT EXISTS security_settings (
            id                  INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash       TEXT,
            totp_secret         TEXT,
            totp_enabled        INTEGER NOT NULL DEFAULT 0,
            backup_codes        TEXT,
            failed_attempts     INTEGER NOT NULL DEFAULT 0,
            locked_until        TEXT,
            last_totp_used      TEXT
        );

        INSERT OR IGNORE INTO security_settings (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS admin_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id     INTEGER NOT NULL,
            session_token   TEXT NOT NULL UNIQUE,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at      TEXT NOT NULL,
            is_active       INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS admin_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id        INTEGER NOT NULL,
            action          TEXT NOT NULL,
            target_user_id  INTEGER,
            amount          INTEGER,
            reason          TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_admin_logs_created ON admin_logs(created_at);
        """
    )
