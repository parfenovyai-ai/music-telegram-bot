import os
import json
import time
import hashlib
import logging
import random
import requests

from datetime import datetime
from zoneinfo import ZoneInfo
from requests.adapters import HTTPAdapter
from html import escape

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
# PHRASES
# =====================

ROCK_PHRASES = [
    "Музыка не стареет — она становится историей",
    "Рок живёт там, где заканчиваются слова",
    "Каждый аккорд оставляет след во времени",
    "Где звучит гитара — там начинается память",
    "И даже тишина боится перегруза",
    "Металл живёт там, где умирает страх",
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
    except:
        client = None

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
            return json.load(f)
    except:
        return []


def load_sent():
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
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
        except:
            pass

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

    prompt = f"""
Ты музыкальный журналист.

ЗАПРЕТ:
- не используй имя
- не используй группу
- не повторяй данные

СОБЫТИЕ:
{item.get('event')}
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Ты музыкальный редактор."},
                {"role": "user", "content": prompt}
            ],
            temperature=1.0,
            max_tokens=250
        )

        return res.choices[0].message.content.strip()

    except:
        return None

# =====================
# HEADER
# =====================

def build_header(item):
    return (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎸 РОК-СОБЫТИЕ СЕГОДНЯ\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 {item.get('artist','—')}\n"
        f"🎵 {item.get('group','—')}\n"
        f"📅 {item.get('event','—')}\n"
        f"🗓 {item.get('date','—')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    )

# =====================
# FRAME
# =====================

def wrap_frame(text):
    return (
        f"{text}\n\n"
        f"🎧 <i>{get_phrase()}</i>"
    )

# =====================
# MESSAGE
# =====================

def build_message(item):

    ai_text = ai_generate(item)

    if not ai_text:
        ai_text = "Музыкальное событие оставило след в истории."

    header = build_header(item)

    return wrap_frame(header + "\n" + ai_text)

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

    for item in events:

        event_date = parse_date(item.get("date", ""))

        if not event_date:
            continue

        if event_date.day != now.day or event_date.month != now.month:
            continue

        event_id = make_event_id(item, year)

        if event_id in processed or event_id in sent:
            continue

        processed.add(event_id)

        text = build_message(item)

        if send_message(text):
            sent.add(event_id)
            time.sleep(SEND_DELAY)

    save_sent(sent)

# =====================
# ENTRY
# =====================

if __name__ == "__main__":
    check_events()
