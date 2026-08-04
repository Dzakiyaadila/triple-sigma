# Catatan Integrasi ML untuk team ML
---

## 1. Perubahan paling penting: kontrak fungsi kamu JADI LEBIH SIMPEL

Draf awal minta fungsi kamu return `sku_name`, `category`, `supplier_name`, `supplier_note`, `reasoning_short`, `reason_more`, `reason_not_more`. **Ini sekarang TIDAK PERLU** kamu isi.

Backend (`decision_run_service.py`) sekarang otomatis:
- Ambil `sku_name`/`category` dari tabel `dim_products` (join by `sku_id`)
- Ambil `supplier_name`/`supplier_note` dari tabel `dim_suppliers` (join lewat `Product.supplier_id`)
- Generate `reasoning_short`/`reason_more`/`reason_not_more` dari `reasoning.py` — rule-based, bukan AI/NLP, cuma nerjemahin angka ke kalimat

**Kamu cuma perlu fokus ke angka-angka analitiknya.**

---

## 2. Kontrak final fungsi `generate_restock_plan()`

### Signature
```python
def generate_restock_plan(
    products: list[dict],       # [{"sku_id": str, "unit_cost_rp": float}, ...] — SEMUA SKU toko
    store_id: str,
    decision_date: str,         # "YYYY-MM-DD"
    budget_rp: float,
    policy_preset: str = "seimbang",   # lihat bagian 3, PENTING beda dari draf awal
    horizon_days: int = 7,
) -> dict:
```

### Output wajib (per level)

**Level 1 — ringkasan run:**
```python
{
  "run_id": str,
  "model_version": str,
  "data_hash": str,
  "budget_allocated_rp": float,
  "expected_nov_contribution_rp": float,
  "estimated_lmar_avoided_rp": float,
  "estimated_wcar_added_rp": float,
  "estimated_fill_rate": float,       # 0.0 - 1.0
  "data_quality": str,
  "warnings": list[str],
  "runtime_ms": int,
  "recommendations": [ ... Level 2 ... ]
}
```

**Level 2 — per SKU (list of dict):**
```python
{
  "sku_id": str,
  "priority_rank": int,
  "recommended_qty": int,
  "required_cash_rp": float,
  "inventory_on_hand": int,
  "inventory_on_order": int,
  "effective_inventory": int,
  "forecast_q10": float, "forecast_q50": float, "forecast_q90": float,
  "forecast_daily_series": [{"date": "YYYY-MM-DD", "q10": float, "q50": float, "q90": float}, ...],
  "stockout_risk_before": float,      # 0.0 - 1.0
  "stockout_risk_after": float,
  "lmar_before_rp": float, "lmar_after_rp": float, "incremental_lmar_avoided_rp": float,
  "wcar_before_rp": float, "wcar_after_rp": float, "incremental_wcar_added_rp": float,
  "supplier_on_time_probability": float,   # 0.0 - 1.0
  "supplier_p90_lead_time_days": int,
  "expected_nov_contribution_rp": float,
  "confidence": str,        # HARUS persis: "tinggi" / "sedang" / "rendah"
  "reason_codes": list[str],   # HARUS dari daftar valid di bagian 4, bukan bebas
  "warnings": list[str],
  "status": "belum_diputuskan",   # selalu ini, backend yang ubah nanti
}
```

**TIDAK PERLU** (backend yang isi): `sku_name`, `category`, `supplier_name`, `supplier_note`, `reasoning_short`, `reason_more`, `reason_not_more`.

---

## 3. `policy_preset` — english

karena draf awal pakai istilah Inggris. **Nilai yang benar dan final:**
```
`protect_cash`/`balanced`/`protect_availability`.
```

**Status implementasi saat ini:** mock backend **belum** benar-benar mengubah hasil berdasarkan nilai ini — 3 tombol di UI udah bisa diklik dan terkirim ke backend, tapi efeknya baru kerasa begitu fungsi kamu beneran membedakan strategi alokasi berdasarkan parameter ini. Ini salah satu hal paling penting yang dicek juri (nunjukkin `policy_preset` benar-benar ngubah trade-off, bukan cuma UI kosmetik).

---

## 4. Daftar `reason_codes` yang valid (WAJIB pakai dari daftar ini)

Backend (`reasoning.py`) punya kalimat siap pakai untuk kombinasi kode tertentu — kalau kamu pakai kode di luar daftar ini, sistem tetap jalan (ada fallback generic), tapi kalimatnya kurang presisi:

```
risiko_stockout_tinggi
supplier_andal
supplier_kurang_andal
data_historis_kurang
```

Kombinasi yang **sudah ada kalimat khusus**:
- `{risiko_stockout_tinggi, supplier_andal}` → "Risiko kehabisan stok tinggi. Supplier cukup bisa diandalkan."
- `{risiko_stockout_tinggi, supplier_kurang_andal}` → "Risiko kehabisan stok tinggi, tapi supplier sering telat — sebaiknya pesan lebih awal."
- `{data_historis_kurang}` → "Data histori penjualan masih terbatas, sistem memakai perkiraan kategori."

Kalau kamu perlu kode baru buat kasus lain, **diskusikan dulu** sebelum dipakai, biar saya tambahin ke `reasoning.py` juga.

---

## 5. Guardrail Oracle — WAJIB dipatuhi

Kolom-kolom ini **ada di dataset** (buat evaluasi/paper) tapi **haram** jadi input ke fungsi forecasting/reconstruction kamu:
```
units_demanded_est, demand_profile, avg_daily_demand_per_store, cash_locked_in_stock_rp
```
Ada test otomatis (`test_oracle_firewall.py`) yang cek kode `decision_run_service.py` nggak pernah nyebut nama kolom ini — kalau kamu nambah kode yang query kolom ini dari database, kabarin dulu biar test-nya disesuaikan (atau dipastikan itu emang cuma dipakai untuk evaluasi, bukan input model).

---

## 6. Data yang tersedia (sumber: dataset sintetis, sudah di-load ke PostgreSQL) - untuk mock

| Tabel | Isi |
|---|---|
| `dim_stores` | 5 toko: `S01`-`S05` |
| `dim_products` | 31 SKU: `SKU001`-`SKU031`, termasuk `unit_cost_rp`, `unit_price_rp`, `supplier_id` |
| `dim_suppliers` | 6 supplier: `SUP01`-`SUP06`, `promised_lead_time_days` |
| `dim_calendar` | 182 hari, flag weekend/holiday/payday |
| `fact_daily_sales` | ~28.200 baris — `units_sold`, `stock_on_hand_start/end`, `stockout_flag`, `promo_flag` |
| `fact_purchase_orders` | 549 baris — `order_qty_units`, `delay_days`, `actual_lead_time_days` |

**"Stok saat ini"** = `stock_on_hand_end` di `fact_daily_sales`, baris tanggal terbaru per kombinasi `store_id`+`sku_id`. Tidak ada tabel snapshot stok terpisah.

---

## 7. Cara integrasi nanti (teknis)

Fungsimu tinggal ditaruh/di-import ke `backend/app/ml/restock_plan.py`, replace fungsi mock yang sekarang ada di situ — **signature harus sama persis** (nama parameter, urutan). Setelah itu, **tidak ada perubahan apapun** yang dibutuhkan di:
- `decision_run_service.py` (udah otomatis enrich sku_name/category/supplier/reasoning)
- Schema Pydantic (udah sesuai)
- Frontend (udah manggil API, nggak peduli isi dalamnya)

---

## 8. Pertanyaan masih terbuka (perlu dijawab sebelum/selama kamu implementasi)

- [ ] Format data historis yang kamu butuhkan — backend query dari DB dan susun jadi apa? (dataframe? list of dict?) Kasih tau bentuk yang kamu mau, saya sesuaikan cara backend nyiapin datanya
- [ ] Berapa lama waktu eksekusi realistis untuk 1 toko penuh (31 SKU)? Sekarang backend proses "sinkron" (nunggu sampai selesai dalam 1 request) — kalau ternyata lambat (>5 detik), perlu didiskusikan ulang arsitekturnya
- [ ] Library solver yang dipakai (SciPy `milp` sesuai rencana awal?) — perlu ditambahkan ke `requirements.txt` backend
- [ ] Apakah `policy_preset` mempengaruhi bobot objective function di optimizer, atau cuma mengubah constraint (misal target service level minimum berbeda per preset)?

---

## 9. Kontak cepat kalau ada yang nggak jelas

Semua kode backend yang relevan ada di:
- `backend/app/ml/restock_plan.py` — tempat kamu kerja
- `backend/app/services/decision_run_service.py` — cara fungsimu dipanggil & hasil di-enrich
- `backend/app/services/reasoning.py` — generator kalimat, referensi buat `reason_codes`
- `backend/app/schemas/decision_run.py` — kontrak tipe data lengkap (Pydantic)

Kalau ada mismatch/pertanyaan pas mulai coding, kabarin duluan sebelum lanjut, biar nggak ada kerja dobel dari kedua sisi.
