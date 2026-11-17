"""
Daily bonus system.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from config import TIMEZONE
from database.db import get_db
from economy import change_balance, get_economy_settings
from models import User


async def can_claim_daily(user_id: int) -> tuple[bool, Optional[str]]:
    """
    Returns (can_claim, next_available_iso or None).
    """
    db = await get_db()
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with db.execute(
        """
        SELECT claimed_at FROM daily_bonuses
        WHERE user_id = ? AND date(claimed_at) = date(?)
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, now.isoformat()),
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            next_day = today_start + timedelta(days=1)
            return False, next_day.isoformat()
    return True, None


async def claim_daily_bonus(user: User) -> int:
    """Claim daily bonus. Returns amount in kopecks."""
    can, next_at = await can_claim_daily(user.id)
    if not can:
        raise ValueError(f"Бонус уже получен. Следующий доступен: {next_at}")

    settings = await get_economy_settings()
    amount = settings.get("daily_bonus_amount", 1000)

    await change_balance(
        user.id,
        amount,
        "daily_bonus",
        description="Ежедневный бонус",
        account="main",
    )

    db = await get_db()
    await db.execute(
        "INSERT INTO daily_bonuses (user_id, amount) VALUES (?, ?)",
        (user.id, amount),
    )
    await db.commit()
    return amount
