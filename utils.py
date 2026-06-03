import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "state.db")


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


def is_sent(event_id: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM sent_events WHERE event_id = ?", (event_id,))
    result = cur.fetchone()

    conn.close()
    return result is not None


def mark_sent(event_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO sent_events (event_id) VALUES (?)",
        (event_id,)
    )

    conn.commit()
    conn.close()
