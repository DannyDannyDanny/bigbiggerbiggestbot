"""Tests for the static exercise reference matcher."""
import exercise_db


class TestLookup:
    def test_loads_bundled_data(self):
        # Free-Exercise-DB ships ~870 entries; just sanity-check it's non-empty.
        assert len(exercise_db.ALL) > 500

    def test_exact_match(self):
        m = exercise_db.lookup("Pullups")
        assert m is not None
        assert m["name"] == "Pullups"
        assert "lats" in m["primary_muscles"]

    def test_case_insensitive(self):
        a = exercise_db.lookup("PULLUPS")
        b = exercise_db.lookup("pullups")
        assert a == b
        assert a["name"] == "Pullups"

    def test_hyphen_matches_compressed(self):
        # User types "Pull-ups", DB has "Pullups". Compressed form catches it.
        m = exercise_db.lookup("Pull-ups")
        assert m is not None
        assert m["name"] == "Pullups"

    def test_multi_word_substring(self):
        m = exercise_db.lookup("Romanian deadlift")
        assert m is not None
        assert m["name"] == "Romanian Deadlift"
        assert "hamstrings" in m["primary_muscles"]

    def test_ambiguous_single_token_returns_none(self):
        # Lots of DB entries contain "Bench" / "Squat" / "Deadlift" as one
        # token. Returning the shortest would mislead ("Bench" → "Bench Dips"
        # → triceps). Refuse instead.
        assert exercise_db.lookup("Bench") is None
        assert exercise_db.lookup("Squat") is None
        assert exercise_db.lookup("Deadlift") is None

    def test_nonsense_returns_none(self):
        assert exercise_db.lookup("flarbenstompf") is None
        assert exercise_db.lookup("") is None
        assert exercise_db.lookup("   ") is None

    def test_returned_shape(self):
        m = exercise_db.lookup("Pullups")
        # The slim view drops `instructions` and `images`.
        assert set(m.keys()) >= {
            "name", "primary_muscles", "secondary_muscles",
            "equipment", "category", "level",
        }
        assert "instructions" not in m
        assert "images" not in m
