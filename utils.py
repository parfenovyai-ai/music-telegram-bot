import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "state.db")


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    print("🟡 SQLite init starting...")

    conn = get_conn()
    cur = conn.cursor()

    # 1. создаём таблицу
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sent_events (
            event_id TEXT PRIMARY KEY
        )
    """)

    conn.commit()
    conn.close()

    # 2. проверка файла
    exists = os.path.exists(DB_PATH)

    print("🟢 SQLite init done")
    print("📦 DB PATH:", DB_PATH)
    print("📦 DB EXISTS:", exists)

    # 3. тестовая запись (самая важная проверка)
    test_id = "__startup_test__"

    try:
        mark_sent(test_id)
        print("🧪 TEST WRITE OK")

        # проверка чтения
        if is_sent(test_id):
            print("🧪 TEST READ OK")

        # очистка теста (чтобы не засорять БД)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM sent_events WHERE event_id = ?", (test_id,))
        conn.commit()
        conn.close()

        print("🧹 TEST CLEANUP OK")

    except Exception as e:
        print("❌ SQLITE INIT FAILED:", e)


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


def make_event_id(item):
    return f"{item['date']}|{item['artist']}|{item['group']}"
