"""
Savings account: deposit, withdraw, interest accrual.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from database.db import get_db
from economy import change_balance, get_economy_settings
from models import User


async def deposit_to_savings(user: User, amount: int) -> tuple[int, int]:
    """Move money from main to savings. Returns (new_main, new_savings)."""
    if amount <= 0:
        raise ValueError("Сумма должна быть положительной")
    if user.main_balance < amount:
        raise ValueError("Недостаточно средств на основном счёте")

    new_main = await change_balance(
        user.id,
        -amount,
        "savings_deposit",
        description="Пополнение накопительного счёта",
        account="main",
    )
    new_sav = await change_balance(
        user.id,
        amount,
        "savings_deposit",
        description="Пополнение накопительного счёта",
        account="savings",
    )
    return new_main, new_sav


async def withdraw_from_savings(user: User, amount: int) -> tuple[int, int]:
    """Move money from savings to main."""
    if amount <= 0:
        raise ValueError("Сумма должна быть положительной")
    if user.savings_balance < amount:
        raise ValueError("Недостаточно средств на накопительном счёте")

    new_sav = await change_balance(
        user.id,
        -amount,
        "savings_withdraw",
        description="Снятие с накопительного счёта",
        account="savings",
    )
    new_main = await change_balance(
        user.id,
        amount,
        "savings_withdraw",
        description="Снятие с накопительного счёта",
        account="main",
    )
    return new_main, new_sav


async def accrue_interest(user_id: int) -> int:
    """
    Accrue interest if period has passed.
    Returns amount accrued (0 if not due).
    Protected against double accrual after restart.
    """
    db = await get_db()
    settings = await get_economy_settings()
    rate = float(settings.get("savings_rate", 0.01))
    period_hours = int(settings.get("savings_period_hours", 24))

    async with db.execute(
        "SELECT savings_balance, last_interest_at FROM accounts WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        if not row or row["savings_balance"] <= 0:
            return 0
        balance = row["savings_balance"]
        last = row["last_interest_at"]

    now = datetime.utcnow()
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if now - last_dt < timedelta(hours=period_hours):
                return 0
        except Exception:
            pass

    interest = int(balance * rate)
    if interest <= 0:
        # Still update timestamp to prevent rapid re-checks
        await db.execute(
            "UPDATE accounts SET last_interest_at = ? WHERE user_id = ?",
            (now.isoformat(), user_id),
        )
        await db.commit()
        return 0

    new_balance = await change_balance(
        user_id,
        interest,
        "savings_interest",
        description=f"Начисление процентов ({rate * 100:.2f}%)",
        account="savings",
    )
    await db.execute(
        "UPDATE accounts SET last_interest_at = ? WHERE user_id = ?",
        (now.isoformat(), user_id),
    )
    await db.commit()
    return interest
