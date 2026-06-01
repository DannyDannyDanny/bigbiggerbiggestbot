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
    """Return the slim entry for the best name match, or None.

    Tiers (priority order):
      1. exact (case-insensitive)
      2. compressed exact — collapses hyphens/spaces ("Pull-ups" → "Pullups")
      3. word-boundary substring (only for multi-token inputs)
      4. token overlap requiring 100% coverage of the user's tokens
         (only for multi-token inputs)

    Single-token inputs (e.g. "Bench", "Squat", "RDL", "OHP") that don't hit
    tier 1 or 2 return None — there's no robust way to disambiguate without
    an alias table.
    """
    if not name:
        return None
    needle = name.strip()
    if not needle:
        return None
    lower = needle.lower()
    compressed = _compress(needle)
    if not compressed:
        return None

    # 1. Exact (case-insensitive).
    hit = _BY_LOWER_NAME.get(lower)
    if hit:
        return _slim(hit)

    # 2. Compressed exact — "Pull-ups" → "Pullups".
    hit = _BY_COMPRESSED.get(compressed)
    if hit:
        return _slim(hit)

    needle_toks = _tokens(needle)
    # Below here, partial matches only — and only for multi-token inputs.
    # A single token is too easily ambiguous (and short acronyms accidentally
    # hit character-level substrings of unrelated names).
    if len(needle_toks) < 2:
        return None

    # 3. Word-boundary substring (lowercase). "bench press" in "bench press
    # with chains" — yes. "rdl" in "hurdle" — no (no word break).
    substring_candidates: list[dict] = []
    for entry in ALL:
        n = entry.get("name", "")
        if not n:
            continue
        nl = n.lower()
        if lower in nl or nl in lower:
            substring_candidates.append(entry)
    if substring_candidates:
        # Prefer the shortest DB name (most specific to the typed input).
        substring_candidates.sort(key=lambda e: len(e["name"]))
        return _slim(substring_candidates[0])

    # 4. Token overlap, 100% coverage of the user's tokens. So "BB Row" with
    # tokens {bb, row} only matches a DB entry that contains both — it never
    # silently latches onto a "row" entry that doesn't share the "bb" cue.
    best: tuple[float, dict] | None = None
    for entry, db_toks in _TOKENS:
        if not db_toks:
            continue
        if not needle_toks <= db_toks:
            continue
        # All user tokens matched; tiebreak by DB-name length (shorter wins,
        # i.e. the most specific variant).
        score = -len(entry["name"])
        if best is None or score > best[0]:
            best = (score, entry)

    return _slim(best[1]) if best else None
