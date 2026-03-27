"""
Scheduled jobs: morning task list + evening scoreboard.
These run via python-telegram-bot's built-in JobQueue (APScheduler under the hood).
"""

import logging
from telegram.ext import ContextTypes
from database import Session, Group
from handlers import build_morning_message, build_evening_message
from utils import today_local

logger = logging.getLogger(__name__)


async def morning_job(context: ContextTypes.DEFAULT_TYPE):
    """Post the daily task list to every active group."""
    logger.info("Running morning job...")
    session = Session()
    try:
        groups = session.query(Group).all()
        today = today_local()

        for group in groups:
            try:
                text = build_morning_message(session, group, today)
                await context.bot.send_message(chat_id=group.chat_id, text=text)
                logger.info(f"Morning post sent to {group.title} ({group.chat_id})")
            except Exception as e:
                logger.error(f"Failed to send morning post to {group.chat_id}: {e}")
    finally:
        session.close()


async def evening_job(context: ContextTypes.DEFAULT_TYPE):
    """Post the evening scoreboard to every active group and roll unfinished tasks."""
    logger.info("Running evening job...")
    session = Session()
    try:
        groups = session.query(Group).all()
        today = today_local()

        for group in groups:
            try:
                text = build_evening_message(session, group, today)
                await context.bot.send_message(chat_id=group.chat_id, text=text)
                logger.info(f"Evening post sent to {group.title} ({group.chat_id})")
            except Exception as e:
                logger.error(f"Failed to send evening post to {group.chat_id}: {e}")

        session.commit()  # Commit rolled tasks + streak updates
    finally:
        session.close()
