"""
manual_test.py

Quick sanity check for tools/inventory.py -- run with:
    python manual_test.py

Not a real test suite (that's tests/test_billing.py etc. later),
just a fast way to eyeball that things work against your real DB.
"""

from tools.inventory import receive_stock, get_stock_level
from tools.billing import start_bill, add_bill_item, remove_bill_item, get_bill_draft, finalize_bill
from tools.khata import get_customer_balance, charge_khata, record_khata_payment

print("Receiving 50 packets of Maggi...")
print(receive_stock("MAGGI-70G", 50, cost_price=12))

print("\nChecking stock level...")
print(get_stock_level("MAGGI-70G"))

print("\n--- Billing test ---")
bill = start_bill()
print("start_bill:", bill)
bill_id = bill["bill_id"]

print(add_bill_item(bill_id, "MAGGI-70G", 4))
print(add_bill_item(bill_id, "TATA-SALT-1KG", 1))
butter_item = add_bill_item(bill_id, "AMUL-BUTTER-100G", 1)
print(butter_item)

print("\nDropping the butter...")
print(remove_bill_item(butter_item["bill_item_id"]))

print("\nCurrent draft:")
print(get_bill_draft(bill_id))

print("\nTrying to oversell (999 Maggi)...")
print(add_bill_item(bill_id, "MAGGI-70G", 999))

print("\nFinalizing...")
print(finalize_bill(bill_id, payment_mode="upi"))

print("\nFinalizing AGAIN (should NOT double-decrement)...")
print(finalize_bill(bill_id, payment_mode="upi"))

print("\nStock after finalize:")
print(get_stock_level("MAGGI-70G"))

print("\n--- Khata test ---")
print("Putting 500 on Ramesh's credit...")
print(charge_khata("Ramesh", 500))

print("\nRamesh's balance:")
print(get_customer_balance("Ramesh"))

print("\nRamesh paid 300...")
print(record_khata_payment("Ramesh", 300))

print("\nRamesh's balance after payment:")
print(get_customer_balance("Ramesh"))

print("\nTrying to settle a khata that doesn't exist...")
print(record_khata_payment("Suresh", 100))