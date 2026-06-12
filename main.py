```python
import os
import json
import time
import hashlib
import logging
import requests

from datetime import datetime
from zoneinfo import ZoneInfo

# =====================
# CONFIG
# =====================

TOKEN = (os.getenv("TOKEN") or "").strip()
CHANNEL_ID = (os.getenv("CHANNEL_ID") or "").strip()

if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("TOKEN or CHANNEL_ID is missing")

DB_FILE = "database.json"
SENT_FILE = "sent.json"

API_URL = f"https://api.telegram.org/bot{TOKEN}"

session = requests.Session()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# =====================
# FILES
# =====================

def load_events():

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error("Database error: %s", e)
        return []


def load_sent():

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_sent(sent):

    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(sent), f, ensure_ascii=False, indent=2)


# =====================
# DATE
# =====================

def parse_date(date_str):

    date_str = date_str.strip()

    for fmt in ("%d-%m-%Y", "%d-%m"):

        try:
            return datetime.strptime(date_str, fmt).date()

        except ValueError:
            pass

    return None


# =====================
# TELEGRAM
# =====================

def check_bot():

    r = session.get(API_URL + "/getMe", timeout=10)

    if r.status_code != 200:
        raise RuntimeError("Telegram bot token is invalid")

    logging.info("Bot connected successfully")


def send_message(text):

    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    for attempt in range(3):

        try:

            r = session.post(
                API_URL + "/sendMessage",
                data=payload,
                timeout=15
            )

            if r.status_code == 200:
                return True

            logging.warning(
                "Telegram error %s %s",
                r.status_code,
                r.text
            )

        except Exception as e:
            logging.warning("Send error: %s", e)

        time.sleep(2)

    return False


# =====================
# EVENT ID
# =====================

def make_event_id(item):

    return hashlib.sha256(

        json.dumps(
            item,
            sort_keys=True,
            ensure_ascii=False
        ).encode("utf-8")

    ).hexdigest()


# =====================
# MESSAGE
# =====================

def build_message(item, current_year):

    text = (
        "🎸 <b>СЕГОДНЯ В ИСТОРИИ РОКА</b>\n\n"
        f"👤 <b>{item.get('artist','')}</b>\n"
        f"🎵 {item.get('group','')}\n\n"
        f"📖 {item.get('event','')}\n"
        f"📅 {item.get('date','')}"
    )

    event_date = parse_date(item.get("date", ""))

    if event_date and event_date.year != 1900:

        age = current_year - event_date.year

        if age > 0 and age % 5 == 0:

            text += f"\n\n🎉 Сегодня юбилей — {age} лет!"

    return text


# =====================
# MAIN
# =====================

def check_events():

    now = datetime.now(ZoneInfo("Europe/Moscow"))

    logging.info("Current Moscow time: %s", now)

    events = load_events()
    sent = load_sent()

    events.sort(
        key=lambda x: (
            x.get("artist", ""),
            x.get("group", "")
        )
    )

    updated = False
    found = 0

    processed = set()

    for item in events:

        event_date = parse_date(item.get("date", ""))

        if not event_date:
            continue

        if (
            event_date.day != now.day
            or event_date.month != now.month
        ):
            continue

        event_id = make_event_id(item)

        if event_id in processed:
            continue

        processed.add(event_id)

        found += 1

        if event_id in sent:
            continue

        message = build_message(item, now.year)

        if send_message(message):

            logging.info(
                "Sent: %s",
                item.get("artist")
            )

            sent.add(event_id)
            updated = True

    if updated:
        save_sent(sent)

    logging.info("Today's events: %s", found)


# =====================
# ENTRY
# =====================

if __name__ == "__main__":

    check_bot()
    check_events()
```
