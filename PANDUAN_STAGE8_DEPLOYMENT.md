# Wonton POS — Stage 8: Vercel + Neon PostgreSQL

## 1. Arsitektur dan batas biaya

- **Vercel** menjalankan Flask melalui Python runtime dan GitHub automatic deployments.
- **Neon PostgreSQL** menyimpan data production secara permanen.
- **GitHub** menjadi repository source code.
- SQLite tetap dipakai untuk development lokal.

Penting untuk usaha nyata: Vercel Hobby ($0) dibatasi untuk penggunaan personal/non-komersial. Wonton POS adalah aplikasi operasional usaha, sehingga penggunaan production untuk bisnis memerlukan Vercel Pro (harga daftar saat pemeriksaan: US$20/bulan). Jangan upgrade atau memasukkan kartu pembayaran tanpa persetujuan. Project ini dapat dipersiapkan dan diuji tanpa mengaktifkan paket berbayar, tetapi jangan deploy operasional bisnis di Hobby jika bertentangan dengan ketentuan Vercel.

Neon Free tersedia dengan kuota terbatas: 100 CU-hours per project per bulan, 1 GB storage per project, hingga 5 GB public network transfer per project per bulan, dan compute scale-to-zero setelah 5 menit idle. Jika kuota habis, compute dapat ditangguhkan sampai kuota reset atau paket berubah; data tidak otomatis dihapus. Periksa harga dan kuota terbaru sebelum penggunaan.

## 2. File deployment

- `index.py`: entrypoint Flask yang dikenali Vercel.
- `run.py`: tetap menjadi application factory launcher lokal.
- `requirements.txt`: dependency runtime Python.
- `.python-version`: Python 3.12.
- `migrations/`: migration Flask-Migrate/Alembic.
- Tidak ada `railway.toml` atau `Procfile`; keduanya khusus Railway dan tidak diperlukan Vercel.

Vercel mengenali Flask secara otomatis. Tidak perlu `vercel.json` khusus untuk routing dasar pada project ini. Flask menangani URL Blueprint dan static/template asset.

## 3. Jalankan lokal

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Buat secret lokal yang kuat:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Masukkan hasilnya ke `SECRET_KEY` di `.env`. Untuk lokal, `DATABASE_URL=sqlite:///wonton_pos.db`.

```powershell
flask --app run:app db upgrade
flask --app run:app create-admin
python run.py
```

## 4. GitHub

1. Buat repository baru di GitHub.
2. Extract project dan buka folder `wonton_pos_stage8`.
3. Pastikan `.env`, `instance/`, `*.db`, virtual environment, dan credential tidak ikut commit.
4. Jalankan `git status` untuk memeriksa file yang akan diunggah.
5. Commit dan push source code ke repository.

Jangan upload database lokal SQLite atau `.env` ke repository publik.

## 5. Buat Neon PostgreSQL

1. Buat akun di Neon dan buat project PostgreSQL.
2. Pilih region yang dekat dengan pengguna aplikasi jika tersedia.
3. Buka project → **Connect**.
4. Pilih database dan role.
5. Aktifkan **Connection pooling** untuk memperoleh pooled connection string (hostname biasanya mengandung `-pooler`).
6. Salin dua URL dengan aman:
   - **Pooled URL** untuk `DATABASE_URL` di Vercel, untuk request aplikasi.
   - **Direct URL** untuk `DIRECT_DATABASE_URL` lokal, untuk migration, backup, dan restore.
7. Jangan menaruh password di source code atau GitHub.

Pooled URL Neon memakai PgBouncer transaction pooling dan cocok untuk koneksi serverless/request. Direct URL dipakai untuk operasi administrasi seperti migration dan `pg_dump`. Jangan memakai direct connection untuk semua request serverless.

## 6. Konfigurasi Vercel

1. Login Vercel.
2. Pilih **Add New → Project**.
3. Import repository GitHub Wonton POS.
4. Biarkan Vercel mendeteksi Python/Flask; jangan menambahkan build command atau output directory tanpa kebutuhan.
5. Pada **Environment Variables**, tambahkan:
   - `SECRET_KEY`: secret acak panjang yang dibuat sendiri.
   - `DATABASE_URL`: Neon pooled connection string.
6. Pilih environment Production (dan Preview jika memang ingin menguji dengan database terpisah).
7. Deploy.

Vercel menetapkan `VERCEL=1` di runtime. Aplikasi akan menolak startup production bila `SECRET_KEY` atau `DATABASE_URL` hilang, atau database production masih SQLite.

## 7. Migration dan Admin pertama

Jangan menjalankan migration otomatis saat setiap request atau build preview. Jalankan migration secara manual dari komputer lokal yang dapat mengakses Neon menggunakan **direct URL**.

PowerShell:

```powershell
$env:DATABASE_URL = "PASTE_NEON_DIRECT_URL_DI_SINI"
flask --app run:app db upgrade
```

Buat Admin pertama setelah schema tersedia:

```powershell
flask --app run:app create-admin
```

Masukkan username, nama, dan password yang kuat saat diminta. Setelah selesai, hapus nilai environment dari sesi PowerShell:

```powershell
Remove-Item Env:DATABASE_URL
```

Untuk perubahan schema berikutnya:
1. Backup database.
2. Ubah model.
3. Buat migration: `flask --app run:app db migrate -m "deskripsi perubahan"`.
4. Tinjau file migration yang dihasilkan.
5. Terapkan ke Neon dengan direct URL: `flask --app run:app db upgrade`.
6. Deploy code yang sesuai.

Jangan menjalankan `db init` lagi; folder migration sudah tersedia. Jangan memakai `drop_all()`.

## 8. Memindahkan data Stage 7

ZIP Stage 7 yang diterima sebelumnya tidak menyertakan file database SQLite. Jika komputer lokal Anda memiliki database lama, backup dahulu file tersebut.

Untuk menyalin database lama ke Neon yang masih kosong, set:
- `SQLITE_DATABASE_URL=sqlite:///path/ke/wonton_pos.db`
- `DATABASE_URL=NEON_DIRECT_URL` (script migrasi data memakai koneksi langsung)

Kemudian jalankan sekali:

```powershell
$env:SQLITE_DATABASE_URL = "sqlite:///instance/wonton_pos.db"
$env:DATABASE_URL = "PASTE_NEON_DIRECT_URL_DI_SINI"
python scripts/copy_sqlite_to_postgres.py
```

Script menolak menyalin jika tabel tujuan yang terkait sudah berisi data. Jangan menjalankannya berulang pada database yang sudah terisi. Setelah copy, verifikasi jumlah User, Menu, Order, OrderItem, dan StockMovement. Pastikan backup SQLite asli tetap disimpan.

## 9. Session, koneksi, dan file

- Flask session memakai signed cookie dengan `SECRET_KEY`, sehingga tidak bergantung pada instance serverless yang sama.
- Cookie `HttpOnly`, `SameSite=Lax`, dan `Secure` aktif saat Vercel production.
- SQLAlchemy memakai pool kecil per instance (`pool_size=5`, `max_overflow=0`, `pool_pre_ping`, `pool_recycle`) untuk membatasi koneksi. Gunakan Neon pooled URL untuk request.
- Tidak ada fitur upload file pada project Stage 7 yang diaudit; object storage tidak ditambahkan.
- Jangan menyimpan file yang perlu permanen pada filesystem fungsi Vercel.

## 10. Backup dan restore

Backup sebelum migration menggunakan `pg_dump` dengan direct URL:

```powershell
$env:PGPASSWORD = "PASSWORD_DATABASE"
pg_dump --format=custom --no-owner --file=wonton-pos-backup.dump "NEON_DIRECT_URL"
Remove-Item Env:PGPASSWORD
```

Restore ke database target yang memang disiapkan untuk pemulihan:

```powershell
pg_restore --no-owner --dbname="NEON_DIRECT_URL_TARGET" wonton-pos-backup.dump
```

Jangan menambahkan `--clean` pada database operasional yang masih berisi data yang harus dipertahankan. Simpan backup di lokasi terpisah dan batasi akses. Backup otomatis tidak dikonfigurasi oleh project ini; periksa fitur snapshot/retensi pada paket Neon yang Anda pilih.

## 11. Checklist setelah deploy

- [ ] Vercel deployment berhasil dan URL publik terbuka.
- [ ] `/health` mengembalikan HTTP 200 dengan `status=ok` dan `database=ok`.
- [ ] Login, logout, dan session tetap berfungsi.
- [ ] Admin, Kasir, Produksi hanya mengakses route sesuai role.
- [ ] Tambah/edit menu dan stok.
- [ ] Buat order, cancel order, dan catatan.
- [ ] Produksi mulai dan selesaikan order.
- [ ] Pastikan stock deduction tidak ganda.
- [ ] Riwayat transaksi, filter, analytics, dan CSV.
- [ ] Waktu dan rekap sesuai WIB.
- [ ] Buat transaksi uji, redeploy, lalu pastikan data tetap ada.
- [ ] Uji dari laptop dan HP serta dua akun berbeda.

## 12. Batas verifikasi

ZIP ini dipersiapkan untuk Vercel + Neon, tetapi deployment ke akun Anda belum dilakukan. Belum diverifikasi: build Vercel, URL publik, koneksi Neon live, concurrency multi-device, dan end-to-end seluruh fitur. Jalankan checklist di atas sebelum digunakan untuk operasional.

Harga dan kuota layanan dapat berubah. Vercel Hobby adalah untuk penggunaan personal/non-komersial; penggunaan bisnis Wonton POS memerlukan paket yang sesuai. Jangan aktifkan paket berbayar tanpa persetujuan.
