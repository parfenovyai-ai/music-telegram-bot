def build_header_message(total_events):
    return get_header(total_events)

def build_deceased_table(items):
    # У каждого музыканта своя дата смерти, включая год из базы данных.
    text = get_death_header(items) + "\n\n"
    for item in items:
        artist = escape(item.get("artist", ""))
        group = escape(item.get("group", ""))
        role = escape(item.get("role", ""))
        raw_date = str(item.get("date") or "").strip()
        date = escape(raw_date.replace("-", "."))
        gender = get_gender(item)
        event = get_death_text(item, gender)
        text += f"👤 <b>{artist}</b>\n"
        if date:
            text += f"📅 {date}\n"
        if group:
            text += f"🎵 {group}\n"
        if role:
            text += f"🎭 {role}\n"
        if event:
            text += f"📖 {event}\n"
        text += "-----------------------\n"
    text += f"\n{get_phrase()}"
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
    text += f"\n\n{get_phrase()}"
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
