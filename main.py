```python
import os
import json
import time
import hashlib
import logging
import requests

from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from requests.adapters import HTTPAdapter

from openai import OpenAI

# =====================
# CONFIG
# =====================

TOKEN = (os.getenv("TOKEN") or "").strip()
CHANNEL_ID = (os.getenv("CHANNEL_ID") or "").strip()
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()

if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("Missing TOKEN or CHANNEL_ID")

if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY")

API_URL = f"https://api.telegram.org/bot{TOKEN}"

DB_FILE = "database.json"
SENT_FILE = "sent.json"

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

MAX_RETRIES = 3
SEND_DELAY = 1

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================
# SESSION
# =====================

session = requests.Session()
session.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=10))

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
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logging.error("DB error: %s", e)
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
    if not date_str:
        return None

    for fmt in ("%d-%m-%Y", "%d-%m"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except:
            continue

    return None


# =====================
# TELEGRAM
# =====================

def check_bot():
    r = session.get(API_URL + "/getMe", timeout=10)
    if r.status_code != 200:
        raise RuntimeError("Invalid bot token")
    logging.info("Bot OK")


def send_message(text):

    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    for _ in range(MAX_RETRIES):
        try:
            r = session.post(API_URL + "/sendMessage", data=payload, timeout=15)

            if r.status_code == 200:
                return True

            logging.warning("Telegram error %s %s", r.status_code, r.text)

        except Exception as e:
            logging.warning("Telegram exception: %s", e)

        time.sleep(2)

    return False


# =====================
# EVENT ID
# =====================

def make_event_id(item, year):
    raw = json.dumps(item, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{year}_{h}"


# =====================
# AI GENERATION
# =====================

def ai_generate(item):

    prompt = f"""
Ты музыкальный редактор (стиль Rolling Stone / Classic Rock).

Напиши пост для Telegram.

ДАННЫЕ:
- Музыкант: {item.get('artist')}
- Группа: {item.get('group')}
- Событие: {item.get('event')}
- Дата: {item.get('date')}

ПРАВИЛА:
- 4–7 предложений
- стиль: журналистика о музыке
- без шаблонов и канцелярита
- объясни значение события для музыки
- живой, но не перегруженный текст
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Ты музыкальный журналист."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            max_tokens=50
        )

        return res.choices[0].message.content.strip()

    except Exception as e:
        logging.error("AI error: %s", e)
        return None


# =====================
# MESSAGE
# =====================

def build_message(item, year):

    artist = escape(item.get("artist", ""))
    group = escape(item.get("group", ""))
    date = escape(item.get("date", ""))

    ai_text = ai_generate(item)

    if not ai_text:
        ai_text = f"{artist} — {group}"

    return (
        "🎸 <b>ROCK HISTORY</b>\n\n"
        f"{ai_text}\n\n"
        f"👤 {artist}\n"
        f"🎵 {group}\n"
        f"📅 {date}"
    )


# =====================
# MAIN
# =====================

def check_events():

    start = time.perf_counter()

    now = datetime.now(MOSCOW_TZ)
    year = now.year

    logging.info("Start: %s", now)

    events = load_events()
    sent = load_sent()

    if not isinstance(events, list):
        return

    # чистим старые годы
    sent = {x for x in sent if x.startswith(f"{year}_")}

    processed = set()

    found = 0
    sent_count = 0
    skipped = 0

    events.sort(key=lambda x: (x.get("artist", ""), x.get("group", "")))

    for item in events:

        event_date = parse_date(item.get("date", ""))

        if not event_date:
            continue

        if event_date.day != now.day or event_date.month != now.month:
            continue

        found += 1

        event_id = make_event_id(item, year)

        if event_id in processed:
            continue

        processed.add(event_id)

        if event_id in sent:
            skipped += 1
            continue

        text = build_message(item, year)

        if send_message(text):
            sent.add(event_id)
            sent_count += 1
            logging.info("Sent: %s", item.get("artist"))
            time.sleep(SEND_DELAY)

        else:
            logging.error("Failed: %s", item.get("artist"))

    save_sent(sent)

    logging.info("=======================")
    logging.info("Found   : %s", found)
    logging.info("Sent    : %s", sent_count)
    logging.info("Skipped : %s", skipped)
    logging.info("Time    : %.2f sec", time.perf_counter() - start)
    logging.info("=======================")


# =====================
# ENTRY
# =====================

if __name__ == "__main__":
    check_bot()
    check_events()
```
