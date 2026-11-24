from datetime import datetime, date, time, timedelta
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

# Database menyimpan waktu dalam UTC (datetime.utcnow).
# WIB = UTC+7 dan Indonesia tidak memakai daylight saving, jadi cukup tambah 7 jam.
WIB_OFFSET = timedelta(hours=7)

STATUS_LABELS = {
    "pending": "Menunggu",
    "preparing": "Sedang dibuat",
    "completed": "Selesai",
    "cancelled": "Dibatalkan",
}
STATUS_BADGES = {
    "pending": "bg-warning-subtle text-warning-emphasis",
    "preparing": "bg-info-subtle text-info-emphasis",
    "completed": "bg-success-subtle text-success",
    "cancelled": "bg-secondary-subtle text-secondary",
}

PERIODS = [
    ("today", "Hari ini"),
    ("yesterday", "Kemarin"),
    ("7days", "7 hari terakhir"),
    ("month", "Bulan ini"),
    ("custom", "Pilih tanggal"),
]


def to_wib(dt):
    return dt + WIB_OFFSET if dt else None


def wib_today():
    return (datetime.utcnow() + WIB_OFFSET).date()


def wib_range_to_utc(start_date, end_date):
    """Tanggal WIB (inklusif) -> batas waktu UTC [awal, akhir) untuk query database."""
    utc_start = datetime.combine(start_date, time.min) - WIB_OFFSET
    utc_end = datetime.combine(end_date + timedelta(days=1), time.min) - WIB_OFFSET
    return utc_start, utc_end


def parse_iso_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_period(args, default="7days"):
    """Baca ?period=...&start=...&end=... lalu kembalikan (period, start, end, error)."""
    today = wib_today()
    period = args.get("period", default)
    error = None
    if period == "custom":
        start = parse_iso_date(args.get("start"))
        end = parse_iso_date(args.get("end"))
        if not start or not end:
            error = "Tanggal mulai dan selesai harus diisi dengan format yang benar."
        elif start > end:
            error = "Tanggal mulai tidak boleh lebih besar dari tanggal selesai."
        elif (end - start).days > 366:
            error = "Rentang tanggal maksimal 366 hari."
        if not error:
            return period, start, end, None
        period = default
    if period not in dict(PERIODS) or period == "custom":
        period = default
    if period == "today":
        start = end = today
    elif period == "yesterday":
        start = end = today - timedelta(days=1)
    elif period == "month":
        start, end = today.replace(day=1), today
    else:  # 7days
        period, start, end = "7days", today - timedelta(days=6), today
    return period, start, end, error


def admin_only(view):
    """Pembatasan di backend: selain Admin ditolak walaupun mengetik URL manual."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Halaman ini hanya bisa diakses Admin.", "danger")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)
    return wrapper


def rupiah(value):
    return "Rp" + "{:,}".format(int(value or 0)).replace(",", ".")


def format_wib(dt, fmt="%d/%m/%Y %H:%M"):
    return to_wib(dt).strftime(fmt) if dt else "-"


def format_pct(value):
    if value is None:
        return "-"
    return ("{:+.1f}".format(value)).replace(".", ",") + "%"
