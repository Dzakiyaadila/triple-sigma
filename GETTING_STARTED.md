# RestockIQ — Cara Menjalankan Project

Panduan ini menjelaskan cara menjalankan RestockIQ dari awal di mesin lokal, mencakup database, backend, frontend, pengujian, dan alur aplikasi.

---

## Prasyarat

- Python 3.12 direkomendasikan
- Node.js dan npm
- PostgreSQL 15 atau lebih baru
- Git

Untuk macOS, PostgreSQL dapat dipasang melalui Homebrew:

```bash
brew install postgresql@15
brew services start postgresql@15
```

Versi PostgreSQL yang lebih baru juga dapat digunakan selama server aktif dan dapat menerima koneksi pada port `5432`.

---

## Langkah 1 — Clone repository

```bash
git clone <url-repo-restockiq>
cd triple-sigma
```

---

## Langkah 2 — Setup backend

Masuk ke direktori backend:

```bash
cd backend
```

Buat dan aktifkan virtual environment:

```bash
python3.12 -m venv venv
source venv/bin/activate
```

Pastikan versi Python yang aktif benar:

```bash
python --version
```

Install dependencies:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Salin konfigurasi environment:

```bash
cp .env.example .env
```

Isi `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://localhost:5432/restockiq
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000,http://localhost:8080
```

Project frontend saat ini umumnya berjalan pada port `8080`. Tetap periksa URL yang ditampilkan oleh Vite dan tambahkan origin tersebut ke `ALLOWED_ORIGINS` bila berbeda.

### Membuat dan mengisi database

Pastikan PostgreSQL aktif:

```bash
pg_isready
```

Buat database apabila belum tersedia:

```bash
createdb restockiq
```

Jika muncul pesan bahwa database sudah ada, langkah tersebut dapatpg_isready
```

Buat database apabila belum tersedia:

```bash
createdb dilewati.

Jalankan proses seed satu kali:

```bash
python -m app.db.seed
```

Harus muncul konfirmasi bahwa enam tabel dataset utama berhasil dimuat, seperti:

```text
Dim_Stores → dim_stores: 5 baris
Dim_Products → dim_products: 31 baris
Dim_Suppliers → dim_suppliers: 6 baris
...
```

Database aplikasi dapat memiliki tabel tambahan untuk menyimpan decision run dan recommendation.

### Menjalankan backend

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Cek:

```text
http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Dokumentasi API tersedia di:

```text
http://localhost:8000/docs
```

Biarkan terminal backend tetap terbuka.

---

## Langkah 3 — Setup frontend

Buka terminal baru, lalu dari root repository:

```bash
cd frontend
```

Jika `package-lock.json` tersedia, gunakan:

```bash
npm ci
```

Jika tidak tersedia, gunakan:

```bash
npm install
```

Salin konfigurasi environment:

```bash
cp .env.example .env
```

Isi `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000/api/v2
```

Jalankan frontend:

```bash
npm run dev
```

Periksa output terminal untuk mengetahui port aktual:

```text
Local: http://localhost:XXXX/
```

Project saat ini umumnya berjalan di:

```text
http://localhost:8080/
```

Apabila frontend memakai port yang belum tercantum pada `ALLOWED_ORIGINS`, tambahkan port tersebut ke `backend/.env`, lalu restart backend.

---

## Langkah 4 — Mencoba alur lengkap

1. Buka halaman Beranda.
2. Klik **Pilih Data Demo**.
3. Lanjut ke **Atur Keputusan**.
4. Pilih toko, tanggal, budget, horizon, dan gaya kebijakan.
5. Klik **Buat Rencana Restock**.
6. Pada halaman Rencana Restock, setujui, edit, atau tolak beberapa SKU.
7. Lanjut ke **Konfirmasi & Ekspor**.
8. Klik **Ekspor CSV** dan pastikan file berhasil diunduh.
9. Klik **Konfirmasi Pesanan**.
10. Buka **Riwayat Keputusan** dan pastikan run yang dikonfirmasi muncul.

Jika seluruh langkah berjalan tanpa error, setup lokal sudah berhasil.

> Catatan: recommendation analytics saat ini masih memakai mock planner hingga implementasi ML asli diintegrasikan.

---

## Menjalankan backend tests

Dari direktori `backend`:

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

Baseline saat dokumentasi ini ditulis:

```text
4 tests passed
```

Jumlah test dapat bertambah seiring pengembangan.

---

## Menjalankan frontend build

Dari direktori `frontend`:

```bash
npm run build
```

Jika script lint tersedia:

```bash
npm run lint
```

---

## Troubleshooting

| Gejala | Kemungkinan penyebab | Solusi |
|---|---|---|
| `ModuleNotFoundError` saat menjalankan Python | Virtual environment belum aktif | Jalankan `source venv/bin/activate` |
| SciPy atau pandas mencoba di-compile dan gagal | Python terlalu baru, misalnya Python 3.14 | Gunakan Python 3.12 dan buat ulang virtual environment |
| `No module named psycopg2` | `DATABASE_URL` masih memakai driver default PostgreSQL | Gunakan `postgresql+psycopg://localhost:5432/restockiq` |
| `database "restockiq" already exists` | Database sudah pernah dibuat | Lewati perintah `createdb restockiq` |
| `Failed to fetch` di browser | Backend belum berjalan atau konfigurasi CORS tidak sesuai | Cek `curl http://localhost:8000/health` dan `ALLOWED_ORIGINS` |
| HTTP 422 pada `POST /decision-runs` | Nilai `policy_preset` tidak valid | Gunakan `lindungi_kas`, `seimbang`, atau `lindungi_ketersediaan` |
| Perubahan `.env` tidak terpakai | Backend belum di-restart | Stop server dengan `Ctrl+C`, lalu jalankan kembali Uvicorn |
| `cp .env.example .env` gagal pada frontend | `.env.example` belum tersedia | Pastikan file `frontend/.env.example` sudah terdapat di repository |

Detail tambahan tersedia di:

- `backend/README.md`
- `frontend/README.md`
- `docs/ML_INTEGRATION_NOTES.md`

---

## Struktur repository

```text
triple-sigma/
├── backend/
├── frontend/
├── docs/
│   └── ML_INTEGRATION_NOTES.md
└── data/
    └── synthetic/
        └── RestockIQ_Dataset_Sintetis.xlsx
```