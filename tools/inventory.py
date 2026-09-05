"""
tools/inventory.py

Plain Python functions for stock in/queries. No agent, no SDK
here -- just functions that take arguments and return dicts.
These get wrapped as agent tools in Day 2. Keeping them plain
for now means we can pytest them directly.
"""

from db.connection import get_connection


def get_product_by_sku(sku: str) -> dict:
    """
    Look up a single product by SKU. Returns
    {"ok": True, "product": {...}} or {"ok": False, "error": "not_found"}.
    """
    with get_connection() as cur:
        cur.execute("SELECT * FROM products WHERE sku = %s", (sku,))
        row = cur.fetchone()
        if row is None:
            return {"ok": False, "error": "not_found", "sku": sku}
        return {"ok": True, "product": dict(row)}


def get_stock_level(sku: str) -> dict:
    """
    Returns just the current quantity_on_hand for a SKU -- the
    thing the agent calls when the owner asks "how much X is left?"
    """
    result = get_product_by_sku(sku)
    if not result["ok"]:
        return result
    p = result["product"]
    return {
        "ok": True,
        "sku": p["sku"],
        "name": p["name"],
        "quantity_on_hand": float(p["quantity_on_hand"]),
        "unit": p["unit"],
    }


def get_low_stock_items() -> dict:
    """
    Returns every product where quantity_on_hand <= reorder_level.
    Powers "what's running out?".
    """
    with get_connection() as cur:
        cur.execute(
            """
            SELECT sku, name, quantity_on_hand, reorder_level, unit
            FROM products
            WHERE quantity_on_hand <= reorder_level
            ORDER BY quantity_on_hand ASC
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        return {"ok": True, "items": rows, "count": len(rows)}


def receive_stock(sku: str, qty: float, cost_price: float = None) -> dict:
    """
    Records stock coming into the shop. Increments quantity_on_hand
    and logs a 'receive' row in stock_transactions.

    If cost_price is given, also updates the product's cost_price
    (the price this batch cost the shop) -- shopkeepers' cost
    prices genuinely fluctuate batch to batch.

    Returns {"ok": True, "new_quantity": ...} or
    {"ok": False, "error": "not_found"} / {"ok": False, "error": "invalid_qty"}.
    """
    if qty <= 0:
        return {"ok": False, "error": "invalid_qty", "detail": "qty must be positive"}

    with get_connection() as cur:
        # SELECT ... FOR UPDATE locks this product row until our
        # transaction commits or rolls back. Any other transaction
        # trying to touch the same row will simply wait its turn --
        # this is what prevents two simultaneous stock changes from
        # clobbering each other.
        cur.execute("SELECT * FROM products WHERE sku = %s FOR UPDATE", (sku,))
        product = cur.fetchone()
        if product is None:
            return {"ok": False, "error": "not_found", "sku": sku}

        if cost_price is not None:
            cur.execute(
                "UPDATE products SET quantity_on_hand = quantity_on_hand + %s, cost_price = %s WHERE id = %s",
                (qty, cost_price, product["id"]),
            )
        else:
            cur.execute(
                "UPDATE products SET quantity_on_hand = quantity_on_hand + %s WHERE id = %s",
                (qty, product["id"]),
            )

        cur.execute(
            "INSERT INTO stock_transactions (product_id, change_qty, type) VALUES (%s, %s, 'receive')",
            (product["id"], qty),
        )

        new_qty = float(product["quantity_on_hand"]) + qty
        return {"ok": True, "sku": sku, "new_quantity": new_qty}