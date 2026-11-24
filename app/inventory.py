from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Menu, StockMovement, Order, OrderItem

inventory_bp = Blueprint("inventory", __name__, url_prefix="/admin")
def admin_required():
    if current_user.role != "admin":
        flash("Halaman ini hanya bisa diakses Admin.", "danger")
        return False
    return True

def reserved_quantity(menu_id):
    active_orders = Order.query.filter(Order.status.in_(["pending", "preparing"])).all()
    return sum(item.quantity for order in active_orders for item in order.items if item.menu_id == menu_id)

@inventory_bp.route("/menus")
@login_required
def menus():
    if not admin_required(): return redirect(url_for("main.dashboard"))
    return render_template("menus.html", menus=Menu.query.order_by(Menu.name.asc()).all())

@inventory_bp.route("/menus/add", methods=["POST"])
@login_required
def add_menu():
    if not admin_required(): return redirect(url_for("main.dashboard"))
    name=request.form.get("name","").strip()
    try: price=int(request.form.get("price",0)); stock=int(request.form.get("stock",0)); minimum=int(request.form.get("minimum_stock",0))
    except ValueError:
        flash("Harga dan stok harus angka.", "danger"); return redirect(url_for("inventory.menus"))
    if not name or min(price,stock,minimum)<0:
        flash("Data menu tidak valid.", "danger"); return redirect(url_for("inventory.menus"))
    menu=Menu(name=name,description=request.form.get("description","").strip(),price=price,stock=stock,minimum_stock=minimum)
    db.session.add(menu); db.session.flush()
    if stock: db.session.add(StockMovement(menu_id=menu.id,user_id=current_user.id,movement_type="initial",quantity_change=stock,stock_before=0,stock_after=stock,note="Stok awal saat menu dibuat"))
    db.session.commit(); flash(f"Menu {name} berhasil ditambahkan.","success")
    return redirect(url_for("inventory.menus"))

@inventory_bp.route("/menus/<int:menu_id>/edit", methods=["POST"])
@login_required
def edit_menu(menu_id):
    if not admin_required(): return redirect(url_for("main.dashboard"))
    menu=db.get_or_404(Menu,menu_id)
    try: price=int(request.form.get("price",0)); minimum=int(request.form.get("minimum_stock",0))
    except ValueError:
        flash("Harga dan batas stok harus angka.","danger"); return redirect(url_for("inventory.menus"))
    name=request.form.get("name","").strip()
    if not name or min(price,minimum)<0:
        flash("Data menu tidak valid.","danger"); return redirect(url_for("inventory.menus"))
    menu.name=name; menu.description=request.form.get("description","").strip(); menu.price=price; menu.minimum_stock=minimum; menu.is_active=request.form.get("is_active")=="on"
    db.session.commit(); flash("Menu berhasil diperbarui.","success")
    return redirect(url_for("inventory.menus"))

@inventory_bp.route("/stock")
@login_required
def stock():
    if not admin_required(): return redirect(url_for("main.dashboard"))
    items=Menu.query.order_by(Menu.name.asc()).all()
    reserved={m.id:reserved_quantity(m.id) for m in items}
    return render_template("stock.html",menus=items,reserved=reserved)

@inventory_bp.route("/stock/movement", methods=["POST"])
@login_required
def movement():
    if not admin_required(): return redirect(url_for("main.dashboard"))
    menu=db.get_or_404(Menu,int(request.form.get("menu_id",0)))
    try: quantity=int(request.form.get("quantity",0))
    except ValueError: quantity=0
    if quantity<=0:
        flash("Jumlah tambahan harus lebih dari 0.","danger"); return redirect(url_for("inventory.stock"))
    before=menu.stock; menu.stock+=quantity
    db.session.add(StockMovement(menu_id=menu.id,user_id=current_user.id,movement_type="addition",quantity_change=quantity,stock_before=before,stock_after=menu.stock,note=request.form.get("note","").strip() or "Penambahan stok"))
    db.session.commit(); flash(f"Stok {menu.name} ditambah {quantity}.","success")
    return redirect(url_for("inventory.stock"))

@inventory_bp.route("/stocktake", methods=["POST"])
@login_required
def stocktake():
    if not admin_required(): return redirect(url_for("main.dashboard"))
    menu=db.get_or_404(Menu,int(request.form.get("menu_id",0)))
    try: actual=int(request.form.get("actual_stock",-1))
    except ValueError: actual=-1
    reserved=reserved_quantity(menu.id)
    if actual<reserved:
        flash(f"Stok aktual tidak boleh lebih kecil dari {reserved} porsi yang sedang dipesan.","danger")
        return redirect(url_for("inventory.stock"))
    if actual<0:
        flash("Stok aktual tidak valid.","danger"); return redirect(url_for("inventory.stock"))
    before=menu.stock; delta=actual-before; menu.stock=actual
    db.session.add(StockMovement(menu_id=menu.id,user_id=current_user.id,movement_type="stocktake",quantity_change=delta,stock_before=before,stock_after=actual,note=request.form.get("note","").strip() or "Stok opname"))
    db.session.commit(); flash(f"Stok opname selesai. Selisih: {delta:+d}.","success")
    return redirect(url_for("inventory.stock"))

@inventory_bp.route("/stock/history")
@login_required
def history():
    if not admin_required(): return redirect(url_for("main.dashboard"))
    return render_template("stock_history.html",movements=StockMovement.query.order_by(StockMovement.created_at.desc()).limit(300).all())
