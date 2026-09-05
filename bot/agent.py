"""
bot/agent.py

Wraps the plain Python functions from tools/*.py as Claude Agent
SDK tools, and builds the ClaudeAgentOptions used to run the agent.

Nothing in here does business logic -- that already lives in
tools/*.py and is already tested. This file is purely plumbing:
describe each function to Claude, and let Claude decide when to
call it.
"""

import json

from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions

from tools.inventory import receive_stock, get_stock_level, get_low_stock_items, get_product_by_sku
from tools.billing import start_bill, add_bill_item, remove_bill_item, get_bill_draft, finalize_bill
from tools.khata import get_customer_balance, charge_khata, record_khata_payment


def _as_content(result: dict) -> dict:
    """Every one of our tool functions returns a plain dict. The SDK
    wants tool results shaped as {"content": [...]}. This wraps any
    dict as a JSON text block -- Claude reads JSON fine."""
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


# ---------- inventory tools ----------

@tool("get_product_info", "Look up a product's details (price, GST rate, stock) by SKU", {"sku": str})
async def t_get_product_info(args):
    return _as_content(get_product_by_sku(args["sku"]))


@tool("get_stock_level", "Get current stock quantity for a product by SKU", {"sku": str})
async def t_get_stock_level(args):
    return _as_content(get_stock_level(args["sku"]))


@tool("get_low_stock_items", "List all products at or below their reorder level", {})
async def t_get_low_stock_items(args):
    return _as_content(get_low_stock_items())


@tool(
    "receive_stock",
    "Record stock coming into the shop for a SKU. Increments quantity on hand.",
    {"sku": str, "qty": float, "cost_price": float},
)
async def t_receive_stock(args):
    return _as_content(receive_stock(args["sku"], args["qty"], args.get("cost_price")))


# ---------- billing tools ----------

@tool("start_bill", "Start a new draft bill, optionally for a named customer", {"customer_id": int})
async def t_start_bill(args):
    return _as_content(start_bill(args.get("customer_id")))


@tool(
    "add_bill_item",
    "Add one line item (a product + quantity) to a draft bill. Does not touch stock.",
    {"bill_id": int, "sku": str, "qty": float},
)
async def t_add_bill_item(args):
    return _as_content(add_bill_item(args["bill_id"], args["sku"], args["qty"]))


@tool("remove_bill_item", "Remove a line item from a draft bill by its bill_item_id", {"bill_item_id": int})
async def t_remove_bill_item(args):
    return _as_content(remove_bill_item(args["bill_item_id"]))


@tool("get_bill_draft", "Get the current items and total for a bill (draft or finalized)", {"bill_id": int})
async def t_get_bill_draft(args):
    return _as_content(get_bill_draft(args["bill_id"]))


@tool(
    "finalize_bill",
    "Finalize a draft bill: decrements stock, records the sale. Safe to call more than once.",
    {"bill_id": int, "payment_mode": str, "payment_ref": str},
)
async def t_finalize_bill(args):
    return _as_content(
        finalize_bill(args["bill_id"], args.get("payment_mode"), args.get("payment_ref"))
    )


# ---------- khata tools ----------

@tool("get_customer_balance", "Get a customer's current khata (credit) balance by name", {"name": str})
async def t_get_customer_balance(args):
    return _as_content(get_customer_balance(args["name"]))


@tool(
    "charge_khata",
    "Put an amount on a customer's khata (credit) -- they now owe the shop more",
    {"name": str, "amount": float},
)
async def t_charge_khata(args):
    return _as_content(charge_khata(args["name"], args["amount"]))


@tool(
    "record_khata_payment",
    "Record a customer paying back some of their khata balance",
    {"name": str, "amount": float},
)
async def t_record_khata_payment(args):
    return _as_content(record_khata_payment(args["name"], args["amount"]))


ALL_TOOLS = [
    t_get_product_info, t_get_stock_level, t_get_low_stock_items, t_receive_stock,
    t_start_bill, t_add_bill_item, t_remove_bill_item, t_get_bill_draft, t_finalize_bill,
    t_get_customer_balance, t_charge_khata, t_record_khata_payment,
]

SERVER_NAME = "shop_tools"

_shop_server = create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=ALL_TOOLS)

# mcp__<server_name>__<tool_name> is how the SDK identifies each tool.
ALLOWED_TOOL_IDS = [f"mcp__{SERVER_NAME}__{t.name}" for t in ALL_TOOLS]

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

AMBIGUITY: if a request is genuinely ambiguous (e.g. "add atta" when
there's more than one kind), ask a short clarifying question rather
than guessing which product they mean.

Keep replies short and conversational -- the owner is running a shop,
not reading a report.
"""


def build_agent_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={SERVER_NAME: _shop_server},
        # `tools` restricts which tools EXIST for this session at all --
        # this is what keeps Claude's built-in Bash/Read/Write/WebFetch
        # etc. out of reach entirely, not just "not pre-approved".
        tools=ALLOWED_TOOL_IDS,
        # `allowed_tools` additionally pre-approves them so they run
        # without a permission prompt (which we can't answer anyway --
        # nobody's watching a CLI for this headless bot).
        allowed_tools=ALLOWED_TOOL_IDS,
        permission_mode="bypassPermissions",
    )