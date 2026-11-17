"""
Helper for sending notifications to users.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from models import format_money


async def notify_user(bot: Bot, telegram_id: int, text: str) -> bool:
    try:
        await bot.send_message(telegram_id, text, parse_mode="HTML")
        return True
    except TelegramAPIError:
        return False


async def notify_transfer(
    bot: Bot,
    sender_tg: int,
    receiver_tg: int,
    amount: int,
    sender_name: str,
    receiver_name: str,
    sender_card: str,
    receiver_card: str,
) -> None:
    amount_str = format_money(amount)
    await notify_user(
        bot,
        sender_tg,
        f"✅ Перевод выполнен\n\n"
        f"Получатель: <b>{receiver_name}</b> ({receiver_card})\n"
        f"Сумма: <b>{amount_str}</b>",
    )
    await notify_user(
        bot,
        receiver_tg,
        f"💰 Вам поступил перевод\n\n"
        f"Отправитель: <b>{sender_name}</b> ({sender_card})\n"
        f"Сумма: <b>{amount_str}</b>",
    )
