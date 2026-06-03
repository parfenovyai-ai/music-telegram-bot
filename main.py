<<<<<<< HEAD
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
=======
import datetime
import requests
import utils
import config
import json
import os
from flask import Flask
>>>>>>> dcf3434b2887ef3c0b027a9c1140273ac590d3f9

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"
<<<<<<< HEAD


# ---------------- STATE LOCK ----------------

scheduler_started = False


# ---------------- TELEGRAM API ----------------
=======
# ---------------- TELEGRAM ----------------
>>>>>>> dcf3434b2887ef3c0b027a9c1140273ac590d3f9

def send_message(text: str):
    url = f"https://api.telegram.org/bot{config.TOKEN}/sendMessage"

    try:
<<<<<<< HEAD
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
=======
        requests.post(url, json={
            "chat_id": config.CHANNEL_ID,
            "text": text
        }, timeout=10)
    except Exception as e:
        print("TELEGRAM ERROR:", e)

# ---------------- LOAD DATA ----------------

def load_events():
>>>>>>> dcf3434b2887ef3c0b027a9c1140273ac590d3f9
    path = os.path.join(os.path.dirname(__file__), "database.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

<<<<<<< HEAD

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

=======
events = load_events()

# ---------------- LOGIC ----------------

def parse_date(date_str):
    parts = date_str.split("-")
    try:
        if len(parts) == 3 and len(parts[0]) == 4:
            return int(parts[2]), int(parts[1])
        return int(parts[0]), int(parts[1])
>>>>>>> dcf3434b2887ef3c0b027a9c1140273ac590d3f9
    except:
        return None


<<<<<<< HEAD
# ---------------- CORE LOGIC ----------------

def check_events():
    today = datetime.datetime.now()
    day, month = today.day, today.month

    print(f"[CHECK] {day}-{month}")

    state = utils.load_state()
    sent = state.get("sent", [])

    for item in get_events():
=======
def check_events():
    now = datetime.datetime.now()
    day, month = now.day, now.month

    print(f"[CRON CHECK] {day}-{month}")

    for item in events:
>>>>>>> dcf3434b2887ef3c0b027a9c1140273ac590d3f9
        parsed = parse_date(item.get("date", ""))
        if not parsed:
            continue

        d, m = parsed
<<<<<<< HEAD

=======
>>>>>>> dcf3434b2887ef3c0b027a9c1140273ac590d3f9
        if d != day or m != month:
            continue

        event_id = utils.make_event_id(item)

<<<<<<< HEAD
        if event_id in sent:
            continue

        print("ADDING:", event_id)

        text = (
            "🎸 РОК-СОБЫТИЕ СЕГОДНЯ\n\n"
            f"👤 {item.get('artist', 'Unknown')}\n"
            f"🎵 {item.get('group', 'Unknown')}\n"
            f"📅 {item.get('event', 'Unknown')}\n"
            f"🗓 {item.get('date', '')}"
        )

        send_message(text)

        sent.append(event_id)

        print("STATE BEFORE SAVE:", state)

        state["sent"] = sent

        print("STATE AFTER SAVE:", state)

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
=======
        if utils.is_sent(event_id):
            continue

        text = (
            "🎸 РОК-СОБЫТИЕ СЕГОДНЯ\n\n"
            f"👤 {item.get('artist')}\n"
            f"🎵 {item.get('group')}\n"
            f"📅 {item.get('event')}\n"
            f"🗓 {item.get('date')}"
        )

        send_message(text)
        utils.mark_sent(event_id)

        print("SENT:", event_id)


# ---------------- ENTRY ----------------

if __name__ == "__main__":
    utils.init_db()
    check_events()
>>>>>>> dcf3434b2887ef3c0b027a9c1140273ac590d3f9
