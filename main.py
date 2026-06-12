import os
import json
import time
import hashlib
import logging
import requests
import random

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

    "Пусть кровь и сталь решат, где правда и где страх",
    "Я выбираю путь, где нет пути назад",
    "Город сгорел, но память не сгорела",
    "Мы дети грома — нас не удержит тишина",
    "Время не лечит, оно лишь шрамирует душу",
    "Сквозь дым и пепел слышен голос судьбы",
    "Я слышу крик гитар в холодной пустоте",
    "Пока горит огонь — мы не станем прахом",
    "Нет света без тьмы, нет веры без боли",
    "Сталь не предаёт, предают только люди",
    "Наши песни тяжелее любых оков",
    "Когда молчит небо — говорит металл",
    "Мы идём сквозь ад, но не просим пощады",
    "Каждый аккорд — как удар судьбы",
    "И даже тьма склоняется перед звуком",
    "Между светом и тьмой я выбираю гром",
    "Судьба играет риффами на костях времени",
    "Мы выжили там, где молчит даже надежда",
    "Пепел прошлого поёт в моих венах",
    "Где заканчивается страх — начинается металл",
    "Я слышу вечность в перегруженных струнах",
    "Мир трещит, но гитара держит небо",
    "Мы не ангелы — мы те, кто остался в огне",
    "Холод стали заменяет нам молитвы",
    "Каждый аккорд — как удар молота судьбы",
    "Там, где падают города, рождается звук",
    "Мы не просим прощения у тишины",
    "Вой ветра звучит как старый рифф",
    "Сквозь кровь и снег идёт наш голос",
    "Нет дороги назад, есть только вперёд",
    "Металл в душе тяжелее любых цепей",
    "Мы пишем историю шрамами на гитаре",
    "Пусть мир сгорит — мы сыграем до конца",
    "Я живу на границе света и разрушения",
    "В каждом ударе барабанов — дыхание войны",
    "Небо рвётся под весом наших аккордов",
    "Тьма учит нас звучать громче света",
    "Мы — эхо тех, кто не вернулся",
    "Риффы режут ночь, как клинки",
    "Память звучит тяжелее стали",
    "Сломанные крылья не мешают летать в огне",
    "Мы дети пепла и перегруженных усилителей",
    "Время не лечит — оно усиливает боль",
    "Каждый концерт — это маленький конец света",
    "Мы поём там, где заканчиваются молитвы",
    "Стены дрожат от правды в наших песнях",
    "Гитары говорят то, что молчит человек",
    "Мы не боимся тишины — мы её ломаем",
    "Осколки света режут тьму внутри нас",
    "Наш путь — это звук без возврата",
    "Металл живёт там, где умирает страх",
    "Я слышу судьбу в перегруженном усилителе",
    "Мы не герои — мы свидетели огня",
    "Город спит, но сцена дышит",
    "Сломанные мечты звучат громче реальности",
    "Мы идём сквозь бурю на одной ноте",
    "Рок не умирает — он становится шрамом",
    "Каждая струна — это нерв эпохи",
    "Мы танцуем на руинах старого мира",
    "Где нет надежды — начинается соло",
    "Наши песни тяжелее времени",
    "Мы слышим правду в искажении звука",
    "Металл — это язык выживших",
    "И даже тишина боится перегруза",
    "Мы не исчезаем — мы превращаемся в звук"
]

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
# AI GENERATION
# =====================

def ai_generate(item, age=None):

    if client is None:
        return None

    prompt = f"""
Ты редактор музыкального медиа уровня Rolling Stone / Kerrang.

Напиши короткий живой текст для Telegram.

ПРАВИЛА:
- 4–6 абзацев
- без упоминания имени и группы напрямую
- эмоционально, но без пафоса
- стиль музыкальной журналистики
- в конце одна сильная короткая фраза

СОБЫТИЕ:
Музыкант: {item.get('artist')}
Группа: {item.get('group')}
Событие: {item.get('event')}
Возраст события: {age}
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

    except Exception as e:
        logging.error("AI error: %s", e)
        return None

# =====================
# 🎸 ROCK FRAME
# =====================

def wrap_rock_frame(text):

    phrase = random.choice(ROCK_PHRASES)

    return (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎸🔥 <b>РОК-СОБЫТИЕ СЕГОДНЯ</b> 🔥🎸\n"
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

    ai_text = ai_generate(item, age)

    if not ai_text:
        ai_text = "Музыкальное событие, которое оставило след в истории."

    return wrap_rock_frame(ai_text)

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
    requests.get(API_URL + "/getMe", timeout=10)
    check_events()
