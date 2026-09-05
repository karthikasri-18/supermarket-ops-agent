"""
tools/khata.py

Khata = running credit ledger per customer, a first-class kirana
concept. Same audit-trail pattern as stock: customers.khata_balance
is the fast-read number, khata_transactions is the append-only log
behind it.

Functions take a customer NAME (not an id) because that's how the
owner actually talks -- "put 500 on Ramesh's credit". We look up
or create the customer row internally.
"""

from db.connection import get_connection


def _get_or_create_customer(cur, name: str) -> dict:
    cur.execute("SELECT * FROM customers WHERE name = %s", (name,))
    customer = cur.fetchone()
    if customer is not None:
        return dict(customer)
    cur.execute(
        "INSERT INTO customers (name, khata_balance) VALUES (%s, 0) RETURNING *",
        (name,),
    )
    return dict(cur.fetchone())


def get_customer_balance(name: str) -> dict:
    with get_connection() as cur:
        cur.execute("SELECT * FROM customers WHERE name = %s", (name,))
        customer = cur.fetchone()
        if customer is None:
            return {"ok": False, "error": "customer_not_found", "name": name}
        return {"ok": True, "name": customer["name"], "khata_balance": float(customer["khata_balance"])}


def charge_khata(name: str, amount: float, ref_bill_id: int = None) -> dict:
    """
    Customer buys on credit -- balance goes UP (they owe more).
    Creates the customer if this is their first time on khata.
    """
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount", "detail": "amount must be positive"}

    with get_connection() as cur:
        # Lock the customer row (or the freshly-created one) before
        # updating -- same reasoning as receive_stock: two khata
        # charges for the same customer at once shouldn't clobber
        # each other's balance update.
        customer = _get_or_create_customer(cur, name)
        cur.execute("SELECT * FROM customers WHERE id = %s FOR UPDATE", (customer["id"],))
        customer = cur.fetchone()

        new_balance = float(customer["khata_balance"]) + amount
        cur.execute(
            "UPDATE customers SET khata_balance = %s WHERE id = %s",
            (new_balance, customer["id"]),
        )
        cur.execute(
            "INSERT INTO khata_transactions (customer_id, amount, type, ref_bill_id) "
            "VALUES (%s, %s, 'charge', %s)",
            (customer["id"], amount, ref_bill_id),
        )
        return {"ok": True, "name": name, "charged": amount, "new_balance": new_balance}


def record_khata_payment(name: str, amount: float) -> dict:
    """
    Customer pays back some/all of what they owe -- balance goes
    DOWN. Refuses if the customer doesn't exist (can't settle a
    khata that was never opened -- one of the brief's guardrails).
    """
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount", "detail": "amount must be positive"}

    with get_connection() as cur:
        cur.execute("SELECT * FROM customers WHERE name = %s FOR UPDATE", (name,))
        customer = cur.fetchone()
        if customer is None:
            return {"ok": False, "error": "customer_not_found", "name": name}

        new_balance = float(customer["khata_balance"]) - amount
        cur.execute(
            "UPDATE customers SET khata_balance = %s WHERE id = %s",
            (new_balance, customer["id"]),
        )
        cur.execute(
            "INSERT INTO khata_transactions (customer_id, amount, type) VALUES (%s, %s, 'payment')",
            (customer["id"], amount),
        )
        return {"ok": True, "name": name, "paid": amount, "new_balance": new_balance}