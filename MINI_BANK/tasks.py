"""
Math tasks generation and checking.
"""

from __future__ import annotations

import random
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from database.db import get_db
from economy import change_balance
from models import User


LEVELS = {
    "beginner": "Начальный",
    "easy": "Лёгкий",
    "medium": "Средний",
    "advanced": "Продвинутый",
    "hard": "Сложный",
    "expert": "Экспертный",
}


async def get_task_settings() -> dict:
    db = await get_db()
    async with db.execute("SELECT * FROM task_settings WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else {}


async def update_task_setting(key: str, value: int) -> None:
    allowed = {
        "daily_limit",
        "streak_bonus",
        "reward_beginner",
        "reward_easy",
        "reward_medium",
        "reward_advanced",
        "reward_hard",
        "reward_expert",
        "timer_seconds",
    }
    if key not in allowed:
        raise ValueError(f"Unknown key: {key}")
    db = await get_db()
    await db.execute(
        f"UPDATE task_settings SET {key} = ? WHERE id = 1",
        (value,),
    )
    await db.commit()


def generate_task(level: str) -> tuple[str, str]:
    """Return (expression_string, correct_answer_string)."""
    if level == "beginner":
        a, b = random.randint(1, 9), random.randint(1, 9)
        op = random.choice(["+", "-"])
        if op == "-" and a < b:
            a, b = b, a
        expr = f"{a} {op} {b}"
        ans = a + b if op == "+" else a - b
        return expr, str(ans)

    if level == "easy":
        a, b = random.randint(10, 99), random.randint(10, 99)
        op = random.choice(["+", "-"])
        if op == "-" and a < b:
            a, b = b, a
        expr = f"{a} {op} {b}"
        ans = a + b if op == "+" else a - b
        return expr, str(ans)

    if level == "medium":
        if random.random() < 0.5:
            a, b = random.randint(2, 20), random.randint(2, 12)
            expr = f"{a} * {b}"
            ans = a * b
        else:
            b = random.randint(2, 12)
            ans = random.randint(2, 20)
            a = ans * b
            expr = f"{a} / {b}"
        return expr, str(ans)

    if level == "advanced":
        a, b = random.randint(100, 999), random.randint(10, 99)
        op = random.choice(["+", "-", "*"])
        if op == "-":
            if a < b:
                a, b = b, a
            expr = f"{a} - {b}"
            ans = a - b
        elif op == "+":
            expr = f"{a} + {b}"
            ans = a + b
        else:
            expr = f"{a} * {b}"
            ans = a * b
        return expr, str(ans)

    if level == "hard":
        a = random.randint(10, 50)
        b = random.randint(2, 15)
        c = random.randint(2, 10)
        op1 = random.choice(["+", "-"])
        expr = f"{a} {op1} {b} * {c}"
        # * has precedence
        mul = b * c
        ans = a + mul if op1 == "+" else a - mul
        return expr, str(ans)

    # expert – decimals
    a = Decimal(random.randint(10, 99)) / 10
    b = Decimal(random.randint(10, 99)) / 10
    op = random.choice(["+", "-"])
    if op == "-" and a < b:
        a, b = b, a
    expr = f"{a} {op} {b}"
    ans = (a + b if op == "+" else a - b).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    return expr, str(ans)


async def count_today_tasks(user_id: int) -> int:
    db = await get_db()
    async with db.execute(
        """
        SELECT COUNT(*) AS cnt FROM task_attempts
        WHERE user_id = ? AND date(created_at) = date('now')
        """,
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return row["cnt"] if row else 0


async def create_task_attempt(user_id: int, level: str) -> dict:
    settings = await get_task_settings()
    limit = settings.get("daily_limit", 20)
    done = await count_today_tasks(user_id)
    if done >= limit:
        raise ValueError(f"Дневной лимит заданий исчерпан ({limit})")

    expr, answer = generate_task(level)
    reward_key = f"reward_{level}"
    reward = settings.get(reward_key, 100)

    db = await get_db()
    async with db.execute(
        """
        INSERT INTO task_attempts (user_id, level, expression, correct_answer, reward)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, level, expr, answer, reward),
    ) as cursor:
        attempt_id = cursor.lastrowid
    await db.commit()
    return {
        "id": attempt_id,
        "expression": expr,
        "reward": reward,
        "level": level,
    }


async def check_answer(attempt_id: int, user_id: int, user_answer: str) -> dict:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM task_attempts WHERE id = ? AND user_id = ?",
        (attempt_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise ValueError("Задание не найдено")
        if row["is_correct"] is not None:
            raise ValueError("Ответ уже был дан")

    correct = str(row["correct_answer"]).strip()
    given = user_answer.strip().replace(",", ".")
    is_correct = given == correct

    reward = 0
    if is_correct:
        reward = row["reward"]
        # streak bonus: last 3 correct
        async with db.execute(
            """
            SELECT is_correct FROM task_attempts
            WHERE user_id = ? AND is_correct IS NOT NULL
            ORDER BY id DESC LIMIT 2
            """,
            (user_id,),
        ) as cursor:
            prev = [r["is_correct"] async for r in cursor]
        if len(prev) == 2 and all(prev):
            settings = await get_task_settings()
            bonus = settings.get("streak_bonus", 500)
            reward += bonus

        await change_balance(
            user_id,
            reward,
            "task_reward",
            description=f"Награда за задание ({row['level']})",
            account="main",
        )
        await db.execute(
            "UPDATE accounts SET tasks_completed = tasks_completed + 1 WHERE user_id = ?",
            (user_id,),
        )

    await db.execute(
        """
        UPDATE task_attempts
        SET user_answer = ?, is_correct = ?, reward = ?
        WHERE id = ?
        """,
        (user_answer, 1 if is_correct else 0, reward if is_correct else 0, attempt_id),
    )
    await db.commit()

    return {
        "is_correct": is_correct,
        "correct_answer": correct,
        "reward": reward,
    }
