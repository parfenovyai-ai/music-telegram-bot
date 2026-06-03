import os
import json
import datetime
from typing import Any

from flask import Flask
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler

import config
import utils

# ---------------- INIT DB ----------------

utils.init_db()

# ---------------- Flask ----------------

app = Flask(__name__)

@app.get("/")
def home() -> str:
    return "Bot is running"

# ---------------- Bot ----------------

bot = Bot(token=config.TOKEN)

def send_message(text: str) -> None:
    try:
        bot.send_message(
            chat_id=config.CHANNEL_ID,
            text=text
        )
    except Exception as e:
        print(f"TELEGRAM ERROR: {e}")

# ---------------- Data ----------------

def load_rock_events() -> list[dict[str, Any]]:
    path = os.path.join(os.path.dirname(__file__), "database.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

rock_events = load_rock_events()

# ---------------- Logic ----------------

def parse_date(date_str: str):
    parts = date_str.split("-")
    try:
        # YYYY-MM-DD
        if len(parts) == 3 and len(parts[0]) == 4:
            return int(parts[2]), int(parts[1])

        # DD-MM-YYYY
        if len(parts) == 3:
            return int(parts[0]), int(parts[1])

        return None
    except:
        return None


def check_events():
    today = datetime.datetime.now()
    day, month = today.day, today.month

    print(f"[CHECK] {day}-{month}")

    state = utils.load_state()
    sent = set(state.get("sent", []))

    for item in rock_events:
        parsed = parse_date(item.get("date", ""))
        if not parsed:
            continue

        d, m = parsed

        if d != day or m != month:
            continue

        event_id = utils.make_event_id(item)

        if event_id in sent:
            continue

        text = (
            "🎸 РОК-СОБЫТИЕ СЕГОДНЯ\n\n"
            f"👤 {item.get('artist', 'Unknown')}\n"
            f"🎵 {item.get('group', 'Unknown')}\n"
            f"📅 {item.get('event', 'Unknown')}\n"
            f"🗓 {item.get('date', '')}"
        )

        send_message(text)

        sent.add(event_id)
        state["sent"] = list(sent)
        utils.save_state(state)

        print(f"SENT: {event_id}")

# ---------------- Scheduler ----------------

scheduler = None
scheduler_started = False

def start_scheduler():
    global scheduler, scheduler_started

    if scheduler_started:
        return

    scheduler_started = True

    scheduler = BackgroundScheduler()
    scheduler.add_job(check_events, "interval", minutes=1)
    scheduler.start()

    print("Scheduler started")

# ---------------- START ----------------

start_scheduler()
