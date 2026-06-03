import sqlite3
import json

DB_PATH = "state.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY,
            data TEXT
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM state")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO state (data) VALUES (?)", ("{}",))

    conn.commit()
    conn.close()


def load_state():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT data FROM state WHERE id = 1")
    row = cursor.fetchone()

    conn.close()

    if row:
        return json.loads(row[0])
    return {"sent": []}


def save_state(state):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE state SET data = ? WHERE id = 1",
        (json.dumps(state, ensure_ascii=False),)
    )

    conn.commit()
    conn.close()


def make_event_id(item):
    return f"{item['date']}|{item['artist']}|{item['group']}"
