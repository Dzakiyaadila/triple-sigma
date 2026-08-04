# Restock Cerdas

Buat web app bernama "RestockIQ" — asisten keputusan restock untuk pemilik UMKM ritel dengan modal kerja terbatas. Bahasa UI: Bahasa Indonesia. Target user utama non-teknis (pemilik toko), tapi aplikasi punya mode detail teknis untuk power user.

═══════════════════════════════

ARAH DESAIN VISUAL

═══════════════════════════════

Konsep: "buku kas/manifest toko" — bukan dashboard SaaS generik.

- Warna latar halaman: #F2F1EC. Permukaan kartu: #FCFBF7.

- Teks utama: #1B2A22, teks sekunder: #5C6B62, garis pembatas: #DAD6C9.

- Aksen utama/prioritas: #B8862F. Status aman: #3F6B4E. Risiko sedang: #C99A3E. Risiko tinggi: #A23B2E.

- Font judul: Space Grotesk. Font body/UI: Inter. SEMUA angka (Rupiah, jumlah, persentase, kode SKU) wajib pakai font monospace (IBM Plex Mono) dengan tabular figures, rata kanan jika dalam list/tabel.

- Border-radius kecil dan konsisten: 6-8px untuk card, 4px untuk badge (badge berbentuk kotak sudut tajam, BUKAN pill/bulat).

- Tidak ada gradient, shadow tebal, glow, atau efek dekoratif. Whitespace lega tapi fungsional. Animasi hanya transisi halus 150-200ms, tidak ada efek masuk yang ramai.

- Setiap Action Card punya garis vertikal tipis di sisi kiri dengan angka prioritas besar dalam monospace, dan hairline divider horizontal antar baris informasi di dalam card — meniru tampilan slip/nota, bukan card dashboard biasa.

═══════════════════════════════

STRUKTUR NAVIGASI

═══════════════════════════════

Sidebar kiri minimal (collapsible di mobile jadi bottom nav) dengan 4 item:

- Beranda (dashboard utama)

- Simulasi budget

- Peta risiko

- Riwayat

═══════════════════════════════

TOP BAR (persist di semua halaman)

═══════════════════════════════

- Dropdown "Pilih toko" — isi 5 opsi dummy (Toko Melati, Toko Anggrek, Toko Kenanga, Toko Dahlia, Toko Cempaka)

- Input "Modal restock tersedia" — field angka dengan format Rupiah otomatis saat mengetik (contoh placeholder: Rp 3.000.000)

- Tombol utama "Hitung rekomendasi" (warna aksen #B8862F, teks putih) — memicu perhitungan ulang

- Badge kecil abu-abu di ujung kanan: "Data per [tanggal dummy]" — menunjukkan kapan dataset terakhir diperbarui

- Toggle switch kecil berlabel "Detail teknis" — mengaktifkan/nonaktifkan tampilan lanjutan di seluruh halaman (default: OFF)

═══════════════════════════════

HALAMAN 1: BERANDA (dashboard utama)

═══════════════════════════════

1. RINGKASAN ATAS — 4 kartu kecil sejajar horizontal (stack vertikal di mobile):

   - "SKU direkomendasikan" — angka besar monospace

   - "Modal terpakai" — progress bar horizontal + teks "Rp X dari Rp Y tersedia"

   - "Estimasi margin terselamatkan" — angka besar monospace, warna hijau aman

   - "SKU risiko tinggi" — angka besar monospace, warna merah, dengan badge kotak kecil

2. TOOLBAR FILTER di atas list card:

   - Search box "Cari nama SKU..."

   - Dropdown filter kategori produk

   - Dropdown filter level risiko (Semua / Aman / Sedang / Tinggi)

   - Tombol toggle tampilan: grid / list

3. LIST ACTION CARDS — urut berdasarkan prioritas, tiap card berisi:

   - Angka prioritas besar (monospace) di garis kiri card

   - Nama SKU (Space Grotesk, medium weight) + kategori kecil di bawahnya (teks sekunder)

   - Badge kotak kecil status risiko di kanan atas card (warna sesuai level, isi: "Aman" / "Sedang" / "Tinggi")

   - Baris "Rekomendasi beli: [jumlah] unit — Rp [subtotal]" dalam monospace

   - Baris alasan singkat dalam bahasa natural (1-2 kalimat, bukan istilah teknis), contoh: "Risiko kehabisan stok tinggi. Supplier cukup bisa diandalkan."

   - JIKA toggle "Detail teknis" AKTIF: tampilkan baris tambahan — mini bar indikator forecast Q10/Q50/Q90, angka Lost Margin at Risk dan Working Capital at Risk (label singkat + tooltip penjelasan saat hover ikon info), skor keandalan supplier dalam persen

   - Area interaksi bawah card: stepper angka "Sesuaikan jumlah" (tombol minus, input angka, tombol plus) dan tombol "Terima" (berubah jadi tombol "✓ Diterima" berwarna hijau muda setelah diklik, bisa diklik lagi untuk batal)

   - Klik area card (selain tombol) membuka drawer detail dari sisi kanan layar

4. DRAWER DETAIL SKU (slide dari kanan, menutupi maks 40% lebar layar di desktop, full-screen di mobile):

   - Tombol close (X) di kiri atas drawer

   - Judul nama SKU + kode SKU dalam monospace kecil

   - Grafik area chart forecast permintaan (garis Q10, Q50, Q90) sepanjang beberapa hari ke depan

   - Dua kotak angka besar berdampingan: "Potensi margin berisiko" dan "Modal tertahan berisiko" — masing-masing dengan satu kalimat penjelasan awam di bawahnya

   - Info supplier: nama, badge skor keandalan, catatan histori keterlambatan singkat

   - Paragraf alasan lebih lengkap (2-3 kalimat)

   - Tombol "Sesuaikan jumlah" dan "Terima" (sama seperti di card, state tersinkron)

5. SIDEBAR KANAN "Keranjang restock" (sticky, bisa di-collapse dengan tombol panah):

   - Judul "Keranjang restock" + jumlah item

   - List singkat SKU yang berstatus diterima: nama, jumlah, subtotal (monospace, rata kanan)

   - Total keseluruhan vs budget tersedia — progress bar, berubah warna ke merah kalau melebihi budget

   - JIKA kosong: ilustrasi garis sederhana + teks "Belum ada SKU yang diterima. Klik 'Terima' pada rekomendasi untuk menambahkan."

   - Tombol besar di bawah "Tandai semua sudah dipesan" (nonaktif/abu-abu jika keranjang kosong)

   - Setelah tombol diklik: muncul modal konfirmasi kecil "X item ditandai sudah dipesan" dengan tombol "Tutup", lalu keranjang kembali kosong dan status card berubah jadi "Sudah dipesan" (badge abu-abu)

6. STATE KHUSUS:

   - Loading: skeleton card berwarna abu-abu muda berkedip halus, muncul 4-5 placeholder card saat data sedang dihitung

   - Empty (tidak ada rekomendasi/budget terlalu kecil): ilustrasi garis sederhana + judul "Belum ada rekomendasi untuk budget ini" + teks "Coba naikkan modal restock atau pilih toko lain" + tombol "Ubah modal"

   - Error (gagal ambil data): ikon peringatan sederhana + teks "Gagal memuat rekomendasi. Coba lagi." + tombol "Muat ulang"

7. BANNER DISCLAIMER (collapsible, posisi di bawah top bar, bisa ditutup dengan tombol X dan tidak muncul lagi di sesi itu):

   Teks: "Sistem ini menggunakan data simulasi untuk validasi metodologi. Rekomendasi bersifat pendukung keputusan, bukan pengganti penilaian pemilik toko."

═══════════════════════════════

HALAMAN 2: SIMULASI BUDGET (/simulator)

═══════════════════════════════

- Judul halaman + satu kalimat penjelasan singkat

- Slider besar horizontal berlabel "Skenario budget" dari 25% sampai 100% dari kebutuhan ideal, dengan angka Rupiah dinamis di atas slider

- Saat slider digeser: 

  - Card ringkasan di sampingnya update real-time (animasi angka berjalan halus, bukan lompat tiba-tiba): estimasi margin terselamatkan, jumlah SKU ter-cover

  - Preview mini list Action Cards di bawahnya ikut berubah urutan/isi

- Chart garis: sumbu X = persentase budget, sumbu Y = estimasi margin (Rupiah), dengan titik penanda posisi slider saat ini, dibandingkan dengan garis baseline "tanpa optimasi"

- Kalimat penjelasan dinamis di bawah chart yang berubah sesuai posisi slider, contoh: "Pada budget ini, kamu mengamankan sekitar X% dari potensi margin maksimal"

═══════════════════════════════

HALAMAN 3: PETA RISIKO (/risk-map)

═══════════════════════════════

- Judul halaman + kalimat penjelasan singkat

- Scatter plot interaktif: sumbu X = modal kerja berisiko (Rupiah), sumbu Y = margin berisiko (Rupiah)

- Tiap titik = satu SKU, warna titik sesuai level risiko (memakai palet warna status yang sama)

- Hover titik menampilkan tooltip kecil: nama SKU, kedua angka risikonya

- Klik titik membuka drawer detail SKU yang sama seperti di halaman Beranda

- Legenda warna kecil di pojok chart

═══════════════════════════════

HALAMAN 4: RIWAYAT (/history)

═══════════════════════════════

- Tabel sederhana dengan kolom: Tanggal, Toko, SKU, Jumlah dipesan, Status

- Baris tabel memakai font monospace untuk kolom angka

- Filter dropdown di atas tabel: berdasarkan toko, berdasarkan rentang tanggal

- Jika kosong: teks "Belum ada riwayat keputusan restock"

═══════════════════════════════

DATA DUMMY

═══════════════════════════════

Buat 18-20 Action Card dummy dengan variasi realistis (campur risiko tinggi/sedang/aman, berbagai kategori produk retail Indonesia seperti sembako, minuman, kebutuhan rumah tangga). Gunakan struktur data berikut persis:

{

  "sku_id": "SKU-0231",

  "sku_name": "Kopi Sachet 200g",

  "category": "Minuman",

  "store_id": "STR-03",

  "priority_rank": 1,

  "recommended_qty": 48,

  "unit_cost": 12000,

  "forecast": { "q10": 30, "q50": 45, "q90": 60 },

  "stockout_risk_pct": 22.4,

  "lmar": 1250000,

  "wcar": 380000,

  "supplier_reliability": 0.87,

  "reasoning": "Risiko kehabisan stok tinggi. Supplier cukup bisa diandalkan.",

  "status": "belum_diputuskan"

}

═══════════════════════════════

PRIORITAS FOKUS

═══════════════════════════════

Utamakan kejelasan informasi dan kecepatan pengambilan keputusan untuk pengguna non-teknis di tampilan default. Detail teknis harus tetap ada dan lengkap, tapi disembunyikan di balik toggle "Detail teknis" dan drawer detail — jangan tampilkan istilah teknis (LMAR, WCAR, quantile) di layar utama secara default.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/6391dba7-92a1-4c53-a6bb-4c17af50e654).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
