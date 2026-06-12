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
    raise RuntimeError("TOKEN or CHANNEL_ID not specified")

API_URL = f"https://api.telegram.org/bot{TOKEN}"

DB_FILE = "database.json"
SENT_FILE = "sent.json"

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
        logging.error("Database loading error: %s", e)
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
            continue

    return None


# =====================
# TELEGRAM
# =====================

def check_bot():

    r = session.get(API_URL + "/getMe", timeout=10)

    if r.status_code != 200:
        raise RuntimeError("Invalid Telegram bot token")

    logging.info("Telegram bot connected")


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

            logging.warning("Telegram exception: %s", e)

        time.sleep(2)

    return False


# =====================
# EVENT ID
# =====================

def make_event_id(item):

    return hashlib.sha256(

        json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True
        ).encode("utf-8")

    ).hexdigest()


# =====================
# MESSAGE
# =====================

def build_message(item, current_year):

    text = (
        "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ</b>\n\n"
        f"👤 <b>{item.get('artist', '')}</b>\n"
        f"🎵 {item.get('group', '')}\n"
        f"📖 {item.get('event', '')}\n"
        f"🗓 {item.get('date', '')}"
    )

    event_date = parse_date(item.get("date", ""))
    event_text = item.get("event", "").lower()

    death_words = (
        "умер",
        "умерла",
        "скончался",
        "скончалась",
        "погиб",
        "погибла",
        "смерть"
    )

    is_death = any(word in event_text for word in death_words)

    if (
        event_date
        and event_date.year != 1900
        and not is_death
    ):

        age = current_year - event_date.year

        if age > 0 and age % 5 == 0:

            text += (
                f"\n\n🎉 <b>Сегодня исполняется "
                f"{age} лет этому событию!</b>"
            )

    return text


# =====================
# MAIN
# =====================

def check_events():

    now = datetime.now(ZoneInfo("Europe/Moscow"))

    logging.info("Current Moscow time: %s", now)

    events = load_events()
    sent = load_sent()

    processed = set()
    updated = False

    events.sort(
        key=lambda x: (
            x.get("artist", ""),
            x.get("group", "")
        )
    )

    today_found = 0

    for item in events:

        event_date = parse_date(item.get("date", ""))

        if not event_date:
            continue

        if (
            event_date.day != now.day
            or event_date.month != now.month
        ):
            continue

        today_found += 1

        event_id = make_event_id(item)

        if event_id in processed:
            continue

        processed.add(event_id)

        if event_id in sent:
            logging.info(
                "Already sent: %s",
                item.get("artist")
            )
            continue

        message = build_message(
            item,
            now.year
        )

        if send_message(message):

            logging.info(
                "Sent: %s",
                item.get("artist")
            )

            sent.add(event_id)
            updated = True

        else:

            logging.error(
                "Failed: %s",
                item.get("artist")
            )

    if updated:
        save_sent(sent)

    logging.info(
        "Today's events: %s",
        today_found
    )


# =====================
# ENTRY POINT
# =====================

if __name__ == "__main__":

    logging.info("===== BOT STARTED =====")

    check_bot()
    check_events()

    logging.info("===== BOT FINISHED =====")
```
