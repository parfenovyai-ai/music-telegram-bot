import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# =====================
# CONFIG
# =====================
TOKEN = (os.getenv("TOKEN") or "").strip()
CHANNEL_ID = (os.getenv("CHANNEL_ID") or "").strip()

if not TOKEN or not CHANNEL_ID:
    print("❌ ERROR: Missing TOKEN or CHANNEL_ID")
    exit(1)

API_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
TEST_URL = f"https://api.telegram.org/bot{TOKEN}/getMe"

DB_FILE = "database.json"
SENT_FILE = "sent.json"


# =====================
# TELEGRAM CHECK
# =====================
def check_bot():
    try:
        r = requests.get(TEST_URL, timeout=10)
        print("BOT CHECK:", r.status_code, r.text)

        if r.status_code != 200:
            print("❌ Invalid Telegram token (getMe failed)")
            exit(1)

    except Exception as e:
        print("❌ Telegram check error:", e)
        exit(1)


# =====================
# LOAD DATA
# =====================
def load_events():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("ERROR loading database:", e)
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
            json.dump(list(sent), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("ERROR saving sent:", e)


# =====================
# DATE PARSER
# =====================
def parse_date(date_str):
    date_str = date_str.strip()
    for fmt in ("%d-%m-%Y", "%d-%m"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except:
            continue
    return None


# =====================
# TELEGRAM SEND
# =====================
def send_message(text):
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        r = requests.post(API_URL, data=payload, timeout=10)
        print("Telegram response:", r.status_code, r.text)
        return r.status_code == 200
    except Exception as e:
        print("Telegram ERROR:", e)
        return False


# =====================
# MAIN LOGIC
# =====================
def check_events():
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    today_month = now.month
    today_day = now.day

    print("=== CRON START ===")
    print("Moscow time:", now)
    print(f"Today: {today_day:02d}-{today_month:02d}")

    events = load_events()
    sent = load_sent()

    print("Loaded events:", len(events))
    print("Already sent:", len(sent))

    found = 0

    for item in events:
        raw_date = item.get("date", "")
        event_date = parse_date(raw_date)

        if not event_date:
            print("SKIP invalid date:", raw_date)
            continue

        # MATCH by day/month only (supports yearly events)
        if event_date.month != today_month or event_date.day != today_day:
            continue

        found += 1

        event_id = f"{item.get('date')}-{item.get('artist')}-{item.get('group')}"

        if event_id in sent:
            print("SKIP already sent:", event_id)
            continue

        text = (
            "🎸 <b>РОК-СОБЫТИЕ СЕГОДНЯ</b>\n\n"
            f"👤 {item.get('artist', 'Unknown')}\n"
            f"🎵 {item.get('group', 'Unknown')}\n"
            f"📅 {item.get('event', 'Unknown')}\n"
            f"🗓 {item.get('date', '')}"
        )

        if send_message(text):
            sent.add(event_id)
            save_sent(sent)
            print("SENT:", event_id)
        else:
            print("FAILED:", event_id)

    if found == 0:
        print("No events for today")

    print("=== CRON END ===")


# =====================
# ENTRYPOINT
# =====================
if __name__ == "__main__":
    print("TOKEN START:", TOKEN[:10])
    check_bot()
    check_events()
