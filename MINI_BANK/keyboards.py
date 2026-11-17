"""
Inline keyboards for MINI BANK.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tasks import LEVELS


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 Мой счёт", callback_data="menu:account"),
        InlineKeyboardButton(text="💸 Перевести", callback_data="menu:transfer"),
    )
    builder.row(
        InlineKeyboardButton(text="🧠 Заработать", callback_data="menu:earn"),
        InlineKeyboardButton(text="🎮 Игры", callback_data="menu:games"),
    )
    builder.row(
        InlineKeyboardButton(text="🏦 Накопительный", callback_data="menu:savings"),
        InlineKeyboardButton(text="📜 История", callback_data="menu:history"),
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="menu:bonus"),
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
    )
    builder.row(
        InlineKeyboardButton(text="🏆 Топ участников", callback_data="menu:top"),
    )
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def account_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def transfer_start_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔢 По ID / карте", callback_data="transfer:by_id"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def confirm_transfer_kb(to_id: int, amount: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=f"transfer:confirm:{to_id}:{amount}",
        ),
        InlineKeyboardButton(text="❌ Отмена", callback_data="menu:main"),
    )
    return builder.as_markup()


def earn_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, title in LEVELS.items():
        builder.row(
            InlineKeyboardButton(text=title, callback_data=f"task:level:{key}")
        )
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def savings_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Пополнить", callback_data="savings:deposit"),
        InlineKeyboardButton(text="➖ Снять", callback_data="savings:withdraw"),
    )
    builder.row(
        InlineKeyboardButton(text="📈 Начислить %", callback_data="savings:interest"),
    )
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def history_nav_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"history:page:{page - 1}")
        )
    buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(text="➡️", callback_data=f"history:page:{page + 1}")
        )
    builder.row(*buttons)
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def games_user_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Открытые игры", callback_data="games:list"),
    )
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def join_game_kb(game_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Участвовать", callback_data=f"games:join:{game_id}"
        )
    )
    return builder.as_markup()


def admin_panel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users"),
        InlineKeyboardButton(text="💰 Балансы", callback_data="admin:balances"),
    )
    builder.row(
        InlineKeyboardButton(text="🎮 Игры", callback_data="admin:games"),
        InlineKeyboardButton(text="⚙️ Экономика", callback_data="admin:economy"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
        InlineKeyboardButton(text="📋 Журнал", callback_data="admin:logs"),
    )
    builder.row(
        InlineKeyboardButton(text="🔒 Выйти", callback_data="admin:logout"),
    )
    return builder.as_markup()


def admin_back_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ В панель", callback_data="admin:panel")
    )
    return builder.as_markup()
