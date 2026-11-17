"""
Game system: create, join, start, finish, award prize.
"""

from __future__ import annotations

from typing import Optional

from database.db import get_db
from economy import change_balance
from models import User, get_user_by_id


class GameError(Exception):
    pass


async def create_game(
    creator: User,
    title: str,
    description: str,
    prize: int,
) -> int:
    if prize < 0:
        raise GameError("Приз не может быть отрицательным")
    db = await get_db()
    async with db.execute(
        """
        INSERT INTO games (title, description, prize, status, created_by)
        VALUES (?, ?, ?, 'created', ?)
        """,
        (title.strip(), description.strip(), prize, creator.id),
    ) as cursor:
        game_id = cursor.lastrowid
    await db.commit()
    return game_id


async def open_game(game_id: int, admin_id: int) -> None:
    db = await get_db()
    async with db.execute(
        "SELECT status, created_by FROM games WHERE id = ?", (game_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise GameError("Игра не найдена")
        if row["created_by"] != admin_id:
            raise GameError("Только создатель может открыть игру")
        if row["status"] != "created":
            raise GameError("Игра уже открыта или завершена")
    await db.execute(
        "UPDATE games SET status = 'open' WHERE id = ?", (game_id,)
    )
    await db.commit()


async def join_game(game_id: int, user: User) -> None:
    if user.is_blocked:
        raise GameError("Вы заблокированы")
    db = await get_db()
    async with db.execute(
        "SELECT status FROM games WHERE id = ?", (game_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise GameError("Игра не найдена")
        if row["status"] != "open":
            raise GameError("Игра не принимает участников")

    try:
        await db.execute(
            "INSERT INTO game_participants (game_id, user_id) VALUES (?, ?)",
            (game_id, user.id),
        )
        await db.commit()
    except Exception:
        raise GameError("Вы уже участвуете в этой игре")


async def start_game(game_id: int, admin_id: int) -> None:
    db = await get_db()
    async with db.execute(
        "SELECT status, created_by FROM games WHERE id = ?", (game_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise GameError("Игра не найдена")
        if row["created_by"] != admin_id:
            raise GameError("Нет прав")
        if row["status"] != "open":
            raise GameError("Игра должна быть открыта для запуска")

    async with db.execute(
        "SELECT COUNT(*) AS cnt FROM game_participants WHERE game_id = ?",
        (game_id,),
    ) as cursor:
        cnt_row = await cursor.fetchone()
        if (cnt_row["cnt"] or 0) < 1:
            raise GameError("Нет участников")

    await db.execute(
        """
        UPDATE games SET status = 'running', started_at = datetime('now')
        WHERE id = ?
        """,
        (game_id,),
    )
    await db.commit()


async def finish_game(
    game_id: int,
    admin_id: int,
    winner_id: Optional[int] = None,
    is_draw: bool = False,
) -> None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM games WHERE id = ?", (game_id,)
    ) as cursor:
        game = await cursor.fetchone()
        if not game:
            raise GameError("Игра не найдена")
        if game["created_by"] != admin_id:
            raise GameError("Нет прав")
        if game["status"] not in ("running", "open"):
            raise GameError("Игру нельзя завершить в текущем статусе")

    prize = game["prize"]
    if is_draw or winner_id is None:
        await db.execute(
            """
            UPDATE games SET status = 'finished', finished_at = datetime('now'),
                             winner_id = NULL
            WHERE id = ?
            """,
            (game_id,),
        )
        await db.commit()
        return

    # Award prize
    winner = await get_user_by_id(winner_id)
    if not winner:
        raise GameError("Победитель не найден")

    # Check participant
    async with db.execute(
        "SELECT 1 FROM game_participants WHERE game_id = ? AND user_id = ?",
        (game_id, winner_id),
    ) as cursor:
        if not await cursor.fetchone():
            raise GameError("Пользователь не участвовал в игре")

    if prize > 0:
        await change_balance(
            winner_id,
            prize,
            "game_prize",
            description=f"Приз за победу в игре «{game['title']}»",
            account="main",
        )

    await db.execute(
        "UPDATE accounts SET wins = wins + 1 WHERE user_id = ?",
        (winner_id,),
    )
    # Increment losses for others
    await db.execute(
        """
        UPDATE accounts SET losses = losses + 1
        WHERE user_id IN (
            SELECT user_id FROM game_participants
            WHERE game_id = ? AND user_id != ?
        )
        """,
        (game_id, winner_id),
    )

    await db.execute(
        """
        UPDATE games SET status = 'finished', finished_at = datetime('now'),
                         winner_id = ?
        WHERE id = ?
        """,
        (winner_id, game_id),
    )
    await db.commit()


async def cancel_game(game_id: int, admin_id: int) -> None:
    db = await get_db()
    async with db.execute(
        "SELECT status, created_by FROM games WHERE id = ?", (game_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise GameError("Игра не найдена")
        if row["created_by"] != admin_id:
            raise GameError("Нет прав")
        if row["status"] in ("finished", "cancelled"):
            raise GameError("Игра уже завершена")
    await db.execute(
        "UPDATE games SET status = 'cancelled', finished_at = datetime('now') WHERE id = ?",
        (game_id,),
    )
    await db.commit()


async def get_game(game_id: int) -> Optional[dict]:
    db = await get_db()
    async with db.execute("SELECT * FROM games WHERE id = ?", (game_id,)) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_participants(game_id: int) -> list[dict]:
    db = await get_db()
    rows = []
    async with db.execute(
        """
        SELECT u.id, u.telegram_id, u.full_name, u.card_number, gp.joined_at
        FROM game_participants gp
        JOIN users u ON u.id = gp.user_id
        WHERE gp.game_id = ?
        ORDER BY gp.joined_at
        """,
        (game_id,),
    ) as cursor:
        async for row in cursor:
            rows.append(dict(row))
    return rows


async def list_games(limit: int = 20) -> list[dict]:
    db = await get_db()
    rows = []
    async with db.execute(
        """
        SELECT g.*, u.full_name AS creator_name
        FROM games g
        JOIN users u ON u.id = g.created_by
        ORDER BY g.id DESC
        LIMIT ?
        """,
        (limit,),
    ) as cursor:
        async for row in cursor:
            rows.append(dict(row))
    return rows
