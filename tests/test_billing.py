"""
tests/test_billing.py

Proves the three hardest parts of billing:
  1. Overselling is refused with the correct available quantity
  2. Calling finalize_bill twice only decrements stock once
  3. Two REAL concurrent finalize_bill calls (separate threads,
     separate DB connections -- not simulated) on overlapping
     stock can't overdraw it

Uses a disposable test product (created fresh, deleted after)
so re-running the suite never depends on your real seeded stock.
"""

import threading
import pytest

from db.connection import get_connection
from tools.billing import start_bill, add_bill_item, finalize_bill

TEST_SKU = "TEST-CONCURRENCY-ITEM"


@pytest.fixture
def test_product():
    """Creates a fresh test product with 10 units of stock before
    each test, and cleans it up afterward."""
    with get_connection() as cur:
        cur.execute(
            """
            INSERT INTO products
                (sku, name, hsn_code, gst_rate, unit, is_loose,
                 cost_price, mrp, sell_price, quantity_on_hand, reorder_level)
            VALUES (%s, 'Test Item', '0000', 5, 'piece', FALSE, 5, 10, 10, 10, 2)
            RETURNING id
            """,
            (TEST_SKU,),
        )
        product_id = cur.fetchone()["id"]

    yield TEST_SKU, product_id

    # Teardown: remove dependent rows first (foreign keys), then the product.
    with get_connection() as cur:
        cur.execute("DELETE FROM stock_transactions WHERE product_id = %s", (product_id,))
        cur.execute("DELETE FROM bill_items WHERE product_id = %s", (product_id,))
        cur.execute("DELETE FROM products WHERE id = %s", (product_id,))


def test_oversell_rejected_with_correct_available(test_product):
    sku, _ = test_product
    bill = start_bill()
    result = add_bill_item(bill["bill_id"], sku, 999)

    assert result["ok"] is False
    assert result["error"] == "insufficient_stock"
    assert result["available"] == 10.0


def test_finalize_twice_does_not_double_decrement(test_product):
    sku, product_id = test_product
    bill = start_bill()
    add_bill_item(bill["bill_id"], sku, 3)

    first = finalize_bill(bill["bill_id"])
    assert first["ok"] is True
    assert first["already_finalized"] is False

    second = finalize_bill(bill["bill_id"])
    assert second["ok"] is True
    assert second["already_finalized"] is True

    with get_connection() as cur:
        cur.execute("SELECT quantity_on_hand FROM products WHERE id = %s", (product_id,))
        remaining = float(cur.fetchone()["quantity_on_hand"])

    assert remaining == 7.0  # 10 - 3, exactly once


def test_concurrent_finalize_does_not_overdraw_stock(test_product):
    """
    The real concurrency test. Two DRAFT bills each want 6 units,
    but only 10 exist -- together they'd oversell by 2. We finalize
    both AT THE SAME TIME in separate threads (separate DB
    connections, mimicking two real Telegram messages arriving
    together). Exactly one must succeed; the other must be refused;
    stock must never go negative or below what one sale should leave.
    """
    sku, product_id = test_product
    bill_a = start_bill()["bill_id"]
    bill_b = start_bill()["bill_id"]
    add_bill_item(bill_a, sku, 6)
    add_bill_item(bill_b, sku, 6)

    results = {}

    def run(name, bill_id):
        results[name] = finalize_bill(bill_id)

    t1 = threading.Thread(target=run, args=("a", bill_a))
    t2 = threading.Thread(target=run, args=("b", bill_b))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = [r for r in results.values() if r["ok"] and not r.get("error")]
    failures = [r for r in results.values() if r.get("error") == "insufficient_stock"]

    assert len(successes) == 1, f"expected exactly 1 success, got {results}"
    assert len(failures) == 1, f"expected exactly 1 insufficient_stock failure, got {results}"

    with get_connection() as cur:
        cur.execute("SELECT quantity_on_hand FROM products WHERE id = %s", (product_id,))
        remaining = float(cur.fetchone()["quantity_on_hand"])

    assert remaining == 4.0  # 10 - 6, only the winner's sale applied


def test_below_cost_sale_is_refused_without_override(test_product):
    sku, _ = test_product
    bill = start_bill()
    # test_product has cost_price=5 -- offering it at 3 is below cost
    result = add_bill_item(bill["bill_id"], sku, 1, unit_price=3)

    assert result["ok"] is False
    assert result["error"] == "below_cost"
    assert result["cost_price"] == 5.0
    assert result["attempted_price"] == 3.0


def test_below_cost_sale_allowed_with_explicit_override(test_product):
    sku, _ = test_product
    bill = start_bill()
    result = add_bill_item(bill["bill_id"], sku, 1, unit_price=3, override_below_cost=True)

    assert result["ok"] is True
    assert result["sku"] == sku