from datetime import datetime, timezone, timedelta

import db


# ── init_db ──────────────────────────────────────────────────────


class TestInitDb:
    def test_tables_created(self, tmp_db):
        with db.get_db() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert "workouts" in tables
        assert "superset_groups" in tables
        assert "exercises" in tables

    def test_idempotent(self, tmp_db):
        db.init_db()  # second call should not raise

    def test_migrations_applied(self, tmp_db):
        with db.get_db() as conn:
            w_cols = {r[1] for r in conn.execute("PRAGMA table_info(workouts)").fetchall()}
            e_cols = {r[1] for r in conn.execute("PRAGMA table_info(exercises)").fetchall()}
        assert "raw_text" in w_cols
        assert "sets_detail" in e_cols


# ── Helpers ──────────────────────────────────────────────────────


def _make_exercise(name="Bench", sets=3, reps=8, weight=35.0, machine_id=None):
    detail = [{"reps": reps, "weight_kg": weight}] * sets
    return {
        "name": name,
        "machine_id": machine_id,
        "sets": sets,
        "reps": reps,
        "weight_kg": weight,
        "sets_detail": detail,
        "raw_line": f"{name}: {sets}x{reps}x{weight}",
    }


def _save_simple(user_id=1, name="Bench", ts=None):
    ts = ts or datetime.now(timezone.utc)
    return db.save_workout(
        user_id=user_id,
        timestamp=ts,
        superset_groups=[[_make_exercise(name=name)]],
        raw_text=f"{name}: 3x8x35",
    )


# ── save_workout + get_workouts round-trip ───────────────────────


class TestSaveAndGet:
    def test_basic_round_trip(self, tmp_db):
        wid = _save_simple()
        workouts = db.get_workouts(user_id=1)
        assert len(workouts) == 1
        w = workouts[0]
        assert w["id"] == wid
        assert len(w["superset_groups"]) == 1
        ex = w["superset_groups"][0][0]
        assert ex["name"] == "Bench"
        assert ex["sets"] == 3
        assert ex["reps"] == 8
        assert ex["weight_kg"] == 35.0

    def test_sets_detail_round_trip(self, tmp_db):
        detail = [{"reps": 8, "weight_kg": 25}, {"reps": 5, "weight_kg": 35}]
        ex = {
            "name": "Press", "machine_id": None,
            "sets": 2, "reps": 8, "weight_kg": 25,
            "sets_detail": detail, "raw_line": "Press: 8x25, 5x35",
        }
        db.save_workout(1, datetime.now(timezone.utc), [[ex]])
        workouts = db.get_workouts(1)
        got = workouts[0]["superset_groups"][0][0]["sets_detail"]
        assert got == detail

    def test_machine_id(self, tmp_db):
        ex = _make_exercise(machine_id="3032")
        db.save_workout(1, datetime.now(timezone.utc), [[ex]])
        workouts = db.get_workouts(1)
        assert workouts[0]["superset_groups"][0][0]["machine_id"] == "3032"

    def test_raw_text_stored(self, tmp_db):
        _save_simple()
        workouts = db.get_workouts(1)
        assert workouts[0]["raw_text"] == "Bench: 3x8x35"

    def test_newest_first(self, tmp_db):
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        t3 = datetime(2024, 1, 3, tzinfo=timezone.utc)
        _save_simple(name="First", ts=t1)
        _save_simple(name="Second", ts=t2)
        _save_simple(name="Third", ts=t3)
        workouts = db.get_workouts(1)
        names = [w["superset_groups"][0][0]["name"] for w in workouts]
        assert names == ["Third", "Second", "First"]

    def test_pagination(self, tmp_db):
        for i in range(5):
            _save_simple(ts=datetime(2024, 1, i + 1, tzinfo=timezone.utc))
        page1 = db.get_workouts(1, limit=2, offset=0)
        page2 = db.get_workouts(1, limit=2, offset=2)
        page3 = db.get_workouts(1, limit=2, offset=4)
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1


# ── delete_workout ───────────────────────────────────────────────


class TestDeleteWorkout:
    def test_delete_success(self, tmp_db):
        wid = _save_simple()
        assert db.delete_workout(user_id=1, workout_id=wid) is True
        assert db.get_workouts(1) == []  # not visible

    def test_soft_delete_preserves_row(self, tmp_db):
        wid = _save_simple()
        db.delete_workout(user_id=1, workout_id=wid)
        # Row still exists with deleted_at set
        with db.get_db() as conn:
            row = conn.execute("SELECT deleted_at FROM workouts WHERE id = ?", (wid,)).fetchone()
        assert row is not None
        assert row["deleted_at"] is not None

    def test_delete_nonexistent(self, tmp_db):
        assert db.delete_workout(user_id=1, workout_id=999) is False

    def test_delete_wrong_user(self, tmp_db):
        wid = _save_simple(user_id=1)
        assert db.delete_workout(user_id=2, workout_id=wid) is False
        assert len(db.get_workouts(1)) == 1  # still there

    def test_delete_idempotent(self, tmp_db):
        wid = _save_simple()
        assert db.delete_workout(1, wid) is True
        assert db.delete_workout(1, wid) is False  # already deleted


# ── per-user numbering ───────────────────────────────────────────


class TestUserNumbering:
    def test_user_number_in_get_workouts(self, tmp_db):
        t = lambda d: datetime(2024, 1, d, tzinfo=timezone.utc)
        _save_simple(name="First", ts=t(1))
        _save_simple(name="Second", ts=t(2))
        _save_simple(name="Third", ts=t(3))
        ws = db.get_workouts(1)  # newest first
        assert [w["superset_groups"][0][0]["name"] for w in ws] == ["Third", "Second", "First"]
        assert [w["user_number"] for w in ws] == [3, 2, 1]

    def test_numbering_is_per_user(self, tmp_db):
        t = lambda d: datetime(2024, 1, d, tzinfo=timezone.utc)
        _save_simple(user_id=1, ts=t(1))
        _save_simple(user_id=2, ts=t(1))
        _save_simple(user_id=1, ts=t(2))
        _save_simple(user_id=2, ts=t(2))
        assert [w["user_number"] for w in db.get_workouts(1)] == [2, 1]
        assert [w["user_number"] for w in db.get_workouts(2)] == [2, 1]

    def test_numbering_skips_deleted(self, tmp_db):
        t = lambda d: datetime(2024, 1, d, tzinfo=timezone.utc)
        w1 = _save_simple(ts=t(1))
        _save_simple(ts=t(2))
        _save_simple(ts=t(3))
        db.delete_workout(1, w1)
        ws = db.get_workouts(1)  # now 2 workouts, both shift down
        assert [w["user_number"] for w in ws] == [2, 1]

    def test_get_user_workout_number(self, tmp_db):
        t = lambda d: datetime(2024, 1, d, tzinfo=timezone.utc)
        w1 = _save_simple(ts=t(1))
        w2 = _save_simple(ts=t(2))
        assert db.get_user_workout_number(1, w1) == 1
        assert db.get_user_workout_number(1, w2) == 2

    def test_get_user_workout_number_missing(self, tmp_db):
        assert db.get_user_workout_number(1, 9999) is None

    def test_get_user_workout_number_deleted(self, tmp_db):
        wid = _save_simple()
        db.delete_workout(1, wid)
        assert db.get_user_workout_number(1, wid) is None

    def test_resolve_user_number(self, tmp_db):
        t = lambda d: datetime(2024, 1, d, tzinfo=timezone.utc)
        w1 = _save_simple(ts=t(1))
        w2 = _save_simple(ts=t(2))
        assert db.resolve_user_number(1, 1) == w1
        assert db.resolve_user_number(1, 2) == w2

    def test_resolve_user_number_out_of_range(self, tmp_db):
        _save_simple()
        assert db.resolve_user_number(1, 0) is None
        assert db.resolve_user_number(1, 99) is None
        assert db.resolve_user_number(1, -1) is None

    def test_resolve_user_number_wrong_user(self, tmp_db):
        _save_simple(user_id=1)
        assert db.resolve_user_number(user_id=2, user_number=1) is None


# ── global exercise names ────────────────────────────────────────


class TestAllExerciseNames:
    def test_empty(self, tmp_db):
        assert db.get_all_exercise_names() == []

    def test_draws_from_all_users(self, tmp_db):
        _save_simple(user_id=1, name="Bench")
        _save_simple(user_id=2, name="Squat")
        names = db.get_all_exercise_names()
        assert set(names) == {"Bench", "Squat"}

    def test_ordered_by_popularity(self, tmp_db):
        # Squat appears 3x (across users); Bench 2x; Rows 1x.
        for _ in range(3):
            _save_simple(name="Squat")
        for _ in range(2):
            _save_simple(name="Bench")
        _save_simple(name="Rows")
        assert db.get_all_exercise_names() == ["Squat", "Bench", "Rows"]

    def test_case_insensitive_grouping(self, tmp_db):
        _save_simple(name="bench press")
        _save_simple(name="Bench Press")
        _save_simple(name="BENCH PRESS")
        names = db.get_all_exercise_names()
        assert len(names) == 1  # collapsed into one group

    def test_excludes_deleted_workouts(self, tmp_db):
        wid = _save_simple(name="Deadlift")
        _save_simple(name="Squat")
        db.delete_workout(1, wid)
        assert db.get_all_exercise_names() == ["Squat"]

    def test_alphabetical_tiebreak(self, tmp_db):
        # All tied at 1 usage — should come back alphabetical.
        for n in ["Zebra", "Apple", "Mango"]:
            _save_simple(name=n)
        assert db.get_all_exercise_names() == ["Apple", "Mango", "Zebra"]


# ── events / log_event ───────────────────────────────────────────


class TestEvents:
    def test_log_and_fetch(self, tmp_db):
        db.log_event(1, "cmd.start")
        events = db.get_events()
        assert len(events) == 1
        assert events[0]["user_id"] == 1
        assert events[0]["kind"] == "cmd.start"
        assert events[0]["data"] is None

    def test_log_with_data(self, tmp_db):
        db.log_event(1, "set.add", {"exercise": "Bench", "reps": 8, "weight_kg": 35.0})
        events = db.get_events()
        assert events[0]["data"] == {"exercise": "Bench", "reps": 8, "weight_kg": 35.0}

    def test_filter_by_user(self, tmp_db):
        db.log_event(1, "cmd.start")
        db.log_event(2, "cmd.start")
        db.log_event(1, "cmd.history")
        assert {e["kind"] for e in db.get_events(user_id=1)} == {"cmd.start", "cmd.history"}
        assert {e["kind"] for e in db.get_events(user_id=2)} == {"cmd.start"}

    def test_filter_by_kind(self, tmp_db):
        db.log_event(1, "cmd.start")
        db.log_event(1, "set.add", {"reps": 5})
        db.log_event(2, "set.add", {"reps": 3})
        sets = db.get_events(kind="set.add")
        assert len(sets) == 2
        assert all(e["kind"] == "set.add" for e in sets)

    def test_newest_first(self, tmp_db):
        db.log_event(1, "first")
        db.log_event(1, "second")
        db.log_event(1, "third")
        kinds = [e["kind"] for e in db.get_events()]
        assert kinds == ["third", "second", "first"]

    def test_limit(self, tmp_db):
        for i in range(5):
            db.log_event(1, f"k{i}")
        assert len(db.get_events(limit=2)) == 2

    def test_null_user_allowed(self, tmp_db):
        db.log_event(None, "system.tick")
        events = db.get_events()
        assert events[0]["user_id"] is None

    def test_log_failure_returns_minus_one(self, tmp_db):
        # Simulate failure by passing unserializable data
        class X: pass
        result = db.log_event(1, "bad", {"obj": X()})
        assert result == -1


# ── user settings ────────────────────────────────────────────────


class TestSettings:
    def test_default_empty(self, tmp_db):
        assert db.get_settings(1) == {}

    def test_update_creates(self, tmp_db):
        result = db.update_settings(1, {"rest_timer": False})
        assert result == {"rest_timer": False}
        assert db.get_settings(1) == {"rest_timer": False}

    def test_update_merges(self, tmp_db):
        db.update_settings(1, {"rest_timer": False})
        result = db.update_settings(1, {"units": "lb"})
        assert result == {"rest_timer": False, "units": "lb"}

    def test_update_overwrites_key(self, tmp_db):
        db.update_settings(1, {"rest_timer": False})
        db.update_settings(1, {"rest_timer": True})
        assert db.get_settings(1)["rest_timer"] is True

    def test_settings_are_per_user(self, tmp_db):
        db.update_settings(1, {"rest_timer": False})
        db.update_settings(2, {"rest_timer": True})
        assert db.get_settings(1) == {"rest_timer": False}
        assert db.get_settings(2) == {"rest_timer": True}

    def test_patch_must_be_dict(self, tmp_db):
        import pytest
        with pytest.raises(TypeError):
            db.update_settings(1, "not a dict")


# ── update_workout ───────────────────────────────────────────────


class TestUpdateWorkout:
    def test_update_preserves_timestamp(self, tmp_db):
        t = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        wid = db.save_workout(1, t, [[_make_exercise(name="Old")]])
        new_id = db.update_workout(1, wid, [[_make_exercise(name="New")]])
        assert new_id is not None
        assert new_id != wid
        workouts = db.get_workouts(1)
        assert len(workouts) == 1
        assert workouts[0]["superset_groups"][0][0]["name"] == "New"
        assert workouts[0]["timestamp"] == t.isoformat()

    def test_update_soft_deletes_old(self, tmp_db):
        wid = _save_simple()
        db.update_workout(1, wid, [[_make_exercise(name="Updated")]])
        # Old workout should have deleted_at set
        with db.get_db() as conn:
            row = conn.execute("SELECT deleted_at FROM workouts WHERE id = ?", (wid,)).fetchone()
        assert row["deleted_at"] is not None

    def test_update_nonexistent(self, tmp_db):
        assert db.update_workout(1, 999, [[_make_exercise()]]) is None

    def test_update_wrong_user(self, tmp_db):
        wid = _save_simple(user_id=1)
        assert db.update_workout(2, wid, [[_make_exercise()]]) is None
        assert len(db.get_workouts(1)) == 1  # unchanged

    def test_update_with_note(self, tmp_db):
        wid = _save_simple()
        new_id = db.update_workout(1, wid, [[_make_exercise()]], note="Updated note")
        workouts = db.get_workouts(1)
        assert workouts[0]["note"] == "Updated note"


# ── get_workout_count ────────────────────────────────────────────


class TestGetWorkoutCount:
    def test_zero(self, tmp_db):
        assert db.get_workout_count(1) == 0

    def test_counts(self, tmp_db):
        _save_simple()
        _save_simple()
        assert db.get_workout_count(1) == 2


# ── get_stats_sql ────────────────────────────────────────────────


class TestGetStatsSql:
    def test_empty(self, tmp_db):
        stats = db.get_stats_sql(1)
        assert stats["total_workouts"] == 0
        assert stats["total_volume"] == 0

    def test_volume_calculation(self, tmp_db):
        # 3 sets x 10 reps x 50kg = 1500kg volume
        ex = _make_exercise(sets=3, reps=10, weight=50.0)
        db.save_workout(1, datetime.now(timezone.utc), [[ex]])
        stats = db.get_stats_sql(1)
        assert stats["total_workouts"] == 1
        assert stats["total_sets"] == 3
        assert stats["total_volume"] == 1500.0

    def test_unique_exercises(self, tmp_db):
        db.save_workout(1, datetime.now(timezone.utc), [
            [_make_exercise(name="Bench")],
            [_make_exercise(name="Squats")],
        ])
        db.save_workout(1, datetime.now(timezone.utc), [
            [_make_exercise(name="bench")],  # same exercise, different case
        ])
        stats = db.get_stats_sql(1)
        assert stats["unique_exercises"] == 2  # bench + squats
