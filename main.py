import os
import json
import datetime
import threading
import time
from typing import Any

from flask import Flask
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler

import config
import utils

# ---------------- Flask ----------------

app = Flask(__name__)


@app.get("/")
def home() -> str:
    return "Bot is running"


# ---------------- Bot ----------------

bot = Bot(token=config.TOKEN)


def send_message(text: str) -> None:
    try:
        bot.send_message(chat_id=config.CHANNEL_ID, text=text)
    except Exception as e:
        print(f"TELEGRAM ERROR: {e}")


# ---------------- Data ----------------

def load_rock_events() -> list[dict[str, Any]]:
    path = os.path.join(os.path.dirname(__file__), "database.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


rock_events = load_rock_events()


# ---------------- Logic ----------------

def parse_date(date_str: str) -> tuple[int, int] | None:
    """
    Поддерживает форматы:
    YYYY-MM-DD
    DD-MM-YYYY
    DD-MM
    """
    parts = date_str.split("-")

    try:
        if len(parts) == 3 and len(parts[0]) == 4:
            return int(parts[2]), int(parts[1])  # YYYY-MM-DD
        elif len(parts) == 3:
            return int(parts[0]), int(parts[1])  # DD-MM-YYYY
        return None
    except ValueError:
        return None


def check_events() -> None:
    today = datetime.datetime.now()
    day, month = today.day, today.month

    print(f"[CHECK] {day}-{month}")

    state = utils.load_state()
    sent: list[str] = state.get("sent", [])

    for item in rock_events:
        try:
            parsed = parse_date(item.get("date", ""))
            if not parsed:
                continue

            d, m = parsed

            if d != day or m != month:
                continue

            event_id = utils.make_event_id(item)

            if event_id in sent:
                continue

            text = (
                "🎸 РОК-СОБЫТИЕ СЕГОДНЯ\n\n"
                f"👤 {item.get('artist', 'Unknown')}\n"
                f"🎵 {item.get('group', 'Unknown')}\n"
                f"📅 {item.get('event', 'Unknown')}\n"
                f"🗓 {item.get('date', '')}"
            )

            send_message(text)

            sent.append(event_id)
            state["sent"] = sent
            utils.save_state(state)

            print(f"SENT: {event_id}")

        except Exception as e:
            print(f"ERROR: {e}")


# ---------------- Scheduler ----------------

def start_scheduler() -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_events, "interval", minutes=1)
    scheduler.start()

    print("Scheduler started")

    # держим поток живым
    while True:
        time.sleep(60)


# ---------------- MAIN ----------------

def start_app() -> None:
    print("🚀 BOT STARTING")

    threading.Thread(target=start_scheduler, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    start_app()