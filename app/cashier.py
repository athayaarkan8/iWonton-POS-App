from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Menu, Order, OrderItem

cashier_bp = Blueprint("cashier", __name__, url_prefix="/cashier")

def cashier_or_admin():
    return current_user.role in ("kasir", "admin")

def reserved_for(menu_id):
    orders = Order.query.filter(Order.status.in_(["pending", "preparing"])).all()
    return sum(item.quantity for order in orders for item in order.items if item.menu_id == menu_id)

@cashier_bp.route("/")
@login_required
def index():
    if not cashier_or_admin():
        flash("Halaman kasir hanya bisa diakses Kasir atau Admin.", "danger")
        return redirect(url_for("main.dashboard"))
    menus=Menu.query.filter_by(is_active=True).order_by(Menu.name.asc()).all()
    available={m.id:max(0,m.stock-reserved_for(m.id)) for m in menus}
    order_query = Order.query
    if current_user.role == "kasir":
        order_query = order_query.filter_by(cashier_id=current_user.id)
    orders = order_query.order_by(Order.created_at.desc()).limit(30).all()
    return render_template("cashier.html",menus=menus,available=available,orders=orders)



@cashier_bp.route("/availability")
@login_required
def availability():
    if not cashier_or_admin():
        return jsonify({"error": "forbidden"}), 403
    menus = Menu.query.filter_by(is_active=True).all()
    return jsonify({
        str(menu.id): max(0, menu.stock - reserved_for(menu.id))
        for menu in menus
    })

@cashier_bp.route("/create",methods=["POST"])
@login_required
def create_order():
    if not cashier_or_admin():
        flash("Akses ditolak.","danger"); return redirect(url_for("main.dashboard"))
    menu_ids=Menu.query.filter_by(is_active=True).all()
    selections=[]
    total=0
    for menu in menu_ids:
        try: qty=int(request.form.get(f"qty_{menu.id}",0))
        except ValueError: qty=0
        note=request.form.get(f"note_{menu.id}","").strip()
        if qty<0:
            flash("Jumlah tidak boleh negatif.","danger"); return redirect(url_for("cashier.index"))
        if qty:
            available=menu.stock-reserved_for(menu.id)
            if qty>available:
                flash(f"Stok tersedia {menu.name} hanya {max(available,0)} porsi. Pesanan tidak dibuat.","danger")
                return redirect(url_for("cashier.index"))
            selections.append((menu,qty,note))
            total += menu.price*qty
    if not selections:
        flash("Pilih minimal satu menu untuk membuat pesanan.","warning")
        return redirect(url_for("cashier.index"))
    order=Order(order_number=f"ORD-{datetime.now().strftime('%y%m%d-%H%M%S')}-{current_user.id}",cashier_id=current_user.id,status="pending",total=total,customer_note=request.form.get("customer_note","").strip())
    db.session.add(order); db.session.flush()
    for menu,qty,note in selections:
        db.session.add(OrderItem(order_id=order.id,menu_id=menu.id,menu_name=menu.name,unit_price=menu.price,quantity=qty,item_note=note))
    db.session.commit()
    flash(f"Pesanan {order.order_number} berhasil dikirim ke antrean. Stok direservasi, belum dikurangi.","success")
    return redirect(url_for("cashier.index"))

@cashier_bp.route("/<int:order_id>/cancel",methods=["POST"])
@login_required
def cancel_order(order_id):
    if not cashier_or_admin():
        flash("Akses ditolak.","danger"); return redirect(url_for("main.dashboard"))
    order_query = Order.query.filter_by(id=order_id)
    if current_user.role == "kasir":
        order_query = order_query.filter_by(cashier_id=current_user.id)
    order = order_query.first_or_404()
    if order.status!="pending":
        flash("Pesanan hanya bisa dibatalkan saat masih menunggu.","warning")
    else:
        order.status="cancelled"
        db.session.commit()
        flash("Pesanan dibatalkan. Reservasi stok dilepas.","success")
    return redirect(url_for("cashier.index"))
