"""
Telegram Fitness Bot — handles chat commands, reminders, and launches the Mini App.
"""
import logging

from telegram import (
    Update,
    WebAppInfo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database as db
from config import BOT_TOKEN, WEBAPP_URL

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────

def ensure_user(update: Update) -> dict:
    """Create or update the user record from the Telegram message."""
    tg_user = update.effective_user
    return db.upsert_user(
        telegram_id=tg_user.id,
        first_name=tg_user.first_name or "",
        username=tg_user.username or "",
    )


def format_summary(summary: dict) -> str:
    """Format a workout summary dict into a nice chat message."""
    if not summary:
        return "No workout data found."

    lines = [f"*Workout Summary*"]
    lines.append(f"Started: {summary['started_at']}")
    if summary.get("finished_at"):
        lines.append(f"Finished: {summary['finished_at']}")
    lines.append("")

    for exercise_name, sets in summary["exercises"].items():
        lines.append(f"*{exercise_name}*")
        for i, s in enumerate(sets, 1):
            lines.append(f"  Set {i}: {s['reps']} reps × {s['weight']} kg")
        lines.append("")

    lines.append(f"Total sets: {summary['total_sets']}")
    lines.append(f"Total volume: {summary['total_volume']} kg")
    return "\n".join(lines)


# ── Command handlers ─────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Greet the user and show the Mini App button."""
    ensure_user(update)
    webapp_btn = InlineKeyboardButton(
        text="Open Workout Tracker",
        web_app=WebAppInfo(url=WEBAPP_URL),
    )
    keyboard = InlineKeyboardMarkup([[webapp_btn]])

    await update.message.reply_text(
        "Hey! I'm your fitness tracker bot.\n\n"
        "Tap the button below to open the workout logger, "
        "or use these commands:\n"
        "/workout — start a new workout via chat\n"
        "/history — see your recent workouts\n"
        "/help — list all commands",
        reply_markup=keyboard,
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Commands*\n"
        "/start — show the Mini App button\n"
        "/workout — quick-start a new workout\n"
        "/finish — finish the current workout\n"
        "/history — recent workout summaries\n"
        "/help — this message",
        parse_mode="Markdown",
    )


async def cmd_workout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Start a new workout from chat."""
    user = ensure_user(update)
    active = db.get_active_workout(user["telegram_id"])
    if active:
        await update.message.reply_text(
            "You already have an active workout! "
            "Use /finish to end it, or open the Mini App to keep logging."
        )
        return

    workout = db.start_workout(user["telegram_id"])
    webapp_btn = InlineKeyboardButton(
        text="Log Sets",
        web_app=WebAppInfo(url=WEBAPP_URL),
    )
    keyboard = InlineKeyboardMarkup([[webapp_btn]])
    await update.message.reply_text(
        f"Workout #{workout['id']} started! Open the app to log your sets.",
        reply_markup=keyboard,
    )


async def cmd_finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Finish the active workout and send a summary."""
    user = ensure_user(update)
    active = db.get_active_workout(user["telegram_id"])
    if not active:
        await update.message.reply_text("No active workout to finish.")
        return

    db.finish_workout(active["id"], user["telegram_id"])
    summary = db.get_workout_summary(active["id"])
    text = format_summary(summary)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show recent workout summaries."""
    user = ensure_user(update)
    workouts = db.get_recent_workouts(user["telegram_id"], limit=5)
    if not workouts:
        await update.message.reply_text("No workouts yet! Tap /workout to start one.")
        return

    for w in workouts:
        summary = db.get_workout_summary(w["id"])
        text = format_summary(summary)
        await update.message.reply_text(text, parse_mode="Markdown")


# ── Web App data handler ────────────────────────────────────────

async def handle_web_app_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle data sent from the Mini App via Telegram.WebApp.sendData()."""
    data = update.effective_message.web_app_data.data
    logger.info("Received web app data: %s", data)
    await update.message.reply_text("Got it! Your workout has been saved.")


# ── Post-init: set the menu button ──────────────────────────────

async def post_init(app: Application):
    """Set the bot's menu button to open the Mini App."""
    await app.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Workout",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    )
    logger.info("Menu button set to Mini App at %s", WEBAPP_URL)


# ── Main ─────────────────────────────────────────────────────────

def main():
    db.init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("workout", cmd_workout))
    app.add_handler(CommandHandler("finish", cmd_finish))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data)
    )

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
