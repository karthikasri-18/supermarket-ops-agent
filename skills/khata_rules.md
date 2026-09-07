# Khata rules for this shop

Domain notes on khata — the running credit ledger every kirana store
keeps for regular customers. The enforcement lives in
`tools/khata.py`; this file explains the concept and the rules the
agent should reason from.

## What khata means

A customer buys now and pays later. The shop tracks how much each
customer currently owes on a running balance (`customers.khata_balance`),
backed by an append-only log (`khata_transactions`) of every charge
and payment — same audit-trail pattern as stock.

- "Put ₹500 on Ramesh's credit" → a **charge**: balance goes UP.
- "Ramesh paid ₹300" → a **payment**: balance goes DOWN.
- Balance can be positive (customer owes the shop) — this shop does
  not model prepaid/advance balances, so a payment only ever reduces
  what's owed.

## Customer identity

Customers are referred to by name, not ID — the owner will never say
"customer 14". A charge on a name that doesn't exist yet **creates**
that customer (their first-ever khata purchase). A payment on a name
that doesn't exist is refused with `customer_not_found` — you cannot
settle a khata that was never opened. This is one of the brief's
explicit guardrails: confirm or refuse, don't silently create a
customer just to accept a payment for them.

## Linking khata to a bill

When a bill is finalized with `payment_mode = "khata"`, the sale
amount should also be charged to that customer's khata via
`charge_khata`, tagged with the bill's id as `ref_bill_id` — this is
what lets "what does Ramesh owe" be traced back to which specific
bills, not just a floating number.

## Amounts

Charges and payments must be strictly positive — a zero or negative
amount is rejected rather than silently accepted, since that's either
a typo or an attempt to manipulate the balance in a way that isn't
one of the two real khata operations.