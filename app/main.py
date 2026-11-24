from datetime import timedelta
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import Menu, Order
from app.analytics import completed_orders, summarize, per_hour, per_day, top_menus, pct_change
from app.utils import wib_today

main_bp = Blueprint("main", __name__)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.role != "admin":
        # Kasir & Produksi tidak menerima data keuangan sama sekali.
        return render_template("dashboard.html", role=current_user.role)
    today = wib_today()
    yesterday = today - timedelta(days=1)
    today_orders = completed_orders(today, today)
    today_sum = summarize(today_orders)
    yesterday_sum = summarize(completed_orders(yesterday, yesterday))
    week_orders = completed_orders(today - timedelta(days=6), today)
    chart = {"hours": per_hour(today_orders), "days": per_day(week_orders, today - timedelta(days=6), today)}
    return render_template(
        "dashboard.html", role="admin", today=today_sum, yesterday=yesterday_sum,
        change=pct_change(today_sum["revenue"], yesterday_sum["revenue"]),
        running_orders=Order.query.filter(Order.status.in_(["pending", "preparing"])).count(),
        low_stock_count=Menu.query.filter(Menu.is_active == True, Menu.stock <= Menu.minimum_stock).count(),
        top_today=top_menus(today_orders, 3), chart=chart)
