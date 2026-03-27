"""
Accountability Circle Bot — Main entry point.

Run: python bot.py
"""

import logging
import pytz
from datetime import time
from telegram.ext import ApplicationBuilder, CommandHandler

from config import BOT_TOKEN, TIMEZONE, MORNING_HOUR, MORNING_MINUTE, EVENING_HOUR, EVENING_MINUTE
from database import init_db
from handlers import (
    start_command,
    help_command,
    task_command,
    done_command,
    edit_command,
    drop_command,
    move_command,
    tasks_command,
    mytasks_command,
    alltasks_command,
    ppltasks_command,
)
from scheduler import morning_job, evening_job

# ── Logging ──────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    # Initialize database
    init_db()
    logger.info("Database initialized.")

    # Build the bot application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ── Register command handlers ────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("edit", edit_command))
    app.add_handler(CommandHandler("drop", drop_command))
    app.add_handler(CommandHandler("move", move_command))
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(CommandHandler("mytasks", mytasks_command))
    app.add_handler(CommandHandler("alltasks", alltasks_command))
    app.add_handler(CommandHandler("ppltasks", ppltasks_command))

    # ── Schedule daily jobs ──────────────────────────────────────────────
    tz = pytz.timezone(TIMEZONE)
    job_queue = app.job_queue

    # Morning task list
    job_queue.run_daily(
        morning_job,
        time=time(hour=MORNING_HOUR, minute=MORNING_MINUTE, tzinfo=tz),
        name="morning_tasks",
    )
    logger.info(f"Morning job scheduled at {MORNING_HOUR:02d}:{MORNING_MINUTE:02d} {TIMEZONE}")

    # Evening scoreboard
    job_queue.run_daily(
        evening_job,
        time=time(hour=EVENING_HOUR, minute=EVENING_MINUTE, tzinfo=tz),
        name="evening_scoreboard",
    )
    logger.info(f"Evening job scheduled at {EVENING_HOUR:02d}:{EVENING_MINUTE:02d} {TIMEZONE}")

    # ── Start the bot ────────────────────────────────────────────────────
    logger.info("Bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
