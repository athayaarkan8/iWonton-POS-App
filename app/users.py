import hmac
import re
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.models import User
from app.utils import admin_only

users_bp = Blueprint("users", __name__, url_prefix="/admin/users")
ALLOWED_ROLES = {"admin", "kasir", "produksi"}
PER_PAGE = 10
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


def _csrf_token():
    token = session.get("user_admin_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["user_admin_csrf"] = token
    return token


def _validate_csrf():
    submitted = request.form.get("user_admin_csrf_token", "")
    expected = session.get("user_admin_csrf", "")
    if not expected or not submitted or not hmac.compare_digest(expected, submitted):
        abort(400, description="Token keamanan tidak valid. Muat ulang halaman lalu coba kembali.")


def _password_error(password):
    if len(password) < 8:
        return "Password minimal 8 karakter."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Password harus mengandung minimal satu huruf dan satu angka."
    return None


def _clean_profile():
    name = request.form.get("display_name", "").strip()
    username = request.form.get("username", "").strip()
    role = request.form.get("role", "").strip().lower()
    if not name or len(name) > 120:
        return None, "Nama lengkap wajib diisi (maksimal 120 karakter)."
    if not USERNAME_RE.fullmatch(username):
        return None, "Username wajib 3–30 karakter dan hanya boleh berisi huruf, angka, titik, garis bawah, atau tanda hubung."
    if role not in ALLOWED_ROLES:
        return None, "Role tidak valid. Pilih Admin, Kasir, atau Produksi."
    return {"display_name": name, "username": username, "role": role}, None


def _active_admin_count(exclude_user_id=None):
    query = User.query.filter_by(role="admin", is_active=True)
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.count()


@users_bp.route("/", methods=["GET"])
@login_required
@admin_only
def index():
    q = request.args.get("q", "").strip()[:80]
    role = request.args.get("role", "")
    status = request.args.get("status", "")
    query = User.query
    if q:
        pattern = "%" + q + "%"
        query = query.filter(or_(User.display_name.ilike(pattern),
                                 User.username.ilike(pattern)))
    if role in ALLOWED_ROLES:
        query = query.filter_by(role=role)
    else:
        role = ""
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)
    else:
        status = ""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    pagination = query.order_by(User.created_at.desc(), User.id.desc()).paginate(
        page=page, per_page=PER_PAGE, error_out=False
    )
    return render_template("users.html", pagination=pagination, q=q, role=role,
                           status=status, user_admin_csrf_token=_csrf_token(), roles=sorted(ALLOWED_ROLES))


@users_bp.route("/create", methods=["POST"])
@login_required
@admin_only
def create():
    _validate_csrf()
    data, error = _clean_profile()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    if error:
        flash(error, "danger")
    elif User.query.filter(func.lower(User.username) == data["username"].lower()).first():
        flash("Username tersebut sudah digunakan. Pilih username lain.", "danger")
    elif (password_error := _password_error(password)):
        flash(password_error, "danger")
    elif password != confirm:
        flash("Password dan konfirmasi password tidak sama.", "danger")
    else:
        user = User(**data, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Akun {user.username} berhasil dibuat.", "success")
    return redirect(url_for("users.index"))


@users_bp.route("/<int:user_id>/edit", methods=["POST"])
@login_required
@admin_only
def edit(user_id):
    _validate_csrf()
    user = db.get_or_404(User, user_id)
    data, error = _clean_profile()
    if error:
        flash(error, "danger")
    elif User.query.filter(func.lower(User.username) == data["username"].lower(), User.id != user.id).first():
        flash("Username tersebut sudah digunakan. Pilih username lain.", "danger")
    else:
        active_value = request.form.get("is_active", "1")
        if active_value not in {"0", "1"}:
            flash("Status akun tidak valid.", "danger")
            return redirect(url_for("users.index"))
        new_active = active_value == "1"
        if user.id == current_user.id and not new_active:
            flash("Kamu tidak dapat menonaktifkan akun yang sedang digunakan.", "danger")
        elif user.id == current_user.id and data["role"] != "admin":
            flash("Role akun yang sedang digunakan tidak dapat diubah dari Admin.", "danger")
        elif user.is_active and user.role == "admin" and (data["role"] != "admin" or not new_active) and _active_admin_count(user.id) == 0:
            flash("Perubahan ditolak karena sistem harus memiliki minimal satu Admin aktif.", "danger")
        else:
            user.display_name = data["display_name"]
            user.username = data["username"]
            user.role = data["role"]
            user.is_active = new_active
            db.session.commit()
            flash(f"Akun {user.username} berhasil diperbarui.", "success")
        return redirect(url_for("users.index"))
    return redirect(url_for("users.index"))


@users_bp.route("/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_only
def reset_password(user_id):
    _validate_csrf()
    user = db.get_or_404(User, user_id)
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    error = _password_error(password)
    if error:
        flash(error, "danger")
    elif password != confirm:
        flash("Password baru dan konfirmasi password tidak sama.", "danger")
    else:
        user.set_password(password)
        db.session.commit()
        flash(f"Password akun {user.username} berhasil direset.", "success")
    return redirect(url_for("users.index"))


@users_bp.route("/<int:user_id>/toggle-status", methods=["POST"])
@login_required
@admin_only
def toggle_status(user_id):
    _validate_csrf()
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id and user.is_active:
        flash("Kamu tidak dapat menonaktifkan akun yang sedang digunakan.", "danger")
    elif user.is_active and user.role == "admin" and _active_admin_count(user.id) == 0:
        flash("Akun tidak dapat dinonaktifkan karena sistem harus memiliki minimal satu Admin aktif.", "danger")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        state = "diaktifkan" if user.is_active else "dinonaktifkan"
        flash(f"Akun {user.username} berhasil {state}.", "success")
    return redirect(url_for("users.index"))
