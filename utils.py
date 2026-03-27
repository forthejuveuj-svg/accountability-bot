import re
import datetime
import pytz
from config import TIMEZONE


def now_local():
    """Current time in the configured timezone."""
    tz = pytz.timezone(TIMEZONE)
    return datetime.datetime.now(tz)


def today_local():
    """Today's date in the configured timezone."""
    return now_local().date()


def parse_time(text):
    """
    Extract a time from the text (e.g. "at 3pm", "at 15:00", "at 3:30pm").
    Returns (text_without_time, time_or_None).
    """
    # "at 3pm", "at 3:30pm", "at 15:00", "at 3:30 pm"
    time_match = re.search(
        r"\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
        text, re.IGNORECASE,
    )
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = (time_match.group(3) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            cleaned = text[:time_match.start()] + text[time_match.end():]
            return cleaned.strip(), datetime.time(hour, minute)
    return text, None


def parse_due_date(text):
    """
    Extract a due date and optional time from a task string.
    Returns (clean_title, due_date, due_time_or_None).

    Supports:
      - "tomorrow", "today"
      - day names: "monday", "tuesday", ...
      - "by <day/date>"
      - DD/MM or DD.MM format
      - "at 3pm", "at 15:00", "at 3:30pm"
    """
    today = today_local()
    text = text.strip()

    # Extract time first (before date parsing)
    text, due_time = parse_time(text)

    lower = text.lower().strip()

    # Pattern: ends with "tomorrow"
    if lower.endswith("tomorrow"):
        title = text[: -len("tomorrow")].strip().rstrip(",").strip()
        return title, today + datetime.timedelta(days=1), due_time

    # Pattern: ends with "today"
    if lower.endswith("today"):
        title = text[: -len("today")].strip().rstrip(",").strip()
        return title or text, today, due_time

    # Pattern: ends with a day name
    day_names = [
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ]
    for i, day in enumerate(day_names):
        if lower.endswith(day) or lower.endswith("by " + day):
            clean = re.sub(rf"\s*(by\s+)?{day}\s*$", "", text, flags=re.IGNORECASE).strip()
            current_weekday = today.weekday()
            target_weekday = i
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7
            return clean, today + datetime.timedelta(days=days_ahead), due_time

    # Pattern: ends with DD/MM or DD.MM
    date_match = re.search(r"\s+(\d{1,2})[/.](\d{1,2})$", text)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = today.year
        try:
            due = datetime.date(year, month, day)
            if due < today:
                due = datetime.date(year + 1, month, day)
            title = text[: date_match.start()].strip()
            return title, due, due_time
        except ValueError:
            pass

    # Pattern: "by tomorrow" / "by today" in the middle
    by_match = re.search(r"\s+by\s+(tomorrow|today)$", text, re.IGNORECASE)
    if by_match:
        title = text[: by_match.start()].strip()
        if by_match.group(1).lower() == "tomorrow":
            return title, today + datetime.timedelta(days=1), due_time
        return title, today, due_time

    # No date found → default to today
    return text, today, due_time


def parse_mentioned_user(text):
    """
    Extract an @username mention from the beginning of a task string.
    Returns (username_or_none, remaining_text).
    """
    match = re.match(r"@(\w+)\s+(.+)", text.strip())
    if match:
        return match.group(1), match.group(2)
    return None, text


def streak_emoji(count):
    if count >= 14:
        return "👑"
    if count >= 7:
        return "⚡"
    if count >= 3:
        return "🔥"
    return ""


def format_time(t):
    """Format a time object for display, e.g. '3:00pm'."""
    if t is None:
        return ""
    hour = t.hour
    minute = t.minute
    ampm = "am" if hour < 12 else "pm"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12
    if minute == 0:
        return f"{display_hour}{ampm}"
    return f"{display_hour}:{minute:02d}{ampm}"


def format_task_line(task, show_owner=False):
    """Format a single task for display."""
    time_str = ""
    if task.due_time:
        time_str = f"  🕐 {format_time(task.due_time)}"

    overdue = ""
    if task.rolled_count > 0:
        overdue = f"  ⚠️ {task.rolled_count}d overdue"

    owner = ""
    if show_owner:
        owner = f"  ·  {task.owner_rel.display_name}"

    return f"    #{task.display_number}  {task.title}{owner}{time_str}{overdue}"
