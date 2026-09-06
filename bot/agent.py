"""
bot/agent.py

Rewired to use Google's Gemini API (google-genai SDK) instead of
Anthropic's Claude Agent SDK -- switched specifically because
Gemini's Developer API (via Google AI Studio) has a genuinely free
tier with no card required. Everything in tools/*.py is completely
unchanged; only this wrapping layer is different from before.

Key facts about this SDK (checked against Google's current docs,
since this kind of library shifts fast):
  - Package: google-genai (import as `from google import genai`)
  - Plain Python functions with type hints + a Google-style docstring
    (an "Args:" section) can be handed directly as `tools=[...]` --
    the SDK builds the schema from the signature/docstring AND
    automatically executes the function when the model calls it.
    No manual dispatch loop needed.
  - We use the `chats` module (client.chats.create + send_message)
    rather than a raw one-shot call -- Google has flagged an
    upcoming breaking change that removes automatic function calling
    from direct generate_content calls in the SDK's next major
    version, so this is the forward-compatible pattern.
"""

from typing import Optional
from google import genai
from google.genai import types

from tools.inventory import receive_stock, get_stock_level, get_low_stock_items, get_product_by_sku
from tools.billing import start_bill, add_bill_item, remove_bill_item, get_bill_draft, finalize_bill
from tools.khata import get_customer_balance, charge_khata, record_khata_payment
from tools.preferences import get_preference, set_preference
from tools.analytics import get_sales_summary, close_day


# ---------- tool wrappers ----------
# Gemini's automatic function calling reads these type hints and the
# "Args:" docstring section directly to build each tool's schema --
# so this isn't just documentation, the wording actually matters.

def tool_get_product_info(sku: str) -> dict:
    """Look up a product's details (price, GST rate, stock) by SKU.

    Args:
        sku: The product's SKU code.
    """
    return get_product_by_sku(sku)


def tool_get_stock_level(sku: str) -> dict:
    """Get current stock quantity on hand for a product by SKU.

    Args:
        sku: The product's SKU code.
    """
    return get_stock_level(sku)


def tool_get_low_stock_items() -> dict:
    """List all products at or below their reorder level."""
    return get_low_stock_items()


def tool_receive_stock(sku: str, qty: float, cost_price: Optional[float] = None) -> dict:
    """Record stock coming into the shop for a SKU. Increments quantity on hand.

    Args:
        sku: The product's SKU code.
        qty: Quantity received, must be positive.
        cost_price: Optional new cost price for this batch, if the owner mentioned one.
    """
    return receive_stock(sku, qty, cost_price)


def tool_start_bill(customer_id: Optional[int] = None) -> dict:
    """Start a new draft bill, optionally linked to an existing customer id.

    Args:
        customer_id: Optional existing customer id to link this bill to.
    """
    return start_bill(customer_id)


def tool_add_bill_item(bill_id: int, sku: str, qty: float,
                        unit_price: Optional[float] = None,
                        override_below_cost: bool = False) -> dict:
    """Add one line item (a product + quantity) to a draft bill. Does not touch stock.

    If this returns error='below_cost', do NOT retry with override_below_cost=True
    on your own judgment. First tell the owner the cost price and ask them to
    explicitly confirm they want to sell below cost, and only then retry with
    the override set.

    Args:
        bill_id: The draft bill's id.
        sku: The product's SKU code.
        qty: Quantity to add.
        unit_price: Optional override price; defaults to the product's sell_price.
        override_below_cost: Only set true after the owner explicitly confirms.
    """
    return add_bill_item(bill_id, sku, qty, unit_price=unit_price, override_below_cost=override_below_cost)


def tool_remove_bill_item(bill_item_id: int) -> dict:
    """Remove a line item from a draft bill by its bill_item_id.

    Args:
        bill_item_id: The id of the bill_items row to remove.
    """
    return remove_bill_item(bill_item_id)


def tool_get_bill_draft(bill_id: int) -> dict:
    """Get the current items and total for a bill, draft or finalized.

    Args:
        bill_id: The bill's id.
    """
    return get_bill_draft(bill_id)


def tool_finalize_bill(bill_id: int, payment_mode: Optional[str] = None,
                        payment_ref: Optional[str] = None) -> dict:
    """Finalize a draft bill: decrements stock, records the sale. Safe to call
    more than once -- a repeat call returns the already-finalized result
    instead of decrementing stock again.

    Args:
        bill_id: The bill's id.
        payment_mode: One of 'cash', 'upi', 'card', or 'khata'.
        payment_ref: Optional payment reference, e.g. a UPI transaction id.
    """
    return finalize_bill(bill_id, payment_mode, payment_ref)


def tool_get_customer_balance(name: str) -> dict:
    """Get a customer's current khata (credit) balance by name.

    Args:
        name: The customer's name.
    """
    return get_customer_balance(name)


def tool_charge_khata(name: str, amount: float) -> dict:
    """Put an amount on a customer's khata (credit) -- they now owe the shop more.

    Args:
        name: The customer's name.
        amount: Amount to charge, must be positive.
    """
    return charge_khata(name, amount)


def tool_record_khata_payment(name: str, amount: float) -> dict:
    """Record a customer paying back some of their khata balance.

    Args:
        name: The customer's name.
        amount: Amount paid, must be positive.
    """
    return record_khata_payment(name, amount)


def tool_get_preference(key: str) -> dict:
    """Get one stored shop preference by key (e.g. 'default_payment_mode').

    Args:
        key: The preference key.
    """
    return get_preference(key)


def tool_set_preference(key: str, value: str) -> dict:
    """Set a standing shop preference that persists across chats -- e.g.
    default payment mode, preferred brand, shop name/GSTIN for invoices.
    Use this when the owner says something like "always assume X" or
    "remember that...".

    Args:
        key: The preference key.
        value: The preference value.
    """
    return set_preference(key, value)


def tool_get_sales_summary(date_from: Optional[str] = None, date_to: Optional[str] = None) -> dict:
    """Get total sales, tax collected, cash/UPI/card split, and top items for
    a date range (ISO 'YYYY-MM-DD' strings). Defaults to just today if no
    dates are given.

    Args:
        date_from: Optional ISO start date.
        date_to: Optional ISO end date.
    """
    return get_sales_summary(date_from, date_to)


def tool_close_day(day: Optional[str] = None) -> dict:
    """Get the closing sales report for one day, defaults to today.

    Args:
        day: Optional ISO date string.
    """
    return close_day(day)


ALL_TOOLS = [
    tool_get_product_info, tool_get_stock_level, tool_get_low_stock_items, tool_receive_stock,
    tool_start_bill, tool_add_bill_item, tool_remove_bill_item, tool_get_bill_draft, tool_finalize_bill,
    tool_get_customer_balance, tool_charge_khata, tool_record_khata_payment,
    tool_get_preference, tool_set_preference, tool_get_sales_summary, tool_close_day,
]

SYSTEM_PROMPT = """You are the operations agent for an Indian kirana (grocery) store.
The owner talks to you in plain, terse, real-shopkeeper English via Telegram.

GROUNDING RULE (most important): never state a price, stock level, or
khata balance without having just called a tool for it THIS turn. Never
guess or invent a number. If you don't have a tool result for it, call
the tool first.

BILLING: a bill is built over several messages using start_bill,
add_bill_item, remove_bill_item, and get_bill_draft. Nothing is sold
and no stock moves until finalize_bill is explicitly called -- if the
owner hasn't said something like "that's it" / "finalize" / a payment
mode, keep the bill in draft and just confirm what's in it so far.

GUARDRAILS: if a tool call comes back with ok: false, relay the reason
to the owner naturally (e.g. "only 6 left of that" for insufficient
stock) -- never crash, never silently retry with a different number.
For a below_cost error specifically: tell the owner the cost price and
ask them to explicitly confirm before retrying with override_below_cost.
Never set that override on your own judgment.

AMBIGUITY: if a request is genuinely ambiguous (e.g. "add atta" when
there's more than one kind), ask a short clarifying question rather
than guessing which product they mean.

Keep replies short and conversational -- the owner is running a shop,
not reading a report.
"""

MODEL_NAME = "gemini-3.6-flash"

# One shared client for the whole process. Chat SESSIONS (below) are what
# hold per-conversation history -- the client itself is just a connection,
# safe to reuse across every Telegram chat.
_client = genai.Client()


def new_chat_session():
    """
    Creates one fresh conversational session with all shop tools attached.
    Call this once per Telegram chat_id and keep it around -- the `chats`
    module keeps conversation history internally across send_message calls,
    the same way ClaudeSDKClient did.
    """
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
    )
    return _client.chats.create(model=MODEL_NAME, config=config)