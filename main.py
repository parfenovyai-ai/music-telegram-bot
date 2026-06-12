import os
import json
import time
import hashlib
import logging
import random
import requests

from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from requests.adapters import HTTPAdapter

# =====================
# CONFIG
# =====================

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHANNEL_ID = (os.getenv("CHANNEL_ID") or "").strip()
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()

if not BOT_TOKEN or not CHANNEL_ID:
    raise RuntimeError("Missing BOT_TOKEN or CHANNEL_ID")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

DB_FILE = "database.json"
SENT_FILE = "sent.json"

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

MAX_RETRIES = 3
SEND_DELAY = 1

# =====================
# LOGGING
# =====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# =====================
# PHRASES
# =====================

ROCK_PHRASES = [
    "Музыка не стареет — она становится историей",
    "Рок живёт там, где заканчиваются слова",
    "Где звучит гитара — там начинается память",
    "Мы дети грома — нас не удержит тишина",
    "Каждый аккорд — это удар судьбы",
    "Рок не умирает — он становится шрамом"
]

last_phrase = None

def get_phrase():
    global last_phrase
    phrase = random.choice(ROCK_PHRASES)

    while phrase == last_phrase and len(ROCK_PHRASES) > 1:
        phrase = random.choice(ROCK_PHRASES)

    last_phrase = phrase
    return phrase

# =====================
# OPENAI
# =====================

client = None

if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        logging.warning(f"OpenAI init failed: {e}")
        client = None

# =====================
# SESSION
# =====================

session = requests.Session()
session.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=10))

# =====================
# FILES
# =====================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_events():
    return load_json(DB_FILE, [])


def load_sent():
    data = load_json(SENT_FILE, [])
    return set(data)


def save_sent(sent):
    save_json(SENT_FILE, sorted(sent))

# =====================
# DATE
# =====================

def parse_date(date_str):
    if not date_str:
        return None

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
        except Exception as e:
            logging.warning(f"Telegram error: {e}")

        time.sleep(2)

    return False

# =====================
# EVENT ID
# =====================

def make_event_id(item, year):
    raw = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return f"{year}_{hashlib.sha256(raw.encode()).hexdigest()}"

# =====================
# AI
# =====================

def ai_generate(item):
    if not client:
        return None

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Ты музыкальный редактор."},
                {"role": "user", "content": f"Напиши 1–3 предложения о событии: {item.get('event')}"}
            ],
            temperature=1.0,
            max_tokens=150
        )

        return res.choices[0].message.content.strip()

    except Exception as e:
        logging.warning(f"AI error: {e}")
        return None

# =====================
# MESSAGE
# =====================

def build_message(item, current_year):

    artist = escape(item.get("artist", ""))
    group = escape(item.get("group", ""))
    event = escape(item.get("event", ""))
    date = escape(item.get("date", ""))

    text = (
        "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ</b>\n\n"
        f"👤 <b>{artist}</b>\n"
        f"🎵 {group}\n"
        f"📖 {event}\n"
        f"🗓 {date}"
    )

    ai_text = ai_generate(item)
    if ai_text:
        text += f"\n\n🧠 <i>{ai_text}</i>"

    text += f"\n\n🎧 <i>{get_phrase()}</i>"

    return text

# =====================
# MAIN
# =====================

def check_events():

    now = datetime.now(MOSCOW_TZ)
    year = now.year

    events = load_events()
    sent = load_sent()

    sent = {x for x in sent if x.startswith(f"{year}_")}

    processed = set()

    sent_count = 0
    invalid_dates = 0

    for item in events:

        try:
            event_date = parse_date(item.get("date"))

            if not event_date:
                invalid_dates += 1
                continue

            if event_date.day != now.day or event_date.month != now.month:
                continue

            event_id = make_event_id(item, year)

            if event_id in processed or event_id in sent:
                continue

            processed.add(event_id)

            text = build_message(item, year)

            if send_message(text):
                sent.add(event_id)
                sent_count += 1
                time.sleep(SEND_DELAY)

        except Exception as e:
            logging.error(f"Loop error: {e}")

    save_sent(sent)

    logging.info(f"DONE | sent={sent_count} | invalid={invalid_dates}")

# =====================
# ENTRY
# =====================

if __name__ == "__main__":
    check_events()
