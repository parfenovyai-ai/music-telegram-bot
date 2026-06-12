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
# OPENAI (optional)
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
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logging.error("DB error: %s", e)
        return []


def load_sent():
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()


def save_sent(sent):
    try:
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(sent), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error("save_sent error: %s", e)

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
        except Exception as e:
            logging.warning("Telegram error: %s", e)

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
# AI GENERATION (IMPROVED)
# =====================

def ai_generate(item, age=None):

    if client is None:
        return None

    prompt = f"""
Ты редактор музыкального медиа уровня Rolling Stone / Kerrang.

ЗАДАЧА:
Напиши короткий, живой пост для Telegram о музыкальном событии.

СТИЛЬ:
- как колонка музыкального журнала
- живо, эмоционально, без пафоса
- ритмичный текст

СТРУКТУРА:
1. сильный хук (1–2 предложения)
2. развитие события
3. значение для музыки / культуры
4. финал — короткая фраза (как цитата)

ОГРАНИЧЕНИЯ:
- максимум 1200 символов
- 4–6 абзацев
- без слов: "легендарный", "икона", "в истории музыки"
- не использовать списки

КОНТЕКСТ:
- Музыкант: {item.get('artist')}
- Группа: {item.get('group')}
- Событие: {item.get('event')}
- Дата: {item.get('date')}
- Возраст события: {age}
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Ты музыкальный журналист и редактор."},
                {"role": "user", "content": prompt}
            ],
            temperature=1.0,
            max_tokens=300
        )

        return res.choices[0].message.content.strip()

    except Exception as e:
        logging.error("AI error: %s", e)
        return None

# =====================
# MESSAGE
# =====================

def build_message(item, year, age):

    artist = escape(item.get("artist", ""))
    group = escape(item.get("group", ""))
    date = escape(item.get("date", ""))

    ai_text = ai_generate(item, age)

    if not ai_text:
        ai_text = f"{artist} — {group}"

    footer = "\n\n🎧 <i>Музыка не стареет — она становится историей</i>"

    return (
        "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ</b>\n\n"
        f"{ai_text}\n\n"
        f"👤 {artist}\n"
        f"🎵 {group}\n"
        f"📅 {date}"
        f"{footer}"
    )

# =====================
# MAIN
# =====================

def check_events():

    now = datetime.now(MOSCOW_TZ)
    year = now.year

    logging.info("Start: %s", now)

    events = load_events()
    sent = load_sent()

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

        age = year - event_date.year if event_date else None

        found += 1

        event_id = make_event_id(item, year)

        if event_id in processed:
            continue

        processed.add(event_id)

        if event_id in sent:
            skipped += 1
            continue

        text = build_message(item, year, age)

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
    logging.info("=======================")


# =====================
# ENTRY
# =====================

if __name__ == "__main__":
    check_bot = lambda: requests.get(API_URL + "/getMe", timeout=10)
    check_bot()
    check_events()
