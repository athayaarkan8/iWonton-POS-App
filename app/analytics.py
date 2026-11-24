from datetime import timedelta
from sqlalchemy.orm import selectinload
from app.models import Order
from app.utils import wib_range_to_utc, to_wib


def completed_orders(start_date, end_date):
    """Hanya order completed pada rentang tanggal WIB (berdasarkan waktu order dibuat)."""
    utc_start, utc_end = wib_range_to_utc(start_date, end_date)
    return (Order.query.options(selectinload(Order.items))
            .filter(Order.status == "completed", Order.created_at >= utc_start, Order.created_at < utc_end)
            .order_by(Order.created_at.asc()).all())


def summarize(orders):
    revenue = sum(o.total for o in orders)
    count = len(orders)
    portions = sum(i.quantity for o in orders for i in o.items)
    average = round(revenue / count) if count else 0
    return {"revenue": revenue, "count": count, "portions": portions, "average": average}


def per_day(orders, start_date, end_date):
    days, d = [], start_date
    while d <= end_date:
        days.append(d)
        d += timedelta(days=1)
    data = {d: {"revenue": 0, "portions": 0, "orders": 0} for d in days}
    for o in orders:
        key = to_wib(o.created_at).date()
        if key in data:
            data[key]["revenue"] += o.total
            data[key]["portions"] += sum(i.quantity for i in o.items)
            data[key]["orders"] += 1
    return {
        "labels": [d.strftime("%d/%m") for d in days],
        "revenue": [data[d]["revenue"] for d in days],
        "portions": [data[d]["portions"] for d in days],
        "orders": [data[d]["orders"] for d in days],
    }


def per_hour(orders):
    revenue, portions = [0] * 24, [0] * 24
    for o in orders:
        h = to_wib(o.created_at).hour
        revenue[h] += o.total
        portions[h] += sum(i.quantity for i in o.items)
    return {"labels": [f"{h:02d}:00" for h in range(24)], "revenue": revenue, "portions": portions}


def top_menus(orders, limit=None):
    stats = {}
    for o in orders:
        for i in o.items:
            row = stats.setdefault(i.menu_id, {"name": i.menu_name, "qty": 0, "revenue": 0})
            row["name"] = i.menu_name
            row["qty"] += i.quantity
            row["revenue"] += i.unit_price * i.quantity
    ranked = sorted(stats.values(), key=lambda r: (-r["qty"], -r["revenue"], r["name"]))
    for n, row in enumerate(ranked, 1):
        row["rank"] = n
    return ranked[:limit] if limit else ranked


def pct_change(current, previous):
    if not previous:
        return None
    return (current - previous) / previous * 100
