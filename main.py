import os
import json
import time
import hashlib
import logging
import requests
import random

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
# ROCK PHRASES
# =====================

ROCK_PHRASES = [
    "Музыка не стареет — она становится историей",
    "Каждый аккорд оставляет след во времени",
    "Рок живёт там, где заканчиваются слова",
    "История музыки пишется не датами, а звуком",
    "Где звучит гитара — там начинается память",
    "Эпохи уходят, но риффы остаются",
    "Один звук может изменить целую эпоху",
    "Музыка — это память, которая умеет звучать",

    "Где заканчивается страх — начинается металл",
    "Каждый аккорд — как удар судьбы",
    "Мы не герои — мы свидетели огня",
    "Металл живёт там, где умирает страх",
    "Рок не умирает — он становится шрамом",
    "И даже тишина боится перегруза",
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
        logging.error("OpenAI init failed: %s", e)
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
            r = requests.post(API_URL + "/sendMessage", data=payload, timeout=15)
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
# AI GENERATION
# =====================

def ai_generate(item, age=None):

    if client is None:
        return None

    prompt = f"""
Ты редактор музыкального медиа уровня Rolling Stone / Kerrang.

ВАЖНО:
- НЕ используй имя, фамилию, название группы
- НЕ упоминай их вообще
- пиши абстрактно ("музыкант", "группа")

СТИЛЬ:
- живой музыкальный текст
- 4–6 абзацев
- без шаблонов
- финальная короткая сильная фраза

СОБЫТИЕ:
Субъект: музыкант / группа
Событие: {item.get('event')}
Возраст: {age}
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Ты музыкальный журналист."},
                {"role": "user", "content": prompt}
            ],
            temperature=1.0,
            max_tokens=300
        )

        return res.choices[0].message.content.strip()

    except:
        return None

# =====================
# FRAME
# =====================

def wrap_frame(text):
    phrase = get_phrase()

    return (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎸🔥 <b>ROCK HISTORY</b> 🔥🎸\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎧 <i>{phrase}</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

# =====================
# MESSAGE
# =====================

def build_message(item, year, age):

    text = ai_generate(item, age)

    if not text:
        text = "Музыкальное событие оставило след в истории."

    return wrap_frame(text)

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

    found = 0
    sent_count = 0

    for item in events:

        event_date = parse_date(item.get("date", ""))

        if not event_date:
            continue

        if event_date.day != now.day or event_date.month != now.month:
            continue

        age = year - event_date.year

        event_id = make_event_id(item, year)

        if event_id in processed or event_id in sent:
            continue

        processed.add(event_id)

        text = build_message(item, year, age)

        if send_message(text):
            sent.add(event_id)
            sent_count += 1
            time.sleep(SEND_DELAY)

    save_sent(sent)

    print("Found:", found)
    print("Sent:", sent_count)

# =====================
# ENTRY
# =====================

if __name__ == "__main__":
    check_events()
