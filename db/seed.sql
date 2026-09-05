-- ============================================================
-- Supermarket Ops Agent — Seed Data (Day 1)
-- ============================================================
-- Run with: psql "$DATABASE_URL" -f db/seed.sql
-- (or paste into Neon's SQL Editor)
--
-- GST rates reflect the GST 2.0 reform (effective 22 Sept 2025):
-- most goods collapsed into 0% / 5% / 18% bands. Sources checked
-- per-item rather than assumed — see notes below.

INSERT INTO products
    (sku, name, hsn_code, gst_rate, unit, is_loose, cost_price, mrp, sell_price, quantity_on_hand, reorder_level)
VALUES
    -- ---- 0% — unbranded loose staples ----
    ('LOOSE-RICE-KG',  'Rice (loose)',            '1006', 0.00,  'kg', TRUE,  38.00,  45.00,  45.00, 100.000, 15.000),
    ('LOOSE-DAL-KG',   'Toor Dal (loose)',         '0713', 0.00,  'kg', TRUE, 110.00, 135.00, 135.00,  60.000, 10.000),

    -- ---- 0% — salt is GST-exempt regardless of packaging ----
    ('TATA-SALT-1KG',  'Tata Salt 1kg',            '2501', 0.00,  'packet', FALSE, 20.00,  28.00,  27.00, 80.000, 10.000),

    -- ---- 5% — sugar is taxed at 5% even loose (unlike rice/dal) ----
    ('LOOSE-SUGAR-KG', 'Sugar (loose)',            '1701', 5.00,  'kg', TRUE,  42.00,  50.00,  50.00, 90.000, 15.000),

    -- ---- 5% — packaged staples / FMCG under GST 2.0 ----
    ('AASHIRVAAD-ATTA-5KG', 'Aashirvaad Atta 5kg', '1101', 5.00,  'packet', FALSE, 210.00, 260.00, 255.00, 40.000, 8.000),
    ('AMUL-BUTTER-100G',    'Amul Butter 100g',    '0405', 5.00,  'packet', FALSE,  48.00,  62.00,  60.00,  50.000, 10.000),
    ('FORTUNE-OIL-1L',      'Fortune Sunflower Oil 1L', '1512', 5.00, 'packet', FALSE, 118.00, 145.00, 140.00, 45.000, 10.000),
    ('MAGGI-70G',           'Maggi 70g',           '1902', 5.00,  'packet', FALSE,  11.00,  14.00,  14.00, 120.000, 20.000),
    ('PARLE-G',             'Parle-G Biscuits',    '1905', 5.00,  'packet', FALSE,   8.00,  10.00,  10.00, 150.000, 25.000),

    -- ---- 18% — detergent (HSN 3402) stayed at the higher rate ----
    ('SURF-EXCEL-1KG', 'Surf Excel Detergent 1kg', '3402', 18.00, 'packet', FALSE, 95.00, 130.00, 125.00, 35.000, 8.000);

-- One sample customer for testing khata flows
INSERT INTO customers (name, khata_balance) VALUES ('Ramesh', 0.00);

-- Shop identity + default behavior, used by invoices and the agent
INSERT INTO preferences (key, value) VALUES
    ('shop_name', 'Nebula Kirana Store'),
    ('shop_gstin', '33AAAAA0000A1Z5'),
    ('default_payment_mode', 'cash');