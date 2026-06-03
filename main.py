import os
import json
import time
import threading
import datetime
import requests
from flask import Flask

import config
import utils

# ---------------- INIT ----------------

app = Flask(__name__)
utils.init_db()

# ---------------- HEALTH CHECK ----------------

@app.get("/")
def home():
    return "Bot is running"

# ---------------- TELEGRAM (PURE HTTP) ----------------

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

def load_events():
    path = os.path.join(os.path.dirname(__file__), "database.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

events = load_events()

# ---------------- LOGIC ----------------

def parse_date(date_str):
    parts = date_str.split("-")
    try:
        if len(parts) == 3 and len(parts[0]) == 4:
            return int(parts[2]), int(parts[1])
        return int(parts[0]), int(parts[1])
    except:
        return None


def check_events():
    now = datetime.datetime.now()
    day, month = now.day, now.month

    print(f"[CHECK] {day}-{month}")

    state = utils.load_state()
    sent = set(state.get("sent", []))

    for item in events:
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
            f"👤 {item.get('artist')}\n"
            f"🎵 {item.get('group')}\n"
            f"📅 {item.get('event')}\n"
            f"🗓 {item.get('date')}"
        )

        send_message(text)

        sent.add(event_id)
        state["sent"] = list(sent)
        utils.save_state(state)

        print("SENT:", event_id)

# ---------------- BACKGROUND LOOP ----------------

def loop():
    while True:
        try:
            check_events()
        except Exception as e:
            print("ERROR:", e)

        time.sleep(60)

# ---------------- START THREAD ----------------

threading.Thread(target=loop, daemon=True).start()
