# Wonton POS — Stage 8: Deployment & Production (Railway + PostgreSQL)

## 1. Hasil perubahan

- Flask tetap memakai struktur Blueprint dan model Stage 7.
- SQLite tetap menjadi default untuk development lokal.
- `DATABASE_URL` mendukung URL Railway `postgres://`, `postgresql://`, dan PostgreSQL dengan driver psycopg 3.
- Startup tidak lagi menjalankan `db.create_all()` dan tidak lagi membuat akun demo otomatis.
- Flask-Migrate/Alembic digunakan untuk migrasi schema. File konfigurasi Alembic tersedia di `migrations/alembic.ini` sesuai lokasi yang dicari Flask-Migrate.
- Gunicorn menjadi production web server.
- `/health` memeriksa aplikasi dan koneksi database tanpa mengembalikan credential.
- `SECRET_KEY` wajib diisi di production; cookie session HttpOnly, SameSite=Lax, Secure saat production.
- Flask-WTF CSRF protection dipasang pada form POST. Token CSRF internal halaman manajemen pengguna tetap dipertahankan terpisah.
- CLI `flask create-admin` membuat Admin pertama tanpa password default.
- `scripts/copy_sqlite_to_postgres.py` disediakan untuk menyalin data SQLite lama ke database PostgreSQL yang masih kosong.

## 2. Jalankan lokal

Dari folder project:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Salin `.env.example` menjadi `.env`, lalu isi `SECRET_KEY` dengan nilai acak. Contoh membuat secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Untuk development, `DATABASE_URL=sqlite:///wonton_pos.db` menggunakan database instance lokal Flask-SQLAlchemy. Jalankan migrasi dan buat Admin:

```bash
flask --app run:app db upgrade
flask --app run:app create-admin
python run.py
```

Buka `http://127.0.0.1:5000`. Jangan memakai `DEBUG=true` di production.

## 3. Siapkan GitHub

1. Buat repository GitHub baru.
2. Pastikan `.env` dan folder `instance/` tidak ikut di-commit. `.gitignore` sudah mengecualikan keduanya.
3. Periksa `git status` dan pastikan tidak ada database lokal, file `.env`, secret, atau credential.
4. Commit seluruh source code Stage 8 lalu push ke repository.
5. Jangan mengunggah file database SQLite ke repository publik.

## 4. Buat layanan Railway

1. Login ke Railway dan buat project baru.
2. Tambahkan service PostgreSQL melalui menu **New** / **Database** / **PostgreSQL** (label menu dapat berubah).
3. Tambahkan service aplikasi dari repository GitHub Wonton POS.
4. Pada service aplikasi, buka **Variables** dan tambahkan:
   - `SECRET_KEY`: hasil `secrets.token_urlsafe(48)` yang dibuat sendiri.
   - `DATABASE_URL`: gunakan reference variable PostgreSQL dari service database Railway, biasanya tersedia sebagai `${{Postgres.DATABASE_URL }}`. Pilih variable yang benar dari service PostgreSQL Anda.
   - `FLASK_ENV`: `production`.
   - `DEBUG`: `false`.
5. Pastikan `DATABASE_URL` adalah variable dari service PostgreSQL Railway, bukan URL SQLite lokal.
6. File `railway.toml` menentukan Gunicorn start command, health check `/health`, dan menjalankan `flask db upgrade` sebagai pre-deploy command.
7. Deploy service aplikasi. Lihat **Deployments** dan **Logs** jika build atau start gagal.

Tidak ada akses ke akun Railway/GitHub pengguna dari proses pembuatan ZIP ini. URL publik dan deployment belum dibuat atau diverifikasi.

## 5. Migrasi database dan data lama

### Database baru/kosong

`railway.toml` menjalankan:

```bash
flask --app run:app db upgrade
```

Migrasi baseline membuat tabel yang belum ada dan tidak menghapus tabel/data yang sudah ada. Migrasi berikutnya dibuat dan ditinjau dengan:

```bash
flask --app run:app db migrate -m "deskripsi perubahan"
flask --app run:app db upgrade
```

Selalu backup database sebelum menjalankan migrasi produksi.

### Jika database SQLite Stage 7 berisi data yang ingin dipertahankan

ZIP Stage 7 yang diterima tidak menyertakan file database SQLite. Karena itu, isi database lokal tidak dapat otomatis ikut dipindahkan hanya dari ZIP.

1. Temukan file database lokal Stage 7, biasanya `instance/wonton_pos.db`.
2. Buat backup salinan file tersebut.
3. Pastikan PostgreSQL Railway sudah tersedia dan masih kosong.
4. Setelah `DATABASE_URL` Railway tersedia di environment shell, jalankan skrip migrasi satu kali:

```bash
# Windows PowerShell; contoh URL sumber, sesuaikan lokasi file:
$env:SQLITE_DATABASE_URL="sqlite:///instance/wonton_pos.db"
python scripts/copy_sqlite_to_postgres.py
```

`DATABASE_URL` harus menunjuk ke PostgreSQL tujuan. Skrip menolak menyalin jika tabel tujuan sudah berisi baris untuk mencegah duplikasi. Jalankan skrip dari environment yang dapat menjangkau PostgreSQL tersebut. Jika database Railway hanya dapat diakses melalui jaringan privat, jalankan proses dari lingkungan/shell yang memiliki akses jaringan tersebut.

Skrip menyalin data dan ID dari tabel model yang tersedia serta menyesuaikan sequence PostgreSQL. Tetap lakukan verifikasi jumlah akun, menu, order, order item, dan stock movement setelah penyalinan. Jangan menjalankan proses copy berulang pada database berisi data.

## 6. Admin pertama dan akun demo lama

Pada database baru, buat Admin melalui:

```bash
flask --app run:app create-admin
```

Masukkan username, nama Admin, dan password saat diminta. Password tidak perlu ditulis ke source code atau repository.

Akun demo `admin`, `kasir`, dan `produksi` dengan password `wonton123` tidak lagi dibuat otomatis pada database baru. Jika database Stage 7 lama sudah memiliki akun demo tersebut, akun tidak dihapus oleh migrasi. Sebelum aplikasi dibuka untuk publik, login sebagai Admin dan reset password akun yang dipakai, nonaktifkan akun demo yang tidak diperlukan, serta pastikan minimal satu Admin aktif.

## 7. Backup dan restore PostgreSQL

Gunakan `pg_dump` untuk backup sebelum migrasi atau perubahan besar:

```bash
pg_dump "$DATABASE_URL" --format=custom --file=wonton-pos-backup.dump
```

Restore ke database tujuan yang sesuai:

```bash
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" wonton-pos-backup.dump
```

`--clean` menghapus objek target yang namanya sama sebelum restore. Gunakan hanya pada database tujuan yang memang akan dipulihkan/ditimpa, bukan database operasional yang masih berisi data yang ingin dipertahankan. Untuk backup aman, simpan file backup di lokasi terpisah dan batasi aksesnya. Backup otomatis tidak dikonfigurasi oleh project ini; periksa fitur backup/snapshot dan retensi yang tersedia pada paket Railway Anda.

Jika deployment gagal:
1. Baca Railway build/deploy logs.
2. Jangan menghapus PostgreSQL service atau volume.
3. Jika kegagalan terkait migrasi, periksa backup dan error migrasi sebelum mencoba ulang.
4. Rollback aplikasi ke deployment sebelumnya bila perlu; rollback kode tidak otomatis membatalkan perubahan schema.
5. Restore backup hanya setelah memastikan database target dan konsekuensi overwrite.

## 8. Verifikasi setelah deploy

- Buka `https://<domain-railway-anda>/health`. Respons sehat: HTTP 200 dengan `status=ok` dan `database=ok`.
- Login menggunakan Admin yang dibuat.
- Buat akun Kasir dan Produksi dari menu manajemen pengguna.
- Uji login/logout, hak akses per role, menu, stok, stock opname, pembuatan/pembatalan order, antrean produksi, penyelesaian order, riwayat transaksi, analytics, dan export CSV.
- Uji dari dua perangkat/browser berbeda.
- Buat transaksi uji, restart/redeploy aplikasi, lalu pastikan transaksi tetap ada.
- Pastikan waktu laporan dan transaksi sesuai WIB (Asia/Jakarta).

## 9. Catatan operasional dan batas verifikasi

- PostgreSQL menyimpan timestamp model sebagai datetime tanpa timezone dengan konvensi UTC yang sudah dipakai Stage 7; tampilan dan filter laporan tetap mengonversi ke WIB (UTC+7).
- Aplikasi Stage 7 belum memiliki fitur upload file, jadi Stage 8 tidak menambahkan layanan object storage atau biaya storage.
- Railway deployment, URL publik, PostgreSQL live, backup otomatis, dan pengujian multi-device belum dapat diverifikasi dari environment ini.
- Dependency baru ditambahkan ke `requirements.txt`, tetapi instalasi dan runtime test tidak dapat dilakukan di sesi build ini karena akses jaringan package index tidak tersedia.
- Lakukan backup database lama sebelum mengubah environment, dan jangan pernah menjalankan `drop_all()` pada database operasional.
