"""
tools/inventory.py

Plain Python functions for stock in/queries. No agent, no SDK
here -- just functions that take arguments and return dicts.
These get wrapped as agent tools in Day 2. Keeping them plain
for now means we can pytest them directly.
"""

import re
from db.connection import get_connection


def _slugify_sku(name: str) -> str:
    """Turns 'Amul Butter 100g' into 'AMUL-BUTTER-100G' for an
    auto-generated SKU -- the owner never says a SKU when adding a
    new product ("new item: Amul Butter 100g, GST 12%, MRP ₹62"),
    so we have to make one up ourselves."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper()
    return slug or "PRODUCT"


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


def search_products(query: str) -> dict:
    """
    Fuzzy name/SKU lookup -- this is how the agent resolves what the
    owner actually calls things ("sugar", "atta", "maggi") into a real
    SKU, since owners never know or say SKU codes. Matches against
    both name and sku, case-insensitive, substring match.

    Returns {"ok": True, "matches": [...], "count": N}. An empty list
    is a real "we don't stock that", not an error -- the caller should
    relay that honestly rather than asking the owner for a SKU.
    """
    with get_connection() as cur:
        cur.execute(
            """
            SELECT sku, name, unit, sell_price, gst_rate, quantity_on_hand
            FROM products
            WHERE name ILIKE %s OR sku ILIKE %s
            ORDER BY name
            """,
            (f"%{query}%", f"%{query}%"),
        )
        rows = [dict(r) for r in cur.fetchall()]
        return {"ok": True, "matches": rows, "count": len(rows)}


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


def add_product(name: str, hsn_code: str, gst_rate: float, unit: str,
                 mrp: float, cost_price: float, is_loose: bool = False,
                 sell_price: float = None, reorder_level: float = 0) -> dict:
    """
    Registers a brand new product the shop wants to start stocking --
    e.g. "new item: Amul Butter 100g, GST 12%, MRP 62". Starts at 0
    stock on purpose: adding a product and receiving stock of it are
    two separate real-world actions (a new line can be listed before
    the first delivery arrives) -- call receive_stock separately once
    it actually comes in.

    The owner never gives a SKU code (they don't know what one is),
    so one is generated automatically from the product name and made
    unique if it collides with an existing SKU.

    cost_price is required, not optional: without it the below-cost
    guardrail on billing can't function for this product. If the
    owner hasn't stated a cost price, ask for it rather than calling
    this with a guessed value.

    Returns {"ok": True, "sku": ..., "product_id": ...} or
    {"ok": False, "error": "invalid_name" | "invalid_price"}.
    """
    if not name or not name.strip():
        return {"ok": False, "error": "invalid_name"}
    if mrp is None or cost_price is None or mrp <= 0 or cost_price <= 0:
        return {
            "ok": False,
            "error": "invalid_price",
            "detail": "mrp and cost_price are both required and must be positive",
        }

    final_sell_price = sell_price if sell_price is not None else mrp

    with get_connection() as cur:
        # Auto-generate a SKU from the name, then guarantee uniqueness
        # by appending a numeric suffix on collision (e.g. a second
        # "Amul Butter" variant added later).
        base_sku = _slugify_sku(name)
        candidate_sku = base_sku
        suffix = 1
        while True:
            cur.execute("SELECT 1 FROM products WHERE sku = %s", (candidate_sku,))
            if cur.fetchone() is None:
                break
            suffix += 1
            candidate_sku = f"{base_sku}-{suffix}"

        cur.execute(
            """
            INSERT INTO products
                (sku, name, hsn_code, gst_rate, unit, is_loose,
                 cost_price, mrp, sell_price, quantity_on_hand, reorder_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
            RETURNING id
            """,
            (candidate_sku, name, hsn_code, gst_rate, unit, is_loose,
             cost_price, mrp, final_sell_price, reorder_level),
        )
        product_id = cur.fetchone()["id"]

        return {
            "ok": True,
            "product_id": product_id,
            "sku": candidate_sku,
            "name": name,
            "quantity_on_hand": 0.0,
        }


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