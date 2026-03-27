import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Dushanbe")
MORNING_HOUR = int(os.getenv("MORNING_HOUR", "9"))
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", "0"))
EVENING_HOUR = int(os.getenv("EVENING_HOUR", "21"))
EVENING_MINUTE = int(os.getenv("EVENING_MINUTE", "0"))
DB_PATH = os.getenv("DB_PATH", "accountability.db")

# After how many days of rolling should the bot flag a task
ROLL_FLAG_DAYS = 3
