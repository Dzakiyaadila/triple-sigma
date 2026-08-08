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
    *,
    snapshot: RetailSnapshot,
    constraints: MLDecisionConstraints,
    artifacts: ModelArtifacts | None = None,
) -> dict:
```

`RetailSnapshot` dibangun backend dari PostgreSQL dengan dataset/store/date cutoff
yang prediction-time safe. Planner tidak melakukan query database sendiri.

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
  "inventory_on_hand": float,
  "inventory_on_order": float,
  "effective_inventory": float,
  "forecast_q10": float, "forecast_q50": float, "forecast_q90": float,
  "forecast_daily_series": [
      {
          "date": "YYYY-MM-DD",
          "q10": float,
          "q50": float,
          "q90": float
      },
      ...
  ],  # optional; backward compatibility only
  "stockout_risk_before": float,      # 0.0 - 1.0
  "stockout_risk_after": float,
  "lmar_before_rp": float, "lmar_after_rp": float, "incremental_lmar_avoided_rp": float,
  "wcar_before_rp": float, "wcar_after_rp": float, "incremental_wcar_added_rp": float,
  "supplier_on_time_probability": float,   # 0.0 - 1.0
  "supplier_p90_lead_time_days": float,
  "expected_nov_contribution_rp": float,
  "confidence": str,        # HARUS persis: "tinggi" / "sedang" / "rendah"
  "reason_codes": list[str],   # HARUS dari daftar valid di bagian 4, bukan bebas
  "warnings": list[str],
  "status": "belum_diputuskan",   # selalu ini, backend yang ubah nanti
}
```
`forecast_daily_series` bersifat opsional dan hanya dipertahankan untuk
backward compatibility selama masa transisi. Real pipeline tidak boleh
membuat daily path dengan membagi forecast kumulatif atau menambahkan
tren sintetis.

Model final menghasilkan cumulative quantiles untuk horizon H1, H7, dan
H14. Field `forecast_q10`, `forecast_q50`, dan `forecast_q90` mengacu pada
horizon yang dipilih pada decision run.

**TIDAK PERLU** (backend yang isi): `sku_name`, `category`, `supplier_name`, `supplier_note`, `reasoning_short`, `reason_more`, `reason_not_more`.

---

## 3. `policy_preset` — nilai public API

Nilai public API yang final:

lindungi_kas
seimbang
lindungi_ketersediaan

Modul ML boleh melakukan mapping internal ke enum/configuration berbahasa Inggris, tetapi boundary API dan persistence tetap memakai nilai Bahasa Indonesia.

forecast_daily_series bersifat optional untuk backward compatibility.
Model final menghasilkan cumulative quantiles H1/H7/H14 dan tidak boleh
membuat daily path secara sintetis.

**Status implementasi R5:** `policy_preset` sudah masuk ke exact MCKP dan
mengubah objective allocation secara matematis. Regression test R4 membuktikan
policy dapat menghasilkan allocation berbeda pada state dan budget yang sama.

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

Ada satu perbaikan kecil di frontend payload

Sekarang:

```typescript
export interface CreateDecisionRunPayload {
  dataset_id: string;
  store_id: string;
  decision_date: string;
  budget_rp: number;
  horizon_days: number;
  policy_preset: string;
}
```
Lebih aman diselaraskan dengan backend:


```typescript
export type PolicyPreset =
  | "lindungi_kas"
  | "seimbang"
  | "lindungi_ketersediaan";

export interface CreateDecisionRunPayload {
  dataset_id: string;
  store_id: string;
  decision_date: string;
  budget_rp: number;
  horizon_days: number;
  policy_preset: PolicyPreset;
}
```
Dengan ini TypeScript akan menangkap salah ketik sebelum request sampai ke backend.

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

## 7. Cara integrasi real pipeline

Public API dan core journey frontend dipertahankan supaya integrasi model
tidak memerlukan perubahan besar pada UI.

Backend bertanggung jawab untuk:

- membaca data dari PostgreSQL;
- menerapkan cutoff berdasarkan `decision_date`;
- menyusun snapshot historis yang prediction-time safe;
- melakukan enrichment nama produk, kategori, supplier, dan reasoning text.

Modul ML bertanggung jawab untuk:

- validasi Oracle firewall;
- demand reconstruction;
- cumulative probabilistic forecasting;
- supplier-risk estimation;
- effective inventory;
- LMAR/WCAR;
- exact cash-constrained allocation;
- confidence, warnings, dan `reason_codes`.

Production orchestration sekarang memakai typed boundary:

```python
generate_restock_plan(
    snapshot=retail_snapshot,
    constraints=ml_constraints,
)
```

Flow final R5 adalah `RetailSnapshot -> demand inference -> supplier risk ->
LMAR/WCAR -> exact MCKP -> RestockPlan`. Response public ke frontend tetap
kompatibel. `forecast_daily_series` sengaja kosong karena model demand adalah
direct cumulative H1/H7/H14; daily path tidak disintesis.

---

## 8. Keputusan implementasi yang sudah di-freeze

- [x] Backend menyusun typed `RetailSnapshot`; ML tidak query database.
- [x] Runtime 31 SKU tetap sinkron untuk MVP dan diukur melalui `runtime_ms`.
- [x] Production allocator memakai exact sparse MCKP DP, bukan SciPy MILP.
- [x] `policy_preset` mengubah bobot objective optimizer.
- [x] `protected_sku_ids` didukung optimizer.
- [ ] `min_fill_rate` belum menjadi exact constraint dan **ditolak eksplisit**
      agar tidak diam-diam diabaikan. UI harus menonaktifkan/menghapus control
      ini sampai constraint tersebut benar-benar tersedia.
- [ ] Frozen model artifacts perlu dipaketkan pada release/deployment stack.

## 9. Kontak cepat kalau ada yang nggak jelas

Semua kode backend yang relevan ada di:
- `backend/app/ml/restock_plan.py` — tempat kamu kerja
- `backend/app/services/decision_run_service.py` — cara fungsimu dipanggil & hasil di-enrich
- `backend/app/services/reasoning.py` — generator kalimat, referensi buat `reason_codes`
- `backend/app/schemas/decision_run.py` — kontrak tipe data lengkap (Pydantic)

Kalau ada mismatch/pertanyaan pas mulai coding, kabarin duluan sebelum lanjut, biar nggak ada kerja dobel dari kedua sisi.
