import os

TOKEN = os.getenv("TOKEN")

CHANNEL_ID = os.getenv("CHANNEL_ID")  # НЕ int()

CHECK_HOUR = int(os.getenv("CHECK_HOUR", "19"))
CHECK_MINUTE = int(os.getenv("CHECK_MINUTE", "7"))