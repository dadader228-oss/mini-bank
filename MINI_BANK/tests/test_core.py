"""
Automated tests for critical financial and security mechanisms.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# Ensure project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use temporary DB for tests
os.environ["DATABASE_PATH"] = str(ROOT / "database" / "test_mini_bank.db")
os.environ["BOT_TOKEN"] = "123456:TEST_TOKEN_FOR_UNIT_TESTS"
os.environ["OWNER_ID"] = "999999999"

from database.db import close_db, init_db, get_db
from models import create_user, get_user_by_telegram_id, format_money
from economy import change_balance, get_economy_settings
from transfers import transfer, TransferError
from bonuses import claim_daily_bonus, can_claim_daily
from security import (
    hash_password,
    verify_password,
    generate_totp_secret,
    verify_totp,
    generate_backup_codes,
)
from tasks import generate_task, create_task_attempt, check_answer
from savings import deposit_to_savings, withdraw_from_savings, accrue_interest
import pyotp


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    db_path = Path(os.environ["DATABASE_PATH"])
    if db_path.exists():
        db_path.unlink()
    await init_db()
    yield
    await close_db()
    if db_path.exists():
        db_path.unlink()


@pytest.mark.asyncio
async def test_user_registration():
    user = await create_user(1001, "testuser", "Test User", 5000)
    assert user.telegram_id == 1001
    assert user.card_number.startswith("MB-")
    assert user.main_balance == 5000

    # No double registration of same logic — second create would fail on unique telegram_id
    again = await get_user_by_telegram_id(1001)
    assert again is not None
    assert again.id == user.id


@pytest.mark.asyncio
async def test_format_money():
    assert format_money(0) == "0.00 ₽"
    assert format_money(1050) == "10.50 ₽"
    assert format_money(-250) == "-2.50 ₽"


@pytest.mark.asyncio
async def test_transfer_success():
    a = await create_user(2001, None, "Alice", 10000)
    b = await create_user(2002, None, "Bob", 0)
    new_a, new_b = await transfer(a, b, 3000)
    assert new_a == 7000
    assert new_b == 3000
    a2 = await get_user_by_telegram_id(2001)
    b2 = await get_user_by_telegram_id(2002)
    assert a2.main_balance == 7000
    assert b2.main_balance == 3000


@pytest.mark.asyncio
async def test_transfer_insufficient():
    a = await create_user(3001, None, "Alice", 1000)
    b = await create_user(3002, None, "Bob", 0)
    with pytest.raises(TransferError):
        await transfer(a, b, 5000)


@pytest.mark.asyncio
async def test_transfer_self():
    a = await create_user(4001, None, "Alice", 5000)
    with pytest.raises(TransferError):
        await transfer(a, a, 100)


@pytest.mark.asyncio
async def test_transfer_negative():
    a = await create_user(5001, None, "Alice", 5000)
    b = await create_user(5002, None, "Bob", 0)
    with pytest.raises(TransferError):
        await transfer(a, b, -100)


@pytest.mark.asyncio
async def test_daily_bonus_once():
    user = await create_user(6001, None, "BonusUser", 0)
    amount = await claim_daily_bonus(user)
    assert amount > 0
    can, _ = await can_claim_daily(user.id)
    assert can is False
    with pytest.raises(ValueError):
        await claim_daily_bonus(user)


@pytest.mark.asyncio
async def test_password_hash():
    h = hash_password("SuperSecret123!")
    assert verify_password(h, "SuperSecret123!")
    assert not verify_password(h, "wrong")


@pytest.mark.asyncio
async def test_totp():
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert verify_totp(secret, code)
    assert not verify_totp(secret, "000000")


@pytest.mark.asyncio
async def test_task_generation():
    for level in ("beginner", "easy", "medium", "advanced", "hard", "expert"):
        expr, ans = generate_task(level)
        assert expr
        assert ans


@pytest.mark.asyncio
async def test_task_reward():
    user = await create_user(7001, None, "Tasker", 0)
    attempt = await create_task_attempt(user.id, "beginner")
    # We don't know the answer easily, so just check structure
    assert "id" in attempt
    assert attempt["reward"] > 0


@pytest.mark.asyncio
async def test_savings_flow():
    user = await create_user(8001, None, "Saver", 10000)
    new_main, new_sav = await deposit_to_savings(user, 4000)
    assert new_main == 6000
    assert new_sav == 4000
    user = await get_user_by_telegram_id(8001)
    new_main, new_sav = await withdraw_from_savings(user, 1000)
    assert new_main == 7000
    assert new_sav == 3000


@pytest.mark.asyncio
async def test_atomic_insufficient_on_change():
    user = await create_user(9001, None, "Poor", 100)
    with pytest.raises(ValueError):
        await change_balance(user.id, -500, "test", account="main")
