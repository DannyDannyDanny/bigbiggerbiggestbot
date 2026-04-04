"""
Parse workout messages into structured data.

Supported formats per line:
    Exercise Name: SETSxREPSxWEIGHT          — e.g. Bench press: 4x8x35
    Exercise Name: SETSxREPS                  — bodyweight, e.g. Pull-ups: 3x10
    Exercise Name: REPSxWEIGHT, REPSxWEIGHT  — per-set, e.g. Shoulder press: 8x25, 5x35, 6x40
    Exercise Name: REPS, REPS, REPS           — bodyweight per-set, e.g. Pull-ups: 12, 10, 8
    Exercise Name (machine_id): ...           — optional machine ID in parentheses

Lines with no blank line between them form a superset group.
Blank lines separate superset groups.
"""

import re
from dataclasses import dataclass, field


@dataclass
class SetDetail:
    reps: int
    weight_kg: float

    def to_dict(self) -> dict:
        return {"reps": self.reps, "weight_kg": self.weight_kg}


@dataclass
class Exercise:
    name: str
    machine_id: str | None
    sets: int            # total number of sets
    reps: int            # reps of first set (for backward compat / simple display)
    weight_kg: float     # weight of first set (for backward compat / simple display)
    raw_line: str
    sets_detail: list[SetDetail] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "machine_id": self.machine_id,
            "sets": self.sets,
            "reps": self.reps,
            "weight_kg": self.weight_kg,
            "raw_line": self.raw_line,
            "sets_detail": [s.to_dict() for s in self.sets_detail],
        }


# Header pattern: captures exercise name and optional machine ID
HEADER_RE = re.compile(
    r"^(?P<name>.+?)"
    r"(?:\s*\((?P<machine>[^)]+)\))?"
    r"\s*:\s*"
    r"(?P<rest>.+)$",
    re.IGNORECASE,
)

# Classic format: SETSxREPSxWEIGHT (e.g. 4x8x35, 3x10)
CLASSIC_RE = re.compile(
    r"^(?P<sets>\d+)\s*[x*]\s*(?P<reps>\d+)"
    r"(?:\s*[x*]\s*(?P<weight>[\d.]+))?"
    r"$",
    re.IGNORECASE,
)

# Per-set entry: REPSxWEIGHT or just REPS (e.g. 8x25, or 12)
SET_ENTRY_RE = re.compile(
    r"^(?P<reps>\d+)"
    r"(?:\s*[x*]\s*(?P<weight>[\d.]+))?"
    r"$",
    re.IGNORECASE,
)


def parse_exercise_line(line: str) -> Exercise | None:
    """Parse a single exercise line. Returns None if it doesn't match."""
    line = line.strip()
    if not line:
        return None

    m = HEADER_RE.match(line)
    if not m:
        return None

    name = m.group("name").strip()
    machine_id = m.group("machine").strip() if m.group("machine") else None
    rest = m.group("rest").strip()

    # Try classic format first: SETSxREPSxWEIGHT or SETSxREPS
    classic = CLASSIC_RE.match(rest)
    if classic:
        sets = int(classic.group("sets"))
        reps = int(classic.group("reps"))
        weight = float(classic.group("weight")) if classic.group("weight") else 0.0
        details = [SetDetail(reps=reps, weight_kg=weight)] * sets
        return Exercise(
            name=name,
            machine_id=machine_id,
            sets=sets,
            reps=reps,
            weight_kg=weight,
            raw_line=line,
            sets_detail=details,
        )

    # Try comma-separated per-set format: 8x25, 5x35, 6x40 or 12, 10, 8
    entries = [e.strip() for e in rest.split(",")]
    details = []
    for entry in entries:
        em = SET_ENTRY_RE.match(entry)
        if not em:
            return None  # one bad entry invalidates the line
        reps = int(em.group("reps"))
        weight = float(em.group("weight")) if em.group("weight") else 0.0
        details.append(SetDetail(reps=reps, weight_kg=weight))

    if not details:
        return None

    return Exercise(
        name=name,
        machine_id=machine_id,
        sets=len(details),
        reps=details[0].reps,
        weight_kg=details[0].weight_kg,
        raw_line=line,
        sets_detail=details,
    )


class ParseError:
    """Represents a line that looks like a workout entry but failed to parse."""
    def __init__(self, line: str, reason: str):
        self.line = line
        self.reason = reason


def parse_workout(text: str) -> tuple[list[list[Exercise]], list[ParseError]]:
    """
    Parse a full workout message into superset groups.

    Returns (groups, errors):
      - groups: list of superset groups, each a list of Exercises
      - errors: list of ParseError for lines that looked like exercises but failed
    """
    lines = text.strip().splitlines()
    groups: list[list[Exercise]] = []
    current_group: list[Exercise] = []
    errors: list[ParseError] = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if current_group:
                groups.append(current_group)
                current_group = []
            continue

        exercise = parse_exercise_line(stripped)
        if exercise:
            current_group.append(exercise)
        elif ":" in stripped:
            # Has a colon — likely an attempted exercise line that failed to parse
            errors.append(ParseError(stripped, "could not parse sets/reps/weight after colon"))
        # Lines without colons are silently skipped (notes, headers, etc.)

    if current_group:
        groups.append(current_group)

    return groups, errors


def _fmt_weight(w: float) -> str:
    """Format weight: 70.0 → '70', 22.5 → '22.5'."""
    return str(int(w)) if w == int(w) else str(w)


def format_workout(superset_groups: list[list[dict]], include_raw: bool = False) -> str:
    """Format structured workout data back into readable text."""
    parts = []
    for i, group in enumerate(superset_groups):
        if i > 0:
            parts.append("")

        is_superset = len(group) > 1
        if is_superset:
            parts.append("\U0001f517 <b>Superset:</b>")

        for ex in group:
            machine = f" ({ex['machine_id']})" if ex.get("machine_id") else ""
            details = ex.get("sets_detail", [])
            if details and not all(
                d["reps"] == details[0]["reps"] and d["weight_kg"] == details[0]["weight_kg"]
                for d in details
            ):
                # Varying sets — show each
                set_strs = []
                for d in details:
                    if d["weight_kg"]:
                        set_strs.append(f"{d['reps']}x{_fmt_weight(d['weight_kg'])}kg")
                    else:
                        set_strs.append(f"{d['reps']}")
                line = f"  \u2022 {ex['name']}{machine}: {', '.join(set_strs)}"
            else:
                # Uniform sets — compact format
                w = ex.get('weight_kg', 0)
                if w:
                    line = f"  \u2022 {ex['name']}{machine}: {ex['sets']}x{ex['reps']}x{_fmt_weight(w)}kg"
                else:
                    line = f"  \u2022 {ex['name']}{machine}: {ex['sets']}x{ex['reps']}"
            parts.append(line)

    return "\n".join(parts)
