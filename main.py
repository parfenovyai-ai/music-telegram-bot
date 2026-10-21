#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram-бот «Рок-сообщество»: ежедневный дайджест музыкальных дат.

СТРУКТУРА БАЗЫ НЕ МЕНЯЕТСЯ: читается прежний database_deepseek.json,
список объектов с полями date, artist, group, role, event, gender.
Новые поля для работы функций НЕ НУЖНЫ. Бот НИКОГДА не записывает в базу.
Если в базе есть отдельная запись о рождении того же музыканта (имя и
группа совпадают), её дата учитывается при вычислении возраста на момент
смерти. Противоречивые даты не объединяются и не угадываются.
Дополнительные существующие поля (если они уже есть) читаются необязательно.

Изменения по сравнению с первоначальной программой:
- единая шапка с СЕГОДНЯШНЕЙ датой внутри сообщения, не отдельный пустой пост;
- дата каждого ушедшего музыканта указывается отдельно, с его годом;
- возраст / годовщина рассчитываются только при наличии года в базе;
- записи sent.json отмечаются сразу после успешной отправки;
- публикации не содержат выдуманных ИИ биографий или цитат.

Запуск:
  pip install requests
  python rock_community_bot_legacy_json.py --dry-run --date 2026-10-21
  python rock_community_bot_legacy_json.py

Для реальной отправки укажите BOT_TOKEN и CHANNEL_ID в переменных окружения.
Python 3.11+, часовой пояс по умолчанию: Europe/Moscow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter

LOG = logging.getLogger("rock_community")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

DB_FILE = os.getenv("DB_FILE", "database_deepseek.json")
SENT_FILE = os.getenv("SENT_FILE", "sent.json")
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
MAX_MESSAGE_LENGTH = 3800  # Telegram допускает 4096; оставляем запас
MAX_RETRIES = 3
SEND_DELAY = 1.0
SEPARATOR = "──────────────"

RUS_MONTHS = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
    "августа", "сентября", "октября", "ноября", "декабря"
)


@dataclass(frozen=True)
class EventDate:
    day: int
    month: int
    year: int | None = None

    def display(self) -> str:
        return f"{self.day:02d}.{self.month:02d}" + (
            f".{self.year}" if self.year is not None else ""
        )


@dataclass(frozen=True)
class Publication:
    event_ids: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class PersonHistory:
    birth: EventDate | None = None
    death: EventDate | None = None


def as_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def clean_text(value: object, limit: int = 650) -> str:
    text = as_text(value).replace("\r", " ").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def html(value: object, limit: int = 650) -> str:
    return escape(clean_text(value, limit))


def parse_date(value: object) -> EventDate | None:
    """ДД-ММ[-ГГГГ], ДД.ММ[.ГГГГ], ДД/ММ[/ГГГГ], ГГГГ-ММ-ДД.

    Год 2000 служит только для ПРОВЕРКИ даты без года, НЕ как реальный год.
    """
    value = as_text(value)
    if not value:
        return None
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if iso:
        year, month, day = map(int, iso.groups())
    else:
        usual = re.fullmatch(r"(\d{1,2})[-./](\d{1,2})(?:[-./](\d{4}))?", value)
        if not usual:
            return None
        day, month = int(usual.group(1)), int(usual.group(2))
        year = int(usual.group(3)) if usual.group(3) is not None else None
    try:
        date(year if year is not None else 2000, month, day)
    except ValueError:
        return None
    return EventDate(day, month, year)


def valid_year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (str, int)):
        return None
    raw = str(value).strip()
    if not re.fullmatch(r"\d{4}", raw):
        return None
    year = int(raw)
    return year if 1000 <= year <= 9999 else None


def with_year(value: EventDate | None, *year_options: object) -> EventDate | None:
    if value is None or value.year is not None:
        return value
    for candidate in year_options:
        year = valid_year(candidate)
        if year is None:
            continue
        try:
            date(year, value.month, value.day)
        except ValueError:
            continue
        return EventDate(value.day, value.month, year)
    return value


def event_kind(item: dict) -> str:
    kind = as_text(item.get("type") or item.get("event_type") or item.get("kind")).casefold()
    if kind in {"birth", "birthday", "рождение", "день рождения"}:
        return "birth"
    if kind in {"death", "memorial", "смерть", "память"}:
        return "death"
    event = as_text(item.get("event")).casefold()
    if re.search(r"\b(родился|родилась|день рождения)\b", event):
        return "birth"
    if re.search(r"\b(умер|умерла|погиб|погибла|скончался|скончалась|смерть|уш[её]л из жизни|ушла из жизни)\b", event):
        return "death"
    return "other"


def date_for_event(item: dict) -> EventDate | None:
    parsed = parse_date(item.get("date") or item.get("event_date"))
    if parsed is None:
        return None
    kind = event_kind(item)
    if kind == "birth":
        extra_years = (item.get("birth_year"), item.get("year_of_birth"))
    elif kind == "death":
        extra_years = (item.get("death_year"), item.get("year_of_death"))
    else:
        extra_years = ()
    return with_year(parsed, *extra_years, item.get("event_year"), item.get("year"))


def person_birth_date(item: dict) -> EventDate | None:
    parsed = parse_date(item.get("birth_date") or item.get("born_date"))
    if parsed is None and event_kind(item) == "birth":
        parsed = date_for_event(item)
    return with_year(parsed, item.get("birth_year"), item.get("year_of_birth"))


def person_death_date(item: dict) -> EventDate | None:
    parsed = parse_date(item.get("death_date"))
    if parsed is None and event_kind(item) == "death":
        parsed = date_for_event(item)
    return with_year(parsed, item.get("death_year"), item.get("year_of_death"))


def person_key(item: dict) -> tuple[str, str] | None:
    """Сопоставляем только явно одинаковые имя и группу.

    Не объединяем однофамильцев, а также записи разных групп по догадке.
    """
    artist = " ".join(as_text(item.get("artist")).casefold().split())
    group = " ".join(as_text(item.get("group")).casefold().split())
    return (artist, group) if artist else None


def consistent_date(dates: set[EventDate]) -> EventDate | None:
    """Не выбираем произвольно одну из несовпадающих дат."""
    if not dates or len({(d.day, d.month) for d in dates}) != 1:
        return None
    complete = {d for d in dates if d.year is not None}
    if len(complete) > 1:
        return None
    return next(iter(complete)) if complete else next(iter(dates))


def index_person_history(events: list[dict]) -> dict[tuple[str, str], PersonHistory]:
    """Используем старые строки JSON, не дописывая birth_date и death_date.

    Пример: отдельные события «Родился» и «Умер» для одного имени/группы.
    Если в базе спорные годы, возраст из таких записей не вычисляется.
    """
    candidates: dict[tuple[str, str], dict[str, set[EventDate]]] = {}
    for item in events:
        key = person_key(item)
        kind = event_kind(item)
        event_date = date_for_event(item)
        if key is None or kind not in ("birth", "death") or event_date is None:
            continue
        dates_by_kind = candidates.setdefault(key, {"birth": set(), "death": set()})
        dates_by_kind[kind].add(event_date)
    return {
        key: PersonHistory(
            consistent_date(values["birth"]),
            consistent_date(values["death"]),
        )
        for key, values in candidates.items()
    }


def merged_date(direct: EventDate | None, inferred: EventDate | None) -> EventDate | None:
    """Заполнить недостающий год только при совпадении дня и месяца."""
    if direct is None:
        return inferred
    if inferred is None:
        return direct
    if (direct.day, direct.month) != (inferred.day, inferred.month):
        return None  # противоречащие даты — никаких расчётов
    if direct.year is not None and inferred.year is not None and direct.year != inferred.year:
        return None
    return direct if direct.year is not None else inferred


def known_dates(item: dict, people: dict[tuple[str, str], PersonHistory] | None
               ) -> tuple[EventDate | None, EventDate | None]:
    history = (people or {}).get(person_key(item))
    birth = merged_date(person_birth_date(item), history.birth if history else None)
    death = merged_date(person_death_date(item), history.death if history else None)
    return birth, death


def years_word(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return "лет"
    if n % 10 == 1:
        return "год"
    if n % 10 in (2, 3, 4):
        return "года"
    return "лет"


def age_at_death(born: EventDate | None, died: EventDate | None) -> int | None:
    """Возраст на дату смерти; не угадываем возраст из одних лишь годов."""
    if born is None or died is None or born.year is None or died.year is None:
        return None
    birth_day = date(born.year, born.month, born.day)
    death_day = date(died.year, died.month, died.day)
    if death_day < birth_day:
        return None
    return died.year - born.year - ((died.month, died.day) < (born.month, born.day))


def died_by(item: dict, on_day: date, known_death: EventDate | None = None) -> bool:
    """True только если в базе есть основание утверждать смерть к этой дате."""
    if item.get("deceased") is True or item.get("alive") is False:
        return True
    died = known_death if known_death is not None else person_death_date(item)
    if died and died.year is not None:
        if died.year < on_day.year:
            return True
        if died.year == on_day.year and (died.month, died.day) <= (on_day.month, on_day.day):
            return True
    yr = valid_year(item.get("death_year") or item.get("year_of_death"))
    return yr is not None and yr < on_day.year


def verified_quote(item: dict) -> list[str]:
    """Поддержка полей из v2. Не ищем, не генерируем и не приписываем цитаты."""
    quote = as_text(item.get("quote"))
    source = as_text(item.get("quote_source"))
    if not (quote and source and item.get("quote_verified") is True):
        return []
    if as_text(item.get("quote_type")).lower() in {"lyrics", "песня", "строка песни"}:
        if len(quote.split()) > 10:
            LOG.warning("Слишком длинная цитата из песни (%s)", item.get("artist", "?"))
            return []
    result = [f"💬 <i>«{html(quote.strip('«»\" '), 260)}»</i>"]
    raw_url = as_text(item.get("quote_url") or item.get("quote_source_url"))
    src = f"Источник: {html(source, 180)}"
    if raw_url and len(raw_url) <= 500:
        parsed = urlsplit(raw_url)
        if parsed.scheme in ("http", "https") and parsed.hostname:
            src += f' (<a href="{escape(raw_url, quote=True)}">ссылка</a>)'
    result.append(f"📚 {src}")
    return result


def list_achievements(item: dict) -> list[str]:
    raw = item.get("achievements") or item.get("achievement")
    if isinstance(raw, str):
        return [clean_text(raw, 260)] if raw.strip() else []
    if isinstance(raw, list):
        return [clean_text(s, 260) for s in raw if isinstance(s, str) and s.strip()][:3]
    return []


def details_from_database(item: dict, kind: str) -> list[str]:
    """Показываем только данные, уже записанные в JSON."""
    lines: list[str] = []
    event = as_text(item.get("event"))
    if event and event.casefold().strip(" .!:") not in {
        "родился", "родилась", "умер", "умерла", "скончался", "скончалась",
        "погиб", "погибла", "ушёл из жизни", "ушла из жизни",
    }:
        lines.append(f"📖 {html(event, 620)}")

    achievements = list_achievements(item)
    if achievements:
        lines.append("🏆 <b>Достижения и вклад:</b>")
        lines.extend(f"• {html(value, 260)}" for value in achievements)
    note = item.get("contribution") if kind == "death" else item.get("fact")
    if note:
        lines.append(f"💡 {html(note, 380)}")
    if item.get("song"):
        lines.append(f"🎧 Что послушать: {html(item['song'], 130)}")
    lines.extend(verified_quote(item))
    return lines


def person_info(item: dict) -> list[str]:
    lines = [f"👤 <b>{html(item.get('artist') or 'Музыкант', 170)}</b>"]
    if as_text(item.get("group")):
        lines.append(f"🎵 {html(item['group'], 150)}")
    if as_text(item.get("role")):
        lines.append(f"🎸 {html(item['role'], 150)}")
    return lines


def format_birth(item: dict, today: date,
                 people: dict[tuple[str, str], PersonHistory] | None = None) -> str:
    lines = person_info(item)
    birthday, death = known_dates(item, people)
    if birthday:
        lines.append(f"📅 Дата рождения: {birthday.display()}")
        if birthday.year is not None and birthday.year <= today.year:
            years = today.year - birthday.year
            if died_by(item, today, death):
                lines.append(f"🎂 Сегодня исполнилось бы {years} {years_word(years)}")
            else:
                # Нейтрально: отсутствие года смерти в JSON не доказывает, что человек жив.
                lines.append(f"🎉 {years} {years_word(years)} со дня рождения")
    if death and died_by(item, today, death):
        lines.append(f"🕯️ Дата ухода: {death.display()}")
    lines.extend(details_from_database(item, "birth"))
    return "\n".join(lines)


def format_death(item: dict, today: date,
                 people: dict[tuple[str, str], PersonHistory] | None = None) -> str:
    lines = person_info(item)
    birthday, death = known_dates(item, people)
    if death:
        lines.append(f"📅 Дата ухода: {death.display()}")
        if death.year is not None and death.year < today.year:
            years = today.year - death.year
            lines.append(f"🕯️ {years} {years_word(years)} со дня ухода")
        age = age_at_death(birthday, death)
        if age is not None:
            lines.append(f"🌹 Возраст на момент смерти: {age} {years_word(age)}")
    lines.extend(details_from_database(item, "death"))
    return "\n".join(lines)


def format_other(item: dict, today: date,
                 people: dict[tuple[str, str], PersonHistory] | None = None) -> str:
    lines = person_info(item)
    event_date = date_for_event(item)
    if event_date:
        lines.append(f"📅 Дата события: {event_date.display()}")
        if event_date.year is not None and event_date.year < today.year:
            years = today.year - event_date.year
            lines.append(f"⏳ {years} {years_word(years)} со дня события")
    lines.extend(details_from_database(item, "other"))
    return "\n".join(lines)


def event_identity(item: dict, today: date) -> str:
    """Сохраняем алгоритм ID v2, чтобы sent.json от v2 продолжил работать."""
    stable = item.get("id")
    if stable is None or as_text(stable) == "":
        stable = [item.get(k, "") for k in ("artist", "group", "date", "event")]
        stable.append(event_kind(item))
    packed = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(packed.encode("utf-8")).hexdigest()[:24]
    return f"{today.isoformat()}_{digest}"


def original_event_identity(item: dict, today: date) -> str:
    """Совместимость со старым ID формата ГГГГ_<полный sha256>."""
    packed = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return f"{today.year}_{hashlib.sha256(packed.encode('utf-8')).hexdigest()}"


def common_header(today: date) -> str:
    return ("🎸 <b>РОК-СОБЫТИЯ СЕГОДНЯ</b>\n"
            f"📅 {today.day} {RUS_MONTHS[today.month]} {today.year} года\n"
            "🃏 <b>Рок-сообщество</b>")


def publication_text(blocks: list[tuple[str, str, str]], today: date) -> str:
    """У каждого сообщения ровно одна общая шапка, затем разделы."""
    lines = [common_header(today)]
    last_section: str | None = None
    for _, section, content in blocks:
        lines.extend(["", SEPARATOR, ""])
        if section != last_section:
            lines.append(section)
            lines.append("")
        lines.append(content)
        last_section = section
    return "\n".join(lines)


def build_publications(events: list[tuple[str, dict]], today: date,
                       people: dict[tuple[str, str], PersonHistory] | None = None
                       ) -> list[Publication]:
    sections = [
        ("birth", "🎂 <b>ДНИ РОЖДЕНИЯ</b>", format_birth),
        ("death", "🕯️ <b>ПОМНИМ</b>", format_death),
        ("other", "🎼 <b>ЭТОТ ДЕНЬ В ИСТОРИИ РОКА</b>", format_other),
    ]
    blocks: list[tuple[str, str, str]] = []
    for kind, title, formatter in sections:
        for event_id, item in events:
            if event_kind(item) == kind:
                blocks.append((event_id, title, formatter(item, today, people)))

    posts: list[Publication] = []
    current: list[tuple[str, str, str]] = []
    for block in blocks:
        candidate = current + [block]
        if len(publication_text(candidate, today)) > MAX_MESSAGE_LENGTH and current:
            posts.append(Publication(tuple(entry[0] for entry in current), publication_text(current, today)))
            current = []
        if len(publication_text([block], today)) > MAX_MESSAGE_LENGTH:
            LOG.error("Пропущена слишком длинная запись: %s", block[0])
            continue
        current.append(block)
    if current:
        posts.append(Publication(tuple(entry[0] for entry in current), publication_text(current, today)))
    return posts


def load_events(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig") as stream:
        data = json.load(stream)
    if isinstance(data, dict):
        data = data.get("events")
    if not isinstance(data, list):
        raise ValueError("База должна быть списком событий или объектом {'events': [...]}")
    records = [item for item in data if isinstance(item, dict)]
    if len(records) != len(data):
        LOG.warning("Пропущено неверных строк JSON: %d", len(data) - len(records))
    return records


def load_sent(path: str) -> set[str]:
    if not Path(path).exists():
        return set()
    with open(path, "r", encoding="utf-8-sig") as stream:
        data = json.load(stream)
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        # При повреждении журнала безопаснее отменить публикацию, чем создать дубли.
        raise ValueError("sent.json повреждён: ожидается JSON-список строк")
    return set(data)


def save_sent(path: str, markers: set[str]) -> None:
    """Запись через временный файл (как в v2); совместимость с исходным списком."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(sorted(markers), stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


def make_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=10))
    return session


def send_telegram(session: requests.Session, token: str, channel_id: str, text: str) -> bool:
    payload = {
        "chat_id": channel_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(MAX_RETRIES):
        try:
            response = session.post(endpoint, data=payload, timeout=20)
            if response.ok and response.json().get("ok") is True:
                return True
            if response.status_code == 429:
                try:
                    delay = min(60, max(1, int(response.json().get("parameters", {}).get("retry_after", 3))))
                except (ValueError, TypeError):
                    delay = 3
            elif response.status_code >= 500:
                delay = 2 ** attempt
            else:
                LOG.error("Telegram HTTP %s: %s", response.status_code, response.text[:250])
                return False
        except (requests.RequestException, ValueError) as exc:
            LOG.warning("Ошибка Telegram: %s", exc)
            delay = 2 ** attempt
        if attempt < MAX_RETRIES - 1:
            time.sleep(delay)
    return False


def check_events(*, db_path: str = DB_FILE, sent_path: str = SENT_FILE,
                 today: date | None = None, dry_run: bool = False) -> int:
    """Возвращает число успешно опубликованных СООБЩЕНИЙ, не событий."""
    today = today or datetime.now(MOSCOW_TZ).date()
    events = load_events(db_path)  # ТОЛЬКО ЧТЕНИЕ: файл базы не изменяется
    people = index_person_history(events)
    sent = set() if dry_run else load_sent(sent_path)

    pending: list[tuple[str, dict]] = []
    seen: set[str] = set()
    skipped_invalid = 0
    for item in events:
        event_date = date_for_event(item)
        if event_date is None:
            skipped_invalid += 1
            LOG.warning("Некорректная дата для: %s", item.get("artist", "?"))
            continue
        if (event_date.month, event_date.day) != (today.month, today.day):
            continue
        if event_date.year is not None and event_date.year > today.year:
            continue
        marker = event_identity(item, today)
        if marker in seen or marker in sent or original_event_identity(item, today) in sent:
            continue
        pending.append((marker, item))
        seen.add(marker)

    posts = build_publications(pending, today, people)
    LOG.info("%s: найдено %d новых событий, сообщений %d, неверных дат %d",
             today.isoformat(), len(pending), len(posts), skipped_invalid)

    if dry_run:
        if not posts:
            print("Для выбранной даты публикаций нет.")
        for index, post in enumerate(posts, start=1):
            print(f"\n{'=' * 55}\nПРЕДПРОСМОТР {index}/{len(posts)}\n{'=' * 55}")
            print(post.text)
        print("\nЭто предпросмотр: в Telegram ничего не отправлено; sent.json не изменён.")
        return 0

    if not posts:
        return 0
    token = as_text(os.getenv("BOT_TOKEN"))
    channel_id = as_text(os.getenv("CHANNEL_ID"))
    if not token or not channel_id:
        raise RuntimeError("Укажите BOT_TOKEN и CHANNEL_ID для публикации")

    sent_count = 0
    session = make_session()
    try:
        for index, post in enumerate(posts, start=1):
            if send_telegram(session, token, channel_id, post.text):
                sent.update(post.event_ids)
                # Сохраняем после КАЖДОГО сообщения: при частичном сбое
                # уже опубликованные события не дублируются.
                save_sent(sent_path, sent)
                sent_count += 1
                LOG.info("Опубликовано сообщение %d/%d (событий: %d)",
                         index, len(posts), len(post.event_ids))
            else:
                LOG.error("Сообщение %d/%d не опубликовано; события останутся в очереди",
                          index, len(posts))
            if index < len(posts):
                time.sleep(SEND_DELAY)
    finally:
        session.close()
    return sent_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Ежедневный бот 'Рок-сообщество'")
    parser.add_argument("--dry-run", action="store_true", help="Посмотреть публикации без отправки")
    parser.add_argument("--date", help="Дата YYYY-MM-DD, только с --dry-run")
    parser.add_argument("--db", default=DB_FILE, help="Путь к database_deepseek.json")
    parser.add_argument("--sent", default=SENT_FILE, help="Путь к sent.json")
    args = parser.parse_args()
    if args.date and not args.dry_run:
        parser.error("--date допустима только с --dry-run")
    try:
        selected_date = date.fromisoformat(args.date) if args.date else None
        check_events(db_path=args.db, sent_path=args.sent, today=selected_date, dry_run=args.dry_run)
    except (OSError, ValueError, RuntimeError) as exc:
        LOG.error("Работа бота прервана: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
