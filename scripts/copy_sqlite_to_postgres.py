"""Copy existing Stage 7 SQLite records into an empty PostgreSQL database.

Set DATABASE_URL to the Neon PostgreSQL URL and SQLITE_DATABASE_URL to the
local SQLite URL. Back up both databases before running this one-time utility.
"""
import os
from sqlalchemy import create_engine, inspect, text
from app import db, create_app
from app import models  # register model metadata


def normalize(url):
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


source_url = os.environ.get("SQLITE_DATABASE_URL", "sqlite:///instance/wonton_pos.db")
target_url = normalize(os.environ["DATABASE_URL"])
if not source_url.startswith("sqlite:"):
    raise SystemExit("SQLITE_DATABASE_URL harus menunjuk ke database SQLite.")
if not target_url.startswith("postgresql+psycopg://"):
    raise SystemExit("DATABASE_URL harus menunjuk ke PostgreSQL.")

app = create_app()
source = create_engine(source_url)
target = create_engine(target_url, pool_pre_ping=True)

with app.app_context():
    db.metadata.create_all(target, checkfirst=True)
    source_inspector = inspect(source)
    source_tables = set(source_inspector.get_table_names())
    tables = [table for table in db.metadata.sorted_tables if table.name in source_tables]

    with target.begin() as conn:
        target_inspector = inspect(conn)
        for table in tables:
            if table.name in target_inspector.get_table_names():
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar_one()
                if count:
                    raise SystemExit(
                        f"Target tidak kosong: tabel {table.name} memiliki {count} baris. "
                        "Batalkan copy untuk mencegah duplikasi."
                    )

    copied = 0
    with source.connect() as src, target.begin() as dst:
        for table in tables:
            rows = src.execute(table.select()).mappings().all()
            if rows:
                dst.execute(table.insert(), [dict(row) for row in rows])
                copied += len(rows)

        if target.dialect.name == "postgresql":
            for table in tables:
                for column in table.columns:
                    if column.primary_key and column.autoincrement in (True, "auto"):
                        sequence = dst.execute(
                            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                            {"table_name": table.name, "column_name": column.name},
                        ).scalar_one_or_none()
                        if sequence:
                            dst.execute(
                                text("SELECT setval(CAST(:sequence AS regclass), COALESCE((SELECT MAX(" +
                                     '"' + column.name + '"' + ") FROM " +
                                     '"' + table.name + '"' + "), 1), "
                                     "EXISTS (SELECT 1 FROM " + '"' + table.name + '"' + "))"),
                                {"sequence": sequence},
                            )
    print(f"Selesai. {copied} baris disalin dari SQLite ke PostgreSQL.")
