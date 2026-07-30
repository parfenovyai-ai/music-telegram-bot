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
FACTS_CACHE_FILE = "facts_cache.json"

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
# FACT FETCHER
# =====================

class FactFetcher:
    def __init__(self):
        self.cache = self.load_cache()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def load_cache(self):
        try:
            with open(FACTS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    
    def save_cache(self):
        try:
            with open(FACTS_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def get_facts_for_artist(self, artist_name):
        if artist_name in self.cache:
            return self.cache[artist_name]
        
        try:
            search_url = "https://ru.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": artist_name,
                "format": "json",
                "srlimit": 1
            }
            response = self.session.get(search_url, params=params, timeout=10)
            data = response.json()
            
            if data.get('query', {}).get('search'):
                page_title = data['query']['search'][0]['title']
                
                params = {
                    "action": "query",
                    "prop": "extracts",
                    "exintro": True,
                    "explaintext": True,
                    "titles": page_title,
                    "format": "json"
                }
                response = self.session.get(search_url, params=params, timeout=10)
                data = response.json()
                
                pages = data.get('query', {}).get('pages', {})
                for page_id, page_data in pages.items():
                    if 'extract' in page_data:
                        extract = page_data['extract']
                        sentences = extract.replace('\n', ' ').split('. ')
                        facts = []
                        for sentence in sentences[:3]:
                            if len(sentence) > 50:
                                facts.append(sentence.strip() + '.')
                        if facts:
                            self.cache[artist_name] = facts
                            self.save_cache()
                            return facts
        except Exception as e:
            logging.warning(f"Error getting facts: {e}")
        
        return None
    
    def get_random_fact(self, artist_name):
        facts = self.get_facts_for_artist(artist_name)
        if facts:
            return random.choice(facts)
        return None

fact_fetcher = FactFetcher()

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

def check_deceased(item):
    event_text = item.get("event", "").lower()
    death_keywords = ["смерть", "умер", "погиб", "скончал", "ушла", "ушёл", "трагически"]
    return any(keyword in event_text for keyword in death_keywords)

def check_birth(item):
    event_text = item.get("event", "").lower()
    birth_keywords = ["родился", "родилась"]
    return any(keyword in event_text for keyword in birth_keywords)

def get_gender(item):
    gender = item.get("gender", "").lower()
    if gender in ["ж", "жен", "female", "женщина"]:
        return "female"
    elif gender in ["м", "муж", "male", "мужчина"]:
        return "male"
    artist = item.get("artist", "")
    if artist.endswith(("а", "я", "ия", "ья")):
        return "female"
    return "male"

def get_birth_text(item):
    gender = get_gender(item)
    if gender == "female":
        return "🎂 <b>РОДИЛАСЬ</b>"
    else:
        return "🎂 <b>РОДИЛСЯ</b>"

def get_death_header(items):
    has_female = any(get_gender(item) == "female" for item in items)
    if len(items) == 1:
        if has_female:
            return "🕯️ <b>УШЛА ИЗ ЖИЗНИ</b>"
        else:
            return "🕯️ <b>УШЁЛ ИЗ ЖИЗНИ</b>"
    else:
        return "🕯️ <b>УШЛИ ИЗ ЖИЗНИ</b>"

def get_death_text(item, gender):
    event = item.get("event", "")
    death_words = ["ушёл из жизни", "ушла из жизни", "ушли из жизни", "умер", "погиб", "скончался", "трагически погиб"]
    for word in death_words:
        event = event.replace(word, "").strip()
        event = event.replace(",,", ",").replace(" ,", ",")
    event = event.replace("😢", "").replace("😊", "").strip()
    return escape(event)

def get_header(total_events):
    if total_events > 1:
        return "🎸 <b>РОК-СОБЫТИЯ СЕГОДНЯ от бота сообщества 🃏</b>"
    else:
        return "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ от бота сообщества 🃏</b>"

def build_header_message(total_events):
    return get_header(total_events)

def build_deceased_table(items):
    first_item = items[0]
    date = escape(first_item.get("date", ""))
    text = get_death_header(items) + "\n\n"
    text += f"📅 {date}\n\n"
    for item in items:
        artist = escape(item.get("artist", ""))
        group = escape(item.get("group", ""))
        role = escape(item.get("role", ""))
        gender = get_gender(item)
        event = get_death_text(item, gender)
        text += f"👤 <b>{artist}</b>\n"
        if group:
            text += f"🎵 {group}\n"
        if role:
            text += f"🎭 {role}\n"
        if event:
            text += f"📖 {event}\n"
        text += "-----------------------\n"
    last_artist = items[-1].get("artist", "")
    fact = fact_fetcher.get_random_fact(last_artist)
    if fact:
        text += f"\n📌 <i>{fact}</i>"
    else:
        text += f"\n🎧 <i>Музыка не стареет — она становится историей</i>"
    return text

def build_regular_message(item, current_year, is_birth):
    artist = escape(item.get("artist", ""))
    group = escape(item.get("group", ""))
    role = escape(item.get("role", ""))    
    event = escape(item.get("event", ""))
    date = escape(item.get("date", ""))
    text = ""
    if is_birth:
        birth_text = get_birth_text(item)
        text += birth_text + "\n\n"
        event = event.replace("Родился", "").replace("Родилась", "").replace("😊", "").strip()
    text += f"👤 <b>{artist}</b>\n"
    if group:
        text += f"🎵 {group}\n"
    if role:
        text += f"🎭 {role}\n"
    if event:
        text += f"📖 {event}\n"
    text += f"🗓 {date}"
    ai_text = ai_generate(item)
    if ai_text:
        text += f"\n\n🧠 <i>{ai_text}</i>"
    fact = fact_fetcher.get_random_fact(item.get("artist", ""))
    if fact:
        text += f"\n\n📌 <i>{fact}</i>"
    else:
        text += f"\n\n🎧 <i>Музыка не стареет — она становится историей</i>"
    return text

def build_messages_for_day(events, current_year):
    regular_events = []
    deceased_events = []
    for item in events:
        if check_deceased(item):
            deceased_events.append(item)
        else:
            regular_events.append(item)
    messages = []
    total_events = len(events)
    messages.append(build_header_message(total_events))
    if deceased_events:
        messages.append(build_deceased_table(deceased_events))
    for item in regular_events:
        is_birth = check_birth(item)
        messages.append(build_regular_message(item, current_year, is_birth))
    return messages

# =====================
# MAIN
# =====================

def check_events():
    now = datetime.now(MOSCOW_TZ)
    today_prefix = now.strftime("%Y-%m-%d")
    events = load_events()
    sent = load_sent()
    sent = {x for x in sent if x.startswith(today_prefix)}
    processed = set()
    sent_count = 0
    invalid_dates = 0
    logging.info(f"Начата проверка событий за {now.strftime('%d.%m.%Y')}")
    today_events = []
    for item in events:
        try:
            event_date = parse_date(item.get("date"))
            if event_date is None:
                invalid_dates += 1
                continue
            if event_date.day != now.day or event_date.month != now.month:
                continue
            event_id = make_event_id(item, now.year)
            if event_id in processed:
                continue
            processed.add(event_id)
            if event_id in sent:
                logging.info(f"Пропуск (уже отправлено): {item.get('artist', 'Без имени')}")
                continue
            today_events.append(item)
        except Exception as e:
            logging.exception(f"Ошибка обработки записи: {e}")
    if today_events:
        messages = build_messages_for_day(today_events, now.year)
        for message in messages:
            if send_message(message):
                sent_count += 1
                logging.info(f"Отправлено сообщение")
                time.sleep(SEND_DELAY)
            else:
                logging.warning("Не удалось отправить сообщение")
    save_sent(sent)
    if sent_count == 0:
        logging.info("Сегодня событий для публикации не найдено.")
    logging.info(f"Проверка завершена | Отправлено: {sent_count} | Некорректных дат: {invalid_dates}")

if __name__ == "__main__":
    check_events()
