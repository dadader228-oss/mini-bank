"""
Security module: password hashing (Argon2id), TOTP, admin sessions.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from config import (
    ADMIN_SESSION_TIMEOUT_MINUTES,
    LOCKOUT_MINUTES,
    MAX_LOGIN_ATTEMPTS,
    TOTP_WINDOW,
)
from database.db import get_db

ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, account_name: str = "MINI BANK Admin") -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=account_name, issuer_name="MINI BANK")


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code or len(code) != 6 or not code.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=TOTP_WINDOW)


def generate_backup_codes(count: int = 8) -> list[str]:
    return [secrets.token_hex(4).upper() for _ in range(count)]


async def get_security_settings() -> dict:
    db = await get_db()
    async with db.execute("SELECT * FROM security_settings WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        if not row:
            return {}
        return dict(row)


async def set_password_hash(password_hash: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE security_settings SET password_hash = ? WHERE id = 1",
        (password_hash,),
    )
    await db.commit()


async def set_totp_secret(secret: str, enabled: bool = True) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE security_settings SET totp_secret = ?, totp_enabled = ? WHERE id = 1",
        (secret, 1 if enabled else 0),
    )
    await db.commit()


async def set_backup_codes(codes: list[str]) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE security_settings SET backup_codes = ? WHERE id = 1",
        (",".join(codes),),
    )
    await db.commit()


async def is_locked() -> bool:
    settings = await get_security_settings()
    locked_until = settings.get("locked_until")
    if not locked_until:
        return False
    try:
        until = datetime.fromisoformat(locked_until)
        return datetime.utcnow() < until
    except Exception:
        return False


async def record_failed_attempt() -> None:
    db = await get_db()
    settings = await get_security_settings()
    attempts = (settings.get("failed_attempts") or 0) + 1
    locked_until = None
    if attempts >= MAX_LOGIN_ATTEMPTS:
        locked_until = (
            datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        ).isoformat()
        attempts = 0
    await db.execute(
        """
        UPDATE security_settings
        SET failed_attempts = ?, locked_until = ?
        WHERE id = 1
        """,
        (attempts, locked_until),
    )
    await db.commit()


async def reset_failed_attempts() -> None:
    db = await get_db()
    await db.execute(
        "UPDATE security_settings SET failed_attempts = 0, locked_until = NULL WHERE id = 1"
    )
    await db.commit()


async def create_admin_session(telegram_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(minutes=ADMIN_SESSION_TIMEOUT_MINUTES)
    db = await get_db()
    # Deactivate old sessions
    await db.execute(
        "UPDATE admin_sessions SET is_active = 0 WHERE telegram_id = ?",
        (telegram_id,),
    )
    await db.execute(
        """
        INSERT INTO admin_sessions (telegram_id, session_token, expires_at)
        VALUES (?, ?, ?)
        """,
        (telegram_id, token, expires.isoformat()),
    )
    await db.commit()
    return token


async def validate_admin_session(telegram_id: int, token: str) -> bool:
    db = await get_db()
    async with db.execute(
        """
        SELECT expires_at FROM admin_sessions
        WHERE telegram_id = ? AND session_token = ? AND is_active = 1
        """,
        (telegram_id, token),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return False
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.utcnow() > expires:
                await db.execute(
                    "UPDATE admin_sessions SET is_active = 0 WHERE session_token = ?",
                    (token,),
                )
                await db.commit()
                return False
            return True
        except Exception:
            return False


async def invalidate_admin_session(telegram_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE admin_sessions SET is_active = 0 WHERE telegram_id = ?",
        (telegram_id,),
    )
    await db.commit()


async def log_admin_action(
    admin_id: int,
    action: str,
    target_user_id: Optional[int] = None,
    amount: Optional[int] = None,
    reason: Optional[str] = None,
) -> None:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO admin_logs (admin_id, action, target_user_id, amount, reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        (admin_id, action, target_user_id, amount, reason),
    )
    await db.commit()
