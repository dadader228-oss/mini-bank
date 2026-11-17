"""
Data models and repository helpers for MINI BANK.
All amounts are integers (kopecks).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from database.db import get_db


@dataclass
class User:
    id: int
    telegram_id: int
    username: Optional[str]
    full_name: str
    card_number: str
    is_blocked: bool
    created_at: str
    main_balance: int = 0
    savings_balance: int = 0
    wins: int = 0
    losses: int = 0
    tasks_completed: int = 0


def format_money(kopecks: int) -> str:
    """Format integer kopecks as human-readable rubles."""
    sign = "-" if kopecks < 0 else ""
    abs_val = abs(kopecks)
    rubles = abs_val // 100
    kop = abs_val % 100
    return f"{sign}{rubles:,}.{kop:02d} ₽".replace(",", " ")


async def get_next_card_number() -> str:
    """Generate next unique card number MB-XXXXXX."""
    db = await get_db()
    async with db.execute("SELECT COUNT(*) AS cnt FROM users") as cursor:
        row = await cursor.fetchone()
        count = row["cnt"] if row else 0
    return f"MB-{count + 1:06d}"


async def create_user(
    telegram_id: int,
    username: Optional[str],
    full_name: str,
    initial_balance: int,
) -> User:
    """Register a new user with main account and unique card."""
    db = await get_db()
    card = await get_next_card_number()

    async with db.execute(
        """
        INSERT INTO users (telegram_id, username, full_name, card_number)
        VALUES (?, ?, ?, ?)
        """,
        (telegram_id, username, full_name, card),
    ) as cursor:
        user_id = cursor.lastrowid

    await db.execute(
        """
        INSERT INTO accounts (user_id, main_balance, savings_balance)
        VALUES (?, ?, 0)
        """,
        (user_id, initial_balance),
    )

    # Initial deposit transaction
    await db.execute(
        """
        INSERT INTO transactions (user_id, type, amount, balance_after, description)
        VALUES (?, 'initial', ?, ?, 'Начальный баланс')
        """,
        (user_id, initial_balance, initial_balance),
    )
    await db.commit()

    return User(
        id=user_id,
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        card_number=card,
        is_blocked=False,
        created_at=datetime.utcnow().isoformat(),
        main_balance=initial_balance,
        savings_balance=0,
    )


async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    """Fetch user with account balances by Telegram ID."""
    db = await get_db()
    async with db.execute(
        """
        SELECT u.*, a.main_balance, a.savings_balance, a.wins, a.losses, a.tasks_completed
        FROM users u
        LEFT JOIN accounts a ON a.user_id = u.id
        WHERE u.telegram_id = ?
        """,
        (telegram_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        return _row_to_user(row)


async def get_user_by_id(user_id: int) -> Optional[User]:
    db = await get_db()
    async with db.execute(
        """
        SELECT u.*, a.main_balance, a.savings_balance, a.wins, a.losses, a.tasks_completed
        FROM users u
        LEFT JOIN accounts a ON a.user_id = u.id
        WHERE u.id = ?
        """,
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        return _row_to_user(row)


async def get_user_by_card(card_number: str) -> Optional[User]:
    db = await get_db()
    async with db.execute(
        """
        SELECT u.*, a.main_balance, a.savings_balance, a.wins, a.losses, a.tasks_completed
        FROM users u
        LEFT JOIN accounts a ON a.user_id = u.id
        WHERE u.card_number = ?
        """,
        (card_number,),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        return _row_to_user(row)


def _row_to_user(row: Any) -> User:
    return User(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row["username"],
        full_name=row["full_name"],
        card_number=row["card_number"],
        is_blocked=bool(row["is_blocked"]),
        created_at=row["created_at"],
        main_balance=row["main_balance"] or 0,
        savings_balance=row["savings_balance"] or 0,
        wins=row["wins"] or 0,
        losses=row["losses"] or 0,
        tasks_completed=row["tasks_completed"] or 0,
    )


async def update_last_active(telegram_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE users SET last_active = datetime('now') WHERE telegram_id = ?",
        (telegram_id,),
    )
    await db.commit()


async def set_blocked(user_id: int, blocked: bool) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE users SET is_blocked = ? WHERE id = ?",
        (1 if blocked else 0, user_id),
    )
    await db.commit()


async def list_users(limit: int = 50, offset: int = 0) -> list[User]:
    db = await get_db()
    users: list[User] = []
    async with db.execute(
        """
        SELECT u.*, a.main_balance, a.savings_balance, a.wins, a.losses, a.tasks_completed
        FROM users u
        LEFT JOIN accounts a ON a.user_id = u.id
        ORDER BY u.id
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ) as cursor:
        async for row in cursor:
            users.append(_row_to_user(row))
    return users


async def count_users() -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) AS cnt FROM users") as cursor:
        row = await cursor.fetchone()
        return row["cnt"] if row else 0
