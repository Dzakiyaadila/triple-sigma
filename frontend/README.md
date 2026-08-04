# RestockIQ Frontend — Dokumentasi Lengkap

**Status:** Core journey wired penuh ke backend (bukan lagi data dummy lokal). File-file shadcn yang tidak terpakai sudah dibersihkan.

---

## 1. Ringkasan

Frontend RestockIQ dibangun di atas **TanStack Start** (React 19 + Vite, file-based routing mirip Next.js tapi konvensi beda). Awalnya digenerate Lovable, sekarang sudah diaudit dan dirapikan — komponen yang dipakai murni yang relevan.

**Konsep desain:** "buku kas/manifest toko" — warna hangat netral, font monospace untuk semua angka, badge kotak (bukan pill).

---

## 2. Tech stack

| Layer | Pilihan |
|---|---|
| Framework | TanStack Start (React 19 + Vite) |
| Routing | TanStack Router (file-based, lihat bagian 5) |
| Styling | Tailwind CSS v4 (native `@theme`, format warna `oklch`) |
| Data fetching | `fetch()` native lewat `src/lib/api.ts` (bukan React Query, meski provider-nya sudah terpasang) |
| Komponen UI dasar | Cuma 3 dari shadcn: `slider`, `switch`, `tooltip` — sisanya custom (lihat `primitives.tsx`) |
| Icon | lucide-react |

---

## 3. Struktur folder (final, setelah cleanup)

```
frontend/
├── src/
│   ├── components/
│   │   ├── restock/
│   │   │   ├── AppShell.tsx        # Sidebar + TopBar + Wizard Stepper
│   │   │   ├── OrderCart.tsx       # Sidebar kanan "Keranjang restock"
│   │   │   ├── PlanCard.tsx        # Satu Action Card
│   │   │   ├── PlanDrawer.tsx      # Panel detail SKU (klik card)
│   │   │   └── primitives.tsx      # GoldButton, GhostButton, FlatBadge, Meter, dst
│   │   └── ui/
│   │       ├── slider.tsx
│   │       ├── switch.tsx
│   │       └── tooltip.tsx
│   ├── lib/
│   │   ├── api.ts                  # SEMUA pemanggilan backend ada di sini
│   │   ├── plan-data.ts            # tipe data, konstanta (STORES, dll), helper format
│   │   ├── restock-store.tsx       # STATE GLOBAL — lihat bagian 6, paling penting
│   │   ├── utils.ts                # helper cn() gabung className Tailwind
│   │   ├── error-capture.ts        # infrastruktur error handling SSR
│   │   └── error-page.ts           # halaman fallback kalau server crash
│   ├── routes/                     # satu file = satu URL, lihat bagian 5
│   │   ├── __root.tsx              # bungkus semua halaman (provider, AppShell)
│   │   ├── index.tsx                → /
│   │   ├── atur.tsx                 → /atur
│   │   ├── rencana.tsx              → /rencana
│   │   ├── konfirmasi.tsx           → /konfirmasi
│   │   ├── riwayat.tsx              → /riwayat
│   │   └── evaluasi.tsx             → /evaluasi
│   ├── router.tsx                  # setup TanStack Router + QueryClient
│   ├── server.ts / start.ts        # infrastruktur SSR, jarang disentuh
│   └── styles.css                  # design token (warna, font) — Tailwind v4 @theme
├── .env                             # VITE_API_URL
└── vite.config.ts
```

---

## 4. State global: `restock-store.tsx` — INI YANG PALING PENTING

Semua state aplikasi (dataset dipilih, parameter keputusan, hasil rencana, keputusan per SKU, keranjang, riwayat) hidup di **satu React Context** (`RestockProvider`), dipasang sekali di `__root.tsx`, diakses halaman manapun lewat `useRestock()`.

### Fungsi-fungsi kunci

| Fungsi | Manggil backend? | Keterangan |
|---|---|---|
| `chooseDataset("demo")` | ✅ `GET /datasets/demo/readiness` | |
| `chooseDataset("upload", file)` | ❌ Masih simulasi `setTimeout` | Backend belum ada endpoint upload |
| `runPlan()` | ✅ `POST /decision-runs` | Hasil disimpan ke state `planItems` |
| `setStatus(sku, status)` | ✅ `PATCH .../recommendations/{sku}` | Approve/reject sekaligus sync ke server |
| `setQty(sku, qty)` | ✅ (kalau status sudah `disetujui`) | Sync qty yang diedit |
| `confirmOrder()` | ✅ `POST .../confirm` | + catat ke riwayat LOKAL (lihat batasan di bawah) |

### Alur data (penting dipahami)

```
User isi form di atur.tsx
  → updateSetup() ubah state global
  → klik "Buat Rencana Restock" → runPlan()
  → runPlan() fetch ke backend, hasil masuk state `planItems`
  → rencana.tsx baca `items` (turunan dari `planItems`) via useRestock()
  → render jadi PlanCard satu-satu
```

---

## 5. Halaman (routes)

| File | URL | Isi |
|---|---|---|
| `index.tsx` | `/` | Pilih Data Demo / Upload |
| `atur.tsx` | `/atur` | Toko, tanggal, budget, gaya kebijakan (3 pilihan), service level, protected SKU |
| `rencana.tsx` | `/rencana` | Action Cards + summary strip + keranjang |
| `konfirmasi.tsx` | `/konfirmasi` | Ringkasan akhir, ekspor CSV, konfirmasi |
| `riwayat.tsx` | `/riwayat` | Tabel riwayat run (⚠️ lihat batasan) |
| `evaluasi.tsx` | `/evaluasi` | Mode Teknis — metrik model (masih placeholder statis) |

**Konvensi routing TanStack Start** (beda dari Next.js): `index.tsx` → `/`, `$id.tsx` → dynamic segment, `__root.tsx` → root layout wajib. `routeTree.gen.ts` auto-generated, jangan diedit manual.

---

## 6. Batasan yang perlu diketahui tim

1. **Riwayat cuma tersimpan di memory browser** (state React, bukan fetch dari backend) — kalau refresh halaman, riwayat hilang. Backend belum punya endpoint listing history.
2. **Upload data toko sendiri masih simulasi** — backend belum ada endpoint-nya (stretch feature, prioritas rendah).
3. **3 pilihan "Gaya kebijakan" belum benar-benar mengubah hasil** — mock ML backend belum implementasi diferensiasi berdasarkan `policy_preset`. Tombolnya bisa diklik dan terkirim, tapi efeknya baru kelihatan setelah optimizer asli Della terpasang.
4. **Halaman Evaluasi masih placeholder** — metrik model (WMAPE dkk) hardcoded, belum ambil data asli.
5. **Ekspor PDF sengaja dihapus** dari UI (keputusan scope, CSV cukup untuk MVP).

---

## 7. Setup dari fresh clone

```bash
cd frontend
npm install
cp .env.example .env    # isi VITE_API_URL=http://localhost:8000/api/v2
npm run dev
```

Cek port yang muncul di terminal (`Local: http://localhost:XXXX/`) — TanStack Start punya "sandbox port detection" jadi port bisa beda-beda tiap mesin, tidak selalu `5173`.

**Backend harus sudah jalan duluan** (`localhost:8000`) sebelum coba fitur apapun yang manggil API — kalau belum, akan muncul error "Failed to fetch" di console.

---

## 8. Gotcha yang pernah dialami

1. **Sidebar tidak muncul di halaman pertama** — dulu ada kondisi `hasCompletedRun` yang nyembunyiin sidebar sampai 1 run selesai. Sudah diperbaiki (sidebar sekarang selalu tampil).
2. **42 dari 45 komponen shadcn/ui tidak terpakai** — sudah dihapus semua kecuali `slider`, `switch`, `tooltip` (dicek dengan grep pemakaian di seluruh `src/`, termasuk cross-import antar file `ui/*` sendiri).
3. **CORS "Failed to fetch"** — pastikan port frontend ada di `ALLOWED_ORIGINS` backend, dan backend di-restart setelah ubah `.env`.
4. **422 di `POST /decision-runs`** — `policy_preset` harus persis `lindungi_kas`/`seimbang`/`lindungi_ketersediaan` (Indonesia), bukan `protect_cash`/`balanced`/dst.
5. **Project awalnya setup untuk `bun`** (ada `bun.lock`, `bunfig.toml`) tapi kita pakai `npm` — file bun sudah dihapus, aman diabaikan kalau ada referensi lama.