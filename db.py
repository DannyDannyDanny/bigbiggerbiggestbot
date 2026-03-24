"""Database layer for the fitness bot."""

import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "workouts.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS workouts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                timestamp   TEXT    NOT NULL,  -- ISO-8601, original workout time
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                note        TEXT               -- optional free-text note
            );

            CREATE TABLE IF NOT EXISTS superset_groups (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_id  INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
                position    INTEGER NOT NULL   -- ordering within the workout
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                superset_group_id   INTEGER NOT NULL REFERENCES superset_groups(id) ON DELETE CASCADE,
                position            INTEGER NOT NULL,   -- ordering within the superset group
                name                TEXT    NOT NULL,
                machine_id          TEXT,                -- e.g. "500", "620"
                sets                INTEGER NOT NULL,
                reps                INTEGER NOT NULL,
                weight_kg           REAL    NOT NULL,
                raw_line            TEXT                 -- the original line as typed
            );

            CREATE INDEX IF NOT EXISTS idx_workouts_user
                ON workouts(user_id, timestamp);
        """)

        # Migration: add raw_text column if it doesn't exist yet
        cols = {r[1] for r in conn.execute("PRAGMA table_info(workouts)").fetchall()}
        if "raw_text" not in cols:
            conn.execute("ALTER TABLE workouts ADD COLUMN raw_text TEXT")


def save_workout(user_id: int, timestamp: datetime, superset_groups: list[list[dict]], raw_text: str | None = None, note: str | None = None) -> int:
    """
    Save a parsed workout.

    superset_groups: list of groups, each group is a list of exercise dicts:
        {name, machine_id, sets, reps, weight_kg, raw_line}
    raw_text: the full original message text, stored verbatim.

    Returns the workout id.
    """
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO workouts (user_id, timestamp, note, raw_text) VALUES (?, ?, ?, ?)",
            (user_id, timestamp.isoformat(), note, raw_text),
        )
        workout_id = cur.lastrowid

        for group_pos, group in enumerate(superset_groups):
            cur2 = conn.execute(
                "INSERT INTO superset_groups (workout_id, position) VALUES (?, ?)",
                (workout_id, group_pos),
            )
            group_id = cur2.lastrowid

            for ex_pos, ex in enumerate(group):
                conn.execute(
                    """INSERT INTO exercises
                       (superset_group_id, position, name, machine_id, sets, reps, weight_kg, raw_line)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (group_id, ex_pos, ex["name"], ex.get("machine_id"),
                     ex["sets"], ex["reps"], ex["weight_kg"], ex.get("raw_line")),
                )

        return workout_id


def get_workouts(user_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
    """Fetch recent workouts for a user, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, timestamp, note, raw_text, created_at
               FROM workouts
               WHERE user_id = ?
               ORDER BY timestamp DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()

        workouts = []
        for row in rows:
            workout = dict(row)
            groups = conn.execute(
                """SELECT sg.id as group_id, sg.position as group_pos,
                          e.name, e.machine_id, e.sets, e.reps, e.weight_kg, e.raw_line, e.position as ex_pos
                   FROM superset_groups sg
                   JOIN exercises e ON e.superset_group_id = sg.id
                   WHERE sg.workout_id = ?
                   ORDER BY sg.position, e.position""",
                (row["id"],),
            ).fetchall()

            superset_groups = {}
            for g in groups:
                gp = g["group_pos"]
                if gp not in superset_groups:
                    superset_groups[gp] = []
                superset_groups[gp].append(dict(g))

            workout["superset_groups"] = [superset_groups[k] for k in sorted(superset_groups)]
            workouts.append(workout)

        return workouts


def get_workout_count(user_id: int) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM workouts WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["cnt"]
