"""
network_test.py

Bypasses python-telegram-bot entirely -- just tests whether plain
Python can reach api.telegram.org at all. Run: python network_test.py
"""

import os
from dotenv import load_dotenv
import httpx

load_dotenv()
token = os.environ["TELEGRAM_BOT_TOKEN"]

print("Attempting request to api.telegram.org...")
try:
    resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
    print("SUCCESS:", resp.json())
except Exception as e:
    print("FAILED:", type(e).__name__, e)