"""
tools/preferences.py

Simple key-value store. bot/main.py already reads this table
directly and prepends it to every message -- these functions are
for the AGENT to read/write preferences mid-conversation (e.g.
"always assume UPI unless I say cash" should actually persist).
"""

from db.connection import get_connection


def get_preference(key: str) -> dict:
    with get_connection() as cur:
        cur.execute("SELECT value FROM preferences WHERE key = %s", (key,))
        row = cur.fetchone()
        if row is None:
            return {"ok": False, "error": "not_set", "key": key}
        return {"ok": True, "key": key, "value": row["value"]}


def set_preference(key: str, value: str) -> dict:
    with get_connection() as cur:
        cur.execute(
            """
            INSERT INTO preferences (key, value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            (key, value),
        )
        return {"ok": True, "key": key, "value": value}


def get_all_preferences() -> dict:
    with get_connection() as cur:
        cur.execute("SELECT key, value FROM preferences ORDER BY key")
        prefs = {row["key"]: row["value"] for row in cur.fetchall()}
        return {"ok": True, "preferences": prefs}