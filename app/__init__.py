import os

import click
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def _database_url(raw_url=None):
    url = (raw_url or os.environ.get("DATABASE_URL") or "sqlite:///wonton_pos.db").strip()
    # Cloud providers may provide postgres:// or postgresql:// URLs.
    # psycopg 3 is the explicit SQLAlchemy driver used in production.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def create_app(test_config=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    is_production = (
        os.environ.get("VERCEL") == "1"
        or os.environ.get("FLASK_ENV", "").lower() == "production"
    )

    secret_key = os.environ.get("SECRET_KEY")
    raw_database_url = os.environ.get("DATABASE_URL")
    if is_production and not (test_config and test_config.get("TESTING")):
        if not secret_key:
            raise RuntimeError("SECRET_KEY wajib diatur pada Environment Variables production.")
        if not raw_database_url:
            raise RuntimeError("DATABASE_URL wajib diatur ke PostgreSQL cloud pada production.")
    database_url = _database_url(raw_database_url)
    if is_production and database_url.startswith("sqlite:") and not (test_config and test_config.get("TESTING")):
        raise RuntimeError("SQLite tidak boleh digunakan sebagai database production.")

    engine_options = {"pool_pre_ping": True}
    if database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        # Each warm serverless instance keeps at most one DB connection.
        # Use Neon's pooled (-pooler) hostname for request traffic.
        engine_options.update(pool_size=5, max_overflow=0, pool_recycle=300, pool_timeout=10)

    app.config.update(
        SECRET_KEY=secret_key or "local-development-only-change-me",
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS=engine_options,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=is_production,
        SESSION_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SECURE=is_production,
        WTF_CSRF_TIME_LIMIT=3600,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Silakan login terlebih dahulu."
    login_manager.login_message_category = "warning"

    from app.models import User, Menu, StockMovement, Order, OrderItem
    from app.auth import auth_bp
    from app.main import main_bp
    from app.inventory import inventory_bp
    from app.cashier import cashier_bp
    from app.production import production_bp
    from app.reports import reports_bp
    from app.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(cashier_bp)
    app.register_blueprint(production_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(users_bp)

    from app.utils import rupiah, format_wib, format_pct, STATUS_LABELS, STATUS_BADGES
    app.jinja_env.filters["rupiah"] = rupiah
    app.jinja_env.filters["wib"] = format_wib
    app.jinja_env.filters["pct"] = format_pct
    app.jinja_env.globals["STATUS_LABELS"] = STATUS_LABELS
    app.jinja_env.globals["STATUS_BADGES"] = STATUS_BADGES

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user = db.session.get(User, int(user_id))
            return user if user and user.is_active else None
        except (TypeError, ValueError):
            return None

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="ok", database="ok"), 200
        except Exception:
            db.session.rollback()
            app.logger.exception("Health check database failure")
            return jsonify(status="unavailable"), 503

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled application error: %s", error)
        return "Terjadi kesalahan pada server. Silakan coba kembali.", 500

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--display-name", prompt="Nama Admin")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(username, display_name, password):
        """Buat akun Admin awal tanpa password default."""
        from app.models import User
        from sqlalchemy import func
        username = username.strip()
        display_name = display_name.strip()
        import re
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username):
            raise click.ClickException("Username wajib 3–30 karakter: huruf, angka, titik, garis bawah, atau tanda hubung.")
        if not display_name or len(display_name) > 120 or len(password) < 8:
            raise click.ClickException("Nama wajib diisi (maksimal 120 karakter) dan password minimal 8 karakter.")
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            raise click.ClickException("Username sudah digunakan.")
        user = User(username=username, display_name=display_name, role="admin", is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin '{username}' berhasil dibuat.")

    return app
