"""
tests/test_inventory.py

Covers search_products -- added after live testing revealed the
agent had no way to resolve a plain product name ("aashirvaad atta")
into a SKU, since every other tool requires the SKU already known.
"""

from tools.inventory import search_products


def test_search_products_finds_partial_case_insensitive_match():
    result = search_products("aashirvaad")
    assert result["ok"] is True
    assert result["count"] >= 1
    assert any(m["sku"] == "AASHIRVAAD-ATTA-5KG" for m in result["matches"])


def test_search_products_no_match_returns_empty_not_error():
    result = search_products("this product does not exist at all")
    assert result["ok"] is True
    assert result["count"] == 0
    assert result["matches"] == []