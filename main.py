import datetime
import requests
import utils
import config
import json
import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"
# ---------------- TELEGRAM ----------------

def send_message(text: str):
    url = f"https://api.telegram.org/bot{config.TOKEN}/sendMessage"

    try:
        requests.post(url, json={
            "chat_id": config.CHANNEL_ID,
            "text": text
        }, timeout=10)
    except Exception as e:
        print("TELEGRAM ERROR:", e)

# ---------------- LOAD DATA ----------------

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

    print(f"[CRON CHECK] {day}-{month}")

    for item in events:
        parsed = parse_date(item.get("date", ""))
        if not parsed:
            continue

        d, m = parsed
        if d != day or m != month:
            continue

        event_id = utils.make_event_id(item)

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
