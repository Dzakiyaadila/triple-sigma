# RestockIQ Backend — Dokumentasi Lengkap

**Status:** Core journey backend selesai dan teruji. Mock ML aktif (menunggu implementasi asli Della). Frontend sudah wired penuh ke endpoint-endpoint di bawah.

---

## 1. Ringkasan

RestockIQ backend adalah FastAPI service yang menyediakan seluruh logika di balik keputusan restock: dari validasi data toko, generate rencana restock (forecast + risiko + optimisasi), sampai approve/edit/reject per SKU dan ekspor purchase order.

**Bukan** POS/inventory CRUD — backend ini murni decision-support layer di atas dataset yang sudah ada.

---

## 2. Tech stack

| Layer | Pilihan | Catatan |
|---|---|---|
| Python | 3.13 | |
| Framework | FastAPI 0.115.0 | |
| Validasi | Pydantic v2 | |
| ORM | SQLAlchemy 2.0.35 | |
| Database | PostgreSQL 15 (lokal via Homebrew) | Rencana produksi: Docker |
| DB driver | **psycopg (v3)**, bukan psycopg2 | Wajib, lihat bagian 8 |
| Data processing | pandas >=2.2.3 | Wajib versi ini, lihat bagian 8 |
| Testing | pytest 8.3.3 | |

---

## 3. Struktur folder

```
backend/
├── app/
│   ├── main.py                       # entry point, wiring semua router + CORS
│   ├── api/routes/
│   │   ├── datasets.py               # GET /datasets/demo/readiness
│   │   ├── decision_runs.py          # POST /decision-runs, GET .../plan
│   │   ├── recommendations.py        # PATCH approve/edit/reject, POST confirm
│   │   └── export.py                 # GET .../export.csv
│   ├── services/
│   │   ├── decision_run_service.py   # orkestrasi: DB → panggil ML → enrich → simpan
│   │   ├── reasoning.py              # generator teks penjelasan (rule-based)
│   │   └── plan_cache.py             # cache in-memory hasil plan per run_id
│   ├── ml/
│   │   └── restock_plan.py           # MOCK generate_restock_plan() — lihat bagian 9
│   ├── db/
│   │   ├── models.py                 # SQLAlchemy models, 9 tabel
│   │   ├── session.py                # engine, SessionLocal, get_db()
│   │   └── seed.py                   # load dataset sintetis Excel → database
│   ├── schemas/
│   │   ├── common.py
│   │   ├── dataset.py
│   │   └── decision_run.py           # kontrak data lengkap (Pydantic)
│   └── core/
│       └── config.py                 # baca .env: DATABASE_URL, ALLOWED_ORIGINS
├── tests/
│   ├── test_oracle_firewall.py
│   └── test_budget_constraint.py
├── data/synthetic/
│   └── RestockIQ_Dataset_Sintetis.xlsx
├── requirements.txt
├── pytest.ini
└── .env / .env.example
```

---

## 4. Setup dari fresh clone

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # WAJIB tiap buka terminal baru
pip install -r requirements.txt
cp .env.example .env            # lalu isi DATABASE_URL & ALLOWED_ORIGINS
createdb restockiq              # sekali saja
python -m app.db.seed           # sekali saja, load dataset sintetis
uvicorn app.main:app --reload --port 8000
```

Swagger UI interaktif: `http://localhost:8000/docs` — bisa langsung test semua endpoint dari situ.

`.env` contoh:
```
DATABASE_URL=postgresql+psycopg://localhost:5432/restockiq
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000,http://localhost:8081
```
> Frontend TanStack Start kadang jalan di port yang beda-beda (ada "sandbox detection" otomatis) — cek port asli dari output `npm run dev`, tambahkan ke `ALLOWED_ORIGINS` kalau belum ada.

---

## 5. Skema database (9 tabel)

### Sumber data (dari dataset sintetis Della)
| Tabel | Kolom kunci | Catatan |
|---|---|---|
| `dim_stores` | store_id (`S01`-`S05`), store_name, city | |
| `dim_suppliers` | supplier_id (`SUP01`-`SUP06`), supplier_name | |
| `dim_products` | sku_id (`SKU001`-`SKU031`), product_name, category, unit_cost_rp, supplier_id | `demand_profile`, `avg_daily_demand_per_store` = ⚠️Oracle |
| `dim_calendar` | date, is_weekend, is_holiday, is_payday_week | |
| `fact_daily_sales` | date, store_id, sku_id, units_sold, stock_on_hand_start/end | `units_demanded_est`, `demand_profile`, `cash_locked_in_stock_rp` = ⚠️Oracle |
| `fact_purchase_orders` | po_id, store_id, sku_id, supplier_id, delay_days | |

### Tabel produk (fitur RestockIQ)
| Tabel | Kolom kunci |
|---|---|
| `datasets` | dataset_id, source_type, readiness_status |
| `decision_runs` | run_id, store_id, decision_date, budget_rp, policy_preset, status |
| `recommendations` | recommendation_id, run_id, sku_id, status, adjusted_qty, before_metrics_json |

⚠️Oracle = ground-truth, boleh disimpan tapi **tidak boleh** jadi input ke modul ML — dijaga `test_oracle_firewall.py`.

**"Stok saat ini"** diambil dari `stock_on_hand_end` di `fact_daily_sales` (tanggal terakhir), bukan tabel terpisah.

---

## 6. Kontrak API lengkap

Base URL: `/api/v2`

### `GET /datasets/demo/readiness`
```json
{ "data": {
  "dataset_id": "demo-retail-v1", "source_type": "demo",
  "days_covered": 182, "store_count": 5, "sku_count": 31,
  "supplier_count": 6, "transaction_count": 28210,
  "is_ready": true, "warnings": []
}}
```

### `POST /decision-runs`
```json
// Request
{
  "dataset_id": "demo-retail-v1",
  "store_id": "S01",
  "decision_date": "2024-06-24",
  "budget_rp": 3000000,
  "horizon_days": 7,
  "policy_preset": "seimbang"
}
```
> **`policy_preset` pakai istilah Indonesia**: `"lindungi_kas"` / `"seimbang"` / `"lindungi_ketersediaan"` — BUKAN `protect_cash`/`balanced`/dst. Ini sempat jadi bug 422 karena mismatch, sudah diperbaiki di schema.

Response: objek `RestockPlan` lengkap (lihat bagian 9).

### `GET /decision-runs/{run_id}/plan`
Ambil ulang plan yang sama dari cache in-memory.

### `PATCH /decision-runs/{run_id}/recommendations/{sku_id}`
```json
{ "status": "disetujui", "adjusted_qty": 40 }
```
`status` valid: `belum_diputuskan` / `disetujui` / `diedit` / `ditolak`. Backend **selalu revalidasi total budget** — kalau approved total > `budget_rp`, return 400 dengan pesan jelas.

### `POST /decision-runs/{run_id}/confirm`
Return `{ confirmed_count, confirmed_at, total_cost_rp }`.

### `GET /decision-runs/{run_id}/export.csv`
Download CSV berisi item berstatus `disetujui`. Header `Content-Disposition: attachment`.

**Belum ada** (belum dibangun, jadi Riwayat di frontend sekarang cuma lokal, hilang kalau refresh): `GET /decision-runs` (listing history). Lihat bagian 10.

---

## 7. Format error konsisten

```json
{ "detail": "pesan error dari HTTPException" }
```
atau untuk validation error Pydantic:
```json
{ "detail": [{ "loc": ["body", "policy_preset"], "msg": "...", "type": "..." }] }
```
Frontend sudah punya parser (`extractErrorMessage()` di `api.ts`) buat nampilin ini dengan jelas, bukan `[object Object]`.

---

## 8. Gotcha teknis (biar tidak terulang di mesin lain)

1. **`psycopg2-binary` segfault** di macOS Apple Silicon + PostgreSQL Homebrew. **Fix: `psycopg[binary]==3.2.3`**, `DATABASE_URL` prefix `postgresql+psycopg://`.
2. **`pandas==2.2.2` segfault** di Python 3.13. **Fix: `pandas>=2.2.3`.**
3. **`pandas.to_sql()` tidak reliable** dengan SQLAlchemy 2.0 + Python 3.13. **Fix: `seed.py` insert manual pakai SQLAlchemy Core `insert()`.**
4. **pytest butuh `pythonpath = .` di `pytest.ini`** biar bisa resolve `import app.*`.
5. **`.env` dibaca cuma sekali saat start** — ubah `.env` (`DATABASE_URL`, `ALLOWED_ORIGINS`) **wajib restart `uvicorn`**, tidak auto-reload meski pakai flag `--reload` (itu cuma reload kode Python, bukan environment variable).
6. **Virtual environment harus diaktifkan ulang tiap sesi terminal baru** (`source venv/bin/activate`).
7. **CORS error "Failed to fetch"** — cek `ALLOWED_ORIGINS` sudah include port frontend yang benar (cek port asli dari `npm run dev`, port TanStack Start bisa dinamis), lalu restart backend.

---

## 9. Kontrak dengan modul ML — PENTING dibaca Della

**Ini sudah diperbarui dari draf awal — beberapa field yang dulu diminta dari Della TERNYATA sekarang di-generate backend, bukan tanggung jawab modul ML lagi.** Lihat dokumen terpisah `ML_INTEGRATION_NOTES.md` untuk detail lengkap dan alasan perubahannya.

Ringkasnya: fungsi `generate_restock_plan()` di `app/ml/restock_plan.py` **tidak perlu** return `sku_name`, `category`, `supplier_name`, `supplier_note`, `reasoning_short`, `reason_more`, `reason_not_more` — itu semua ditambahkan otomatis oleh `decision_run_service.py` (join ke `dim_products`/`dim_suppliers`) dan `reasoning.py` (generator teks rule-based) setelah fungsi Della selesai jalan.

---

## 10. Yang belum dibangun (known gaps)

- [ ] Endpoint `GET /decision-runs` untuk listing riwayat — Riwayat di frontend sekarang murni state lokal React, hilang kalau browser refresh
- [ ] Endpoint upload data toko (`POST /datasets/validate`, `POST /datasets`) — stretch feature, belum prioritas
- [ ] Integrasi ML asli (masih mock)
- [ ] `policy_preset` belum benar-benar mengubah hasil di mock — baru berpengaruh nyata setelah optimizer asli Della terpasang

---

## 11. Testing

```bash
pytest tests/ -v
```
4 test, semua passed: 2 oracle firewall, 2 budget constraint.