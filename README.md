# Supermarket Ops Agent

A conversational operations agent for an Indian kirana store. The owner runs the shop through **Telegram only**, using plain natural language to manage inventory, billing, GST, customer khata, daily sales, and business documents.

PostgreSQL is the source of truth for products, stock, bills, customers, preferences, and audit trails.

## Live Demo

**Telegram Bot:** `@nebula_kirana_bot`


**Demo Video:** https://drive.google.com/file/d/1Bon1Pj6c1ofP72Np_l8biRfYTNmE71ql/view?usp=sharing

The recording demonstrates the required flow:
- Receive stock
- Build and edit a multi-item bill
- Oversell protection
- Khata charge/payment cycle
- Generate a GST invoice PDF
- Generate the sales analysis PPTX
- Set a preference
- Start `/new` chat and verify the preference is remembered

## Invoice Output

The agent generates a real GST invoice PDF from a finalized bill, including product/HSN details, taxable value, CGST, SGST, and totals.

![Generated Invoice](image.png)

## Analysis Deck

The agent can generate a PowerPoint sales-analysis deck containing store metrics, top-selling items, stock health, GST collected, and charts.

## Harness & Control Loop

The agent uses Google's `google-genai` SDK with **Gemini (`gemini-3.1-flash-lite`)**. Typed Python functions are exposed as model tools, allowing Gemini to decide which capabilities to call and to chain multiple tool calls within a single turn.

The control loop is:

1. Telegram receives the owner's natural-language request.
2. The bot loads persistent shop preferences from PostgreSQL.
3. Gemini reasons over the request and conversation context.
4. Gemini calls one or more typed tools as required.
5. Tool results are fed back automatically until the task is complete.
6. The final response is returned to Telegram, while generated PDFs/PPTX files are sent as real Telegram documents.

Gemini was chosen because Google AI Studio provides a free developer tier without requiring a payment card.

## Key Features

- Natural-language product search without requiring the owner to know SKUs
- Inventory receiving, stock lookup, and low-stock detection
- Product creation with HSN and GST validation
- Multi-turn bill creation and bill editing
- GST-inclusive pricing with taxable value, CGST, SGST, and correct rounding
- Authoritative oversell protection during finalization
- Below-cost sale guardrail
- Cash, UPI, Card, and Khata payment modes
- Customer khata charges, payments, and balances
- Daily sales and payment-mode summaries
- GST-correct PDF invoice generation
- PowerPoint sales-analysis deck generation with charts
- Persistent shop preferences across `/new` conversations
- Telegram update idempotency and mutation recovery after transient API failures

## Hard Parts & Reliability

- **Grounding:** Prices, GST, stock, and balances are retrieved from PostgreSQL through tools; the model is not allowed to invent them.
- **Product resolution:** Natural-language names are resolved through product search before SKU-based operations. Ambiguous matches are clarified rather than guessed.
- **Oversell protection:** Stock is checked during draft creation and re-checked authoritatively during finalization.
- **GST correctness:** Each bill line retains its GST/HSN information. GST-inclusive prices are split into taxable value, CGST, and SGST using `Decimal` with round-half-up.
- **Multi-turn billing:** Bills remain drafts while being built and can be edited. Stock is changed only when the bill is finalized.
- **Idempotency:** Telegram `update_id` values prevent duplicate processing. Khata mutations use idempotency keys, and finalized bills are safe to replay.
- **Concurrency:** Finalization locks involved product rows in a consistent order and checks aggregate demand before changing stock.
- **Guardrails:** Missing/invalid HSN information, missing prices, unknown khata customers, overselling, and below-cost sales are refused or require the appropriate confirmation.
- **Persistence:** Shop data and preferences live in PostgreSQL and survive `/new` and process restarts.
- **Transient failures:** If a mutation commits before a downstream Gemini/API failure, the bot reports the committed action rather than asking the owner to repeat it.

## Tool & Skill Design

The model-facing wrappers are in [`bot/agent.py`](bot/agent.py). Business logic is kept in small database-backed modules:

| Module | Responsibility |
|---|---|
| `tools/inventory.py` | Product search, product creation, stock receiving, stock levels, HSN validation, low-stock queries |
| `tools/billing.py` | Bill lifecycle, GST calculations, below-cost checks, oversell protection, finalization |
| `tools/khata.py` | Customer balances, credit charges, payments, idempotency |
| `tools/analytics.py` | Sales summaries and daily closing |
| `tools/documents.py` | GST invoice PDFs and PPTX analysis decks |
| `tools/preferences.py` | Persistent shop preferences |
| `skills/gst_rules.md` | GST/domain guidance |
| `skills/khata_rules.md` | Khata/domain guidance |

Business rules are enforced in the tools/database layer rather than relying only on prompt instructions.

## Tech Stack

- **Interface:** Telegram Bot API
- **Agent:** Google `google-genai` SDK + Gemini
- **Backend:** Python
- **Database:** PostgreSQL
- **Documents:** PDF invoices + PPTX analysis decks
- **Deployment:** Railway
- **Testing:** pytest

## Project Structure

```text
supermarket-ops-agent/
├── bot/
│   ├── agent.py
│   └── main.py
├── db/
│   ├── connection.py
│   ├── schema.sql
│   └── seed.sql
├── tools/
│   ├── inventory.py
│   ├── billing.py
│   ├── khata.py
│   ├── analytics.py
│   ├── documents.py
│   └── preferences.py
├── skills/
│   ├── gst_rules.md
│   └── khata_rules.md
├── tests/
├── docs/
│   ├── invoice-screenshot.png
│   └── analysis-deck-screenshot.png
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

Requirements: Python 3.10+ and PostgreSQL.

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

Configure:

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

Run:

```bash
python -m bot.main
```

For Railway or another worker platform, use:

```bash
python -m bot.main
```

This application uses Telegram long polling and therefore runs as a background worker rather than an HTTP web service.

## Example Conversation

```text
50 packets of Maggi came in, cost ₹12, MRP ₹14
make a bill: 2kg sugar, 1 Aashirvaad atta 5kg, 4 Maggi, UPI
actually make the Maggi 6
finalize
send me that bill as a PDF
put ₹500 on Ramesh's credit
Ramesh's balance?
Ramesh paid ₹300
show today's sales
make a sales analysis deck
always assume UPI unless I say cash
/new
```

An invoice can only be generated for a finalized bill. A payment mode mentioned during bill creation does not itself finalize the sale.

## Submission Links

- **Telegram Bot:** `@nebula_kirana_bot`
- **Demo Recording:** https://drive.google.com/file/d/1Bon1Pj6c1ofP72Np_l8biRfYTNmE71ql/view?usp=sharing
- **GitHub Repository:** `https://github.com/karthikasri-18/supermarket-ops-agent.git`

## Testing

With a configured test database:

```bash
pytest
```

Tests cover GST slabs and rounding, product search, below-cost protection, overselling, cumulative quantities in drafts, idempotent finalization, and concurrent finalization.