import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "state.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)

    cur.execute("SELECT COUNT(*) FROM state")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO state (data) VALUES (?)", ("{}",))

    conn.commit()
    conn.close()


def load_state():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT data FROM state WHERE id = 1")
    row = cur.fetchone()
    conn.close()

    if row:
        return json.loads(row[0])

    return {"sent": []}


def save_state(state):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "UPDATE state SET data = ? WHERE id = 1",
        (json.dumps(state, ensure_ascii=False),)
    )

    conn.commit()
    conn.close()


def make_event_id(item):
    return f"{item['date']}|{item['artist']}|{item['group']}"
