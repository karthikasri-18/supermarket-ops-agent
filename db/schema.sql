-- ============================================================
-- Supermarket Ops Agent — Schema (Day 1)
-- ============================================================
-- Run with: psql "$DATABASE_URL" -f db/schema.sql

-- ---------- products ----------
-- One row per SKU. cost_price/sell_price both stored so we can
-- enforce "don't sell below cost" without doing math elsewhere.
CREATE TABLE products (
    id                SERIAL PRIMARY KEY,
    sku               TEXT UNIQUE NOT NULL,
    name              TEXT NOT NULL,
    hsn_code          TEXT NOT NULL,          -- GST classification code
    gst_rate          NUMERIC(5,2) NOT NULL,  -- e.g. 0, 5, 12, 18
    unit              TEXT NOT NULL,          -- kg / g / litre / ml / packet / dozen / piece
    is_loose          BOOLEAN NOT NULL DEFAULT FALSE,
    cost_price        NUMERIC(10,2) NOT NULL,
    mrp               NUMERIC(10,2) NOT NULL,
    sell_price        NUMERIC(10,2) NOT NULL,
    quantity_on_hand  NUMERIC(10,3) NOT NULL DEFAULT 0,  -- NUMERIC not INT: loose items can be 2.5kg
    reorder_level     NUMERIC(10,3) NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- stock_transactions ----------
-- Append-only audit log. Never update or delete rows here.
CREATE TABLE stock_transactions (
    id            SERIAL PRIMARY KEY,
    product_id    INTEGER NOT NULL REFERENCES products(id),
    change_qty    NUMERIC(10,3) NOT NULL,     -- positive = stock in, negative = stock out
    type          TEXT NOT NULL,              -- 'receive' | 'sale' | 'adjustment'
    ref_bill_id   INTEGER,                    -- links to bills.id when type = 'sale'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- customers ----------
CREATE TABLE customers (
    id             SERIAL PRIMARY KEY,
    name           TEXT NOT NULL,
    khata_balance  NUMERIC(10,2) NOT NULL DEFAULT 0,  -- amount customer owes the shop
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- bills ----------
-- status: 'draft' while being built over multiple messages,
-- 'finalized' once stock has been decremented. Nothing before
-- finalize touches quantity_on_hand.
CREATE TABLE bills (
    id            SERIAL PRIMARY KEY,
    status        TEXT NOT NULL DEFAULT 'draft',   -- 'draft' | 'finalized'
    payment_mode  TEXT,                            -- 'cash' | 'upi' | 'card' | 'khata'
    payment_ref   TEXT,
    customer_id   INTEGER REFERENCES customers(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalized_at  TIMESTAMPTZ
);

-- ---------- bill_items ----------
-- gst_rate is copied from products at the time of sale (not
-- looked up later) so a bill stays historically accurate even
-- if the product's GST rate changes in future.
CREATE TABLE bill_items (
    id          SERIAL PRIMARY KEY,
    bill_id     INTEGER NOT NULL REFERENCES bills(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    qty         NUMERIC(10,3) NOT NULL,
    unit_price  NUMERIC(10,2) NOT NULL,
    gst_rate    NUMERIC(5,2) NOT NULL,
    cgst_amt    NUMERIC(10,2) NOT NULL,
    sgst_amt    NUMERIC(10,2) NOT NULL,
    line_total  NUMERIC(10,2) NOT NULL
);

-- ---------- khata_transactions ----------
-- Audit trail behind customers.khata_balance, same pattern as
-- stock_transactions behind quantity_on_hand.
CREATE TABLE khata_transactions (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    amount       NUMERIC(10,2) NOT NULL,
    type         TEXT NOT NULL,             -- 'charge' | 'payment'
    ref_bill_id  INTEGER,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- preferences ----------
-- Simple key-value store, read fresh from DB on every incoming
-- message — this is what survives a /new chat.
CREATE TABLE preferences (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- processed_updates ----------
-- Idempotency guard against Telegram redelivering the same
-- update. Before processing an update, try to INSERT its id
-- here; if it already exists, skip processing entirely.
CREATE TABLE processed_updates (
    telegram_update_id  BIGINT PRIMARY KEY,
    processed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);