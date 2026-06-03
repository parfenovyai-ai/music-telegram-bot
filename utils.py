import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "state.db")


# ---------------- INIT DB ----------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)

    # создаём единственную строку состояния
    cursor.execute("SELECT COUNT(*) FROM state")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO state (data) VALUES (?)", ("{}",))

    conn.commit()
    conn.close()


# ---------------- LOAD STATE ----------------

def load_state():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT data FROM state WHERE id = 1")
    row = cursor.fetchone()

    conn.close()

    if row:
        return json.loads(row[0])

    return {"sent": []}


# ---------------- SAVE STATE ----------------

def save_state(state):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE state SET data = ? WHERE id = 1",
        (json.dumps(state, ensure_ascii=False),)
    )

    conn.commit()
    conn.close()


# ---------------- EVENT ID ----------------

def make_event_id(item):
    return f"{item['date']}|{item['artist']}|{item['group']}"
