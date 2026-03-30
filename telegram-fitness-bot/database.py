import sqlite3
import json
from datetime import datetime, timezone
from contextlib import contextmanager

from config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                first_name  TEXT NOT NULL DEFAULT '',
                username    TEXT DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                UNIQUE(user_id, name)
            );

            CREATE TABLE IF NOT EXISTS workouts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                started_at  TEXT NOT NULL DEFAULT (datetime('now')),
                finished_at TEXT,
                notes       TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS sets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_id  INTEGER NOT NULL,
                exercise_id INTEGER NOT NULL,
                set_order   INTEGER NOT NULL DEFAULT 0,
                reps        INTEGER NOT NULL,
                weight      REAL NOT NULL,
                logged_at   TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (workout_id) REFERENCES workouts(id),
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            );
        """)


# ── User operations ──────────────────────────────────────────────

def upsert_user(telegram_id: int, first_name: str, username: str = "") -> dict:
    with get_db() as db:
        db.execute(
            """INSERT INTO users (telegram_id, first_name, username)
               VALUES (?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                   first_name = excluded.first_name,
                   username   = excluded.username""",
            (telegram_id, first_name, username),
        )
        row = db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return dict(row)


# ── Exercise operations ──────────────────────────────────────────

def add_exercise(user_id: int, name: str) -> dict:
    with get_db() as db:
        db.execute(
            "INSERT INTO exercises (user_id, name) VALUES (?, ?)",
            (user_id, name.strip()),
        )
        row = db.execute(
            "SELECT * FROM exercises WHERE user_id = ? AND name = ?",
            (user_id, name.strip()),
        ).fetchone()
        return dict(row)


def get_exercises(user_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM exercises WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_exercise(user_id: int, exercise_id: int) -> bool:
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM exercises WHERE id = ? AND user_id = ?",
            (exercise_id, user_id),
        )
        return cur.rowcount > 0


# ── Workout operations ───────────────────────────────────────────

def start_workout(user_id: int) -> dict:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO workouts (user_id) VALUES (?)", (user_id,)
        )
        row = db.execute(
            "SELECT * FROM workouts WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)


def finish_workout(workout_id: int, user_id: int) -> dict | None:
    with get_db() as db:
        db.execute(
            """UPDATE workouts SET finished_at = datetime('now')
               WHERE id = ? AND user_id = ?""",
            (workout_id, user_id),
        )
        row = db.execute(
            "SELECT * FROM workouts WHERE id = ?", (workout_id,)
        ).fetchone()
        return dict(row) if row else None


def get_active_workout(user_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """SELECT * FROM workouts
               WHERE user_id = ? AND finished_at IS NULL
               ORDER BY started_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_recent_workouts(user_id: int, limit: int = 10) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            """SELECT * FROM workouts
               WHERE user_id = ?
               ORDER BY started_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Set operations ───────────────────────────────────────────────

def add_set(workout_id: int, exercise_id: int, reps: int, weight: float) -> dict:
    with get_db() as db:
        # figure out next set_order for this exercise in this workout
        row = db.execute(
            """SELECT COALESCE(MAX(set_order), 0) + 1 AS next_order
               FROM sets WHERE workout_id = ? AND exercise_id = ?""",
            (workout_id, exercise_id),
        ).fetchone()
        next_order = row["next_order"]

        cur = db.execute(
            """INSERT INTO sets (workout_id, exercise_id, set_order, reps, weight)
               VALUES (?, ?, ?, ?, ?)""",
            (workout_id, exercise_id, next_order, reps, weight),
        )
        new_row = db.execute(
            "SELECT * FROM sets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(new_row)


def get_workout_sets(workout_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            """SELECT s.*, e.name AS exercise_name
               FROM sets s
               JOIN exercises e ON e.id = s.exercise_id
               WHERE s.workout_id = ?
               ORDER BY s.exercise_id, s.set_order""",
            (workout_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_set(set_id: int) -> bool:
    with get_db() as db:
        cur = db.execute("DELETE FROM sets WHERE id = ?", (set_id,))
        return cur.rowcount > 0


# ── Summary helpers ──────────────────────────────────────────────

def get_workout_summary(workout_id: int) -> dict:
    """Return a human-friendly summary of a finished workout."""
    with get_db() as db:
        workout = db.execute(
            "SELECT * FROM workouts WHERE id = ?", (workout_id,)
        ).fetchone()
        if not workout:
            return {}

        sets = db.execute(
            """SELECT e.name, s.reps, s.weight, s.set_order
               FROM sets s JOIN exercises e ON e.id = s.exercise_id
               WHERE s.workout_id = ?
               ORDER BY s.exercise_id, s.set_order""",
            (workout_id,),
        ).fetchall()

        exercises = {}
        for s in sets:
            name = s["name"]
            if name not in exercises:
                exercises[name] = []
            exercises[name].append({"reps": s["reps"], "weight": s["weight"]})

        total_sets = len(sets)
        total_volume = sum(s["reps"] * s["weight"] for s in sets)

        return {
            "workout_id": workout_id,
            "started_at": workout["started_at"],
            "finished_at": workout["finished_at"],
            "exercises": exercises,
            "total_sets": total_sets,
            "total_volume": round(total_volume, 1),
        }
