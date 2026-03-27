"""
Command handlers for the accountability bot.

Group commands:
  /task <title> [date] [at time] – create a task (optionally with time)
  /task @user <title> [date]     – create a task for someone
  /done <number or name>         – mark a task as done
  /edit <number> <new task text> – edit title, date, time, or owner
  /drop <number>                 – remove a task
  /move <number> <date>          – reschedule a task
  /tasks                         – show today's tasks for the group
  /alltasks                      – show all open tasks by date
  /ppltasks                      – show all open tasks by person
  /mytasks                       – show your own tasks
  /help                          – show commands

DM commands:
  /start                         – register with the bot
  All task commands also work in DM (mapped to your most recent group)
"""

import datetime
import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import (
    Session, get_or_create_user, get_or_create_group, ensure_membership,
    create_task, get_task_by_number, get_all_tasks_by_number,
    get_open_tasks_for_date, get_all_open_tasks_for_group,
    search_open_tasks_by_name, get_or_create_streak, User, Group,
    GroupMember, Task,
)
from utils import (
    parse_due_date, parse_mentioned_user, today_local, streak_emoji,
    format_task_line, format_time,
)
from config import ROLL_FLAG_DAYS

logger = logging.getLogger(__name__)


def _register_chat(session, update: Update):
    """Register the user and (if group) the group + membership. Returns (user, group_or_None)."""
    tg_user = update.effective_user
    user = get_or_create_user(
        session,
        telegram_id=tg_user.id,
        first_name=tg_user.first_name or "",
        username=tg_user.username or "",
    )

    group = None
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        group = get_or_create_group(session, chat_id=chat.id, title=chat.title or "")
        ensure_membership(session, group, user)

    return user, group


def _find_user_group_for_dm(session, user):
    """If command is in DM, find the user's most recent group."""
    membership = (
        session.query(GroupMember)
        .filter_by(user_id=user.id)
        .order_by(GroupMember.joined_at.desc())
        .first()
    )
    if membership:
        return membership.group
    return None


# ── /start ───────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)
        session.commit()

        if update.effective_chat.type == "private":
            await update.message.reply_text(
                f"Hey {user.first_name}! 👋\n\n"
                "I'm your accountability bot. Add me to a group chat "
                "and I'll help your crew stay on track.\n\n"
                "Once I'm in a group, use /task to create tasks "
                "and /help to see all commands."
            )
        else:
            members = session.query(GroupMember).filter_by(group_id=group.id).count()
            await update.message.reply_text(
                f"Accountability bot active! ✅\n"
                f"{members} member(s) registered.\n\n"
                "Use /task to create tasks, /help for all commands.\n"
                "I'll post morning task lists and evening scoreboards daily."
            )
    finally:
        session.close()


# ── /help ────────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋  *Commands*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✏️  *Create tasks*\n"
        "  `/task Finish pitch deck` — due today\n"
        "  `/task Gym tomorrow at 3pm` — with time\n"
        "  `/task @user Review PR by friday` — assign to someone\n\n"
        "✅  *Complete tasks*\n"
        "  `/done 5` — mark task #5 as done\n"
        "  `/done gym` — mark a task matching \"gym\"\n\n"
        "🛠  *Manage tasks*\n"
        "  `/edit 5 New name tomorrow at 2pm` — edit a task\n"
        "  `/edit 5 @user Same task friday` — reassign\n"
        "  `/drop 5` — remove task #5\n"
        "  `/move 5 tomorrow` — reschedule task #5\n\n"
        "👀  *View tasks*\n"
        "  `/tasks` — today's tasks for the group\n"
        "  `/alltasks` — all open tasks by date\n"
        "  `/ppltasks` — all open tasks by person\n"
        "  `/mytasks` — just your tasks\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖  *Automatic*\n"
        "  📋  Morning — daily task list\n"
        "  📊  Evening — scoreboard + streaks\n"
        "  🔁  Unfinished tasks roll to next day\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ── /task ────────────────────────────────────────────────────────────────

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        # In DM, resolve the user's group
        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text(
                    "You're not in any group yet. Add me to a group first!"
                )
                return

        # Parse the task text
        raw_text = " ".join(context.args) if context.args else ""
        if not raw_text.strip():
            await update.message.reply_text(
                "Usage: `/task Finish pitch deck tomorrow`\n"
                "Or: `/task @user Review PR by friday`",
                parse_mode="Markdown",
            )
            return

        # Check for @mention (assigning to someone else)
        mentioned_username, remaining = parse_mentioned_user(raw_text)

        if mentioned_username:
            # Find the mentioned user in the group
            target_user = (
                session.query(User)
                .join(GroupMember, GroupMember.user_id == User.id)
                .filter(
                    GroupMember.group_id == group.id,
                    User.username == mentioned_username,
                )
                .first()
            )
            if not target_user:
                await update.message.reply_text(
                    f"@{mentioned_username} isn't registered in this group yet. "
                    "They need to send /start first."
                )
                return
            owner = target_user
            task_text = remaining
        else:
            owner = user
            task_text = raw_text

        # Parse due date and time
        title, due_date, due_time = parse_due_date(task_text)

        if not title:
            await update.message.reply_text("Task needs a title!")
            return

        task = create_task(session, group, owner, user, title, due_date, due_time)
        session.commit()

        # Format response
        due_str = "today" if due_date == today_local() else due_date.strftime("%a %b %d")
        time_str = ""
        if due_time:
            time_str = f"  ·  🕐  {format_time(due_time)}"
        owner_str = owner.display_name if owner.id != user.id else "you"

        await update.message.reply_text(
            f"✅  Task #{task.display_number} created\n\n"
            f"  📌  {title}\n"
            f"  👤  {owner_str}  ·  📅  {due_str}{time_str}"
        )

        # If assigned to someone else and we're in a group, notify
        if owner.id != user.id and update.effective_chat.type in ("group", "supergroup"):
            pass  # Already visible in group
        elif owner.id != user.id:
            # Created in DM for someone else — notify group
            try:
                await context.bot.send_message(
                    chat_id=group.chat_id,
                    text=(
                        f"📌 {user.display_name} assigned a task to {owner.display_name}:\n"
                        f"  #{task.display_number}. {title} (due {due_str})"
                    ),
                )
            except Exception as e:
                logger.warning(f"Could not notify group: {e}")

    finally:
        session.close()


# ── /done ────────────────────────────────────────────────────────────────

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text("You're not in any group yet.")
                return

        if not context.args:
            await update.message.reply_text(
                "Usage:\n"
                "  `/done 5` — by task number\n"
                "  `/done gym` — by name",
                parse_mode="Markdown",
            )
            return

        raw_arg = " ".join(context.args)

        # Try parsing as a number first
        task = None
        try:
            task_num = int(raw_arg)
            task = get_task_by_number(session, group.id, task_num)
            if not task:
                existing = get_all_tasks_by_number(session, group.id, task_num)
                if existing and existing.status == "done":
                    await update.message.reply_text(f"Task #{task_num} is already done! ✅")
                elif existing and existing.status == "dropped":
                    await update.message.reply_text(f"Task #{task_num} was dropped. 🗑")
                else:
                    await update.message.reply_text(f"Task #{task_num} not found.")
                return
        except ValueError:
            # Not a number — search by name
            matches = search_open_tasks_by_name(session, group.id, raw_arg)
            if not matches:
                await update.message.reply_text(
                    f"🔍 No open tasks matching \"{raw_arg}\"."
                )
                return
            elif len(matches) == 1:
                task = matches[0]
            else:
                lines = [f"🔍 Multiple tasks match \"{raw_arg}\":\n"]
                for t in matches:
                    lines.append(
                        f"  #{t.display_number}  {t.title}  ({t.owner_rel.display_name})"
                    )
                lines.append("\nReply with `/done <number>` to pick one.")
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                return

        # Mark the task as done (anyone in the group can do it)
        task.status = "done"
        task.completed_at = datetime.datetime.utcnow()
        task_owner = task.owner_rel

        # Count today's progress for the task owner
        today = today_local()
        open_tasks = (
            session.query(Task)
            .filter(
                Task.group_id == group.id,
                Task.owner_id == task.owner_id,
                Task.due_date <= today,
                Task.status == "open",
            )
            .count()
        )
        done_today = (
            session.query(Task)
            .filter(
                Task.group_id == group.id,
                Task.owner_id == task.owner_id,
                Task.status == "done",
                Task.completed_at >= datetime.datetime.combine(today, datetime.time.min),
            )
            .count()
        ) + 1  # +1 for the one we just completed

        total = open_tasks + done_today

        session.commit()

        # Build the completion message
        who_did_it = user.display_name
        if task.owner_id != user.id:
            who_did_it = f"{user.display_name} (for {task_owner.display_name})"

        progress_bar = _progress_bar(done_today, total)
        msg = (
            f"✅  {who_did_it} finished \"{task.title}\"\n"
            f"{progress_bar}  {done_today}/{total} today"
        )
        if done_today == total and total > 0:
            msg += "\n\n🎉  All tasks done! Great work!"

        if update.effective_chat.type == "private":
            await update.message.reply_text(
                f"✅  \"{task.title}\" done!  ({done_today}/{total} today)\n→ Posted to group."
            )
            try:
                await context.bot.send_message(chat_id=group.chat_id, text=msg)
            except Exception as e:
                logger.warning(f"Could not notify group: {e}")
        else:
            await update.message.reply_text(msg)

    finally:
        session.close()


def _progress_bar(done, total, length=10):
    """Build a text progress bar."""
    if total == 0:
        return "░" * length
    filled = round(length * done / total)
    return "▓" * filled + "░" * (length - filled)


# ── /drop ────────────────────────────────────────────────────────────────

async def drop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text("You're not in any group yet.")
                return

        if not context.args:
            await update.message.reply_text("Usage: `/drop 5`", parse_mode="Markdown")
            return

        try:
            task_num = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Task number must be a number.")
            return

        task = get_task_by_number(session, group.id, task_num)
        if not task:
            await update.message.reply_text(f"Task #{task_num} not found (or already done/dropped).")
            return

        # Owner or creator can drop
        if task.owner_id != user.id and task.creator_id != user.id:
            await update.message.reply_text("You can only drop your own tasks (or ones you created).")
            return

        task.status = "dropped"
        session.commit()

        await update.message.reply_text(f"🗑 Task #{task_num} dropped: \"{task.title}\"")

    finally:
        session.close()


# ── /edit ────────────────────────────────────────────────────────────────

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text("You're not in any group yet.")
                return

        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage:\n"
                "  `/edit 5 New task name tomorrow`\n"
                "  `/edit 5 @user New task at 3pm friday`",
                parse_mode="Markdown",
            )
            return

        try:
            task_num = int(context.args[0])
        except ValueError:
            await update.message.reply_text("First argument must be a task number.")
            return

        task = get_task_by_number(session, group.id, task_num)
        if not task:
            await update.message.reply_text(f"Task #{task_num} not found (or already done/dropped).")
            return

        raw_text = " ".join(context.args[1:])

        # Check for @mention (reassigning)
        mentioned_username, remaining = parse_mentioned_user(raw_text)

        if mentioned_username:
            target_user = (
                session.query(User)
                .join(GroupMember, GroupMember.user_id == User.id)
                .filter(
                    GroupMember.group_id == group.id,
                    User.username == mentioned_username,
                )
                .first()
            )
            if not target_user:
                await update.message.reply_text(
                    f"@{mentioned_username} isn't registered in this group yet."
                )
                return
            task.owner_id = target_user.id
            task_text = remaining
        else:
            task_text = raw_text

        # Parse new title, date, and time
        title, due_date, due_time = parse_due_date(task_text)

        # Build a summary of what changed
        changes = []

        if title and title != task.title:
            task.title = title
            changes.append("title")

        if due_date != task.due_date:
            task.due_date = due_date
            changes.append("date")

        if due_time is not None and due_time != task.due_time:
            task.due_time = due_time
            changes.append("time")

        if mentioned_username:
            changes.append("owner")

        if not changes:
            await update.message.reply_text("Nothing changed — task is the same.")
            return

        session.commit()

        due_str = "today" if task.due_date == today_local() else task.due_date.strftime("%a %b %d")
        time_str = ""
        if task.due_time:
            time_str = f"  ·  🕐  {format_time(task.due_time)}"

        await update.message.reply_text(
            f"✏️  Task #{task_num} updated  ({', '.join(changes)})\n\n"
            f"  📌  {task.title}\n"
            f"  👤  {task.owner_rel.display_name}  ·  📅  {due_str}{time_str}"
        )

    finally:
        session.close()


# ── /move ────────────────────────────────────────────────────────────────

async def move_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text("You're not in any group yet.")
                return

        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: `/move 5 tomorrow`",
                parse_mode="Markdown",
            )
            return

        try:
            task_num = int(context.args[0])
        except ValueError:
            await update.message.reply_text("First argument must be a task number.")
            return

        task = get_task_by_number(session, group.id, task_num)
        if not task:
            await update.message.reply_text(f"Task #{task_num} not found (or already done/dropped).")
            return

        if task.owner_id != user.id:
            await update.message.reply_text("You can only reschedule your own tasks.")
            return

        date_text = " ".join(context.args[1:])
        _, new_date, new_time = parse_due_date("placeholder " + date_text)

        task.due_date = new_date
        if new_time is not None:
            task.due_time = new_time
        session.commit()

        due_str = "today" if new_date == today_local() else new_date.strftime("%a %b %d")
        time_str = ""
        if new_time:
            time_str = f" at {format_time(new_time)}"
        await update.message.reply_text(
            f"📅  Task #{task_num} moved to {due_str}{time_str}: \"{task.title}\""
        )

    finally:
        session.close()


# ── /tasks ───────────────────────────────────────────────────────────────

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text("You're not in any group yet.")
                return

        today = today_local()
        text = build_morning_message(session, group, today)
        await update.message.reply_text(text)

    finally:
        session.close()


# ── /mytasks ─────────────────────────────────────────────────────────────

async def mytasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text("You're not in any group yet.")
                return

        today = today_local()
        tasks = (
            session.query(Task)
            .filter(
                Task.group_id == group.id,
                Task.owner_id == user.id,
                Task.status == "open",
                Task.due_date <= today,
            )
            .order_by(Task.due_date, Task.display_number)
            .all()
        )

        if not tasks:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎉  No open tasks!\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "You're all caught up. Use /task to add something new."
            )
            return

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📋  Your Tasks",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for t in tasks:
            lines.append(format_task_line(t))

        lines.append("")
        lines.append("💡  /done <number or name> to complete")
        await update.message.reply_text("\n".join(lines))

    finally:
        session.close()


# ── /alltasks ───────────────────────────────────────────────────────────

async def alltasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text("You're not in any group yet.")
                return

        tasks = get_all_open_tasks_for_group(session, group.id)

        if not tasks:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎉  No open tasks!\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "The group is all caught up."
            )
            return

        today = today_local()

        # Group tasks by date
        by_date = {}
        for t in tasks:
            if t.due_date not in by_date:
                by_date[t.due_date] = []
            by_date[t.due_date].append(t)

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📋  All Open Tasks",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        for due_date in sorted(by_date.keys()):
            date_tasks = by_date[due_date]

            if due_date < today:
                date_label = "⚠️  Overdue"
            elif due_date == today:
                date_label = "📌  Today"
            elif due_date == today + datetime.timedelta(days=1):
                date_label = "📅  Tomorrow"
            else:
                date_label = "📅  " + due_date.strftime("%A, %b %d")

            lines.append("")
            lines.append(f"{date_label}  —  {due_date.strftime('%b %d')}")

            # Group by person within each date
            by_owner = {}
            for t in date_tasks:
                if t.owner_id not in by_owner:
                    by_owner[t.owner_id] = {"user": t.owner_rel, "tasks": []}
                by_owner[t.owner_id]["tasks"].append(t)

            owner_list = list(by_owner.items())
            for idx, (owner_id, data) in enumerate(owner_list):
                u = data["user"]
                lines.append(f"  👤  {u.display_name}")
                for t in data["tasks"]:
                    lines.append(format_task_line(t))
                if idx < len(owner_list) - 1:
                    lines.append("")  # 1 blank line between people

            lines.append("")
            lines.append("")  # 2 blank lines between dates

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        total = len(tasks)
        lines.append(f"📊  {total} open task{'s' if total != 1 else ''} total")

        await update.message.reply_text("\n".join(lines))

    finally:
        session.close()


# ── /ppltasks ──────────────────────────────────────────────────────────

async def ppltasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user, group = _register_chat(session, update)

        if not group:
            group = _find_user_group_for_dm(session, user)
            if not group:
                await update.message.reply_text("You're not in any group yet.")
                return

        tasks = get_all_open_tasks_for_group(session, group.id)

        if not tasks:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎉  No open tasks!\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "The group is all caught up."
            )
            return

        today = today_local()

        # Group tasks by person
        by_owner = {}
        for t in tasks:
            if t.owner_id not in by_owner:
                by_owner[t.owner_id] = {"user": t.owner_rel, "tasks": []}
            by_owner[t.owner_id]["tasks"].append(t)

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━",
            "👥  Tasks by Person",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        for owner_id, data in by_owner.items():
            u = data["user"]
            owner_tasks = data["tasks"]
            count = len(owner_tasks)

            lines.append("")
            lines.append(f"👤  {u.display_name}  ·  {count} task{'s' if count != 1 else ''}")

            # Group this person's tasks by date
            by_date = {}
            for t in owner_tasks:
                if t.due_date not in by_date:
                    by_date[t.due_date] = []
                by_date[t.due_date].append(t)

            for due_date in sorted(by_date.keys()):
                if due_date < today:
                    date_label = "⚠️ Overdue"
                elif due_date == today:
                    date_label = "📌 Today"
                elif due_date == today + datetime.timedelta(days=1):
                    date_label = "📅 Tomorrow"
                else:
                    date_label = "📅 " + due_date.strftime("%a %b %d")

                lines.append(f"    {date_label}")
                for t in by_date[due_date]:
                    lines.append(format_task_line(t))

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        total = len(tasks)
        lines.append(f"📊  {total} open task{'s' if total != 1 else ''} total")

        await update.message.reply_text("\n".join(lines))

    finally:
        session.close()


# ── Message builders (used by handlers + scheduler) ──────────────────────

def build_morning_message(session, group, today):
    """Build the morning task list for a group."""
    tasks = get_open_tasks_for_date(session, group.id, today)

    if not tasks:
        return (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"☀️  Good morning!  —  {today.strftime('%A, %B %d')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "No tasks for today! Use /task to add some."
        )

    # Group tasks by owner
    by_owner = {}
    for t in tasks:
        if t.owner_id not in by_owner:
            by_owner[t.owner_id] = {"user": t.owner_rel, "tasks": []}
        by_owner[t.owner_id]["tasks"].append(t)

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"☀️  Good morning!  —  {today.strftime('%A, %B %d')}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for owner_id, data in by_owner.items():
        u = data["user"]
        user_tasks = data["tasks"]
        count = len(user_tasks)
        lines.append("")
        lines.append(f"👤  {u.display_name}  ·  {count} task{'s' if count != 1 else ''}")
        for t in user_tasks:
            lines.append(format_task_line(t))

    lines.append("")
    lines.append("")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡  /done <number or name> to complete  ·  /task to add more")
    return "\n".join(lines)


def build_evening_message(session, group, today):
    """Build the evening scoreboard for a group."""
    members = (
        session.query(GroupMember)
        .filter_by(group_id=group.id)
        .all()
    )

    if not members:
        return "📊  No members registered yet."

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊  Scoreboard  —  {today.strftime('%A, %B %d')}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    scoreboard = []
    uncompleted = []

    for mem in members:
        u = mem.user
        all_tasks = (
            session.query(Task)
            .filter(
                Task.group_id == group.id,
                Task.owner_id == u.id,
                Task.due_date <= today,
                Task.status.in_(["open", "done"]),
            )
            .all()
        )

        relevant = []
        for t in all_tasks:
            if t.status == "done" and t.completed_at:
                if t.completed_at.date() == today or t.due_date == today:
                    relevant.append(t)
            elif t.status == "open":
                relevant.append(t)

        if not relevant:
            continue

        done = sum(1 for t in relevant if t.status == "done")
        total = len(relevant)

        # Streak
        streak = get_or_create_streak(session, u.id, group.id)
        streak_str = ""
        if done == total and total > 0:
            if streak.last_completed_date == today - datetime.timedelta(days=1):
                streak.current_streak += 1
            elif streak.last_completed_date != today:
                streak.current_streak = 1
            streak.last_completed_date = today
            if streak.current_streak > streak.best_streak:
                streak.best_streak = streak.current_streak

            emoji = streak_emoji(streak.current_streak)
            if streak.current_streak >= 3:
                streak_str = f"  {emoji} {streak.current_streak}-day streak!"
        else:
            if total > 0 and streak.current_streak > 0:
                streak.current_streak = 0

        scoreboard.append((done, total, u, streak_str))

        for t in relevant:
            if t.status == "open":
                uncompleted.append(t)

    # Sort: completed first, then by done ratio
    scoreboard.sort(key=lambda x: (x[0] < x[1], -(x[0] / max(x[1], 1))))

    for done, total, u, streak_str in scoreboard:
        bar = _progress_bar(done, total)
        check = "  ✅" if done == total and total > 0 else ""
        lines.append("")
        lines.append(f"👤  {u.display_name}")
        lines.append(f"    {bar}  {done}/{total}{check}{streak_str}")

    # Summary
    total_done = sum(s[0] for s in scoreboard)
    total_all = sum(s[1] for s in scoreboard)
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊  Total: {total_done}/{total_all} tasks completed")

    # Uncompleted tasks (auto-roll)
    if uncompleted:
        lines.append("")
        lines.append("🔁  Rolled to tomorrow:")
        flagged = []
        for t in uncompleted:
            t.due_date = today + datetime.timedelta(days=1)
            t.rolled_count += 1
            rolled_note = ""
            if t.rolled_count >= ROLL_FLAG_DAYS:
                flagged.append(t)
                rolled_note = "  ⚠️"
            lines.append(f"    → {t.owner_rel.display_name}: {t.title}{rolled_note}")

        if flagged:
            lines.append("")
            for t in flagged:
                lines.append(
                    f"⚠️  \"{t.title}\" has been on {t.owner_rel.display_name}'s "
                    f"list for {t.rolled_count} days — /drop {t.display_number} or do it?"
                )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
