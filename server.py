"""
API + static file server for the Telegram Mini App.
Serves webapp/ and REST endpoints, using the existing db.py layer.
"""
import csv
import hashlib
import hmac
import io
import json
import logging
import os
import pathlib
import subprocess
import zlib
from datetime import datetime, timezone
from urllib.parse import parse_qs

from aiohttp import web

from db import init_db, get_db, save_workout, get_workouts, get_workout_count, get_stats_sql, delete_workout, update_workout, export_workouts, get_user_workout_number
from parser import parse_workout, format_workout

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Version (computed once at startup) ───────────────────────────

def _resolve_ref(git_dir: pathlib.Path, ref: str) -> str | None:
    """Resolve a ref name to its SHA, handling loose and packed refs."""
    loose = git_dir / ref
    if loose.is_file():
        return loose.read_text().strip()
    packed = git_dir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text().splitlines():
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    return None


def _read_commit_date_utc(git_dir: pathlib.Path, sha: str) -> str | None:
    """Parse a loose commit object and return committer date as YYYY-MM-DD (UTC)."""
    obj_path = git_dir / "objects" / sha[:2] / sha[2:]
    if not obj_path.exists():
        return None  # packed — skip; recent HEAD is usually loose
    try:
        raw = zlib.decompress(obj_path.read_bytes())
        content = raw[raw.index(b"\0") + 1:].decode("utf-8", errors="replace")
        for line in content.splitlines():
            if line.startswith("committer "):
                # "committer Name <email> <unix-ts> <tz>"
                parts = line.rsplit(" ", 2)
                if len(parts) == 3 and parts[1].lstrip("-").isdigit():
                    ts = int(parts[1])
                    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return None
    except (OSError, ValueError, zlib.error):
        return None


def _compute_version() -> str:
    """Return '<YYYY-MM-DD> <short-sha>', with a pure-Python fallback for
    environments where the `git` binary isn't on PATH (e.g. minimal
    systemd service environments on NixOS).
    """
    repo_root = pathlib.Path(__file__).parent

    # Preferred: git (%cs = committer date short, %h = short SHA).
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs %h"],
            cwd=repo_root,
            capture_output=True, text=True, timeout=2, check=True,
        )
        if out.stdout.strip():
            return out.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    # Fallback: resolve HEAD + read commit object for the date.
    try:
        git_dir = repo_root / ".git"
        if not git_dir.is_dir():
            return "unknown"  # worktree or unusual layout
        head = (git_dir / "HEAD").read_text().strip()
        sha = _resolve_ref(git_dir, head[5:]) if head.startswith("ref: ") else head
        if not sha:
            return "unknown"
        short_sha = sha[:7]
        date = _read_commit_date_utc(git_dir, sha)
        return f"{date} {short_sha}" if date else short_sha
    except OSError:
        return "unknown"


_VERSION = _compute_version()


# ── Token (injected by start.py via env) ─────────────────────────

def _get_bot_token() -> str:
    return os.environ.get("BOT_TOKEN", "")


# ── Telegram initData validation ─────────────────────────────────

def validate_init_data(init_data: str) -> dict | None:
    """Validate Telegram WebApp initData. Returns user dict if valid."""
    if not init_data:
        return None

    bot_token = _get_bot_token()
    if not bot_token:
        return None

    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        return None

    data_pairs = []
    for key, values in parsed.items():
        if key == "hash":
            continue
        data_pairs.append(f"{key}={values[0]}")
    data_pairs.sort()
    data_check_string = "\n".join(data_pairs)

    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        logger.warning("Invalid initData hash")
        return None

    user_json = parsed.get("user", [None])[0]
    if not user_json:
        return None

    try:
        return json.loads(user_json)
    except json.JSONDecodeError:
        return None


# ── Auth middleware ───────────────────────────────────────────────

def get_user_id(request: web.Request) -> int | None:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = validate_init_data(init_data)
    if user:
        return user["id"]
    return None


def require_auth(handler):
    async def wrapper(request: web.Request):
        user_id = get_user_id(request)
        if not user_id:
            return web.json_response({"error": "Unauthorized"}, status=401)
        request["user_id"] = user_id
        return await handler(request)
    return wrapper


# ── API Routes ───────────────────────────────────────────────────

@require_auth
async def api_get_workouts(request: web.Request):
    """Return recent workouts with exercises."""
    limit = int(request.query.get("limit", "20"))
    offset = int(request.query.get("offset", "0"))
    workouts = get_workouts(request["user_id"], limit=limit, offset=offset)
    total = get_workout_count(request["user_id"])
    return web.json_response({"workouts": workouts, "total": total})


@require_auth
async def api_save_workout(request: web.Request):
    """Save a workout from structured JSON or raw text."""
    body = await request.json()
    raw_text = body.get("raw_text", "")
    superset_groups = body.get("superset_groups")
    note = body.get("note") or None

    if superset_groups:
        # Structured input from the Mini App UI
        from datetime import datetime, timezone
        workout_id = save_workout(
            user_id=request["user_id"],
            timestamp=datetime.now(timezone.utc),
            superset_groups=superset_groups,
            raw_text=raw_text or None,
            note=note,
        )
    elif raw_text:
        # Text-based input (same format as sending a message to the bot)
        groups, errors = parse_workout(raw_text)
        if not groups:
            error_lines = [e.line for e in errors] if errors else []
            return web.json_response(
                {"error": "Could not parse workout text", "failed_lines": error_lines},
                status=400,
            )
        from datetime import datetime, timezone
        superset_dicts = [[ex.to_dict() for ex in group] for group in groups]
        workout_id = save_workout(
            user_id=request["user_id"],
            timestamp=datetime.now(timezone.utc),
            superset_groups=superset_dicts,
            raw_text=raw_text,
            note=note,
        )
    else:
        return web.json_response(
            {"error": "Provide superset_groups or raw_text"}, status=400
        )

    user_number = get_user_workout_number(request["user_id"], workout_id)
    return web.json_response(
        {"workout_id": workout_id, "user_number": user_number},
        status=201,
    )


@require_auth
async def api_update_workout(request: web.Request):
    """Update a workout — soft-deletes old, creates new with same timestamp."""
    workout_id = int(request.match_info["workout_id"])
    body = await request.json()
    superset_groups = body.get("superset_groups")
    note = body.get("note") or None

    if not superset_groups:
        return web.json_response({"error": "Provide superset_groups"}, status=400)

    new_id = update_workout(request["user_id"], workout_id, superset_groups, note=note)
    if new_id is None:
        return web.json_response({"error": "Not found"}, status=404)
    user_number = get_user_workout_number(request["user_id"], new_id)
    return web.json_response({"workout_id": new_id, "user_number": user_number})


@require_auth
async def api_delete_workout(request: web.Request):
    """Soft-delete a workout by ID."""
    workout_id = int(request.match_info["workout_id"])
    if delete_workout(request["user_id"], workout_id):
        return web.json_response({"deleted": True})
    return web.json_response({"error": "Not found"}, status=404)


@require_auth
async def api_get_exercise_names(request: web.Request):
    """Return unique exercise names this user has logged (for autocomplete)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT e.name
               FROM exercises e
               JOIN superset_groups sg ON sg.id = e.superset_group_id
               JOIN workouts w ON w.id = sg.workout_id
               WHERE w.user_id = ?
               ORDER BY e.name""",
            (request["user_id"],),
        ).fetchall()
    return web.json_response({"exercises": [r["name"] for r in rows]})


@require_auth
async def api_get_stats(request: web.Request):
    """Return summary stats for the user."""
    stats = get_stats_sql(request["user_id"])
    return web.json_response(stats)


@require_auth
async def api_export_json(request: web.Request):
    """Export all workouts as JSON."""
    data = export_workouts(request["user_id"])
    return web.json_response({"records": data, "count": len(data)})


async def api_version(request: web.Request):
    """Return the running server version. Unauthenticated."""
    return web.json_response({"version": _VERSION})


@require_auth
async def api_export_csv(request: web.Request):
    """Export all workouts as CSV."""
    data = export_workouts(request["user_id"])

    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

    return web.Response(
        text=output.getvalue(),
        content_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=workouts.csv"},
    )


# ── App setup ────────────────────────────────────────────────────

def create_app() -> web.Application:
    init_db()

    app = web.Application()

    app.router.add_get("/api/workouts", api_get_workouts)
    app.router.add_post("/api/workouts", api_save_workout)
    app.router.add_put("/api/workouts/{workout_id}", api_update_workout)
    app.router.add_delete("/api/workouts/{workout_id}", api_delete_workout)
    app.router.add_get("/api/exercises", api_get_exercise_names)
    app.router.add_get("/api/stats", api_get_stats)
    app.router.add_get("/api/export/json", api_export_json)
    app.router.add_get("/api/export/csv", api_export_csv)
    app.router.add_get("/api/version", api_version)

    # Serve the webapp/ folder
    webapp_dir = pathlib.Path(__file__).parent / "webapp"

    async def index_handler(request):
        return web.FileResponse(webapp_dir / "index.html")

    app.router.add_get("/", index_handler)
    app.router.add_static("/", webapp_dir)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", "8080"))
    host = os.environ.get("API_HOST", "0.0.0.0")
    app = create_app()
    logger.info("Server starting on %s:%s", host, port)
    web.run_app(app, host=host, port=port)
