# RestockIQ — Cara Jalanin Project (Awal sampai Akhir)

Panduan ini buat siapa pun di tim yang mau jalanin RestockIQ dari nol di mesinnya sendiri — backend + database + frontend, semua sampai bisa dites di browser.

---

## Prasyarat

- Python 3.11+ (dipakai: 3.13)
- Node.js + npm
- PostgreSQL terinstall dan jalan (macOS: `brew install postgresql@15` lalu `brew services start postgresql@15`)
- Git

---

## Langkah 1 — Clone repo

```bash
git clone <url-repo-restockiq>
cd triple-sigma
```

## Langkah 2 — Setup Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Buka `.env`, isi:
```
DATABASE_URL=postgresql+psycopg://localhost:5432/restockiq
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```
*(nanti kalau frontend jalan di port lain, tambahkan port itu ke `ALLOWED_ORIGINS` dan restart backend)*

```bash
createdb restockiq
python -m app.db.seed
```
Harus muncul konfirmasi 6 tabel ter-load (`Dim_Stores → dim_stores: 5 baris`, dst).

```bash
uvicorn app.main:app --reload --port 8000
```
Cek `http://localhost:8000/health` di browser — harus muncul `{"status":"ok"}`. **Biarkan terminal ini tetap terbuka.**

## Langkah 3 — Setup Frontend (buka terminal BARU)

```bash
cd frontend
npm install
cp .env.example .env
```
Isi `.env`:
```
VITE_API_URL=http://localhost:8000/api/v2
```

```bash
npm run dev
```
Cek output terminal buat lihat port asli (`Local: http://localhost:XXXX/`) — kalau bukan `5173`/`3000`, **tambahkan ke `ALLOWED_ORIGINS` di `backend/.env`, lalu restart backend** (Ctrl+C, jalankan ulang `uvicorn`).

Buka URL yang muncul di browser.

## Langkah 4 — Coba alur lengkap

1. Beranda → klik **"Pilih Data Demo"**
2. Lanjut ke **Atur Keputusan** → isi budget, pilih gaya kebijakan → **"Buat Rencana Restock"**
3. Di **Rencana Restock**, setujui beberapa SKU (tombol Setujui/sesuaikan jumlah)
4. Lanjut ke **Konfirmasi & Ekspor** → cek ringkasan, klik **"Ekspor CSV"** (harus ke-download), lalu **"Konfirmasi Pesanan"**

Kalau semua langkah ini jalan tanpa error, setup kamu sudah benar.

---

## Menjalankan test backend

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```
Harus 4 test PASSED.

---

## Kalau ada error

| Gejala | Kemungkinan penyebab | Solusi |
|---|---|---|
| `ModuleNotFoundError` pas jalanin Python | Lupa aktifkan venv | `source venv/bin/activate` |
| Backend crash/segfault pas seed | Versi psycopg2/pandas salah | Pastikan `requirements.txt` pakai `psycopg[binary]==3.2.3` dan `pandas>=2.2.3` |
| "Failed to fetch" di browser | Backend belum jalan, atau CORS | Cek `curl http://localhost:8000/health`, cek `ALLOWED_ORIGINS` sudah include port frontend, restart backend |
| 422 di `POST /decision-runs` | `policy_preset` salah format | Harus `lindungi_kas`/`seimbang`/`lindungi_ketersediaan` (lihat pesan error detail dari `extractErrorMessage`) |
| `.env` yang diubah nggak ke-apply | Server belum di-restart | `.env` cuma dibaca sekali saat start, wajib restart manual |

Detail lebih lengkap ada di `backend/README.md` dan `frontend/README.md`.

---

## Struktur repo (ringkas)

```
triple-sigma/
├── backend/     → lihat backend/README.md
├── frontend/    → lihat frontend/README.md
├── docs/
│   └── ML_INTEGRATION_NOTES.md   → wajib dibaca Della sebelum integrasi
└── data/synthetic/
    └── RestockIQ_Dataset_Sintetis.xlsx
```
