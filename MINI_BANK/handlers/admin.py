"""
Admin panel handlers with password + TOTP authentication.
"""

from __future__ import annotations

import io
from typing import Optional

import qrcode
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from config import OWNER_ID
from economy import (
    change_balance,
    get_economy_settings,
    total_system_balance,
    update_economy_setting,
)
from games import (
    GameError,
    cancel_game,
    create_game,
    finish_game,
    get_game,
    get_participants,
    list_games,
    open_game,
    start_game,
)
from keyboards import admin_back_kb, admin_panel_kb, back_to_menu_kb
from models import (
    count_users,
    format_money,
    get_user_by_id,
    get_user_by_telegram_id,
    list_users,
    set_blocked,
)
from security import (
    create_admin_session,
    generate_backup_codes,
    generate_totp_secret,
    get_security_settings,
    get_totp_uri,
    hash_password,
    invalidate_admin_session,
    is_locked,
    log_admin_action,
    record_failed_attempt,
    reset_failed_attempts,
    set_backup_codes,
    set_password_hash,
    set_totp_secret,
    validate_admin_session,
    verify_password,
    verify_totp,
)
from tasks import get_task_settings, update_task_setting

router = Router(name="admin")

# In-memory session tokens for simplicity (also stored in DB)
_admin_tokens: dict[int, str] = {}


class AdminAuth(StatesGroup):
    waiting_password = State()
    waiting_totp = State()
    setup_password = State()
    setup_totp_confirm = State()


class AdminActions(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()
    waiting_reason = State()
    waiting_game_title = State()
    waiting_game_desc = State()
    waiting_game_prize = State()
    waiting_setting_value = State()


def _is_owner(telegram_id: int) -> bool:
    return telegram_id == OWNER_ID


async def _require_admin(telegram_id: int) -> bool:
    if not _is_owner(telegram_id):
        return False
    token = _admin_tokens.get(telegram_id)
    if not token:
        return False
    return await validate_admin_session(telegram_id, token)


# ── Entry ────────────────────────────────────────────────────────────────────

@router.message(Command("apanel"))
async def cmd_apanel(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_owner(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    if await is_locked():
        await message.answer("🔒 Админ-панель временно заблокирована. Попробуйте позже.")
        return

    settings = await get_security_settings()
    pwd_hash = settings.get("password_hash")

    if not pwd_hash:
        await state.set_state(AdminAuth.setup_password)
        await message.answer(
            "🔐 <b>Первоначальная настройка администратора</b>\n\n"
            "Придумайте надёжный пароль (минимум 8 символов) и отправьте его:",
            parse_mode="HTML",
        )
        return

    # Check existing session
    if await _require_admin(message.from_user.id):
        await message.answer(
            "🔓 Админ-панель",
            reply_markup=admin_panel_kb(),
        )
        return

    await state.set_state(AdminAuth.waiting_password)
    await message.answer("🔐 Введите пароль администратора:")


@router.message(AdminAuth.setup_password)
async def setup_password(message: Message, state: FSMContext) -> None:
    pwd = (message.text or "").strip()
    if len(pwd) < 8:
        await message.answer("Пароль слишком короткий (минимум 8 символов).")
        return
    h = hash_password(pwd)
    await set_password_hash(h)
    # Setup TOTP
    secret = generate_totp_secret()
    await state.update_data(totp_secret=secret)
    await state.set_state(AdminAuth.setup_totp_confirm)

    uri = get_totp_uri(secret)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    await message.answer_photo(
        BufferedInputFile(buf.read(), filename="totp_qr.png"),
        caption=(
            "📱 Отсканируйте QR-код в Google Authenticator (или Authy).\n\n"
            f"Или введите секрет вручную:\n<code>{secret}</code>\n\n"
            "После добавления введите текущий 6-значный код:"
        ),
        parse_mode="HTML",
    )


@router.message(AdminAuth.setup_totp_confirm)
async def setup_totp_confirm(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip()
    data = await state.get_data()
    secret = data.get("totp_secret")
    if not secret or not verify_totp(secret, code):
        await message.answer("Неверный код. Попробуйте ещё раз:")
        return

    await set_totp_secret(secret, enabled=True)
    codes = generate_backup_codes()
    await set_backup_codes(codes)
    await state.clear()

    token = await create_admin_session(message.from_user.id)
    _admin_tokens[message.from_user.id] = token

    codes_text = "\n".join(f"<code>{c}</code>" for c in codes)
    await message.answer(
        f"✅ Двухфакторная аутентификация активирована!\n\n"
        f"Резервные коды (сохраните в надёжном месте):\n{codes_text}\n\n"
        f"Админ-панель открыта.",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML",
    )


@router.message(AdminAuth.waiting_password)
async def process_admin_password(message: Message, state: FSMContext) -> None:
    settings = await get_security_settings()
    pwd_hash = settings.get("password_hash")
    if not pwd_hash or not verify_password(pwd_hash, message.text or ""):
        await record_failed_attempt()
        await message.answer("❌ Неверный пароль.")
        await state.clear()
        return

    if settings.get("totp_enabled"):
        await state.set_state(AdminAuth.waiting_totp)
        await message.answer("📱 Введите 6-значный код из Google Authenticator:")
    else:
        await reset_failed_attempts()
        token = await create_admin_session(message.from_user.id)
        _admin_tokens[message.from_user.id] = token
        await state.clear()
        await message.answer("🔓 Админ-панель", reply_markup=admin_panel_kb())


@router.message(AdminAuth.waiting_totp)
async def process_admin_totp(message: Message, state: FSMContext) -> None:
    settings = await get_security_settings()
    secret = settings.get("totp_secret")
    code = (message.text or "").strip()

    # Allow backup codes
    backup = settings.get("backup_codes") or ""
    backup_list = [c.strip() for c in backup.split(",") if c.strip()]

    ok = False
    if secret and verify_totp(secret, code):
        ok = True
    elif code.upper() in backup_list:
        ok = True
        # Consume backup code
        backup_list = [c for c in backup_list if c != code.upper()]
        await set_backup_codes(backup_list)

    if not ok:
        await record_failed_attempt()
        await message.answer("❌ Неверный код.")
        await state.clear()
        return

    await reset_failed_attempts()
    token = await create_admin_session(message.from_user.id)
    _admin_tokens[message.from_user.id] = token
    await state.clear()
    await message.answer("🔓 Админ-панель", reply_markup=admin_panel_kb())


@router.callback_query(F.data == "admin:logout")
async def cb_admin_logout(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.from_user:
        await invalidate_admin_session(callback.from_user.id)
        _admin_tokens.pop(callback.from_user.id, None)
    await callback.message.edit_text("Сессия завершена.", reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "admin:panel")
async def cb_admin_panel(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback.from_user.id):
        await callback.message.edit_text("Сессия истекла. Используйте /apanel")
        return
    await callback.message.edit_text("🔓 Админ-панель", reply_markup=admin_panel_kb())


# ── Users ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:users")
async def cb_admin_users(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback.from_user.id):
        return
    users = await list_users(30)
    lines = ["👥 <b>Пользователи</b>\n"]
    for u in users:
        status = "🚫" if u.is_blocked else "✅"
        lines.append(
            f"{status} {u.full_name} | {u.card_number} | "
            f"ID {u.telegram_id} | {format_money(u.main_balance)}"
        )
    await callback.message.edit_text(
        "\n".join(lines) if users else "Нет пользователей.",
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )


# ── Balances ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:balances")
async def cb_admin_balances(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not await _require_admin(callback.from_user.id):
        return
    await state.set_state(AdminActions.waiting_user_id)
    await state.update_data(action="balance")
    await callback.message.edit_text(
        "Введите Telegram ID пользователя для управления балансом:",
        reply_markup=admin_back_kb(),
    )


@router.message(AdminActions.waiting_user_id)
async def admin_user_id(message: Message, state: FSMContext) -> None:
    if not await _require_admin(message.from_user.id):
        await state.clear()
        return
    try:
        tg_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Некорректный ID.")
        return
    user = await get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    data = await state.get_data()
    action = data.get("action")
    await state.update_data(target_user_id=user.id, target_tg=tg_id)

    if action == "balance":
        await state.set_state(AdminActions.waiting_amount)
        await message.answer(
            f"Пользователь: {user.full_name}\n"
            f"Баланс: {format_money(user.main_balance)}\n\n"
            f"Введите сумму (положительная — начислить, отрицательная — списать):"
        )
    elif action == "block":
        await set_blocked(user.id, True)
        admin = await get_user_by_telegram_id(message.from_user.id)
        await log_admin_action(admin.id if admin else 0, "block", user.id)
        await state.clear()
        await message.answer(f"Пользователь {user.full_name} заблокирован.")
    elif action == "unblock":
        await set_blocked(user.id, False)
        admin = await get_user_by_telegram_id(message.from_user.id)
        await log_admin_action(admin.id if admin else 0, "unblock", user.id)
        await state.clear()
        await message.answer(f"Пользователь {user.full_name} разблокирован.")


@router.message(AdminActions.waiting_amount)
async def admin_amount(message: Message, state: FSMContext) -> None:
    if not await _require_admin(message.from_user.id):
        await state.clear()
        return
    try:
        rubles = float((message.text or "").replace(",", "."))
        amount = int(round(rubles * 100))
        if amount == 0:
            raise ValueError
    except ValueError:
        await message.answer("Некорректная сумма.")
        return
    await state.update_data(amount=amount)
    await state.set_state(AdminActions.waiting_reason)
    await message.answer("Укажите причину корректировки:")


@router.message(AdminActions.waiting_reason)
async def admin_reason(message: Message, state: FSMContext) -> None:
    if not await _require_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    target_id = data.get("target_user_id")
    amount = data.get("amount", 0)
    reason = (message.text or "").strip() or "Без указания причины"
    await state.clear()

    try:
        new_bal = await change_balance(
            target_id,
            amount,
            "admin_adjust",
            description=f"Корректировка админом: {reason}",
            account="main",
        )
        admin = await get_user_by_telegram_id(message.from_user.id)
        await log_admin_action(
            admin.id if admin else 0,
            "adjust_balance",
            target_id,
            amount,
            reason,
        )
        await message.answer(
            f"✅ Баланс изменён.\nНовый баланс: {format_money(new_bal)}",
            reply_markup=admin_panel_kb(),
        )
    except ValueError as e:
        await message.answer(f"❌ {e}", reply_markup=admin_panel_kb())


# ── Games admin ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:games")
async def cb_admin_games(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback.from_user.id):
        return
    games = await list_games(15)
    lines = ["🎮 <b>Игры</b>\n"]
    for g in games:
        lines.append(
            f"#{g['id']} {g['title']} [{g['status']}] приз {format_money(g['prize'])}"
        )
    lines.append("\nКоманды: /newgame — создать")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )


@router.message(Command("newgame"))
async def cmd_newgame(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _require_admin(message.from_user.id):
        await message.answer("⛔ Только для администратора (после /apanel).")
        return
    await state.set_state(AdminActions.waiting_game_title)
    await message.answer("Введите название игры:")


@router.message(AdminActions.waiting_game_title)
async def game_title(message: Message, state: FSMContext) -> None:
    await state.update_data(game_title=(message.text or "").strip())
    await state.set_state(AdminActions.waiting_game_desc)
    await message.answer("Введите описание игры:")


@router.message(AdminActions.waiting_game_desc)
async def game_desc(message: Message, state: FSMContext) -> None:
    await state.update_data(game_desc=(message.text or "").strip())
    await state.set_state(AdminActions.waiting_game_prize)
    await message.answer("Введите приз победителю в рублях (0 — без приза):")


@router.message(AdminActions.waiting_game_prize)
async def game_prize(message: Message, state: FSMContext) -> None:
    try:
        rubles = float((message.text or "").replace(",", "."))
        prize = int(round(rubles * 100))
        if prize < 0:
            raise ValueError
    except ValueError:
        await message.answer("Некорректная сумма.")
        return

    data = await state.get_data()
    await state.clear()
    admin = await get_user_by_telegram_id(message.from_user.id)
    if not admin:
        return
    try:
        game_id = await create_game(
            admin,
            data.get("game_title", "Игра"),
            data.get("game_desc", ""),
            prize,
        )
        await open_game(game_id, admin.id)
        # Publish invite
        from keyboards import join_game_kb
        await message.answer(
            f"🎮 Новая игра!\n\n"
            f"<b>{data.get('game_title')}</b>\n"
            f"{data.get('game_desc')}\n"
            f"Приз: {format_money(prize)}\n\n"
            f"Нажмите, чтобы участвовать:",
            reply_markup=join_game_kb(game_id),
            parse_mode="HTML",
        )
        await message.answer(
            f"Игра #{game_id} создана и открыта.\n"
            f"Команды:\n"
            f"/startgame {game_id} — запустить\n"
            f"/finishgame {game_id} <winner_tg_id|draw> — завершить\n"
            f"/cancelgame {game_id} — отменить",
            reply_markup=admin_panel_kb(),
        )
    except GameError as e:
        await message.answer(f"❌ {e}")


@router.message(Command("startgame"))
async def cmd_startgame(message: Message) -> None:
    if not message.from_user or not await _require_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /startgame <game_id>")
        return
    try:
        game_id = int(parts[1])
        admin = await get_user_by_telegram_id(message.from_user.id)
        await start_game(game_id, admin.id)
        await message.answer(f"Игра #{game_id} запущена.")
    except (ValueError, GameError) as e:
        await message.answer(f"❌ {e}")


@router.message(Command("finishgame"))
async def cmd_finishgame(message: Message) -> None:
    if not message.from_user or not await _require_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("Использование: /finishgame <game_id> <winner_tg_id|draw>")
        return
    try:
        game_id = int(parts[1])
        admin = await get_user_by_telegram_id(message.from_user.id)
        if parts[2].lower() == "draw":
            await finish_game(game_id, admin.id, is_draw=True)
            await message.answer(f"Игра #{game_id} завершена ничьёй.")
        else:
            winner_tg = int(parts[2])
            winner = await get_user_by_telegram_id(winner_tg)
            if not winner:
                await message.answer("Победитель не найден.")
                return
            await finish_game(game_id, admin.id, winner_id=winner.id)
            await message.answer(
                f"Игра #{game_id} завершена. Победитель: {winner.full_name}"
            )
    except (ValueError, GameError) as e:
        await message.answer(f"❌ {e}")


@router.message(Command("cancelgame"))
async def cmd_cancelgame(message: Message) -> None:
    if not message.from_user or not await _require_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /cancelgame <game_id>")
        return
    try:
        game_id = int(parts[1])
        admin = await get_user_by_telegram_id(message.from_user.id)
        await cancel_game(game_id, admin.id)
        await message.answer(f"Игра #{game_id} отменена.")
    except (ValueError, GameError) as e:
        await message.answer(f"❌ {e}")


# ── Economy ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:economy")
async def cb_admin_economy(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback.from_user.id):
        return
    eco = await get_economy_settings()
    task = await get_task_settings()
    text = (
        f"⚙️ <b>Экономика</b>\n\n"
        f"Ежедневный бонус: {format_money(eco.get('daily_bonus_amount', 0))}\n"
        f"Начальный баланс: {format_money(eco.get('initial_balance', 0))}\n"
        f"Ставка накоплений: {eco.get('savings_rate', 0) * 100:.2f}%\n"
        f"Период % (часов): {eco.get('savings_period_hours', 24)}\n"
        f"Макс. перевод: {format_money(eco.get('max_transfer', 0))}\n\n"
        f"<b>Задания:</b>\n"
        f"Лимит в день: {task.get('daily_limit')}\n"
        f"Бонус за серию: {format_money(task.get('streak_bonus', 0))}\n"
        f"Награды: beginner={task.get('reward_beginner')} ... expert={task.get('reward_expert')}"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode="HTML")


# ── Stats ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback.from_user.id):
        return
    users_cnt = await count_users()
    total_bal = await total_system_balance()
    from database.db import get_db
    db = await get_db()
    async with db.execute("SELECT COUNT(*) AS c FROM transactions") as c:
        tx_cnt = (await c.fetchone())["c"]
    async with db.execute(
        "SELECT COUNT(*) AS c FROM task_attempts WHERE is_correct = 1"
    ) as c:
        tasks_cnt = (await c.fetchone())["c"]
    async with db.execute("SELECT COUNT(*) AS c FROM games") as c:
        games_cnt = (await c.fetchone())["c"]

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"Пользователей: {users_cnt}\n"
        f"Сумма всех балансов: {format_money(total_bal)}\n"
        f"Транзакций: {tx_cnt}\n"
        f"Выполненных заданий: {tasks_cnt}\n"
        f"Игровых партий: {games_cnt}"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode="HTML")


# ── Logs ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:logs")
async def cb_admin_logs(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback.from_user.id):
        return
    from database.db import get_db
    db = await get_db()
    lines = ["📋 <b>Журнал администратора</b>\n"]
    async with db.execute(
        """
        SELECT * FROM admin_logs ORDER BY id DESC LIMIT 20
        """
    ) as cursor:
        async for row in cursor:
            lines.append(
                f"<code>{row['created_at'][:16]}</code> {row['action']} "
                f"user={row['target_user_id']} amt={row['amount']} {row['reason'] or ''}"
            )
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
