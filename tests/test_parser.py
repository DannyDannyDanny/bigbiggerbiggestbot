from parser import parse_exercise_line, parse_workout, format_workout, _fmt_weight


# ── parse_exercise_line ──────────────────────────────────────────


class TestParseExerciseLine:
    def test_classic_format(self):
        ex = parse_exercise_line("Bench press: 4x8x35")
        assert ex.name == "Bench press"
        assert ex.sets == 4
        assert ex.reps == 8
        assert ex.weight_kg == 35.0
        assert len(ex.sets_detail) == 4
        assert all(s.reps == 8 and s.weight_kg == 35.0 for s in ex.sets_detail)

    def test_bodyweight(self):
        ex = parse_exercise_line("Pull-ups: 3x10")
        assert ex.sets == 3
        assert ex.reps == 10
        assert ex.weight_kg == 0.0

    def test_per_set_varying(self):
        ex = parse_exercise_line("Shoulder press: 8x25, 5x35, 6x40")
        assert ex.sets == 3
        assert ex.sets_detail[0].reps == 8
        assert ex.sets_detail[0].weight_kg == 25.0
        assert ex.sets_detail[1].reps == 5
        assert ex.sets_detail[1].weight_kg == 35.0
        assert ex.sets_detail[2].reps == 6
        assert ex.sets_detail[2].weight_kg == 40.0

    def test_per_set_bodyweight(self):
        ex = parse_exercise_line("Pull-ups: 12, 10, 8")
        assert ex.sets == 3
        assert [s.reps for s in ex.sets_detail] == [12, 10, 8]
        assert all(s.weight_kg == 0.0 for s in ex.sets_detail)

    def test_machine_id(self):
        ex = parse_exercise_line("Shoulder press (3032): 4x8x25")
        assert ex.machine_id == "3032"
        assert ex.name == "Shoulder press"

    def test_machine_id_with_per_set(self):
        ex = parse_exercise_line("Butterfly chest (5014): 7x40, 7x40, 5x45")
        assert ex.machine_id == "5014"
        assert ex.sets == 3

    def test_asterisk_separator(self):
        ex = parse_exercise_line("Deadlift: 3*5*100")
        assert ex.sets == 3
        assert ex.reps == 5
        assert ex.weight_kg == 100.0

    def test_decimal_weight(self):
        ex = parse_exercise_line("Bench: 3x8x22.5")
        assert ex.weight_kg == 22.5

    def test_no_colon_returns_none(self):
        assert parse_exercise_line("just text") is None

    def test_bad_format_after_colon_returns_none(self):
        assert parse_exercise_line("Foo: abc") is None

    def test_empty_string_returns_none(self):
        assert parse_exercise_line("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_exercise_line("   ") is None


# ── parse_workout ────────────────────────────────────────────────


class TestParseWorkout:
    def test_single_line(self):
        groups, errors = parse_workout("Bench: 4x8x35")
        assert len(groups) == 1
        assert len(groups[0]) == 1
        assert groups[0][0].name == "Bench"

    def test_superset_consecutive_lines(self):
        groups, errors = parse_workout("Bench: 4x8x35\nCurls: 3x10x15")
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_blank_line_separates_groups(self):
        groups, errors = parse_workout("Bench: 4x8x35\n\nSquats: 5x5x60")
        assert len(groups) == 2
        assert len(groups[0]) == 1
        assert len(groups[1]) == 1

    def test_errors_collected(self):
        groups, errors = parse_workout("Bench: 4x8x35\nBad: nope\nSquats: 5x5x60")
        assert len(groups) == 1  # bench and squats in one group (no blank line)
        assert len(groups[0]) == 2
        assert len(errors) == 1
        assert "Bad: nope" in errors[0].line

    def test_all_lines_fail(self):
        groups, errors = parse_workout("Bad: nope\nAlso bad: xyz")
        assert len(groups) == 0
        assert len(errors) == 2

    def test_lines_without_colon_skipped_silently(self):
        groups, errors = parse_workout("Note: this is a header\nBench: 4x8x35")
        # "Note: this is a header" has a colon but fails parse → error
        # Actually let me check: it tries to parse "this is a header" as sets
        # which fails, so it IS an error
        assert len(groups) == 1
        assert len(errors) == 1

    def test_plain_text_no_colon_no_error(self):
        groups, errors = parse_workout("just a note\nBench: 4x8x35")
        assert len(groups) == 1
        assert len(errors) == 0

    def test_empty_text(self):
        groups, errors = parse_workout("")
        assert groups == []
        assert errors == []

    def test_full_workout(self):
        text = """Shoulder press (3032): 8x25, 5x35, 6x40, 6x40
Butterfly chest (5014): 7x40, 7x40, 5x45
Bicep curl machine: 10x20, 5x25, 4x25
Ab curls: 3x7x70"""
        groups, errors = parse_workout(text)
        assert len(errors) == 0
        assert len(groups) == 1  # all consecutive = one superset group
        assert len(groups[0]) == 4


# ── format_workout ───────────────────────────────────────────────


class TestFormatWorkout:
    def test_uniform_sets_compact(self):
        data = [[{"name": "Bench", "machine_id": None, "sets": 4, "reps": 8,
                   "weight_kg": 35, "sets_detail": [{"reps": 8, "weight_kg": 35}] * 4}]]
        result = format_workout(data)
        assert "4x8x35kg" in result

    def test_varying_sets_listed(self):
        data = [[{"name": "Press", "machine_id": None, "sets": 2, "reps": 8,
                   "weight_kg": 25, "sets_detail": [
                       {"reps": 8, "weight_kg": 25}, {"reps": 5, "weight_kg": 35}]}]]
        result = format_workout(data)
        assert "8x25kg" in result
        assert "5x35kg" in result

    def test_machine_id_shown(self):
        data = [[{"name": "Press", "machine_id": "3032", "sets": 1, "reps": 8,
                   "weight_kg": 25, "sets_detail": [{"reps": 8, "weight_kg": 25}]}]]
        result = format_workout(data)
        assert "(3032)" in result

    def test_bodyweight_omits_kg(self):
        data = [[{"name": "Pull-ups", "machine_id": None, "sets": 3, "reps": 10,
                   "weight_kg": 0, "sets_detail": [{"reps": 10, "weight_kg": 0}] * 3}]]
        result = format_workout(data)
        assert "kg" not in result
        assert "3x10" in result

    def test_superset_label(self):
        data = [[
            {"name": "A", "machine_id": None, "sets": 1, "reps": 10, "weight_kg": 20,
             "sets_detail": [{"reps": 10, "weight_kg": 20}]},
            {"name": "B", "machine_id": None, "sets": 1, "reps": 10, "weight_kg": 20,
             "sets_detail": [{"reps": 10, "weight_kg": 20}]},
        ]]
        result = format_workout(data)
        assert "Superset" in result


# ── _fmt_weight ──────────────────────────────────────────────────


class TestFmtWeight:
    def test_integer(self):
        assert _fmt_weight(70.0) == "70"

    def test_fractional(self):
        assert _fmt_weight(22.5) == "22.5"

    def test_zero(self):
        assert _fmt_weight(0.0) == "0"
