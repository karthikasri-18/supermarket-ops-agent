"""
db/connection.py

Central place for talking to Postgres. Every tool function in
tools/*.py should go through get_connection() so we have one
consistent way of opening transactions and locking rows.
"""

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()  # reads .env into environment variables

DATABASE_URL = os.environ["DATABASE_URL"]


@contextmanager
def get_connection():
    """
    Opens a connection + transaction, hands you a cursor, and
    commits automatically if the `with` block finishes cleanly —
    or rolls back automatically if anything inside it raises.

    Usage:
        with get_connection() as cur:
            cur.execute("SELECT ...")
            row = cur.fetchone()
            cur.execute("UPDATE ...")
        # commits here, once the block exits without error
    """
    conn = psycopg2.connect(DATABASE_URL)
    try:
        # RealDictCursor gives us rows as dicts (row["sku"]) instead
        # of plain tuples (row[0]) -- much easier to read and debug.
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()