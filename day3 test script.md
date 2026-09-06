# Day 3 — Live Telegram Test Script

Message your bot these in order. Restart `python -m bot.main` first if it's not
already running. For each step, check the "expect" line before moving on.

## 1. Multi-turn bill with an edit
1. "make a bill: 2kg sugar, 1 aashirvaad atta, 4 maggi, 1 amul butter, upi"
   -> expect: agent starts a bill, adds all 4 items, tells you a running total.
   If "aashirvaad atta" is ambiguous in your seed data (it isn't -- you only
   have one atta SKU), it should still just work. If you ever add a second
   atta variant later, THIS is the moment it should ask which one.
2. "drop the butter, make it 6 maggi"
   -> expect: it removes the butter line and updates maggi's qty to 6, then
   shows you the new total. It should NOT ask you to restate the whole bill.
3. "what's in the bill so far?"
   -> expect: an accurate summary matching what you'd get from get_bill_draft.

## 2. Oversell guard, live
4. "add 500 packets of maggi"
   -> expect: refused, tells you how many are actually available. Does NOT
   crash, does NOT silently cap the quantity to what's available without
   telling you.

## 3. Finalize + idempotency, live
5. "that's it, finalize"
   -> expect: confirms the bill is done, stock decremented.
6. Send the EXACT same "that's it, finalize" message again (or "finalize" again).
   -> expect: agent says it's already finalized / doesn't double-charge.
   (This tests your idempotency table, but through natural conversation
   rather than calling finalize_bill twice programmatically like the
   pytest test did.)

## 4. Khata cycle, live
7. "put 500 on ramesh's credit"
   -> expect: confirms, new balance 500 (or +500 if Ramesh already has a
   balance from earlier testing -- check what get_customer_balance shows
   first if you're unsure).
8. "what's ramesh's balance?"
   -> expect: correct current number, matching the DB.
9. "ramesh paid 300"
   -> expect: confirms, balance drops by exactly 300.

## 5. Below-cost guardrail, live
10. "sell 1 amul butter for 10 rupees" (butter's cost price is higher than this
    in your seed data -- check tools/inventory or query the DB if unsure)
    -> expect: agent tells you it's below cost and asks you to confirm
    before proceeding. It should NOT silently add it at that price.
11. "yes, sell it anyway"
    -> expect: NOW it adds the item, since you explicitly confirmed.

## 6. Grounding sanity check
12. "how much rice do we have and what does it cost?"
    -> expect: numbers that match reality (check against a fresh
    get_stock_level/get_product_info call, or the Neon dashboard).
    This is the one to be paranoid about -- if the agent EVER states a
    number without it matching your DB, that's a grounding failure and
    worth digging into before moving on.

---
If everything above behaves as expected, Day 3's hardest parts are proven
live, not just in pytest. Note any deviation exactly (what you typed, what
it said, what you expected) so we can debug precisely rather than guessing.