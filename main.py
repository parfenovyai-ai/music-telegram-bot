def check_events():
    moscow_time = datetime.now(timezone.utc) + timedelta(hours=3)

    today_mm = f"{moscow_time.month:02d}"
    today_dd = f"{moscow_time.day:02d}"

    print(f"[CRON CHECK] {today_dd}-{today_mm}")
    print("Moscow time:", moscow_time.strftime("%Y-%m-%d %H:%M:%S"))

    utils.init_db()

    events = load_events()
    if not events:
        print("No events found")
        return

    has_today_events = False

    for item in events:
        mm_dd = get_mm_dd(item.get("date", ""))
        if not mm_dd:
            continue

        mm, dd = mm_dd

        if mm != today_mm or dd != today_dd:
            continue

        has_today_events = True

        event_id = utils.make_event_id(item)

        if utils.is_sent(event_id):
            print("SKIP (already sent):", event_id)
            continue

        text = (
            "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ</b>\n\n"
            f"👤 {item.get('artist', 'Unknown')}\n"
            f"🎵 {item.get('group', 'Unknown')}\n"
            f"📅 {item.get('event', 'Unknown')}\n"
            f"🗓 {item.get('date', '')}"
        )

        if send_message(text):
            utils.mark_sent(event_id)
            print("SENT:", event_id)
        else:
            print("FAILED:", event_id)

    if not has_today_events:
        print("No events for today")
