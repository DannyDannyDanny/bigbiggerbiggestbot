"""
API + static file server for the Telegram Mini App.
Run alongside bot.py — serves the webapp/ folder and REST endpoints.
"""
import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qs

from aiohttp import web

import database as db
from config import BOT_TOKEN, API_HOST, API_PORT

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Telegram initData validation ─────────────────────────────────

def validate_init_data(init_data: str) -> dict | None:
    """
    Validate the Telegram WebApp initData string.
    Returns the parsed user dict if valid, None otherwise.
    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None

    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        return None

    # Build the data-check-string: sorted key=value pairs, excluding "hash"
    data_pairs = []
    for key, values in parsed.items():
        if key == "hash":
            continue
        data_pairs.append(f"{key}={values[0]}")
    data_pairs.sort()
    data_check_string = "\n".join(data_pairs)

    # HMAC-SHA256 with secret = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        logger.warning("Invalid initData hash")
        return None

    # Parse the user JSON
    user_json = parsed.get("user", [None])[0]
    if not user_json:
        return None

    try:
        user = json.loads(user_json)
        return user
    except json.JSONDecodeError:
        return None


# ── Auth middleware ───────────────────────────────────────────────

def get_user_id(request: web.Request) -> int | None:
    """Extract and validate the user from the request headers."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    # In production, always validate. For local dev, allow a fallback.
    user = validate_init_data(init_data)
    if user:
        # Upsert user record
        db.upsert_user(
            telegram_id=user["id"],
            first_name=user.get("first_name", ""),
            username=user.get("username", ""),
        )
        return user["id"]

    # DEV FALLBACK: if token is placeholder, allow X-Dev-User-Id header
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        dev_id = request.headers.get("X-Dev-User-Id")
        if dev_id:
            return int(dev_id)

    return None


def require_auth(handler):
    """Decorator that rejects unauthenticated requests."""
    async def wrapper(request: web.Request):
        user_id = get_user_id(request)
        if not user_id:
            return web.json_response({"error": "Unauthorized"}, status=401)
        request["user_id"] = user_id
        return await handler(request)
    return wrapper


# ── API Routes ───────────────────────────────────────────────────

# Exercises

@require_auth
async def get_exercises(request: web.Request):
    exercises = db.get_exercises(request["user_id"])
    return web.json_response({"exercises": exercises})


@require_auth
async def create_exercise(request: web.Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return web.json_response({"error": "Name is required"}, status=400)
    try:
        exercise = db.add_exercise(request["user_id"], name)
        return web.json_response({"exercise": exercise}, status=201)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


@require_auth
async def delete_exercise(request: web.Request):
    exercise_id = int(request.match_info["id"])
    ok = db.delete_exercise(request["user_id"], exercise_id)
    if not ok:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response({"ok": True})


# Workouts

@require_auth
async def get_workouts(request: web.Request):
    workouts = db.get_recent_workouts(request["user_id"])
    # Attach summaries
    result = []
    for w in workouts:
        w["summary"] = db.get_workout_summary(w["id"])
        result.append(w)
    return web.json_response({"workouts": result})


@require_auth
async def get_active_workout(request: web.Request):
    workout = db.get_active_workout(request["user_id"])
    return web.json_response({"workout": workout})


@require_auth
async def create_workout(request: web.Request):
    # Check if there's already an active one
    active = db.get_active_workout(request["user_id"])
    if active:
        return web.json_response({"workout": active})
    workout = db.start_workout(request["user_id"])
    return web.json_response({"workout": workout}, status=201)


@require_auth
async def finish_workout(request: web.Request):
    workout_id = int(request.match_info["id"])
    workout = db.finish_workout(workout_id, request["user_id"])
    if not workout:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response({"workout": workout})


# Sets

@require_auth
async def get_workout_sets(request: web.Request):
    workout_id = int(request.match_info["id"])
    sets = db.get_workout_sets(workout_id)
    return web.json_response({"sets": sets})


@require_auth
async def create_set(request: web.Request):
    workout_id = int(request.match_info["id"])
    body = await request.json()

    exercise_id = body.get("exercise_id")
    reps = body.get("reps")
    weight = body.get("weight", 0)

    if not exercise_id or not reps:
        return web.json_response(
            {"error": "exercise_id and reps are required"}, status=400
        )

    new_set = db.add_set(workout_id, exercise_id, int(reps), float(weight))
    return web.json_response({"set": new_set}, status=201)


@require_auth
async def delete_set(request: web.Request):
    set_id = int(request.match_info["id"])
    ok = db.delete_set(set_id)
    if not ok:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response({"ok": True})


# ── App setup ────────────────────────────────────────────────────

def create_app() -> web.Application:
    db.init_db()

    app = web.Application()

    # API routes
    app.router.add_get("/api/exercises", get_exercises)
    app.router.add_post("/api/exercises", create_exercise)
    app.router.add_delete("/api/exercises/{id}", delete_exercise)

    app.router.add_get("/api/workouts", get_workouts)
    app.router.add_get("/api/workouts/active", get_active_workout)
    app.router.add_post("/api/workouts", create_workout)
    app.router.add_post("/api/workouts/{id}/finish", finish_workout)

    app.router.add_get("/api/workouts/{id}/sets", get_workout_sets)
    app.router.add_post("/api/workouts/{id}/sets", create_set)
    app.router.add_delete("/api/sets/{id}", delete_set)

    # Serve the webapp/ folder for the Mini App
    import pathlib
    webapp_dir = pathlib.Path(__file__).parent / "webapp"
    app.router.add_static("/", webapp_dir, show_index=True)

    return app


if __name__ == "__main__":
    app = create_app()
    logger.info("Server starting on %s:%s", API_HOST, API_PORT)
    web.run_app(app, host=API_HOST, port=API_PORT)
