import sqlite3
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "state.db")

LOCK_FILE = os.path.join(BASE_DIR, "bot.lock")
_lock = threading.Lock()


# ---------------- DB ----------------

def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sent_events (
            event_id TEXT PRIMARY KEY
        )
    """)

    conn.commit()
    conn.close()


# ---------------- SAFE CHECK ----------------

def is_sent(event_id: str) -> bool:
    with _lock:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM sent_events WHERE event_id = ?", (event_id,))
        result = cur.fetchone()

        conn.close()
        return result is not None


# ---------------- SAFE WRITE ----------------

def mark_sent(event_id: str):
    with _lock:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            "INSERT OR IGNORE INTO sent_events (event_id) VALUES (?)",
            (event_id,)
        )

        conn.commit()
        conn.close()


# ---------------- EVENT ID ----------------

def make_event_id(item):
    return f"{item['date']}|{item['artist']}|{item['group']}"


# ---------------- PROCESS LOCK ----------------

def acquire_lock():
    """
    Возвращает True если можно запускать бот
    False если он уже запущен
    """
    if os.path.exists(LOCK_FILE):
        return False

    with open(LOCK_FILE, "w") as f:
        f.write("running")

    return True


def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)