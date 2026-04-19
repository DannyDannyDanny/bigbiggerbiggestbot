"""Database layer for the fitness bot."""

import json
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
                machine_id          TEXT,                -- e.g. "3032", "5014"
                sets                INTEGER NOT NULL,
                reps                INTEGER NOT NULL,
                weight_kg           REAL    NOT NULL,
                raw_line            TEXT,                -- the original line as typed
                sets_detail         TEXT                 -- JSON array of {reps, weight_kg} per set
            );

            CREATE INDEX IF NOT EXISTS idx_workouts_user
                ON workouts(user_id, timestamp);

            CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                text        TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                kind        TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                data        TEXT                 -- optional JSON payload
            );

            CREATE INDEX IF NOT EXISTS idx_events_user_created
                ON events(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_kind_created
                ON events(kind, created_at);
        """)

        # Migrations
        cols = {r[1] for r in conn.execute("PRAGMA table_info(workouts)").fetchall()}
        if "raw_text" not in cols:
            conn.execute("ALTER TABLE workouts ADD COLUMN raw_text TEXT")
        if "deleted_at" not in cols:
            conn.execute("ALTER TABLE workouts ADD COLUMN deleted_at TEXT")

        ex_cols = {r[1] for r in conn.execute("PRAGMA table_info(exercises)").fetchall()}
        if "sets_detail" not in ex_cols:
            conn.execute("ALTER TABLE exercises ADD COLUMN sets_detail TEXT")


def _save_exercises(conn, workout_id: int, superset_groups: list[list[dict]]):
    """Insert superset groups and exercises for a workout."""
    for group_pos, group in enumerate(superset_groups):
        cur = conn.execute(
            "INSERT INTO superset_groups (workout_id, position) VALUES (?, ?)",
            (workout_id, group_pos),
        )
        group_id = cur.lastrowid

        for ex_pos, ex in enumerate(group):
            sets_detail_json = None
            if ex.get("sets_detail"):
                sets_detail_json = json.dumps(ex["sets_detail"])
            conn.execute(
                """INSERT INTO exercises
                   (superset_group_id, position, name, machine_id, sets, reps, weight_kg, raw_line, sets_detail)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (group_id, ex_pos, ex["name"], ex.get("machine_id"),
                 ex["sets"], ex["reps"], ex["weight_kg"], ex.get("raw_line"),
                 sets_detail_json),
            )


def save_workout(user_id: int, timestamp: datetime, superset_groups: list[list[dict]], raw_text: str | None = None, note: str | None = None) -> int:
    """
    Save a parsed workout. Returns the workout id.
    """
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO workouts (user_id, timestamp, note, raw_text) VALUES (?, ?, ?, ?)",
            (user_id, timestamp.isoformat(), note, raw_text),
        )
        workout_id = cur.lastrowid
        _save_exercises(conn, workout_id, superset_groups)
        return workout_id


def update_workout(user_id: int, workout_id: int, superset_groups: list[list[dict]], note: str | None = None) -> int | None:
    """
    Update a workout by soft-deleting the old one and creating a new one
    with the same timestamp. Returns the new workout id, or None if not found.
    """
    with get_db() as conn:
        # Fetch the original workout
        row = conn.execute(
            "SELECT timestamp, raw_text FROM workouts WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (workout_id, user_id),
        ).fetchone()
        if not row:
            return None

        # Soft-delete the old workout
        conn.execute(
            "UPDATE workouts SET deleted_at = datetime('now') WHERE id = ?",
            (workout_id,),
        )

        # Create new workout with original timestamp
        cur = conn.execute(
            "INSERT INTO workouts (user_id, timestamp, note, raw_text) VALUES (?, ?, ?, ?)",
            (user_id, row["timestamp"], note, row["raw_text"]),
        )
        new_id = cur.lastrowid
        _save_exercises(conn, new_id, superset_groups)
        return new_id


def delete_workout(user_id: int, workout_id: int) -> bool:
    """Soft-delete a workout. Returns True if found, False otherwise."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE workouts SET deleted_at = datetime('now') WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (workout_id, user_id),
        )
        return cur.rowcount > 0


def get_workouts(user_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
    """Fetch recent non-deleted workouts for a user, newest first.

    Each workout includes a `user_number` — the per-user display rank when
    ordered by timestamp ascending (1 = the user's first workout).
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, timestamp, note, raw_text, created_at,
                      ROW_NUMBER() OVER (ORDER BY timestamp ASC, id ASC) AS user_number
               FROM workouts
               WHERE user_id = ? AND deleted_at IS NULL
               ORDER BY timestamp DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()

        workouts = []
        for row in rows:
            workout = dict(row)
            groups = conn.execute(
                """SELECT sg.id as group_id, sg.position as group_pos,
                          e.name, e.machine_id, e.sets, e.reps, e.weight_kg,
                          e.raw_line, e.position as ex_pos, e.sets_detail
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
                ex_dict = dict(g)
                if ex_dict.get("sets_detail"):
                    try:
                        ex_dict["sets_detail"] = json.loads(ex_dict["sets_detail"])
                    except json.JSONDecodeError:
                        ex_dict["sets_detail"] = []
                else:
                    ex_dict["sets_detail"] = []
                superset_groups[gp].append(ex_dict)

            workout["superset_groups"] = [superset_groups[k] for k in sorted(superset_groups)]
            workouts.append(workout)

        return workouts


def get_user_workout_number(user_id: int, workout_id: int) -> int | None:
    """Return the per-user display number for a specific workout, or None
    if the workout doesn't exist or is deleted.
    """
    with get_db() as conn:
        row = conn.execute(
            """SELECT user_number FROM (
                   SELECT id, ROW_NUMBER() OVER (ORDER BY timestamp ASC, id ASC) AS user_number
                   FROM workouts
                   WHERE user_id = ? AND deleted_at IS NULL
               )
               WHERE id = ?""",
            (user_id, workout_id),
        ).fetchone()
        return row["user_number"] if row else None


def resolve_user_number(user_id: int, user_number: int) -> int | None:
    """Map a per-user display number to the global workout id, or None."""
    if user_number < 1:
        return None
    with get_db() as conn:
        row = conn.execute(
            """SELECT id FROM (
                   SELECT id, ROW_NUMBER() OVER (ORDER BY timestamp ASC, id ASC) AS n
                   FROM workouts
                   WHERE user_id = ? AND deleted_at IS NULL
               )
               WHERE n = ?""",
            (user_id, user_number),
        ).fetchone()
        return row["id"] if row else None


def get_workout_count(user_id: int) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM workouts WHERE user_id = ? AND deleted_at IS NULL", (user_id,)
        ).fetchone()
        return row["cnt"]


def get_all_exercise_names() -> list[str]:
    """Return exercise names across all users (for autocomplete), ordered by
    popularity (most-used first), then alphabetically. Case-insensitive
    grouping — each distinct name is returned once in its most-used casing.
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT e.name, COUNT(*) AS n
               FROM exercises e
               JOIN superset_groups sg ON sg.id = e.superset_group_id
               JOIN workouts w ON w.id = sg.workout_id
               WHERE w.deleted_at IS NULL
               GROUP BY LOWER(e.name)
               ORDER BY n DESC, LOWER(e.name) ASC""",
        ).fetchall()
        return [r["name"] for r in rows]


def get_stats_sql(user_id: int) -> dict:
    """Compute stats entirely in SQL."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT w.id) as total_workouts,
                COUNT(DISTINCT LOWER(e.name)) as unique_exercises,
                COALESCE(SUM(e.sets), 0) as total_sets,
                COALESCE(SUM(e.sets * e.reps * e.weight_kg), 0) as total_volume
            FROM workouts w
            JOIN superset_groups sg ON sg.workout_id = w.id
            JOIN exercises e ON e.superset_group_id = sg.id
            WHERE w.user_id = ? AND w.deleted_at IS NULL
        """, (user_id,)).fetchone()

        return {
            "total_workouts": row["total_workouts"],
            "unique_exercises": row["unique_exercises"],
            "total_sets": row["total_sets"],
            "total_volume": round(row["total_volume"], 1),
        }


def export_workouts(user_id: int) -> list[dict]:
    """Export all non-deleted workouts as flat records for CSV/JSON export."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                w.id as workout_id, w.timestamp, w.created_at, w.raw_text,
                sg.position as group_pos,
                e.name, e.machine_id, e.sets, e.reps, e.weight_kg,
                e.raw_line, e.sets_detail
            FROM workouts w
            JOIN superset_groups sg ON sg.workout_id = w.id
            JOIN exercises e ON e.superset_group_id = sg.id
            WHERE w.user_id = ? AND w.deleted_at IS NULL
            ORDER BY w.timestamp DESC, sg.position, e.position
        """, (user_id,)).fetchall()

        return [dict(r) for r in rows]


def log_event(user_id: int | None, kind: str, data: dict | None = None) -> int:
    """Record a user event for audit / telemetry. Failures are swallowed so
    logging never breaks a caller."""
    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO events (user_id, kind, data) VALUES (?, ?, ?)",
                (user_id, kind, json.dumps(data) if data else None),
            )
            return cur.lastrowid
    except Exception:
        return -1


def get_events(
    user_id: int | None = None,
    kind: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Fetch events, newest first. Filter by user_id and/or kind if given."""
    where = []
    params: list = []
    if user_id is not None:
        where.append("user_id = ?")
        params.append(user_id)
    if kind is not None:
        where.append("kind = ?")
        params.append(kind)
    sql = "SELECT id, user_id, kind, created_at, data FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("data"):
                try:
                    d["data"] = json.loads(d["data"])
                except json.JSONDecodeError:
                    pass
            out.append(d)
        return out


def save_feedback(user_id: int, text: str) -> int:
    """Save user feedback. Returns the feedback id."""
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO feedback (user_id, text) VALUES (?, ?)",
            (user_id, text),
        )
        return cur.lastrowid


def get_feedback(limit: int = 50) -> list[dict]:
    """Get all feedback, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, user_id, text, created_at FROM feedback ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
