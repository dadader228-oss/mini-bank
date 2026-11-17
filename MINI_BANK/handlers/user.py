"""
User-facing handlers: account, transfer, tasks, savings, bonus, profile, history, games, top.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bonuses import can_claim_daily, claim_daily_bonus
from economy import get_transactions, count_transactions
from games import get_game, get_participants, join_game, list_games, GameError
from keyboards import (
    account_kb,
    back_to_menu_kb,
    confirm_transfer_kb,
    earn_kb,
    games_user_kb,
    history_nav_kb,
    join_game_kb,
    main_menu_kb,
    savings_kb,
    transfer_start_kb,
)
from models import (
    User,
    format_money,
    get_user_by_telegram_id,
    list_users,
    update_last_active,
)
from notifications import notify_transfer
from savings import accrue_interest, deposit_to_savings, withdraw_from_savings
from tasks import LEVELS, check_answer, create_task_attempt
from transfers import TransferError, find_recipient, transfer

router = Router(name="user")


class TransferStates(StatesGroup):
    waiting_recipient = State()
    waiting_amount = State()


class SavingsStates(StatesGroup):
    waiting_deposit = State()
    waiting_withdraw = State()


class TaskStates(StatesGroup):
    waiting_answer = State()


# ── Account ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:account")
async def cb_account(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.is_blocked:
        return
    text = (
        f"💳 <b>Мой счёт</b>\n\n"
        f"Карта: <code>{user.card_number}</code>\n"
        f"Основной баланс: <b>{format_money(user.main_balance)}</b>\n"
        f"Накопительный: <b>{format_money(user.savings_balance)}</b>\n"
        f"Всего: <b>{format_money(user.main_balance + user.savings_balance)}</b>"
    )
    await callback.message.edit_text(text, reply_markup=account_kb(), parse_mode="HTML")


# ── Profile ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:profile")
async def cb_profile(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.is_blocked:
        return
    uname = f"@{user.username}" if user.username else "—"
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: {user.full_name}\n"
        f"Username: {uname}\n"
        f"Telegram ID: <code>{user.telegram_id}</code>\n"
        f"💳 Карта: <code>{user.card_number}</code>\n"
        f"Дата регистрации: {user.created_at[:10]}\n\n"
        f"🏆 Побед: {user.wins} | Поражений: {user.losses}\n"
        f"🧠 Заданий выполнено: {user.tasks_completed}"
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")


# ── Transfer ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:transfer")
async def cb_transfer_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "💸 <b>Перевод средств</b>\n\nВыберите способ:",
        reply_markup=transfer_start_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "transfer:by_id")
async def cb_transfer_by_id(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(TransferStates.waiting_recipient)
    await callback.message.edit_text(
        "Введите Telegram ID или номер карты (MB-XXXXXX) получателя:",
        reply_markup=back_to_menu_kb(),
    )


@router.message(TransferStates.waiting_recipient)
async def process_recipient(message: Message, state: FSMContext) -> None:
    recipient = await find_recipient(message.text or "")
    if not recipient:
        await message.answer("Пользователь не найден. Попробуйте ещё раз или /start")
        return
    me = await get_user_by_telegram_id(message.from_user.id)
    if me and me.id == recipient.id:
        await message.answer("Нельзя перевести самому себе.")
        return
    await state.update_data(to_user_id=recipient.id, to_name=recipient.full_name)
    await state.set_state(TransferStates.waiting_amount)
    await message.answer(
        f"Получатель: <b>{recipient.full_name}</b> ({recipient.card_number})\n\n"
        f"Введите сумму в рублях (например 10.50):",
        parse_mode="HTML",
        reply_markup=back_to_menu_kb(),
    )


@router.message(TransferStates.waiting_amount)
async def process_amount(message: Message, state: FSMContext) -> None:
    text = (message.text or "").replace(",", ".").strip()
    try:
        rubles = float(text)
        if rubles <= 0:
            raise ValueError
        amount = int(round(rubles * 100))
    except ValueError:
        await message.answer("Некорректная сумма. Введите число, например 25.50")
        return

    data = await state.get_data()
    to_id = data.get("to_user_id")
    to_name = data.get("to_name", "")
    await state.clear()

    me = await get_user_by_telegram_id(message.from_user.id)
    if not me:
        return

    await message.answer(
        f"Подтвердите перевод:\n\n"
        f"Кому: <b>{to_name}</b>\n"
        f"Сумма: <b>{format_money(amount)}</b>\n"
        f"Ваш баланс: {format_money(me.main_balance)}",
        reply_markup=confirm_transfer_kb(to_id, amount),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("transfer:confirm:"))
async def cb_confirm_transfer(callback: CallbackQuery) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) != 4:
        return
    to_id = int(parts[2])
    amount = int(parts[3])

    from models import get_user_by_id as get_user_by_pk
    from_user = await get_user_by_telegram_id(callback.from_user.id)
    to_user = await get_user_by_pk(to_id)
    if not from_user or not to_user:
        await callback.message.edit_text("Ошибка: пользователь не найден.")
        return

    try:
        new_from, _ = await transfer(from_user, to_user, amount)
        await notify_transfer(
            callback.bot,
            from_user.telegram_id,
            to_user.telegram_id,
            amount,
            from_user.full_name,
            to_user.full_name,
            from_user.card_number,
            to_user.card_number,
        )
        await callback.message.edit_text(
            f"✅ Перевод выполнен!\n"
            f"Списано: {format_money(amount)}\n"
            f"Новый баланс: {format_money(new_from)}",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
    except TransferError as e:
        await callback.message.edit_text(
            f"❌ {e}",
            reply_markup=back_to_menu_kb(),
        )


# ── Daily bonus ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:bonus")
async def cb_bonus(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.is_blocked:
        return

    can, next_at = await can_claim_daily(user.id)
    if not can:
        await callback.message.edit_text(
            f"🎁 Ежедневный бонус уже получен.\n"
            f"Следующий доступен: {next_at[:16] if next_at else 'завтра'}",
            reply_markup=back_to_menu_kb(),
        )
        return

    try:
        amount = await claim_daily_bonus(user)
        await callback.message.edit_text(
            f"🎁 Вы получили ежедневный бонус: <b>{format_money(amount)}</b>!",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
    except ValueError as e:
        await callback.message.edit_text(str(e), reply_markup=back_to_menu_kb())


# ── Savings ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:savings")
async def cb_savings(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.is_blocked:
        return
    # Try accrue on view
    interest = await accrue_interest(user.id)
    user = await get_user_by_telegram_id(callback.from_user.id)  # refresh
    extra = ""
    if interest > 0:
        extra = f"\n\n📈 Начислено процентов: {format_money(interest)}"
    text = (
        f"🏦 <b>Накопительный счёт</b>\n\n"
        f"Баланс: <b>{format_money(user.savings_balance)}</b>"
        f"{extra}"
    )
    await callback.message.edit_text(text, reply_markup=savings_kb(), parse_mode="HTML")


@router.callback_query(F.data == "savings:deposit")
async def cb_savings_deposit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SavingsStates.waiting_deposit)
    await callback.message.edit_text(
        "Введите сумму пополнения накопительного счёта (в рублях):",
        reply_markup=back_to_menu_kb(),
    )


@router.callback_query(F.data == "savings:withdraw")
async def cb_savings_withdraw(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SavingsStates.waiting_withdraw)
    await callback.message.edit_text(
        "Введите сумму снятия с накопительного счёта (в рублях):",
        reply_markup=back_to_menu_kb(),
    )


@router.callback_query(F.data == "savings:interest")
async def cb_savings_interest(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        return
    amount = await accrue_interest(user.id)
    if amount > 0:
        await callback.message.edit_text(
            f"📈 Начислено: <b>{format_money(amount)}</b>",
            reply_markup=savings_kb(),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            "Проценты пока не начисляются (период не истёк или баланс 0).",
            reply_markup=savings_kb(),
        )


@router.message(SavingsStates.waiting_deposit)
async def process_deposit(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        rubles = float((message.text or "").replace(",", "."))
        amount = int(round(rubles * 100))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Некорректная сумма.", reply_markup=back_to_menu_kb())
        return
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return
    try:
        new_main, new_sav = await deposit_to_savings(user, amount)
        await message.answer(
            f"✅ Пополнено.\nОсновной: {format_money(new_main)}\n"
            f"Накопительный: {format_money(new_sav)}",
            reply_markup=back_to_menu_kb(),
        )
    except ValueError as e:
        await message.answer(f"❌ {e}", reply_markup=back_to_menu_kb())


@router.message(SavingsStates.waiting_withdraw)
async def process_withdraw(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        rubles = float((message.text or "").replace(",", "."))
        amount = int(round(rubles * 100))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Некорректная сумма.", reply_markup=back_to_menu_kb())
        return
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return
    try:
        new_main, new_sav = await withdraw_from_savings(user, amount)
        await message.answer(
            f"✅ Снято.\nОсновной: {format_money(new_main)}\n"
            f"Накопительный: {format_money(new_sav)}",
            reply_markup=back_to_menu_kb(),
        )
    except ValueError as e:
        await message.answer(f"❌ {e}", reply_markup=back_to_menu_kb())


# ── Tasks / Earn ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:earn")
async def cb_earn(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "🧠 <b>Математические задания</b>\n\nВыберите уровень сложности:",
        reply_markup=earn_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task:level:"))
async def cb_task_level(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    level = callback.data.split(":")[-1]
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        return
    try:
        attempt = await create_task_attempt(user.id, level)
        await state.set_state(TaskStates.waiting_answer)
        await state.update_data(attempt_id=attempt["id"])
        await callback.message.edit_text(
            f"Уровень: <b>{LEVELS.get(level, level)}</b>\n"
            f"Награда: {format_money(attempt['reward'])}\n\n"
            f"Решите: <code>{attempt['expression']}</code>\n\n"
            f"Введите ответ:",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
    except ValueError as e:
        await callback.message.edit_text(str(e), reply_markup=back_to_menu_kb())


@router.message(TaskStates.waiting_answer)
async def process_task_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    attempt_id = data.get("attempt_id")
    await state.clear()
    if not attempt_id:
        return
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        return
    try:
        result = await check_answer(attempt_id, user.id, message.text or "")
        if result["is_correct"]:
            text = (
                f"✅ Верно! +{format_money(result['reward'])}"
            )
        else:
            text = (
                f"❌ Неверно. Правильный ответ: {result['correct_answer']}"
            )
        await message.answer(text, reply_markup=back_to_menu_kb())
    except ValueError as e:
        await message.answer(str(e), reply_markup=back_to_menu_kb())


# ── History ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:history")
async def cb_history(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_history(callback, page=0)


@router.callback_query(F.data.startswith("history:page:"))
async def cb_history_page(callback: CallbackQuery) -> None:
    await callback.answer()
    page = int(callback.data.split(":")[-1])
    await _show_history(callback, page=page)


async def _show_history(callback: CallbackQuery, page: int) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        return
    per_page = 8
    total = await count_transactions(user.id)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    txs = await get_transactions(user.id, limit=per_page, offset=page * per_page)

    if not txs:
        text = "📜 История пуста."
    else:
        lines = ["📜 <b>История операций</b>\n"]
        for t in txs:
            sign = "+" if t["amount"] > 0 else ""
            related = ""
            if t.get("related_name"):
                related = f" ({t['related_name']})"
            lines.append(
                f"<code>{t['created_at'][:16]}</code> "
                f"{sign}{format_money(t['amount'])} "
                f"— {t['type']}{related}"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=history_nav_kb(page, total_pages),
        parse_mode="HTML",
    )


# ── Games (user) ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:games")
async def cb_games(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "🎮 <b>Игры</b>\n\nОткрытые игры и ваша статистика.",
        reply_markup=games_user_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "games:list")
async def cb_games_list(callback: CallbackQuery) -> None:
    await callback.answer()
    games = await list_games(10)
    open_games = [g for g in games if g["status"] == "open"]
    if not open_games:
        await callback.message.edit_text(
            "Сейчас нет открытых игр.",
            reply_markup=back_to_menu_kb(),
        )
        return
    lines = ["📋 <b>Открытые игры:</b>\n"]
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for g in open_games:
        lines.append(f"• {g['title']} — приз {format_money(g['prize'])}")
        builder.row(
            InlineKeyboardButton(
                text=f"Участвовать: {g['title'][:20]}",
                callback_data=f"games:join:{g['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:games"))
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("games:join:"))
async def cb_join_game(callback: CallbackQuery) -> None:
    await callback.answer()
    game_id = int(callback.data.split(":")[-1])
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        return
    try:
        await join_game(game_id, user)
        await callback.message.edit_text(
            "✅ Вы успешно присоединились к игре!",
            reply_markup=back_to_menu_kb(),
        )
    except GameError as e:
        await callback.message.edit_text(f"❌ {e}", reply_markup=back_to_menu_kb())


# ── Top ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:top")
async def cb_top(callback: CallbackQuery) -> None:
    await callback.answer()
    users = await list_users(limit=15)
    # Sort by total balance desc
    users_sorted = sorted(
        users,
        key=lambda u: u.main_balance + u.savings_balance,
        reverse=True,
    )
    lines = ["🏆 <b>Топ участников по балансу</b>\n"]
    for i, u in enumerate(users_sorted[:10], 1):
        total = u.main_balance + u.savings_balance
        lines.append(
            f"{i}. {u.full_name} — {format_money(total)} ({u.card_number})"
        )
    await callback.message.edit_text(
        "\n".join(lines) if lines else "Пока нет участников.",
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )
