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

DB_FILE = "database_deepseek.json"
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
    role = escape(item.get("role", ""))    
    event = escape(item.get("event", ""))
    date = escape(item.get("date", ""))

    text = (
        "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ от бота сообщества 🃏</b>\n\n"
        f"👤 <b>{artist}</b>\n"
        f"🎵 {group}\n"
        f"🎭 {role}\n"
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
    today_prefix = now.strftime("%Y-%m-%d")

    events = load_events()
    sent = load_sent()

    # Оставляем только сегодняшние записи
    sent = {x for x in sent if x.startswith(today_prefix)}

    processed = set()

    sent_count = 0
    invalid_dates = 0

    logging.info(
        f"Начата проверка событий за {now.strftime('%d.%m.%Y')}"
    )

    for item in events:

        try:

            event_date = parse_date(item.get("date"))

            if event_date is None:
                invalid_dates += 1
                continue

            # Сравниваем только день и месяц
            if (
                event_date.day != now.day
                or event_date.month != now.month
            ):
                continue

            event_id = make_event_id(item, now.year)

            # Защита от дублей внутри одного запуска
            if event_id in processed:
                continue

            processed.add(event_id)

            # Уже отправлялось сегодня
            if event_id in sent:
                logging.info(
                    f"Пропуск (уже отправлено): "
                    f"{item.get('artist', 'Без имени')}"
                )
                continue

            text = build_message(item, now.year)

            if send_message(text):

                sent.add(event_id)
                sent_count += 1

                logging.info(
                    f"Отправлено: "
                    f"{item.get('artist', 'Без имени')}"
                )

                time.sleep(SEND_DELAY)

            else:

                logging.warning(
                    f"Не удалось отправить: "
                    f"{item.get('artist', 'Без имени')}"
                )

        except Exception as e:

            logging.exception(
                f"Ошибка обработки записи: {e}"
            )

    # Сохраняем только сегодняшние отправленные события
    save_sent(sent)

    if sent_count == 0:
        logging.info("Сегодня событий для публикации не найдено.")

    logging.info(
        "Проверка завершена | "
        f"Отправлено: {sent_count} | "
        f"Некорректных дат: {invalid_dates}"
    )

# =====================
# ENTRY
# =====================

if __name__ == "__main__":
    check_events()
