import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# === CONFIG ===
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

API_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

DB_FILE = "database.json"


# === LOAD EVENTS ===
def load_events():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("ERROR loading database:", e)
        return []


# === SENT STORAGE (simple file-based) ===
SENT_FILE = "sent.json"


def load_sent():
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()


def save_sent(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent), f)


# === PARSE DATE ===
def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        return None


# === SEND MESSAGE ===
def send_message(text):
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        r = requests.post(API_URL, data=payload, timeout=10)
        print("Telegram response:", r.status_code, r.text)

        return r.status_code == 200
    except Exception as e:
        print("Telegram send error:", e)
        return False


# === MAIN LOGIC ===
def check_events():
    moscow_time = datetime.now(ZoneInfo("Europe/Moscow"))
    today = moscow_time.date()

    print("=== CRON START ===")
    print("Moscow time:", moscow_time)
    print("Today:", today)

    events = load_events()
    sent = load_sent()

    print("Loaded events:", len(events))
    print("Already sent:", len(sent))

    found = 0

    for item in events:
        event_date = parse_date(item.get("date", ""))

        if not event_date:
            continue

        if event_date != today:
            continue

        found += 1

        event_id = f"{item.get('date')}-{item.get('artist')}-{item.get('group')}"

        if event_id in sent:
            print("SKIP already sent:", event_id)
            continue

        text = (
            "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ</b>\n\n"
            f"👤 {item.get('artist', 'Unknown')}\n"
            f"🎵 {item.get('group', 'Unknown')}\n"
            f"📅 {item.get('event', 'Unknown')}\n"
            f"🗓 {item.get('date', '')}"
        )

        if send_message(text):
            sent.add(event_id)
            save_sent(sent)
            print("SENT:", event_id)
        else:
            print("FAILED:", event_id)

    if found == 0:
        print("No events for today")

    print("=== CRON END ===")


if __name__ == "__main__":
    check_events()
