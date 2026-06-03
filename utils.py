import json
import os
from threading import Lock

STATE_FILE = "state.json"
file_lock = Lock()


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"sent": []}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with file_lock:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


def make_event_id(item):
    return f"{item['date']}|{item['artist']}|{item['group']}"