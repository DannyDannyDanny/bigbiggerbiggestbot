"""Static exercise reference data from the Free-Exercise-DB.

Source: https://github.com/yuhonas/free-exercise-db (public domain).
Bundled at data/exercises.json (~870 entries). Loaded once at import.

Exports:
- `lookup(name)` — best-effort fuzzy name match → dict with primary/secondary
  muscles, equipment, etc. Returns None if no plausible match.
- `ALL` — the raw list (for ad-hoc queries).

Matching, in priority order:
  1. exact case-insensitive name match
  2. case-insensitive substring (either way)
  3. token-overlap score above a small threshold

Keep this conservative — a wrong match is worse than no match for the user.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Optional

_DATA_PATH = pathlib.Path(__file__).parent / "data" / "exercises.json"


def _load() -> list[dict]:
    try:
        with _DATA_PATH.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


ALL: list[dict] = _load()

# Normalised name → entry (case-insensitive exact key)
_BY_LOWER_NAME: dict[str, dict] = {e["name"].lower(): e for e in ALL if e.get("name")}


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _tokens(s: str) -> set[str]:
    return set(_TOKEN_RE.findall(s.lower()))


def _compress(s: str) -> str:
    """Collapse to lowercase alphanumeric, no separators.

    "Pull-Ups", "Pull Ups", "Pullups" all → "pullups".
    """
    return _NON_ALNUM.sub("", s.lower())


# Pre-compute token sets and compressed forms (one-time at import).
_TOKENS: list[tuple[dict, set[str]]] = [
    (e, _tokens(e["name"])) for e in ALL if e.get("name")
]
_COMPRESSED: list[tuple[dict, str]] = [
    (e, _compress(e["name"])) for e in ALL if e.get("name")
]
_BY_COMPRESSED: dict[str, dict] = {
    _compress(e["name"]): e for e in ALL if e.get("name")
}


# Public-facing slim shape — drop instructions/images for now (heavy).
def _slim(entry: dict) -> dict:
    return {
        "name": entry.get("name"),
        "primary_muscles": entry.get("primaryMuscles") or [],
        "secondary_muscles": entry.get("secondaryMuscles") or [],
        "equipment": entry.get("equipment"),
        "category": entry.get("category"),
        "level": entry.get("level"),
        "force": entry.get("force"),
        "mechanic": entry.get("mechanic"),
    }


def lookup(name: str) -> Optional[dict]:
    """Return the slim entry for the best name match, or None."""
    if not name:
        return None
    needle = name.strip()
    if not needle:
        return None
    lower = needle.lower()
    compressed = _compress(needle)
    if not compressed:
        return None

    # 1. Exact (case-insensitive)
    hit = _BY_LOWER_NAME.get(lower)
    if hit:
        return _slim(hit)

    # 2. Compressed exact — catches "Pull-ups" → "Pullups", etc.
    hit = _BY_COMPRESSED.get(compressed)
    if hit:
        return _slim(hit)

    # 3. Compressed substring (either direction).
    substring_candidates: list[dict] = [
        e for e, c in _COMPRESSED if compressed in c or c in compressed
    ]
    if substring_candidates:
        # Single-token generics ("Bench", "Squat", "Deadlift") match too many
        # specific DB entries. Refuse rather than confidently mislead the
        # user — the planned alias table will handle these properly.
        needle_toks = _tokens(needle)
        if len(needle_toks) == 1 and len(substring_candidates) > 2:
            return None
        substring_candidates.sort(key=lambda e: len(e["name"]))
        return _slim(substring_candidates[0])

    # 4. Token overlap (Jaccard-ish). Require ≥1 shared token AND that the
    # shared portion covers ≥50% of the user's tokens, so "row" doesn't
    # match "single arm cable row machine" via one stop-token.
    needle_toks = _tokens(needle)
    if not needle_toks:
        return None
    best: tuple[float, dict] | None = None
    for entry, db_toks in _TOKENS:
        if not db_toks:
            continue
        overlap = needle_toks & db_toks
        if not overlap:
            continue
        coverage = len(overlap) / len(needle_toks)
        if coverage < 0.5:
            continue
        # Score = coverage, tiebreak by DB-name length (shorter wins).
        score = coverage - 0.001 * len(entry["name"])
        if best is None or score > best[0]:
            best = (score, entry)

    return _slim(best[1]) if best else None
