import os
import json
import time
import hashlib
import logging
import random
import requests
import re

from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

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
# GOOGLE/WIKIPEDIA FACT FETCHER
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
        with open(FACTS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    def get_wikipedia_url(self, artist_name):
        """Поиск страницы Википедии через Google"""
        search_query = f"{artist_name} музыкант википедия"
        search_url = f"https://www.google.com/search?q={search_query}"
        
        try:
            response = self.session.get(search_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем ссылки на Википедию
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if 'wikipedia.org' in href and '/wiki/' in href:
                    # Очищаем URL от параметров
                    match = re.search(r'https?://[a-z]+\.wikipedia\.org/wiki/[^?&"]+', href)
                    if match:
                        return match.group(0)
            
            return None
        except Exception as e:
            logging.warning(f"Error searching Wikipedia: {e}")
            return None
    
    def extract_facts_from_wikipedia(self, url):
        """Извлечение фактов из Википедии"""
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем основной контент
            content = soup.find('div', {'class': 'mw-parser-output'})
            if not content:
                return None
            
            # Собираем факты из первого абзаца
            paragraphs = content.find_all('p', recursive=False)
            facts = []
            
            for p in paragraphs[:3]:  # Берем первые 3 абзаца
                text = p.get_text().strip()
                # Очищаем текст от скобок и лишнего
                text = re.sub(r'\[[0-9]+\]', '', text)
                if len(text) > 50:  # Только содержательные абзацы
                    facts.append(text)
            
            # Ищем факты в инфобоксе
            infobox = soup.find('table', {'class': 'infobox'})
            if infobox:
                rows = infobox.find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        label = cells[0].get_text().strip()
                        value = cells[1].get_text().strip()
                        if label and value and len(value) > 20:
                            facts.append(f"{label}: {value}")
            
            return facts[:5]  # Ограничиваем 5 фактами
            
        except Exception as e:
            logging.warning(f"Error extracting facts from Wikipedia: {e}")
            return None
    
    def get_facts_for_artist(self, artist_name):
        """Получение фактов для артиста"""
        # Проверяем кеш
        if artist_name in self.cache:
            return self.cache[artist_name]
        
        # Ищем Википедию
        wiki_url = self.get_wikipedia_url(artist_name)
        if wiki_url:
            facts = self.extract_facts_from_wikipedia(wiki_url)
            if facts:
                self.cache[artist_name] = facts
                self.save_cache()
                return facts
        
        return None
    
    def get_random_fact(self, artist_name):
        """Получение случайного факта"""
        facts = self.get_facts_for_artist(artist_name)
        if facts:
            return random.choice(facts)
        return None

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

fact_fetcher = FactFetcher()

def check_deceased(item):
    """Проверяет, является ли событие смертью"""
    event_text = item.get("event", "").lower()
    death_keywords = ["смерть", "умер", "погиб", "скончал", "ушла", "ушёл", "трагически"]
    return any(keyword in event_text for keyword in death_keywords)

def check_birth(item):
    """Проверяет, является ли событие рождением"""
    event_text = item.get("event", "").lower()
    birth_keywords = ["родился", "родилась"]
    return any(keyword in event_text for keyword in birth_keywords)

def get_gender(item):
    """Определяет пол по полю gender или контексту"""
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
    """Возвращает текст для рождения с учётом рода"""
    gender = get_gender(item)
    if gender == "female":
        return "🎂 <b>РОДИЛАСЬ</b>"
    else:
        return "🎂 <b>РОДИЛСЯ</b>"

def get_death_header(items):
    """Возвращает заголовок с учётом количества и пола"""
    has_female = any(get_gender(item) == "female" for item in items)
    
    if len(items) == 1:
        if has_female:
            return "🕯️ <b>УШЛА ИЗ ЖИЗНИ</b>"
        else:
            return "🕯️ <b>УШЁЛ ИЗ ЖИЗНИ</b>"
    else:
        return "🕯️ <b>УШЛИ ИЗ ЖИЗНИ</b>"

def get_death_text(item, gender):
    """Возвращает текст события без указания смерти"""
    event = item.get("event", "")
    
    death_words = ["ушёл из жизни", "ушла из жизни", "ушли из жизни", "умер", "погиб", "скончался", "трагически погиб"]
    for word in death_words:
        event = event.replace(word, "").strip()
        event = event.replace(",,", ",").replace(" ,", ",")
    
    event = event.replace("😢", "").replace("😊", "").strip()
    
    return escape(event)

def get_header(total_events):
    """Возвращает заголовок в зависимости от количества событий"""
    if total_events > 1:
        return "🎸 <b>РОК-СОБЫТИЯ СЕГОДНЯ от бота сообщества 🃏</b>"
    else:
        return "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ от бота сообщества 🃏</b>"

def build_header_message(total_events):
    """Строит отдельное первое сообщение с заголовком"""
    return get_header(total_events)

def build_deceased_table(items):
    """Строит таблицу для умерших с общей датой"""
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
    
    # Добавляем факт о последнем музыканте
    last_artist = items[-1].get("artist", "")
    fact = fact_fetcher.get_random_fact(last_artist)
    if fact:
        text += f"\n📌 <i>{fact}</i>"
    else:
        text += f"\n🎧 <i>Музыка не стареет — она становится историей</i>"
    
    return text

def build_regular_message(item, current_year, is_birth):
    """Строит сообщение для обычного события"""
    artist = escape(item.get("artist", ""))
    group = escape(item.get("group", ""))
    role = escape(item.get("role", ""))    
    event = escape(item.get("event", ""))
    date = escape(item.get("date", ""))

    text = ""
    
    # Если это рождение - выносим "РОДИЛСЯ/РОДИЛАСЬ" вверх
    if is_birth:
        birth_text = get_birth_text(item)
        text += birth_text + "\n\n"
        # Убираем "Родился/Родилась" из события
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

    # Добавляем факт о музыканте
    fact = fact_fetcher.get_random_fact(item.get("artist", ""))
    if fact:
        text += f"\n\n📌 <i>{fact}</i>"
    else:
        text += f"\n\n🎧 <i>Музыка не стареет — она становится историей</i>"

    return text

def build_messages_for_day(events, current_year):
    """Разделяет события на обычные и умерших, формирует сообщения"""
    regular_events = []
    deceased_events = []
    
    for item in events:
        if check_deceased(item):
            deceased_events.append(item)
        else:
            regular_events.append(item)
    
    messages = []
    
    # Общее количество событий
    total_events = len(events)
    
    # Первое сообщение - только заголовок
    messages.append(build_header_message(total_events))
    
    # Второе сообщение - блок с умершими (если есть)
    if deceased_events:
        messages.append(build_deceased_table(deceased_events))
    
    # Затем добавляем обычные события
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

    logging.info(
        f"Начата проверка событий за {now.strftime('%d.%m.%Y')}"
    )

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
                logging.info(
                    f"Пропуск (уже отправлено): "
                    f"{item.get('artist', 'Без имени')}"
                )
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
