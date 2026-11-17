"""
Economy helpers: settings, balance operations (atomic).
"""

from __future__ import annotations

from typing import Optional

from database.db import get_db
from models import format_money


async def get_economy_settings() -> dict:
    db = await get_db()
    async with db.execute("SELECT * FROM economy_settings WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else {}


async def update_economy_setting(key: str, value) -> None:
    allowed = {
        "daily_bonus_amount",
        "initial_balance",
        "savings_rate",
        "savings_period_hours",
        "max_transfer",
    }
    if key not in allowed:
        raise ValueError(f"Unknown setting: {key}")
    db = await get_db()
    await db.execute(
        f"UPDATE economy_settings SET {key} = ? WHERE id = 1",
        (value,),
    )
    await db.commit()


async def change_balance(
    user_id: int,
    amount: int,
    tx_type: str,
    description: str = "",
    related_user_id: Optional[int] = None,
    account: str = "main",
) -> int:
    """
    Atomically change main or savings balance.
    amount can be positive (credit) or negative (debit).
    Returns new balance.
    Raises ValueError on insufficient funds.
    """
    if amount == 0:
        raise ValueError("Amount cannot be zero")

    db = await get_db()
    balance_col = "main_balance" if account == "main" else "savings_balance"

    async with db.execute(
        f"SELECT {balance_col} FROM accounts WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise ValueError("Account not found")
        current = row[balance_col]

    new_balance = current + amount
    if new_balance < 0:
        raise ValueError("Insufficient funds")

    await db.execute(
        f"UPDATE accounts SET {balance_col} = ? WHERE user_id = ?",
        (new_balance, user_id),
    )
    await db.execute(
        """
        INSERT INTO transactions
            (user_id, type, amount, balance_after, related_user_id, description)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, tx_type, amount, new_balance, related_user_id, description),
    )
    await db.commit()
    return new_balance


async def get_transactions(
    user_id: int,
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    db = await get_db()
    rows = []
    async with db.execute(
        """
        SELECT t.*, u.full_name AS related_name, u.card_number AS related_card
        FROM transactions t
        LEFT JOIN users u ON u.id = t.related_user_id
        WHERE t.user_id = ?
        ORDER BY t.id DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset),
    ) as cursor:
        async for row in cursor:
            rows.append(dict(row))
    return rows


async def count_transactions(user_id: int) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS cnt FROM transactions WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return row["cnt"] if row else 0


async def total_system_balance() -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COALESCE(SUM(main_balance + savings_balance), 0) AS total FROM accounts"
    ) as cursor:
        row = await cursor.fetchone()
        return row["total"] if row else 0
