"""
tests/test_gst.py

Proves the GST math for the three slabs your seed data actually
uses: 0%, 5%, 18%. Uses round-number prices (105, 118) on purpose
so the expected results are exact, not approximate -- makes the
test readable and removes any doubt about rounding hiding a bug.
"""

from tools.billing import compute_gst_split


def test_gst_split_zero_percent():
    result = compute_gst_split(qty=1, unit_price=100, gst_rate=0)
    assert result["line_total"] == 100.0
    assert result["taxable_value"] == 100.0
    assert result["cgst_amt"] == 0.0
    assert result["sgst_amt"] == 0.0


def test_gst_split_five_percent():
    # 105 inclusive of 5% GST -> exactly 100 taxable + 5 GST (2.5 + 2.5)
    result = compute_gst_split(qty=1, unit_price=105, gst_rate=5)
    assert result["line_total"] == 105.0
    assert result["taxable_value"] == 100.0
    assert result["cgst_amt"] == 2.5
    assert result["sgst_amt"] == 2.5


def test_gst_split_eighteen_percent():
    # 118 inclusive of 18% GST -> exactly 100 taxable + 18 GST (9 + 9)
    result = compute_gst_split(qty=1, unit_price=118, gst_rate=18)
    assert result["line_total"] == 118.0
    assert result["taxable_value"] == 100.0
    assert result["cgst_amt"] == 9.0
    assert result["sgst_amt"] == 9.0


def test_gst_split_scales_with_quantity():
    # 3 units should scale the whole split linearly
    result = compute_gst_split(qty=3, unit_price=105, gst_rate=5)
    assert result["line_total"] == 315.0
    assert result["taxable_value"] == 300.0
    assert result["cgst_amt"] == 7.5
    assert result["sgst_amt"] == 7.5