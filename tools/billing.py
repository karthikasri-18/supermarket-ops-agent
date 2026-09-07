"""
tools/billing.py

Bill lifecycle as plain functions: start_bill -> add_bill_item /
remove_bill_item (repeatable, draft only) -> finalize_bill.

Only finalize_bill ever touches quantity_on_hand. Everything
before that is just rows in bill_items describing a draft.
"""

from decimal import Decimal, ROUND_HALF_UP
from db.connection import get_connection

TWO_PLACES = Decimal("0.01")


def _round(value) -> float:
    """Round money to 2 decimal places the way tax calculations
    are expected to round -- 0.5 always rounds up, not banker's
    rounding (Python's built-in round() would give 12.50 -> 12.0
    on some values, which is wrong for money)."""
    return float(Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


def compute_gst_split(qty, unit_price, gst_rate) -> dict:
    """
    unit_price is treated as GST-INCLUSIVE (like an MRP).
    Splits a line into taxable_value + cgst + sgst that together
    reconstruct the original line_total.

    Example: qty=1, unit_price=14, gst_rate=5
      line_total     = 14.00
      taxable_value  = 14.00 / 1.05           = 13.33
      total_gst      = 14.00 - 13.33          = 0.67
      cgst = sgst    = total_gst / 2          = 0.33 / 0.34 (rounded, may differ by a paisa)
    """
    line_total = Decimal(str(qty)) * Decimal(str(unit_price))
    rate = Decimal(str(gst_rate)) / Decimal("100")
    taxable_value = line_total / (Decimal("1") + rate)

    total_gst = line_total - taxable_value
    cgst = total_gst / 2
    sgst = total_gst - cgst  # avoids losing a paisa to rounding vs total_gst/2 twice

    return {
        "taxable_value": _round(taxable_value),
        "cgst_amt": _round(cgst),
        "sgst_amt": _round(sgst),
        "line_total": _round(line_total),
    }


def start_bill(customer_id: int = None) -> dict:
    with get_connection() as cur:
        cur.execute(
            "INSERT INTO bills (status, customer_id) VALUES ('draft', %s) RETURNING id",
            (customer_id,),
        )
        bill_id = cur.fetchone()["id"]
        return {"ok": True, "bill_id": bill_id}


def add_bill_item(bill_id: int, sku: str, qty: float, unit_price: float = None,
                   override_below_cost: bool = False) -> dict:
    """
    Adds one line to a draft bill. Does NOT touch stock -- this is
    a quote, not a sale, until finalize_bill runs.

    Does a soft stock check here (fast feedback for the owner) but
    the authoritative check happens again at finalize_bill, because
    stock can change between add and finalize.
    """
    with get_connection() as cur:
        cur.execute("SELECT status FROM bills WHERE id = %s", (bill_id,))
        bill = cur.fetchone()
        if bill is None:
            return {"ok": False, "error": "bill_not_found", "bill_id": bill_id}
        if bill["status"] != "draft":
            return {"ok": False, "error": "bill_not_editable", "status": bill["status"]}

        cur.execute("SELECT * FROM products WHERE sku = %s", (sku,))
        product = cur.fetchone()
        if product is None:
            return {"ok": False, "error": "not_found", "sku": sku}

        price = float(unit_price) if unit_price is not None else float(product["sell_price"])

        if price < float(product["cost_price"]) and not override_below_cost:
            return {
                "ok": False,
                "error": "below_cost",
                "sku": sku,
                "cost_price": float(product["cost_price"]),
                "attempted_price": price,
                "detail": "Selling below cost needs override_below_cost=True",
            }

        # Sum what THIS draft bill already has for this product -- the
        # same SKU can be added across multiple messages (e.g. "4 maggi"
        # now, "6 more maggi" later), so the real check is against total
        # demand so far, not just this one call's qty.
        cur.execute(
            "SELECT COALESCE(SUM(qty), 0) AS already_qty FROM bill_items "
            "WHERE bill_id = %s AND product_id = %s",
            (bill_id, product["id"]),
        )
        already_in_bill = float(cur.fetchone()["already_qty"])
        total_demand = already_in_bill + qty

        if total_demand > float(product["quantity_on_hand"]):
            return {
                "ok": False,
                "error": "insufficient_stock",
                "sku": sku,
                "available": float(product["quantity_on_hand"]),
                "requested": qty,
                "already_in_bill": already_in_bill,
                "total_requested": total_demand,
            }

        split = compute_gst_split(qty, price, float(product["gst_rate"]))

        cur.execute(
            """
            INSERT INTO bill_items
                (bill_id, product_id, qty, unit_price, gst_rate, cgst_amt, sgst_amt, line_total)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (bill_id, product["id"], qty, price, product["gst_rate"],
             split["cgst_amt"], split["sgst_amt"], split["line_total"]),
        )
        item_id = cur.fetchone()["id"]

        return {"ok": True, "bill_item_id": item_id, "sku": sku, "qty": qty, **split}


def remove_bill_item(bill_item_id: int) -> dict:
    with get_connection() as cur:
        cur.execute(
            """
            SELECT bi.id, b.status FROM bill_items bi
            JOIN bills b ON b.id = bi.bill_id
            WHERE bi.id = %s
            """,
            (bill_item_id,),
        )
        row = cur.fetchone()
        if row is None:
            return {"ok": False, "error": "not_found", "bill_item_id": bill_item_id}
        if row["status"] != "draft":
            return {"ok": False, "error": "bill_not_editable", "status": row["status"]}

        cur.execute("DELETE FROM bill_items WHERE id = %s", (bill_item_id,))
        return {"ok": True, "removed_bill_item_id": bill_item_id}


def _fetch_bill_draft(cur, bill_id: int) -> dict:
    """
    Shared implementation used by both get_bill_draft (its own
    connection/transaction) and finalize_bill (reuses finalize_bill's
    OWN open cursor). This matters: if finalize_bill instead called
    get_bill_draft() directly, that would open a brand-new connection
    that can't see finalize_bill's own not-yet-committed UPDATE --
    Postgres correctly isolates uncommitted transactions from each
    other -- and you'd see stale data (e.g. status still 'draft'
    immediately after finalizing). Passing the same cursor through
    means we're reading our own transaction's own writes, which is
    always visible.
    """
    cur.execute("SELECT * FROM bills WHERE id = %s", (bill_id,))
    bill = cur.fetchone()
    if bill is None:
        return {"ok": False, "error": "bill_not_found", "bill_id": bill_id}

    cur.execute(
        """
        SELECT bi.id AS bill_item_id, p.sku, p.name, p.hsn_code, bi.qty, bi.unit_price,
               bi.gst_rate, bi.cgst_amt, bi.sgst_amt, bi.line_total
        FROM bill_items bi
        JOIN products p ON p.id = bi.product_id
        WHERE bi.bill_id = %s
        ORDER BY bi.id
        """,
        (bill_id,),
    )
    items = [dict(r) for r in cur.fetchall()]
    total = _round(sum(i["line_total"] for i in items)) if items else 0.0

    return {"ok": True, "bill_id": bill_id, "status": bill["status"], "items": items, "total": total}


def get_bill_draft(bill_id: int) -> dict:
    with get_connection() as cur:
        return _fetch_bill_draft(cur, bill_id)


def finalize_bill(bill_id: int, payment_mode: str = None, payment_ref: str = None) -> dict:
    """
    The critical function. Locks every product row involved (in a
    consistent order, sorted by product_id, to avoid deadlocking
    against another finalize_bill running at the same time), then:
      1. If already finalized -> return the existing result, don't
         redo anything (idempotency: safe against Telegram retries).
      2. Re-checks stock for every item under the lock (authoritative
         oversell guard -- this is what a concurrent sale can't slip past).
      3. If all good: decrements stock, logs stock_transactions,
         flips the bill to 'finalized'.
      All checks fail together -- if ANY item is short, NOTHING is
      decremented (the whole transaction rolls back).
    """
    with get_connection() as cur:
        cur.execute("SELECT * FROM bills WHERE id = %s", (bill_id,))
        bill = cur.fetchone()
        if bill is None:
            return {"ok": False, "error": "bill_not_found", "bill_id": bill_id}

        if bill["status"] == "finalized":
            # Idempotent replay: same result, no double-decrement.
            return {**_fetch_bill_draft(cur, bill_id), "already_finalized": True}

        cur.execute(
            """
            SELECT bi.id AS bill_item_id, bi.product_id, bi.qty, bi.line_total, p.sku
            FROM bill_items bi JOIN products p ON p.id = bi.product_id
            WHERE bi.bill_id = %s
            ORDER BY bi.product_id
            """,
            (bill_id,),
        )
        items = cur.fetchall()
        if not items:
            return {"ok": False, "error": "empty_bill", "bill_id": bill_id}

        # Lock every involved product row, in product_id order, before
        # checking anything -- this is what makes two simultaneous
        # finalize_bill calls (different bills, overlapping SKUs) safe.
        product_ids = sorted({row["product_id"] for row in items})
        locked = {}
        for pid in product_ids:
            cur.execute("SELECT * FROM products WHERE id = %s FOR UPDATE", (pid,))
            locked[pid] = cur.fetchone()

        # Aggregate demand PER PRODUCT before checking. The same product
        # can appear across multiple bill_item rows -- e.g. added in two
        # separate messages ("4 maggi" then later "add 6 more maggi").
        # Checking each row independently against raw stock would miss
        # the case where no single row oversells but their SUM does.
        demand_by_product = {}
        sku_by_product = {}
        for row in items:
            pid = row["product_id"]
            demand_by_product[pid] = demand_by_product.get(pid, 0.0) + float(row["qty"])
            sku_by_product[pid] = row["sku"]

        for pid, total_qty in demand_by_product.items():
            available = float(locked[pid]["quantity_on_hand"])
            if total_qty > available:
                return {
                    "ok": False,
                    "error": "insufficient_stock",
                    "sku": sku_by_product[pid],
                    "available": available,
                    "requested": total_qty,
                }

        for row in items:
            cur.execute(
                "UPDATE products SET quantity_on_hand = quantity_on_hand - %s WHERE id = %s",
                (row["qty"], row["product_id"]),
            )
            cur.execute(
                "INSERT INTO stock_transactions (product_id, change_qty, type, ref_bill_id) "
                "VALUES (%s, %s, 'sale', %s)",
                (row["product_id"], -float(row["qty"]), bill_id),
            )

        cur.execute(
            "UPDATE bills SET status = 'finalized', payment_mode = %s, payment_ref = %s, "
            "finalized_at = now() WHERE id = %s",
            (payment_mode, payment_ref, bill_id),
        )

        result = _fetch_bill_draft(cur, bill_id)
        return {**result, "already_finalized": False}