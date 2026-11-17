"""
Common handlers: /start, main menu.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from config import OWNER_ID
from economy import get_economy_settings
from keyboards import main_menu_kb
from models import create_user, get_user_by_telegram_id, update_last_active

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return

    tg_id = message.from_user.id
    user = await get_user_by_telegram_id(tg_id)

    if user is None:
        settings = await get_economy_settings()
        initial = settings.get("initial_balance", 5000)
        full_name = message.from_user.full_name or "Пользователь"
        username = message.from_user.username
        user = await create_user(tg_id, username, full_name, initial)
        text = (
            f"👋 Добро пожаловать в <b>MINI BANK</b>!\n\n"
            f"Ваш счёт создан.\n"
            f"💳 Карта: <code>{user.card_number}</code>\n"
            f"💰 Начальный баланс: {initial / 100:.2f} ₽\n\n"
            f"Выберите действие:"
        )
    else:
        if user.is_blocked:
            await message.answer("⛔ Ваш аккаунт заблокирован.")
            return
        await update_last_active(tg_id)
        text = (
            f"👋 С возвращением, <b>{user.full_name}</b>!\n"
            f"💳 Карта: <code>{user.card_number}</code>\n\n"
            f"Выберите действие:"
        )

    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user:
        return
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.is_blocked:
        await callback.message.edit_text("⛔ Доступ запрещён.")
        return
    await callback.message.edit_text(
        f"🏦 <b>MINI BANK</b>\n💳 {user.card_number}\n\nВыберите действие:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
