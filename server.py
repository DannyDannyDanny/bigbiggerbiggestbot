"""
API + static file server for the Telegram Mini App.
Serves webapp/ and REST endpoints, using the existing db.py layer.
"""
import hashlib
import hmac
import json
import logging
import os
from urllib.parse import parse_qs

from aiohttp import web

from db import init_db, get_db, save_workout, get_workouts, get_workout_count
from parser import parse_workout, format_workout

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


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

    if superset_groups:
        # Structured input from the Mini App UI
        from datetime import datetime, timezone
        workout_id = save_workout(
            user_id=request["user_id"],
            timestamp=datetime.now(timezone.utc),
            superset_groups=superset_groups,
            raw_text=raw_text or None,
        )
    elif raw_text:
        # Text-based input (same format as sending a message to the bot)
        groups = parse_workout(raw_text)
        if not groups:
            return web.json_response({"error": "Could not parse workout text"}, status=400)
        from datetime import datetime, timezone
        superset_dicts = [[ex.to_dict() for ex in group] for group in groups]
        workout_id = save_workout(
            user_id=request["user_id"],
            timestamp=datetime.now(timezone.utc),
            superset_groups=superset_dicts,
            raw_text=raw_text,
        )
    else:
        return web.json_response(
            {"error": "Provide superset_groups or raw_text"}, status=400
        )

    return web.json_response({"workout_id": workout_id}, status=201)


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
    user_id = request["user_id"]
    total = get_workout_count(user_id)
    if total == 0:
        return web.json_response({
            "total_workouts": 0, "unique_exercises": 0,
            "total_sets": 0, "total_volume": 0,
        })

    workouts = get_workouts(user_id, limit=10000)
    exercise_names = set()
    total_sets = 0
    total_volume = 0.0
    for w in workouts:
        for group in w["superset_groups"]:
            for ex in group:
                exercise_names.add(ex["name"].lower())
                total_sets += ex["sets"]
                total_volume += ex["sets"] * ex["reps"] * ex["weight_kg"]

    return web.json_response({
        "total_workouts": total,
        "unique_exercises": len(exercise_names),
        "total_sets": total_sets,
        "total_volume": round(total_volume, 1),
    })


# ── App setup ────────────────────────────────────────────────────

def create_app() -> web.Application:
    init_db()

    app = web.Application()

    app.router.add_get("/api/workouts", api_get_workouts)
    app.router.add_post("/api/workouts", api_save_workout)
    app.router.add_get("/api/exercises", api_get_exercise_names)
    app.router.add_get("/api/stats", api_get_stats)

    # Serve the webapp/ folder
    import pathlib
    webapp_dir = pathlib.Path(__file__).parent / "webapp"
    app.router.add_static("/", webapp_dir, show_index=True)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", "8080"))
    host = os.environ.get("API_HOST", "0.0.0.0")
    app = create_app()
    logger.info("Server starting on %s:%s", host, port)
    web.run_app(app, host=host, port=port)
