# GST rules for this shop

Domain notes for the agent on how GST works in this store. The actual
math lives in `tools/billing.py::compute_gst_split` — this file is
the reasoning behind that code, not a duplicate of it.

## Slab structure (GST 2.0, effective 22 Sept 2025)

India's old five-slab system (0/5/12/18/28%) was rationalised into
three slabs. This shop only stocks items in these bands:

- **0%** — unbranded loose staples (loose rice, loose dal) and salt
  (salt is GST-exempt regardless of packaging).
- **5%** — packaged staples and everyday FMCG: packaged atta, butter,
  cooking oil, instant noodles, biscuits, and loose sugar (sugar is
  taxed even loose, unlike rice/dal — don't assume "loose = 0%").
- **18%** — non-food FMCG like detergent.

Every product's `gst_rate` and `hsn_code` are stored on the product
row and are the source of truth — never guess a rate from the product
name. If a new product is being added and the owner doesn't state a
GST rate, ask rather than defaulting to 5%.

## CGST / SGST split

This shop operates intra-state, so GST is split evenly between CGST
and SGST (no IGST). `unit_price` is treated as **GST-inclusive** (the
way an MRP works) — the taxable value is backed out, not added on
top:

```
taxable_value = line_total / (1 + gst_rate/100)
total_gst     = line_total - taxable_value
cgst = sgst   = total_gst / 2 (sgst absorbs any odd paisa)
```

## Rounding rule

Money always rounds to 2 decimal places using round-half-up (12.505
→ 12.51), never Python's default banker's rounding, which can round
12.5 down and silently shortchange the till by a paisa on every line.

## What the invoice must show

Per line: item, qty, rate, taxable value, CGST, SGST, HSN code, line
total. The bill total is the exact sum of line totals — it should
never be recomputed by re-multiplying qty × rate × (1 + rate/100),
since that can disagree with the sum of already-rounded lines by a
paisa.