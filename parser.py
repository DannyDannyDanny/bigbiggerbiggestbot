"""
Parse workout messages into structured data.

Format per line:
    Exercise Name (optional_machine_id): SETSxREPSxWEIGHT

Lines with no blank line between them form a superset group.
Blank lines separate superset groups.
"""

import re
from dataclasses import dataclass


@dataclass
class Exercise:
    name: str
    machine_id: str | None
    sets: int
    reps: int
    weight_kg: float
    raw_line: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "machine_id": self.machine_id,
            "sets": self.sets,
            "reps": self.reps,
            "weight_kg": self.weight_kg,
            "raw_line": self.raw_line,
        }


# Matches lines like:
#   Bench press: 4x8x35
#   Lat pulldown (500): 3x5x45
#   Russian Twists: 3x15x0
EXERCISE_RE = re.compile(
    r"^(?P<name>.+?)"              # exercise name (lazy)
    r"(?:\s*\((?P<machine>\d+)\))?" # optional (machine_id)
    r"\s*:\s*"                      # colon separator
    r"(?P<sets>\d+)\s*x\s*"        # sets
    r"(?P<reps>\d+)\s*x\s*"        # reps
    r"(?P<weight>[\d.]+)"          # weight
    r"\s*$",
    re.IGNORECASE,
)


def parse_exercise_line(line: str) -> Exercise | None:
    """Parse a single exercise line. Returns None if it doesn't match."""
    line = line.strip()
    if not line:
        return None

    m = EXERCISE_RE.match(line)
    if not m:
        return None

    return Exercise(
        name=m.group("name").strip(),
        machine_id=m.group("machine"),
        sets=int(m.group("sets")),
        reps=int(m.group("reps")),
        weight_kg=float(m.group("weight")),
        raw_line=line,
    )


def parse_workout(text: str) -> list[list[Exercise]]:
    """
    Parse a full workout message into superset groups.

    Returns a list of groups, where each group is a list of Exercises.
    Consecutive non-blank lines form a superset group.
    Blank lines separate groups.
    """
    lines = text.strip().splitlines()
    groups: list[list[Exercise]] = []
    current_group: list[Exercise] = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            # blank line → end current group
            if current_group:
                groups.append(current_group)
                current_group = []
            continue

        exercise = parse_exercise_line(stripped)
        if exercise:
            current_group.append(exercise)
        # non-matching lines are silently skipped (e.g. notes, headers)

    # flush last group
    if current_group:
        groups.append(current_group)

    return groups


def format_workout(superset_groups: list[list[dict]], include_raw: bool = False) -> str:
    """Format structured workout data back into readable text."""
    parts = []
    for i, group in enumerate(superset_groups):
        if i > 0:
            parts.append("")  # blank line between groups

        is_superset = len(group) > 1
        if is_superset:
            parts.append("🔗 <b>Superset:</b>")

        for ex in group:
            machine = f" ({ex['machine_id']})" if ex.get("machine_id") else ""
            line = f"  • {ex['name']}{machine}: {ex['sets']}x{ex['reps']}x{ex['weight_kg']}kg"
            parts.append(line)

    return "\n".join(parts)
