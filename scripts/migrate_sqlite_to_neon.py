import os
import sqlite3
from datetime import datetime, date, time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, MetaData, Table, insert, text
from sqlalchemy.sql.sqltypes import Boolean, DateTime, Date, Time


# ============================================================
# KONFIGURASI
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_PATH = BASE_DIR / "instance" / "wonton_pos.db"
BACKUP_PATH = BASE_DIR / "instance" / "wonton_pos_backup.db"

TABLES = [
    "user",
    "menu",
    "stock_movement",
    "order",
    "order_item",
]

# Load .env dari folder utama project
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL tidak ditemukan di .env")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )


# ============================================================
# VALIDASI FILE
# ============================================================

if not SQLITE_PATH.exists():
    raise FileNotFoundError(f"Database SQLite tidak ditemukan: {SQLITE_PATH}")

if not BACKUP_PATH.exists():
    raise FileNotFoundError(f"Backup tidak ditemukan: {BACKUP_PATH}")

print("=" * 60)
print("MIGRASI DATA WONTON POS: SQLITE -> NEON")
print("=" * 60)

print(f"SQLite  : {SQLITE_PATH}")
print(f"Backup  : {BACKUP_PATH}")
print("Target  : PostgreSQL Neon")
print()


# ============================================================
# HELPER KONVERSI TIPE DATA
# ============================================================

def convert_value(value, column_type):
    if value is None:
        return None

    if isinstance(column_type, Boolean):
        return bool(value)

    if isinstance(column_type, DateTime):
        if isinstance(value, datetime):
            return value

        return datetime.fromisoformat(str(value))

    if isinstance(column_type, Date):
        if isinstance(value, date):
            return value

        return date.fromisoformat(str(value))

    if isinstance(column_type, Time):
        if isinstance(value, time):
            return value

        return time.fromisoformat(str(value))

    return value


# ============================================================
# KONEKSI
# ============================================================

sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

try:
    pg_inspector = inspect(engine)

    pg_tables = pg_inspector.get_table_names()

    missing_tables = [
        table for table in TABLES
        if table not in pg_tables
    ]

    if missing_tables:
        raise RuntimeError(
            f"Tabel Neon belum tersedia: {missing_tables}"
        )

    metadata = MetaData()

    pg_metadata = MetaData()

    for table_name in TABLES:
        Table(
            table_name,
            pg_metadata,
            autoload_with=engine,
        )

    # ========================================================
    # CEK DATABASE TUJUAN HARUS KOSONG
    # ========================================================

    print("=== PEMERIKSAAN DATABASE NEON ===")

    with engine.connect() as conn:
        existing_counts = {}

        for table_name in TABLES:
            count = conn.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}"')
            ).scalar()

            existing_counts[table_name] = count

            print(f"{table_name}: {count}")

    if any(count != 0 for count in existing_counts.values()):
        raise RuntimeError(
            "\nDIBATALKAN: Database Neon sudah memiliki data. "
            "Script tidak akan menimpa atau menggabungkan data."
        )

    # ========================================================
    # CEK STRUKTUR SOURCE DAN TARGET
    # ========================================================

    print("\n=== PEMERIKSAAN STRUKTUR ===")

    source_columns = {}
    target_tables = {}

    for table_name in TABLES:
        cursor = sqlite_conn.execute(
            f'PRAGMA table_info("{table_name}")'
        )

        source_columns[table_name] = {
            row["name"]
            for row in cursor.fetchall()
        }

        target_table = Table(
            table_name,
            metadata,
            autoload_with=engine,
        )

        target_tables[table_name] = target_table

        target_columns = {
            column.name
            for column in target_table.columns
        }

        if source_columns[table_name] != target_columns:
            raise RuntimeError(
                f"\nStruktur kolom tidak cocok: {table_name}\n"
                f"SQLite : {source_columns[table_name]}\n"
                f"Neon   : {target_columns}"
            )

        print(f"{table_name}: cocok")

    # ========================================================
    # BACA DATA SQLITE
    # ========================================================

    source_data = {}
    expected_counts = {}

    print("\n=== DATA SUMBER ===")

    for table_name in TABLES:
        cursor = sqlite_conn.execute(
            f'SELECT * FROM "{table_name}"'
        )

        rows = [
            dict(row)
            for row in cursor.fetchall()
        ]

        source_data[table_name] = rows
        expected_counts[table_name] = len(rows)

        print(f"{table_name}: {len(rows)} record")

    # ========================================================
    # TRANSFER DATA
    # ========================================================

    print("\n=== MEMINDAHKAN DATA ===")

    with engine.begin() as conn:

        for table_name in TABLES:
            rows = source_data[table_name]

            if not rows:
                print(f"{table_name}: dilewati (kosong)")
                continue

            target_table = target_tables[table_name]

            converted_rows = []

            for row in rows:
                converted_row = {}

                for column in target_table.columns:
                    column_name = column.name

                    converted_row[column_name] = convert_value(
                        row[column_name],
                        column.type,
                    )

                converted_rows.append(converted_row)

            conn.execute(
                insert(target_table),
                converted_rows,
            )

            print(
                f"{table_name}: "
                f"{len(converted_rows)} record berhasil dimasukkan"
            )

        # ====================================================
        # RESET SEQUENCE ID POSTGRESQL
        # ====================================================

        print("\n=== RESET ID SEQUENCE ===")

        for table_name in TABLES:

            max_id = conn.execute(
                text(f'SELECT MAX(id) FROM "{table_name}"')
            ).scalar()

            if max_id is None:
                continue

            sequence_name = conn.execute(
                text(
                    "SELECT pg_get_serial_sequence(:table_name, 'id')"
                ),
                {
                    "table_name": f'"{table_name}"'
                },
            ).scalar()

            if sequence_name:
                conn.execute(
                    text(
                        "SELECT setval(CAST(:sequence_name AS regclass), :max_id, true)"
                    ),
                    {
                        "sequence_name": sequence_name,
                        "max_id": max_id,
                    },
                )

                print(
                    f"{table_name}: sequence disesuaikan ke {max_id}"
                )

        # ====================================================
        # VERIFIKASI DALAM TRANSAKSI
        # ====================================================

        print("\n=== VERIFIKASI DATA NEON ===")

        for table_name in TABLES:

            actual_count = conn.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}"')
            ).scalar()

            expected_count = expected_counts[table_name]

            print(
                f"{table_name}: "
                f"SQLite={expected_count}, Neon={actual_count}"
            )

            if actual_count != expected_count:
                raise RuntimeError(
                    f"Jumlah data tidak cocok pada {table_name}"
                )

    print("\n" + "=" * 60)
    print("MIGRASI BERHASIL!")
    print("Seluruh data telah dipindahkan dan diverifikasi.")
    print("Database SQLite lokal tidak diubah.")
    print("=" * 60)

finally:
    sqlite_conn.close()
    engine.dispose()