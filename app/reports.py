import csv
import io
from datetime import timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from app import db
from app.models import Order, User
from app.analytics import completed_orders, summarize, per_day, per_hour, top_menus
from app.utils import (admin_only, resolve_period, parse_iso_date, wib_range_to_utc, to_wib,
                       STATUS_LABELS, wib_today)

reports_bp = Blueprint("reports", __name__, url_prefix="/admin")
PER_PAGE = 20


@reports_bp.route("/reports")
@login_required
@admin_only
def reports():
    period, start, end, error = resolve_period(request.args, default="7days")
    if error:
        flash(error, "warning")
    orders = completed_orders(start, end)
    days = per_day(orders, start, end)
    menus = top_menus(orders)
    chart = {
        "days": days,
        "hours": per_hour(orders),
        "menus": {"labels": [m["name"] for m in menus[:8]], "qty": [m["qty"] for m in menus[:8]]},
    }
    return render_template("reports.html", period=period, start=start, end=end,
                           summary=summarize(orders), menus=menus, chart=chart)


def _parse_filters(args):
    status = args.get("status", "")
    if status not in STATUS_LABELS:
        status = ""
    start = parse_iso_date(args.get("start"))
    end = parse_iso_date(args.get("end"))
    error = None
    if args.get("start") and not start or args.get("end") and not end:
        error = "Format tanggal tidak valid."
        start = end = None
    if start and not end:
        end = start          # hanya satu tanggal diisi -> tampilkan tanggal itu saja
    if end and not start:
        start = end
    if start and end and start > end:
        error = "Tanggal mulai tidak boleh lebih besar dari tanggal selesai."
        start = end = None
    return {"q": args.get("q", "").strip()[:60], "status": status, "start": start, "end": end}, error


def _transaction_query(f):
    query = Order.query.join(User, Order.cashier_id == User.id)
    if f["status"]:
        query = query.filter(Order.status == f["status"])
    if f["q"]:
        safe = f["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{safe}%"
        query = query.filter(or_(Order.order_number.ilike(like, escape="\\"),
                                 User.display_name.ilike(like, escape="\\"),
                                 User.username.ilike(like, escape="\\")))
    if f["start"] and f["end"]:
        utc_start, utc_end = wib_range_to_utc(f["start"], f["end"])
        query = query.filter(Order.created_at >= utc_start, Order.created_at < utc_end)
    return query.order_by(Order.created_at.desc(), Order.id.desc())


@reports_bp.route("/transactions")
@login_required
@admin_only
def transactions():
    f, error = _parse_filters(request.args)
    if error:
        flash(error, "warning")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    pagination = (_transaction_query(f).options(selectinload(Order.items))
                  .paginate(page=page, per_page=PER_PAGE, error_out=False))
    return render_template("transactions.html", pagination=pagination, f=f, statuses=STATUS_LABELS)


@reports_bp.route("/transactions/<int:order_id>")
@login_required
@admin_only
def transaction_detail(order_id):
    order = db.get_or_404(Order, order_id)
    return render_template("transaction_detail.html", order=order)


def _safe(value):
    """Cegah CSV injection: teks yang diawali = + - @ diberi tanda petik di depan."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _csv_response(header, rows, filename):
    sep = "," if request.args.get("sep") == "comma" else ";"   # Excel Indonesia memakai titik koma
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep)
    writer.writerow(header)
    writer.writerows(rows)
    data = "\ufeff" + buf.getvalue()                            # BOM agar Excel membaca UTF-8
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def _export_orders():
    f, _ = _parse_filters(request.args)
    return _transaction_query(f).options(selectinload(Order.items)).all()


@reports_bp.route("/export/transactions.csv")
@login_required
@admin_only
def export_transactions():
    rows = []
    for o in _export_orders():
        t = to_wib(o.created_at)
        rows.append([o.order_number, t.strftime("%Y-%m-%d"), t.strftime("%H:%M"), _safe(o.cashier.display_name),
                     sum(i.quantity for i in o.items), o.total,
                     o.total if o.status == "completed" else 0, STATUS_LABELS.get(o.status, o.status)])
    header = ["Nomor Transaksi", "Tanggal", "Jam", "Kasir", "Jumlah Item", "Total Pembayaran", "Omzet Dihitung", "Status"]
    return _csv_response(header, rows, f"transaksi_{wib_today().isoformat()}.csv")


@reports_bp.route("/export/items.csv")
@login_required
@admin_only
def export_items():
    rows = []
    for o in _export_orders():
        t = to_wib(o.created_at)
        for i in o.items:
            rows.append([o.order_number, t.strftime("%Y-%m-%d"), t.strftime("%H:%M"), _safe(o.cashier.display_name),
                         STATUS_LABELS.get(o.status, o.status), _safe(i.menu_name), i.quantity, i.unit_price,
                         i.unit_price * i.quantity, _safe(i.item_note), _safe(o.customer_note)])
    header = ["Nomor Transaksi", "Tanggal", "Jam", "Kasir", "Status", "Menu", "Jumlah", "Harga Satuan",
              "Subtotal", "Catatan Item", "Catatan Order"]
    return _csv_response(header, rows, f"detail_item_{wib_today().isoformat()}.csv")
