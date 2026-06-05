import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

import config
import utils


# ---------------- TELEGRAM ----------------

def send_message(text: str) -> bool:
    if not config.TOKEN or not config.CHANNEL_ID:
        print("ERROR: Missing TOKEN or CHANNEL_ID")
        return False

    url = f"https://api.telegram.org/bot{config.TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": config.CHANNEL_ID,
                "text": text,
                "parse_mode": "HTML"
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
        print("ERROR: database.json not found")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"Loaded {len(data)} events")
        return data

    except Exception as e:
        print("LOAD ERROR:", str(e))
        return []


# ---------------- DATE LOGIC ----------------

def get_mm_dd(date_str: str):
    """
    Поддерживает:
    YYYY-MM-DD
    DD-MM
    """
    try:
        parts = date_str.split("-")

        if len(parts) == 3:
            # YYYY-MM-DD
            return parts[1], parts[2]

        if len(parts) == 2:
            # DD-MM
            return parts[1], parts[0]

    except Exception as e:
        print("BAD DATE:", date_str, e)

    return None


# ---------------- CORE ----------------

def check_events():
    moscow_time = datetime.now(timezone.utc) + timedelta(hours=3)

    today_mm = f"{moscow_time.month:02d}"
    today_dd = f"{moscow_time.day:02d}"

    print(f"[CRON CHECK] {today_dd}-{today_mm}")
    print("Moscow time:", moscow_time.strftime("%Y-%m-%d %H:%M:%S"))

    utils.init_db()

    events = load_events()
    if not events:
        print("No events found")
        return

    found = False

    for item in events:
        print("CHECKING:", item)

        mm_dd = get_mm_dd(item.get("date", ""))

        if not mm_dd:
            continue

        mm, dd = mm_dd

        if mm != today_mm or dd != today_dd:
            continue

        found = True

        event_id = utils.make_event_id(item)

        if utils.is_sent(event_id):
            print("SKIP (already sent):", event_id)
            continue

        text = (
            "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ</b>\n\n"
            f"👤 {item.get('artist', 'Unknown')}\n"
            f"🎵 {item.get('group', 'Unknown')}\n"
            f"📅 {item.get('event', 'Unknown')}\n"
            f"🗓 {item.get('date', '')}"
        )

        if send_message(text):
            utils.mark_sent(event_id)
            print("SENT:", event_id)
        else:
            print("FAILED:", event_id)

    if not found:
        print("No events for today")


# ---------------- ENTRY ----------------

if __name__ == "__main__":
    print("===== BOT STARTED =====")

    print("TOKEN OK:", bool(config.TOKEN))
    print("CHANNEL:", config.CHANNEL_ID)

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
