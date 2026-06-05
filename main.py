import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

import config
import utils


# ---------------- TELEGRAM ----------------

def send_message(text: str):
    print("=== SEND MESSAGE DEBUG ===")
    print("TOKEN EXISTS:", bool(config.TOKEN))
    print("CHANNEL_ID EXISTS:", bool(config.CHANNEL_ID))

    print("TOKEN PREFIX:", config.TOKEN[:10] if config.TOKEN else None)
    print("CHANNEL_ID:", config.CHANNEL_ID)

    if not config.TOKEN:
        print("ERROR: TOKEN is empty")
        return False

    if not config.CHANNEL_ID:
        print("ERROR: CHANNEL_ID is empty")
        return False

    url = f"https://api.telegram.org/bot{config.TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": config.CHANNEL_ID,
                "text": text
            },
            timeout=30
        )

        print("TG STATUS:", response.status_code)
        print("TG RESPONSE:", response.text)

        return response.status_code == 200

    except Exception as e:
        print("TELEGRAM ERROR:", str(e))
        return False


# ---------------- DATA ----------------

def load_events():
    path = os.path.join(os.path.dirname(__file__), "database.json")

    print("DATABASE PATH:", path)

    if not os.path.exists(path):
        print("database.json not found")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            events = json.load(f)

        print(f"Loaded {len(events)} events")
        return events

    except Exception as e:
        print("LOAD EVENTS ERROR:", str(e))
        return []


# ---------------- DATE PARSE ----------------

def parse_date(date_str: str):
    try:
        parts = date_str.split("-")

        # YYYY-MM-DD
        if len(parts) == 3 and len(parts[0]) == 4:
            return int(parts[2]), int(parts[1])

        # DD-MM
        return int(parts[0]), int(parts[1])

    except Exception:
        print("BAD DATE FORMAT:", date_str)
        return None


# ---------------- CORE ----------------

def check_events():
    moscow_time = datetime.now(timezone.utc) + timedelta(hours=3)

    day = moscow_time.day
    month = moscow_time.month

    print(f"[CRON CHECK] {day:02d}-{month:02d}")
    print("Moscow time:", moscow_time.strftime("%Y-%m-%d %H:%M:%S"))

    utils.init_db()

    events = load_events()

    if not events:
        print("No events found")
        return

    found_today = False

    for item in events:
        print("CHECKING:", item)

        parsed = parse_date(item.get("date", ""))

        if not parsed:
            continue

        d, m = parsed

        if d != day or m != month:
            continue

        found_today = True

        event_id = utils.make_event_id(item)

        if utils.is_sent(event_id):
            print("Already sent:", event_id)
            continue

        text = (
            "🎸 РОК-СОБЫТИЕ СЕГОДНЯ\n\n"
            f"👤 {item.get('artist', 'Unknown')}\n"
            f"🎵 {item.get('group', 'Unknown')}\n"
            f"📅 {item.get('event', 'Unknown')}\n"
            f"🗓 {item.get('date', '')}"
        )

        success = send_message(text)

        if success:
            utils.mark_sent(event_id)
            print("SENT:", event_id)
        else:
            print("FAILED TO SEND:", event_id)

    if not found_today:
        print("No events for today")


# ---------------- ENTRY ----------------

if __name__ == "__main__":
    print("===== BOT STARTED =====")

    print("TOKEN EXISTS:", bool(config.TOKEN))
    print("CHANNEL_ID:", config.CHANNEL_ID)

    print("ENV CHECK:")
    print("TOKEN RAW:", repr(config.TOKEN))
    print("CHANNEL_ID RAW:", repr(config.CHANNEL_ID))

    if config.TOKEN:
        print("TOKEN PREFIX:", config.TOKEN[:10])
    else:
        print("TOKEN IS EMPTY ❌")

    if config.CHANNEL_ID:
        print("CHANNEL_ID OK ✔")
    else:
        print("CHANNEL_ID IS EMPTY ❌")

    if not utils.acquire_lock():
        print("Bot already running - exit")
        sys.exit(0)

    try:
        check_events()

    except Exception as e:
        print("FATAL ERROR:", str(e))

    finally:
        utils.release_lock()
        print("===== BOT FINISHED =====")
