"""
tools/analytics.py

Sales reporting. Only ever reads FINALIZED bills (draft bills
aren't real sales yet) -- an important distinction, since a
half-built draft bill someone abandoned shouldn't show up in
"today's sales".
"""

from datetime import date, timedelta
from db.connection import get_connection


def _parse_date(value):
    """Accepts None, a date object, or an ISO 'YYYY-MM-DD' string."""
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def get_sales_summary(date_from=None, date_to=None) -> dict:
    """
    Summarizes FINALIZED sales in [date_from, date_to] inclusive.
    Defaults to just today if neither is given.
    """
    start = _parse_date(date_from)
    end = _parse_date(date_to) if date_to is not None else start
    # finalized_at is a timestamp; we want the whole end day included,
    # so the upper bound is midnight of the day AFTER `end`.
    end_exclusive = end + timedelta(days=1)

    with get_connection() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(bi.line_total), 0) AS total_sales,
                   COALESCE(SUM(bi.cgst_amt + bi.sgst_amt), 0) AS total_tax
            FROM bill_items bi
            JOIN bills b ON b.id = bi.bill_id
            WHERE b.status = 'finalized'
              AND b.finalized_at >= %s AND b.finalized_at < %s
            """,
            (start, end_exclusive),
        )
        totals = cur.fetchone()

        cur.execute(
            """
            SELECT b.payment_mode, COALESCE(SUM(bi.line_total), 0) AS amount
            FROM bill_items bi
            JOIN bills b ON b.id = bi.bill_id
            WHERE b.status = 'finalized'
              AND b.finalized_at >= %s AND b.finalized_at < %s
            GROUP BY b.payment_mode
            """,
            (start, end_exclusive),
        )
        by_payment_mode = {row["payment_mode"]: float(row["amount"]) for row in cur.fetchall()}

        cur.execute(
            """
            SELECT p.sku, p.name, SUM(bi.qty) AS qty_sold, SUM(bi.line_total) AS revenue
            FROM bill_items bi
            JOIN bills b ON b.id = bi.bill_id
            JOIN products p ON p.id = bi.product_id
            WHERE b.status = 'finalized'
              AND b.finalized_at >= %s AND b.finalized_at < %s
            GROUP BY p.sku, p.name
            ORDER BY qty_sold DESC
            LIMIT 5
            """,
            (start, end_exclusive),
        )
        top_items = [
            {"sku": r["sku"], "name": r["name"], "qty_sold": float(r["qty_sold"]), "revenue": float(r["revenue"])}
            for r in cur.fetchall()
        ]

        return {
            "ok": True,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "total_sales": float(totals["total_sales"]),
            "total_tax_collected": float(totals["total_tax"]),
            "by_payment_mode": by_payment_mode,
            "top_items": top_items,
        }


def close_day(day=None) -> dict:
    """Same data as get_sales_summary, scoped to exactly one day and
    framed as a closing report."""
    target = _parse_date(day)
    summary = get_sales_summary(date_from=target, date_to=target)
    return {**summary, "closed_date": target.isoformat()}