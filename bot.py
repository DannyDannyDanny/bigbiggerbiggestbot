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

from db import init_db, save_workout, get_workouts, get_workout_count, get_stats_sql, delete_workout
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

# Mini App URL — set automatically by start.py via tunnel
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
        "\U0001f4aa <b>Fitness Tracker Bot</b>\n\n"
        "Send me your workout and I'll save it!\n\n"
        "<b>Formats:</b>\n"
        "<code>Bench press: 4x8x35</code>\n"
        "<code>Pull-ups: 3x10</code>  (bodyweight)\n"
        "<code>Shoulder press (3032): 8x25, 5x35, 6x40</code>\n\n"
        "Lines without a blank line between them = superset.\n"
        "Machine IDs go in parentheses.\n\n"
        "You can also <b>forward</b> messages from Saved Messages \u2014 "
        "I'll use the original timestamp.\n\n"
        "<b>Commands:</b>\n"
        "/history \u2014 view recent workouts\n"
        "/stats \u2014 quick summary\n"
        "/delete &lt;id&gt; \u2014 delete a workout\n"
        "/export \u2014 export all data as JSON"
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
        header = f"\U0001f4c5 <b>{ts.strftime('%a %d %b %Y, %H:%M')}</b>  (#{w['id']})"
        body = format_workout(w["superset_groups"])
        parts.append(f"{header}\n{body}")

    text = "\n\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n".join(parts)
    total = get_workout_count(user_id)
    text += f"\n\n<i>Showing latest 5 of {total} workouts.</i>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_stats_sql(user_id)

    if stats["total_workouts"] == 0:
        await update.message.reply_text("No workouts yet \u2014 send me your first one!")
        return

    await update.message.reply_text(
        f"\U0001f4ca <b>Your Stats</b>\n\n"
        f"  \u2022 Workouts logged: <b>{stats['total_workouts']}</b>\n"
        f"  \u2022 Unique exercises: <b>{stats['unique_exercises']}</b>\n"
        f"  \u2022 Total sets: <b>{stats['total_sets']}</b>\n"
        f"  \u2022 Total volume: <b>{stats['total_volume']:,.0f} kg</b>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "Usage: /delete &lt;workout_id&gt;\n"
            "Use /history to see workout IDs.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        workout_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Workout ID must be a number.")
        return

    if delete_workout(user_id, workout_id):
        await update.message.reply_text(f"\U0001f5d1 Workout #{workout_id} deleted.")
    else:
        await update.message.reply_text(
            f"Workout #{workout_id} not found (or not yours)."
        )


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send all workout data as a JSON file."""
    import json
    import io
    from db import export_workouts

    user_id = update.effective_user.id
    data = export_workouts(user_id)

    if not data:
        await update.message.reply_text("No workouts to export.")
        return

    content = json.dumps(data, indent=2, ensure_ascii=False)
    buf = io.BytesIO(content.encode("utf-8"))
    buf.name = "workouts_export.json"

    await update.message.reply_document(
        document=buf,
        caption=f"\U0001f4e6 Exported {len(data)} exercise records.",
    )


# ── Message handler (workout parsing) ───────────────────────────────────────


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse any text message as a potential workout."""
    text = update.effective_message.text
    if not text:
        return

    groups, errors = parse_workout(text)

    if not groups and not errors:
        # Doesn't look like a workout at all — silently ignore
        return

    if not groups and errors:
        # Looks like they tried but every line failed
        error_lines = "\n".join(f"  \u2022 <code>{e.line}</code>" for e in errors)
        await update.message.reply_text(
            f"\u26a0\ufe0f Could not parse workout. Check your format:\n\n"
            f"{error_lines}\n\n"
            f"<b>Expected formats:</b>\n"
            f"<code>Exercise: 4x8x35</code>\n"
            f"<code>Exercise: 3x10</code>  (bodyweight)\n"
            f"<code>Exercise: 8x25, 5x35, 6x40</code>",
            parse_mode=ParseMode.HTML,
        )
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
        f"\u2705 <b>Workout #{workout_id} saved!</b>",
        f"\U0001f4c5 {ts_str}" + (" (from forwarded message)" if is_forwarded else ""),
        f"\U0001f3cb\ufe0f {total_exercises} exercises, {total_sets} total sets",
    ]
    if supersets:
        confirm_parts.append(f"\U0001f517 {supersets} superset(s)")

    # Show errors for partially parsed workouts
    if errors:
        skipped = "\n".join(f"  \u2022 <code>{e.line}</code>" for e in errors)
        confirm_parts.append(f"\n\u26a0\ufe0f Skipped {len(errors)} unparseable line(s):\n{skipped}")

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
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("export", cmd_export))

    # Handle all text messages (including forwarded ones)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started \u2014 polling\u2026")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
