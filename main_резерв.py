import os
import json
import datetime
import threading
import time
import requests
from flask import Flask

import config
import utils

# ---------------- FLASK ----------------

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"


# ---------------- STATE LOCK ----------------

scheduler_started = False


# ---------------- TELEGRAM API ----------------

def send_message(text: str):
    url = f"https://api.telegram.org/bot{config.TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            json={
                "chat_id": config.CHANNEL_ID,
                "text": text
            },
            timeout=10
        )
    except Exception as e:
        print("TELEGRAM ERROR:", e)


# ---------------- DATA ----------------

def load_rock_events():
    path = os.path.join(os.path.dirname(__file__), "database.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_events():
    return load_rock_events()


# ---------------- DATE PARSE ----------------

def parse_date(date_str: str):
    parts = date_str.split("-")

    try:
        # YYYY-MM-DD
        if len(parts) == 3 and len(parts[0]) == 4:
            return int(parts[2]), int(parts[1])

        # DD-MM-YYYY
        if len(parts) == 3:
            return int(parts[0]), int(parts[1])

    except:
        return None


# ---------------- CORE LOGIC ----------------

def check_events():
    today = datetime.datetime.now()
    day, month = today.day, today.month

    print(f"[CHECK] {day}-{month}")

    state = utils.load_state()
    sent = state.get("sent", [])

    for item in get_events():
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

        sent.append(event_id)
        state["sent"] = sent
        utils.save_state(state)

        print(f"SENT: {event_id}")


# ---------------- SCHEDULER ----------------

def scheduler_loop():
    while True:
        try:
            check_events()
        except Exception as e:
            print("SCHEDULER ERROR:", e)

        time.sleep(60)


def start_scheduler():
    global scheduler_started

    if scheduler_started:
        return

    scheduler_started = True

    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()


# ---------------- START ----------------

start_scheduler()