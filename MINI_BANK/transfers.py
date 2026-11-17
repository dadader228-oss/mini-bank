"""
Money transfer logic with atomicity and validation.
"""

from __future__ import annotations

from typing import Optional

from database.db import get_db
from economy import change_balance, get_economy_settings
from models import User, format_money, get_user_by_id, get_user_by_telegram_id


class TransferError(Exception):
    pass


async def transfer(
    from_user: User,
    to_user: User,
    amount: int,
) -> tuple[int, int]:
    """
    Transfer amount (kopecks) from from_user to to_user.
    Returns (new_from_balance, new_to_balance).
    """
    if amount <= 0:
        raise TransferError("Сумма должна быть положительной")
    if from_user.id == to_user.id:
        raise TransferError("Нельзя перевести самому себе")
    if from_user.is_blocked or to_user.is_blocked:
        raise TransferError("Один из участников заблокирован")

    settings = await get_economy_settings()
    max_transfer = settings.get("max_transfer", 100_000_000)
    if amount > max_transfer:
        raise TransferError(f"Максимальная сумма перевода: {format_money(max_transfer)}")

    if from_user.main_balance < amount:
        raise TransferError("Недостаточно средств")

    db = await get_db()
    try:
        # Debit sender
        new_from = await change_balance(
            from_user.id,
            -amount,
            "transfer_out",
            description=f"Перевод пользователю {to_user.full_name} ({to_user.card_number})",
            related_user_id=to_user.id,
            account="main",
        )
        # Credit receiver
        new_to = await change_balance(
            to_user.id,
            amount,
            "transfer_in",
            description=f"Перевод от {from_user.full_name} ({from_user.card_number})",
            related_user_id=from_user.id,
            account="main",
        )
        return new_from, new_to
    except ValueError as e:
        raise TransferError(str(e)) from e


async def find_recipient(identifier: str) -> Optional[User]:
    """Find user by Telegram ID or card number."""
    identifier = identifier.strip()
    if identifier.isdigit():
        return await get_user_by_telegram_id(int(identifier))
    if identifier.upper().startswith("MB-"):
        from models import get_user_by_card
        return await get_user_by_card(identifier.upper())
    return None
