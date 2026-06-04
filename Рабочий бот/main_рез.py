import os
import json
import requests
from datetime import datetime, timezone

import utils
import config
import sys


# ---------------- TELEGRAM ----------------

def send_message(text: str):
    url = f"https://api.telegram.org/bot{config.TOKEN}/sendMessage"

    try:
        resp = requests.post(
            url,
            json={
                "chat_id": config.CHANNEL_ID,
                "text": text
            },
            timeout=10
        )
        print("TG STATUS:", resp.status_code)
	print("TG RESPONSE:", resp.text)
    except Exception as e:
        print("TELEGRAM ERROR:", e)


# ---------------- DATA ----------------

def load_events():
    path = os.path.join(os.path.dirname(__file__), "database.json")

    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("LOAD EVENTS ERROR:", e)
        return []


# ---------------- DATE PARSE ----------------

def parse_date(date_str: str):
    try:
        parts = date_str.split("-")

        if len(parts) == 3 and len(parts[0]) == 4:
            return int(parts[2]), int(parts[1])

        return int(parts[0]), int(parts[1])

    except:
        return None


# ---------------- CORE ----------------

def check_events():
    now = datetime.now(timezone.utc)
    day, month = now.day, now.month

    print(f"[CRON CHECK] {day}-{month}")

    utils.init_db()

    events = load_events()

    if not events:
        print("No events found")
        return

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
            f"👤 {item.get('artist', 'Unknown')}\n"
            f"🎵 {item.get('group', 'Unknown')}\n"
            f"📅 {item.get('event', 'Unknown')}\n"
            f"🗓 {item.get('date', '')}"
        )

        send_message(text)
        utils.mark_sent(event_id)

        print("SENT:", event_id)


# ---------------- ENTRY ----------------

if __name__ == "__main__":
    if not utils.acquire_lock():
        print("Bot already running - exit")
        sys.exit(0)

    try:
        check_events()
    except Exception as e:
        print("FATAL ERROR:", e)
    finally:
        utils.release_lock()