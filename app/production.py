from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import update
from app import db
from app.models import Order, Menu, StockMovement

production_bp = Blueprint("production", __name__, url_prefix="/production")

def production_or_admin():
    return current_user.role in ("produksi", "admin")

@production_bp.route("/")
@login_required
def index():
    if not production_or_admin():
        flash("Dashboard produksi hanya bisa diakses Tim Produksi atau Admin.", "danger")
        return redirect(url_for("main.dashboard"))
    waiting = Order.query.filter_by(status="pending").order_by(Order.created_at.asc()).all()
    preparing = Order.query.filter_by(status="preparing").order_by(Order.created_at.asc()).all()
    completed = Order.query.filter_by(status="completed").order_by(Order.created_at.desc()).limit(30).all()
    return render_template("production.html", waiting=waiting, preparing=preparing, completed=completed)

@production_bp.route("/<int:order_id>/start", methods=["POST"])
@login_required
def start_order(order_id):
    if not production_or_admin():
        flash("Akses ditolak.", "danger")
        return redirect(url_for("main.dashboard"))
    result = db.session.execute(
        update(Order).where(Order.id == order_id, Order.status == "pending")
        .values(status="preparing").execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        db.session.commit()
        flash("Pesanan masuk ke Sedang Dibuat.", "success")
    else:
        db.session.rollback()
        flash("Pesanan sudah berubah status atau tidak ditemukan.", "warning")
    return redirect(url_for("production.index"))

@production_bp.route("/<int:order_id>/complete", methods=["POST"])
@login_required
def complete_order(order_id):
    if not production_or_admin():
        flash("Akses ditolak.", "danger")
        return redirect(url_for("main.dashboard"))
    try:
        # Only one request can claim a preparing order; stock + logs are one transaction.
        result = db.session.execute(
            update(Order).where(Order.id == order_id, Order.status == "preparing")
            .values(status="completed").execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.session.rollback()
            flash("Pesanan sudah selesai, belum mulai, atau tidak ditemukan. Stok tidak diubah.", "warning")
            return redirect(url_for("production.index"))
        order = db.session.get(Order, order_id)
        for item in order.items:
            menu = db.session.get(Menu, item.menu_id)
            if menu is None:
                raise ValueError(f"Menu untuk {item.menu_name} tidak ditemukan.")
            if menu.stock < item.quantity:
                raise ValueError(f"Stok {menu.name} tidak cukup: tersedia fisik {menu.stock}, dibutuhkan {item.quantity}.")
            before = menu.stock
            menu.stock -= item.quantity
            db.session.add(StockMovement(
                menu_id=menu.id, user_id=current_user.id, movement_type="sale",
                quantity_change=-item.quantity, stock_before=before, stock_after=menu.stock,
                note=f"Penjualan {order.order_number}"
            ))
        db.session.commit()
        flash(f"{order.order_number} selesai. Stok fisik dan riwayat stok berhasil diperbarui.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Pesanan belum dapat diselesaikan: {exc}", "danger")
    return redirect(url_for("production.index"))
