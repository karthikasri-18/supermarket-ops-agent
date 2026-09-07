# Supermarket Ops Agent

A conversational operations agent for an Indian kirana store. The owner uses
plain English through Telegram to manage inventory, build and finalize bills,
track customer khata (credit), and generate business documents. PostgreSQL is
the source of truth for products, stock, bills, customers, preferences, and
audit trails.

## Harness

The agent uses Google's `google-genai` SDK with Gemini
(`gemini-3.1-flash-lite`). The SDK receives typed Python functions as tools,
automatically executes functions selected by the model, and returns the final
natural-language response. Gemini was selected because Google AI Studio offers
a free developer tier without requiring a payment card.

The control loop is:

1. Telegram receives a message.
2. The bot loads shop preferences from PostgreSQL.
3. Gemini observes the message and conversation history, reasons about the
   request, and calls one or more tools.
4. Tool results are fed back automatically until Gemini produces a response.
5. The response is sent back to Telegram; generated PDFs/PPTX files are sent
   as real Telegram documents.

## Telegram bot

The bot runs with Telegram long polling. Configure the username created with
BotFather in the deployment or recording notes, for example `@your_store_bot`.
The repository does not contain a bot token or username.

## Features

- Search products by natural-language name instead of requiring SKUs.
- Receive stock, inspect stock, and list low-stock items.
- Add products with generated unique SKUs, required cost price, and validated
  4-, 6-, or 8-digit HSN codes.
- Build multi-turn draft bills, edit/remove lines, and show running totals.
- Refuse overselling using both draft-time checks and an authoritative
  transaction-time check.
- Refuse below-cost sales unless the owner explicitly confirms an override.
- Finalize bills using cash, UPI, card, or khata; only finalization changes
  stock.
- Track khata charges, payments, balances, and bill-linked credit sales.
- Generate GST-correct PDF invoices with HSN, taxable value, CGST, SGST, and
  totals.
- Generate PowerPoint sales analysis decks with a native editable chart.
- Report finalized sales, tax collected, payment-mode totals, and top items.
- Persist shop preferences across `/new` conversations.

## Tool and skill design

The model-facing wrappers live in [bot/agent.py](bot/agent.py). Database-backed
domain logic stays in small, testable modules:

- [tools/inventory.py](tools/inventory.py): product search, product creation,
  stock receiving, stock levels, HSN validation, and low-stock queries.
- [tools/billing.py](tools/billing.py): draft lifecycle, GST calculations,
  below-cost checks, oversell protection, and finalization.
- [tools/khata.py](tools/khata.py): customer balances, credit charges, and
  payments with idempotency keys.
- [tools/analytics.py](tools/analytics.py): finalized-sales summaries and
  day-closing reports.
- [tools/documents.py](tools/documents.py): PDF invoices and PPTX analysis
  decks.
- [tools/preferences.py](tools/preferences.py): persistent shop settings.
- [skills/gst_rules.md](skills/gst_rules.md) and
  [skills/khata_rules.md](skills/khata_rules.md): domain guidance supplied to
  the agent; enforcement remains in the Python tools and database.

## Reliability and guardrails

- **Grounding:** prices, stock, and balances must come from a tool call in the
  current turn; the agent must not guess numbers.
- **Product resolution:** name search happens before SKU-based operations, and
  ambiguous matches are clarified instead of guessed.
- **GST correctness:** product GST/HSN is stored with each bill line; inclusive
  prices are split into taxable value, CGST, and SGST using `Decimal` and
  round-half-up.
- **Draft safety:** editing a bill only changes draft rows. Stock changes only
  during `finalize_bill`.
- **Oversell and concurrency:** finalization locks involved product rows in a
  consistent order, aggregates demand by product, and rolls back the whole
  transaction if any item is short.
- **Idempotency:** finalized bills, khata mutations, and Telegram
  `update_id` values are protected against duplicate processing.
- **Guardrails:** invalid HSN placeholders, missing prices, unknown payment
  customers, and below-cost sales are refused with actionable errors.
- **Cross-session memory:** conversation history is per Telegram chat, while
  shop data and preferences remain in PostgreSQL and survive `/new` or a
  process restart.
- **Transient failures:** API errors after a mutation report the committed
  result rather than asking the owner to repeat a potentially duplicate action.

## Setup

Requirements: Python 3.10+ and a PostgreSQL database (Neon, Supabase,
Railway, or a local PostgreSQL instance).

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set:

```dotenv
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=...
GEMINI_API_KEY=...
```

Initialize the database:

```bash
psql "$DATABASE_URL" -f db/schema.sql
psql "$DATABASE_URL" -f db/seed.sql
```

Run the bot from the repository root as a module:

```bash
python -m bot.main
```

Do not run `python bot/main.py`; module execution preserves the package
imports used by the tools and database modules.

For Railway, Render, or another worker platform, use `python -m bot.main` as
the start command. This is a background worker using Telegram long polling,
not an HTTP web service.

## Example conversations

```text
50 packets of Maggi came in, cost ₹12, MRP ₹14
new item: Amul Butter 100g, GST 5%, MRP ₹62
make a bill: 2kg sugar, 1 Aashirvaad atta 5kg, 4 Maggi, UPI
actually make the Maggi 6
finalize
send me that bill as a PDF
put ₹500 on Ramesh's credit
Ramesh's balance?
Ramesh paid ₹300
show today's sales
make a sales analysis deck
```

An invoice can only be generated for a finalized bill. A bill mentioning a
payment mode is kept as a draft until the owner explicitly asks to finalize.

## Testing

With a configured test database, run:

```bash
pytest
```

The tests cover GST slabs and rounding, product search, below-cost protection,
overselling, cumulative quantities in a draft, idempotent finalization, and
concurrent finalization.