"""Telegram Fitness Bot — track your workouts."""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db import init_db, save_workout, get_workouts, get_workout_count
from parser import parse_workout, format_workout

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Token resolution: secrets file → .env / environment variable
SECRETS_FILE = os.path.expanduser("~/.secrets/bigbiggerbiggestbot")


def _load_token() -> str:
    # 1. Try the secrets file
    if os.path.isfile(SECRETS_FILE):
        token = open(SECRETS_FILE).read().strip()
        if token:
            return token
    # 2. Fall back to env var (set via .env or shell)
    token = os.environ.get("BOT_TOKEN", "").strip()
    if token:
        return token
    raise RuntimeError(
        f"No bot token found. Put it in {SECRETS_FILE} or set BOT_TOKEN env var."
    )


BOT_TOKEN = _load_token()

# Mini App URL — set automatically by start.py via localtunnel
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")


# ── Helpers ──────────────────────────────────────────────────────────────────


def extract_timestamp(update: Update) -> tuple[datetime, bool]:
    """
    Get the best timestamp for a workout message.

    In python-telegram-bot v21+, forwarded message info lives on
    message.forward_origin (a MessageOrigin object) with a .date attribute.

    Returns (timestamp, is_forwarded).
    """
    msg = update.effective_message

    # v21+: forward_origin is set when a user forwards a message
    origin = getattr(msg, "forward_origin", None)
    if origin is not None and hasattr(origin, "date"):
        return origin.date.replace(tzinfo=timezone.utc), True

    return msg.date.replace(tzinfo=timezone.utc), False


# ── Command handlers ────────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💪 <b>Fitness Tracker Bot</b>\n\n"
        "Send me your workout and I'll save it!\n\n"
        "<b>Format:</b>\n"
        "<code>Bench press: 4x8x35</code>\n"
        "<code>Lateral raise: 4x8x4</code>\n\n"
        "<code>Tri Press rom: 3x10x45</code>\n\n"
        "Lines without a blank line between them = superset.\n"
        "Machine IDs go in parentheses: <code>Lat pulldown (500): 3x5x45</code>\n\n"
        "You can also <b>forward</b> messages from Saved Messages — "
        "I'll use the original timestamp.\n\n"
        "<b>Commands:</b>\n"
        "/history — view recent workouts\n"
        "/stats — quick summary"
    )

    if WEBAPP_URL:
        btn = InlineKeyboardButton(
            text="Open Workout Tracker",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[btn]]),
        )
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    workouts = get_workouts(user_id, limit=5)

    if not workouts:
        await update.message.reply_text("No workouts saved yet. Send me one!")
        return

    parts = []
    for w in workouts:
        ts = datetime.fromisoformat(w["timestamp"])
        header = f"📅 <b>{ts.strftime('%a %d %b %Y, %H:%M')}</b>"
        body = format_workout(w["superset_groups"])
        parts.append(f"{header}\n{body}")

    text = "\n\n───────────────\n\n".join(parts)
    total = get_workout_count(user_id)
    text += f"\n\n<i>Showing latest 5 of {total} workouts.</i>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    total = get_workout_count(user_id)

    if total == 0:
        await update.message.reply_text("No workouts yet — send me your first one!")
        return

    workouts = get_workouts(user_id, limit=1000)

    # Collect all unique exercise names
    exercise_names = set()
    total_sets = 0
    total_volume = 0.0
    for w in workouts:
        for group in w["superset_groups"]:
            for ex in group:
                exercise_names.add(ex["name"].lower())
                total_sets += ex["sets"]
                total_volume += ex["sets"] * ex["reps"] * ex["weight_kg"]

    await update.message.reply_text(
        f"📊 <b>Your Stats</b>\n\n"
        f"  • Workouts logged: <b>{total}</b>\n"
        f"  • Unique exercises: <b>{len(exercise_names)}</b>\n"
        f"  • Total sets: <b>{total_sets}</b>\n"
        f"  • Total volume: <b>{total_volume:,.0f} kg</b>",
        parse_mode=ParseMode.HTML,
    )


# ── Message handler (workout parsing) ───────────────────────────────────────


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse any text message as a potential workout."""
    text = update.effective_message.text
    if not text:
        return

    groups = parse_workout(text)
    if not groups:
        # Not a workout message — silently ignore so the bot isn't noisy
        return

    user_id = update.effective_user.id
    timestamp, is_forwarded = extract_timestamp(update)

    superset_dicts = [[ex.to_dict() for ex in group] for group in groups]
    workout_id = save_workout(user_id, timestamp, superset_dicts, raw_text=text)

    # Count totals for the confirmation
    total_exercises = sum(len(g) for g in groups)
    total_sets = sum(ex.sets for g in groups for ex in g)
    supersets = sum(1 for g in groups if len(g) > 1)

    ts_str = timestamp.strftime("%a %d %b %Y, %H:%M")

    confirm_parts = [
        f"✅ <b>Workout #{workout_id} saved!</b>",
        f"📅 {ts_str}" + (" (from forwarded message)" if is_forwarded else ""),
        f"🏋️ {total_exercises} exercises, {total_sets} total sets",
    ]
    if supersets:
        confirm_parts.append(f"🔗 {supersets} superset(s)")

    confirm_parts.append(f"\n{format_workout(superset_dicts)}")

    await update.message.reply_text(
        "\n".join(confirm_parts),
        parse_mode=ParseMode.HTML,
    )


# ── Main ─────────────────────────────────────────────────────────────────────


async def post_init(app: Application):
    """Set the bot's menu button to open the Mini App (if URL is available)."""
    if WEBAPP_URL:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Workout",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        )
        logger.info("Menu button set to Mini App at %s", WEBAPP_URL)
    else:
        logger.info("No WEBAPP_URL — menu button not set")


def main():
    init_db()

    builder = ApplicationBuilder().token(BOT_TOKEN)
    if WEBAPP_URL:
        builder = builder.post_init(post_init)
    app = builder.build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Handle all text messages (including forwarded ones)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started — polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
