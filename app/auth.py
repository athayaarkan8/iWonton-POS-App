from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from app.models import User

auth_bp = Blueprint("auth", __name__)
@auth_bp.route("/", methods=["GET"])
def login():
    if current_user.is_authenticated: return redirect(url_for("main.dashboard"))
    return render_template("login.html")
@auth_bp.route("/login", methods=["POST"])
def login_post():
    user = User.query.filter_by(username=request.form.get("username","").strip()).first()
    if user and user.is_active and user.check_password(request.form.get("password","")):
        login_user(user)
        flash(f"Selamat datang, {user.display_name}!", "success")
        return redirect(url_for("main.dashboard"))
    flash("Username/password salah atau akun sedang nonaktif.", "danger")
    return redirect(url_for("auth.login"))
@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("Kamu sudah logout.", "info")
    return redirect(url_for("auth.login"))
