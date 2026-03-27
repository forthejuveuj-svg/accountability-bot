# Accountability Circle Bot 🎯

A Telegram bot that turns your friend group into an accountability circle — with tasks, daily scoreboards, streaks, and just enough social pressure to follow through.

---

## What It Does

- **Create tasks** for yourself or friends right in the group chat
- **Morning post** (9:00 AM) — shows everyone's tasks for the day
- **Mark done** in the group — everyone sees your wins
- **Evening scoreboard** (9:00 PM) — who crushed it, who didn't, streaks
- **Auto-roll** unfinished tasks to the next day (flags after 3 days)
- Works in **group chat** (primary) and **DM** (secondary)

---

## Commands

| Command | What it does | Example |
|---------|-------------|---------|
| `/task <title>` | Create task for yourself (due today) | `/task Finish pitch deck` |
| `/task <title> tomorrow` | Create task due tomorrow | `/task Gym tomorrow` |
| `/task @user <title>` | Assign task to someone | `/task @timur Review PR by friday` |
| `/done <N>` | Mark task #N as done | `/done 5` |
| `/drop <N>` | Remove task #N | `/drop 3` |
| `/move <N> <date>` | Reschedule task | `/move 5 tomorrow` |
| `/tasks` | Show today's tasks (everyone) | `/tasks` |
| `/mytasks` | Show just your tasks | `/mytasks` |
| `/help` | Show all commands | `/help` |

**Date formats:** `today`, `tomorrow`, day names (`monday`, `friday`), or `DD/MM` (`25/04`).

---

## Setup Guide (Step by Step)

### Step 1: Create Your Bot on Telegram

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., "Accountability Bot")
4. Choose a username (e.g., `my_accountability_bot`)
5. **Copy the token** — you'll need it in Step 3

Optional but recommended — tell BotFather to set commands:
```
/setcommands
```
Then select your bot and paste:
```
task - Create a new task
done - Mark a task as done
drop - Remove a task
move - Reschedule a task
tasks - Show today's tasks
mytasks - Show your tasks
help - Show all commands
```

### Step 2: Get the Code

If you have Git:
```bash
git clone <your-repo-url>
cd accountability-bot
```

Or just download all the files into a folder called `accountability-bot`.

### Step 3: Configure

```bash
cp .env.example .env
```

Edit `.env` and paste your bot token:
```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TIMEZONE=Asia/Dushanbe
```

### Step 4: Install & Run (Local)

You need Python 3.10+ installed.

```bash
pip install -r requirements.txt
python bot.py
```

The bot is now running! Add it to your Telegram group.

### Step 5: Add Bot to Your Group

1. Open your Telegram group
2. Tap the group name → Add Members → search your bot's username
3. Send `/start` in the group
4. Each member should also DM the bot `/start` to register

---

## Deploy to Railway (Free, Always Online)

Local is fine for testing, but you want the bot running 24/7. Railway is the easiest way.

1. Go to [railway.app](https://railway.app) and sign up (free tier available)
2. Click **New Project → Deploy from GitHub repo** (push your code to GitHub first)
3. Or click **New Project → Empty Project → Add a Service → Deploy from local**
4. Set environment variables in Railway dashboard:
   - `BOT_TOKEN` = your token
   - `TIMEZONE` = `Asia/Dushanbe`
   - `MORNING_HOUR` = `9`
   - `EVENING_HOUR` = `21`
5. Railway will auto-detect Python. If not, add this file:

**`Procfile`** (create in project root):
```
worker: python bot.py
```

**`runtime.txt`** (create in project root):
```
python-3.11.6
```

6. Deploy. Your bot runs 24/7.

---

## Deploy to Render (Alternative)

1. Go to [render.com](https://render.com), sign up
2. New → Background Worker
3. Connect your GitHub repo
4. Build command: `pip install -r requirements.txt`
5. Start command: `python bot.py`
6. Add environment variables (same as Railway)

---

## File Structure

```
accountability-bot/
├── bot.py              ← Entry point (run this)
├── config.py           ← Loads settings from .env
├── database.py         ← Database models + helpers
├── handlers.py         ← All /command handlers
├── scheduler.py        ← Morning + evening scheduled posts
├── utils.py            ← Date parsing, formatting
├── requirements.txt    ← Python dependencies
├── .env.example        ← Template for your settings
└── README.md           ← This file
```

---

## How It Looks in Practice

**Morning (9:00 AM):**
```
📋 Today — March 28

@jago (3 tasks)
  1. Finish pitch deck
  2. Review Timur's PR
  3. Call landlord

@timur (2 tasks)
  4. Ship auth flow
  5. Gym

Reply /done N to check off · /task to add more
```

**When someone finishes:**
```
✅ @jago finished "Finish pitch deck" (1/3 today)
```

**Evening (9:00 PM):**
```
📊 Today's Scoreboard — March 28

@timur — 2/2 ✅ (🔥 5-day streak!)
@jago — 2/3

Total: 4/5 tasks completed.

🔁 Rolled to tomorrow:
  → @jago: Call landlord ⚠️

⚠️ "Call landlord" has been on @jago's list for 3 days. /drop 3 or do it?
```

---

## Troubleshooting

**Bot doesn't respond in group:**
- Make sure the bot is an admin, OR go to @BotFather → `/setprivacy` → select your bot → **Disable** (this lets the bot read group messages)

**Scheduled messages not sending:**
- Make sure the bot has permission to send messages in the group
- Check that `TIMEZONE` is set correctly
- Check logs: `python bot.py` should show "Morning job scheduled at..."

**"User not registered" error:**
- Each person needs to DM the bot `/start` at least once to register

---

## What's Next (V2 Ideas)

Once this is working and your group uses it for a week:

- [ ] Natural language task creation (no `/task` prefix needed)
- [ ] Shared goals with hashtag tracking
- [ ] Weekly summary (Sunday evening)
- [ ] Snooze / weekend mode
- [ ] Multiple groups per user
- [ ] Web dashboard for stats
