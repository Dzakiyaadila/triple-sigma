export type RiskLevel = "aman" | "sedang" | "tinggi";
export type Confidence = "tinggi" | "sedang" | "rendah";
export type ItemStatus = "belum_diputuskan" | "disetujui" | "ditolak";
export type PolicyStyle = "lindungi_kas" | "seimbang" | "lindungi_ketersediaan";

export interface PlanItem {
  sku_id: string;
  sku_name: string;
  category: string;
  priority_rank: number;
  recommended_qty: number;
  required_cash_rp: number;
  inventory_on_hand: number;
  inventory_on_order: number;
  effective_inventory: number;
  forecast_q10: number;
  forecast_q50: number;
  forecast_q90: number;
  stockout_risk_before: number;
  stockout_risk_after: number;
  lmar_before_rp: number;
  lmar_after_rp: number;
  incremental_lmar_avoided_rp: number;
  wcar_before_rp: number;
  wcar_after_rp: number;
  incremental_wcar_added_rp: number;
  supplier_name: string;
  supplier_on_time_probability: number;
  supplier_p90_lead_time_days: number;
  supplier_note: string;
  expected_nov_contribution_rp: number;
  confidence: Confidence;
  reason_codes: string[];
  reasoning_short: string;
  reason_more: string;
  reason_not_more: string;
  warnings: string[];
  status: ItemStatus;
}

export const MODEL_VERSION = "Model v1.0";
export const DATA_DATE = "28 Jul 2026";
export const DATA_DATE_ISO = "2026-07-28";

export const STORES = [
  { id: "S01", name: "Toko Berkah Jaya" },
  { id: "S02", name: "Minimarket Sido Mulyo" },
  { id: "S03", name: "Warung Bu Yanti" },
  { id: "S04", name: "Toko Sembako Amanah" },
  { id: "S05", name: "Minimarket Cahaya Baru" },
];

export const DEMO_SUMMARY = {
  days: 180,
  stores: 5,
  skus: 31,
  suppliers: 9,
  rows: 42817,
};

export const DEMO_ISSUES: Array<{ where: string; message: string; severity: "error" | "warning" }> = [
  { where: "kolom promo_flag", message: "Kolom opsional tidak ditemukan, diisi nilai default 0.", severity: "warning" },
  { where: "baris 1.204-1.211", message: "Tanggal transaksi duplikat, sistem memakai baris terakhir.", severity: "warning" },
];

export const UPLOAD_ISSUES: Array<{ where: string; message: string; severity: "error" | "warning" }> = [
  { where: "kolom unit_cost", message: "12 baris berisi nilai kosong. Kolom ini wajib diisi.", severity: "error" },
  { where: "kolom sku_id", message: "3 SKU belum dikenal sistem (SKU-9001, SKU-9002, SKU-9014).", severity: "error" },
  { where: "kolom lead_time_days", message: "Sebagian baris memakai satuan minggu, dikonversi otomatis.", severity: "warning" },
];

export const UPLOAD_SUMMARY = {
  days: 92,
  stores: 1,
  skus: 24,
  suppliers: 5,
  rows: 8134,
};

export const CATEGORIES = ["Sembako", "Minuman", "Makanan Ringan", "Kebutuhan Rumah", "Perawatan Diri"];

export const MODEL_METRICS = [
  { label: "WMAPE (7 hari)", value: "18,4%", note: "Rata-rata galat berbobot pada horizon 7 hari" },
  { label: "Coverage Q10-Q90", value: "88,1%", note: "Target 80%, aktual sedikit konservatif" },
  { label: "Bias", value: "+2,7%", note: "Prediksi sedikit di atas realisasi" },
  { label: "Pinball loss Q50", value: "3,42", note: "Dibanding baseline naive 5,10" },
  { label: "Service level tercapai", value: "92,6%", note: "Simulasi backtest 30 hari terakhir" },
  { label: "Solver gap", value: "0,8%", note: "Jarak dari solusi optimal teoretis" },
];

export function riskLevel(pct: number): RiskLevel {
  if (pct >= 30) return "tinggi";
  if (pct >= 15) return "sedang";
  return "aman";
}

export const RISK_LABEL: Record<RiskLevel, string> = {
  aman: "Aman",
  sedang: "Sedang",
  tinggi: "Tinggi",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  tinggi: "Kepercayaan tinggi",
  sedang: "Kepercayaan sedang",
  rendah: "Kepercayaan rendah",
};

export const POLICY_LABEL: Record<PolicyStyle, string> = {
  lindungi_kas: "Lindungi Kas",
  seimbang: "Seimbang",
  lindungi_ketersediaan: "Lindungi Ketersediaan",
};

export function formatRupiah(n: number) {
  return "Rp " + Math.round(n).toLocaleString("id-ID");
}

export function formatRupiahShort(n: number) {
  if (n >= 1_000_000) return "Rp" + (n / 1_000_000).toFixed(1).replace(".", ",") + "jt";
  if (n >= 1_000) return "Rp" + Math.round(n / 1000) + "rb";
  return "Rp" + n;
}

export function parseRupiah(s: string) {
  const digits = s.replace(/\D/g, "");
  return digits ? parseInt(digits, 10) : 0;
}

export function formatPct(v: number, digits = 0) {
  return (v * 100).toFixed(digits).replace(".", ",") + "%";
}

type Seed = {
  id: string;
  name: string;
  category: string;
  qty: number;
  unit: number;
  onHand: number;
  onOrder: number;
  q: [number, number, number];
  before: number;
  after: number;
  lmarB: number;
  lmarA: number;
  wcarB: number;
  wcarA: number;
  sup: string;
  otp: number;
  p90: number;
  supNote: string;
  nov: number;
  conf: Confidence;
  codes: string[];
  short: string;
  warns: string[];
};

const SEEDS: Seed[] = [
  { id: "SKU007", name: "Kopi Sachet 200g", category: "Minuman", qty: 48, unit: 12000, onHand: 12, onOrder: 20, q: [30, 45, 60], before: 0.38, after: 0.12, lmarB: 2100000, lmarA: 600000, wcarB: 300000, wcarA: 950000, sup: "CV Sumber Rasa", otp: 0.87, p90: 5, supNote: "Terlambat 2 kali dari 15 pengiriman terakhir.", nov: 1200000, conf: "tinggi", codes: ["risiko_stockout_tinggi", "supplier_andal"], short: "Risiko kehabisan stok tinggi. Supplier cukup bisa diandalkan.", warns: [] },
  { id: "SKU012", name: "Beras Premium 5kg", category: "Sembako", qty: 18, unit: 68000, onHand: 6, onOrder: 0, q: [10, 16, 24], before: 0.44, after: 0.09, lmarB: 2650000, lmarA: 520000, wcarB: 410000, wcarA: 1480000, sup: "UD Tani Makmur", otp: 0.91, p90: 4, supNote: "Konsisten tepat waktu sepanjang 3 bulan terakhir.", nov: 1740000, conf: "tinggi", codes: ["risiko_stockout_tinggi", "margin_tinggi"], short: "Penjualan stabil dan stok menipis. Margin per unit besar.", warns: [] },
  { id: "SKU021", name: "Minyak Goreng 2L", category: "Sembako", qty: 24, unit: 34000, onHand: 9, onOrder: 12, q: [16, 23, 33], before: 0.36, after: 0.14, lmarB: 1580000, lmarA: 480000, wcarB: 290000, wcarA: 1010000, sup: "PT Boga Lestari", otp: 0.78, p90: 7, supNote: "Lead time melebar saat akhir bulan.", nov: 890000, conf: "sedang", codes: ["risiko_stockout_tinggi", "lead_time_panjang"], short: "Permintaan naik, tapi supplier kadang telat. Beli lebih awal.", warns: ["Lead time supplier tidak stabil dalam 6 pengiriman terakhir."] },
  { id: "SKU034", name: "Gula Pasir 1kg", category: "Sembako", qty: 30, unit: 15500, onHand: 14, onOrder: 0, q: [20, 28, 38], before: 0.31, after: 0.11, lmarB: 1240000, lmarA: 430000, wcarB: 220000, wcarA: 685000, sup: "UD Tani Makmur", otp: 0.9, p90: 4, supNote: "Pengiriman rutin dua kali seminggu.", nov: 720000, conf: "tinggi", codes: ["permintaan_stabil"], short: "Permintaan stabil, restock rutin menjaga ketersediaan.", warns: [] },
  { id: "SKU045", name: "Teh Celup Isi 25", category: "Minuman", qty: 36, unit: 8500, onHand: 20, onOrder: 0, q: [22, 31, 42], before: 0.27, after: 0.1, lmarB: 860000, lmarA: 300000, wcarB: 170000, wcarA: 476000, sup: "CV Sumber Rasa", otp: 0.86, p90: 5, supNote: "Sesekali kirim sebagian dulu.", nov: 510000, conf: "tinggi", codes: ["permintaan_stabil", "supplier_andal"], short: "Perputaran cepat dengan modal kecil per unit.", warns: [] },
  { id: "SKU052", name: "Mie Instan Goreng", category: "Makanan Ringan", qty: 60, unit: 3200, onHand: 40, onOrder: 24, q: [45, 62, 84], before: 0.33, after: 0.08, lmarB: 940000, lmarA: 230000, wcarB: 180000, wcarA: 372000, sup: "PT Boga Lestari", otp: 0.82, p90: 6, supNote: "Sering kirim lebih cepat dari perkiraan.", nov: 640000, conf: "tinggi", codes: ["perputaran_cepat"], short: "Produk perputaran tercepat di toko ini.", warns: [] },
  { id: "SKU058", name: "Sabun Mandi Batang", category: "Perawatan Diri", qty: 24, unit: 4800, onHand: 11, onOrder: 0, q: [14, 21, 30], before: 0.29, after: 0.12, lmarB: 620000, lmarA: 240000, wcarB: 120000, wcarA: 235000, sup: "CV Harum Sejati", otp: 0.74, p90: 8, supNote: "Dua keterlambatan besar pada Mei 2026.", nov: 330000, conf: "sedang", codes: ["lead_time_panjang"], short: "Stok menipis dan supplier lambat, aman beli sekarang.", warns: ["Riwayat keterlambatan supplier cukup panjang."] },
  { id: "SKU063", name: "Deterjen Bubuk 800g", category: "Kebutuhan Rumah", qty: 20, unit: 16500, onHand: 8, onOrder: 6, q: [12, 18, 26], before: 0.35, after: 0.13, lmarB: 1080000, lmarA: 390000, wcarB: 210000, wcarA: 540000, sup: "CV Harum Sejati", otp: 0.76, p90: 7, supNote: "Kirim mingguan, kadang kurang jumlah.", nov: 590000, conf: "sedang", codes: ["risiko_stockout_tinggi"], short: "Permintaan naik tipis, posisi efektif masih kurang.", warns: [] },
  { id: "SKU070", name: "Susu UHT 1L", category: "Minuman", qty: 24, unit: 18500, onHand: 5, onOrder: 0, q: [15, 22, 31], before: 0.47, after: 0.15, lmarB: 1720000, lmarA: 540000, wcarB: 190000, wcarA: 634000, sup: "PT Segar Nusantara", otp: 0.88, p90: 3, supNote: "Produk mudah rusak, pengiriman dingin.", nov: 980000, conf: "sedang", codes: ["risiko_stockout_tinggi", "umur_simpan_pendek"], short: "Risiko kehabisan paling tinggi, tapi umur simpan pendek.", warns: ["Umur simpan pendek, hindari beli berlebih."] },
  { id: "SKU077", name: "Keripik Singkong 150g", category: "Makanan Ringan", qty: 30, unit: 6800, onHand: 18, onOrder: 0, q: [18, 27, 39], before: 0.24, after: 0.11, lmarB: 540000, lmarA: 220000, wcarB: 130000, wcarA: 334000, sup: "UD Rasa Kampung", otp: 0.69, p90: 9, supNote: "Produsen rumahan, kapasitas terbatas.", nov: 280000, conf: "rendah", codes: ["data_historis_pendek"], short: "Data penjualan baru 6 minggu, perkiraan pakai pola kategori.", warns: ["Data historis pendek, sistem memakai perkiraan kategori."] },
  { id: "SKU081", name: "Tepung Terigu 1kg", category: "Sembako", qty: 24, unit: 11500, onHand: 10, onOrder: 8, q: [14, 21, 29], before: 0.26, after: 0.1, lmarB: 720000, lmarA: 260000, wcarB: 150000, wcarA: 426000, sup: "UD Tani Makmur", otp: 0.92, p90: 4, supNote: "Supplier paling andal untuk kategori ini.", nov: 460000, conf: "tinggi", codes: ["supplier_andal"], short: "Kebutuhan rutin warung makan sekitar, permintaan terjaga.", warns: [] },
  { id: "SKU088", name: "Air Mineral 600ml", category: "Minuman", qty: 72, unit: 2600, onHand: 48, onOrder: 24, q: [55, 74, 98], before: 0.3, after: 0.09, lmarB: 680000, lmarA: 200000, wcarB: 190000, wcarA: 377000, sup: "PT Segar Nusantara", otp: 0.94, p90: 2, supNote: "Kirim harian bila diminta.", nov: 480000, conf: "tinggi", codes: ["perputaran_cepat", "supplier_andal"], short: "Volume besar, biaya per unit rendah, risiko kecil.", warns: [] },
  { id: "SKU093", name: "Pasta Gigi 190g", category: "Perawatan Diri", qty: 18, unit: 13500, onHand: 7, onOrder: 0, q: [10, 16, 23], before: 0.32, after: 0.13, lmarB: 810000, lmarA: 330000, wcarB: 140000, wcarA: 383000, sup: "CV Harum Sejati", otp: 0.79, p90: 6, supNote: "Harga naik 4% bulan lalu.", nov: 420000, conf: "sedang", codes: ["harga_naik"], short: "Harga beli naik, tetap layak karena permintaan tetap.", warns: [] },
  { id: "SKU097", name: "Kecap Manis 600ml", category: "Sembako", qty: 16, unit: 21000, onHand: 9, onOrder: 0, q: [8, 14, 21], before: 0.22, after: 0.09, lmarB: 590000, lmarA: 230000, wcarB: 160000, wcarA: 412000, sup: "PT Boga Lestari", otp: 0.83, p90: 5, supNote: "Pengiriman digabung dengan minyak goreng.", nov: 350000, conf: "tinggi", codes: ["permintaan_stabil"], short: "Permintaan datar, cukup restock jumlah sedang.", warns: [] },
  { id: "SKU104", name: "Tisu Gulung Isi 4", category: "Kebutuhan Rumah", qty: 20, unit: 14500, onHand: 12, onOrder: 0, q: [11, 17, 25], before: 0.2, after: 0.1, lmarB: 480000, lmarA: 210000, wcarB: 180000, wcarA: 424000, sup: "CV Harum Sejati", otp: 0.72, p90: 8, supNote: "Kadang kirim merek pengganti.", nov: 240000, conf: "rendah", codes: ["data_historis_pendek", "substitusi_produk"], short: "Sering tersubstitusi merek lain, perkiraan kurang pasti.", warns: ["Riwayat substitusi produk membuat perkiraan kurang pasti."] },
  { id: "SKU111", name: "Sarden Kaleng 155g", category: "Makanan Ringan", qty: 24, unit: 9800, onHand: 13, onOrder: 0, q: [13, 20, 29], before: 0.25, after: 0.11, lmarB: 620000, lmarA: 250000, wcarB: 150000, wcarA: 385000, sup: "PT Boga Lestari", otp: 0.8, p90: 6, supNote: "Stok pabrik sempat kosong Juni lalu.", nov: 310000, conf: "sedang", codes: ["risiko_pasokan"], short: "Pasokan pabrik pernah kosong, simpan cadangan tipis.", warns: [] },
  { id: "SKU118", name: "Shampo Sachet Isi 12", category: "Perawatan Diri", qty: 40, unit: 5200, onHand: 22, onOrder: 12, q: [26, 37, 52], before: 0.28, after: 0.1, lmarB: 700000, lmarA: 260000, wcarB: 160000, wcarA: 368000, sup: "CV Harum Sejati", otp: 0.77, p90: 7, supNote: "Diskon volume mulai 40 pcs.", nov: 400000, conf: "tinggi", codes: ["diskon_volume"], short: "Ada diskon volume di jumlah ini, biaya per unit turun.", warns: [] },
  { id: "SKU125", name: "Garam Halus 500g", category: "Sembako", qty: 24, unit: 4200, onHand: 16, onOrder: 0, q: [13, 20, 28], before: 0.18, after: 0.08, lmarB: 320000, lmarA: 140000, wcarB: 90000, wcarA: 191000, sup: "UD Tani Makmur", otp: 0.89, p90: 4, supNote: "Tanpa kendala pengiriman.", nov: 180000, conf: "tinggi", codes: ["permintaan_stabil"], short: "Barang murah dengan perputaran tetap, risiko rendah.", warns: [] },
  { id: "SKU131", name: "Pewangi Pakaian 800ml", category: "Kebutuhan Rumah", qty: 12, unit: 17800, onHand: 6, onOrder: 0, q: [6, 10, 16], before: 0.21, after: 0.12, lmarB: 430000, lmarA: 220000, wcarB: 120000, wcarA: 334000, sup: "CV Harum Sejati", otp: 0.7, p90: 9, supNote: "Pengiriman paling lambat di antara supplier lain.", nov: 190000, conf: "rendah", codes: ["data_historis_pendek", "lead_time_panjang"], short: "Produk baru masuk 5 minggu lalu, perkiraan masih kasar.", warns: ["Data historis pendek, sistem memakai perkiraan kategori.", "Lead time supplier panjang."] },
];

export const PLAN_ITEMS: PlanItem[] = SEEDS.map((s, i) => ({
  sku_id: s.id,
  sku_name: s.name,
  category: s.category,
  priority_rank: i + 1,
  recommended_qty: s.qty,
  required_cash_rp: s.qty * s.unit,
  inventory_on_hand: s.onHand,
  inventory_on_order: s.onOrder,
  effective_inventory: s.onHand + s.onOrder,
  forecast_q10: s.q[0],
  forecast_q50: s.q[1],
  forecast_q90: s.q[2],
  stockout_risk_before: s.before,
  stockout_risk_after: s.after,
  lmar_before_rp: s.lmarB,
  lmar_after_rp: s.lmarA,
  incremental_lmar_avoided_rp: s.lmarB - s.lmarA,
  wcar_before_rp: s.wcarB,
  wcar_after_rp: s.wcarA,
  incremental_wcar_added_rp: s.wcarA - s.wcarB,
  supplier_name: s.sup,
  supplier_on_time_probability: s.otp,
  supplier_p90_lead_time_days: s.p90,
  supplier_note: s.supNote,
  expected_nov_contribution_rp: s.nov,
  confidence: s.conf,
  reason_codes: s.codes,
  reasoning_short: s.short,
  reason_more: `Jumlah ${s.qty} unit menutup permintaan sekitar Q90 (${s.q[2]} unit) dikurangi posisi efektif ${s.onHand + s.onOrder} unit, ditambah cadangan untuk lead time ${s.p90} hari.`,
  reason_not_more: `Menambah di atas ${s.qty} unit hanya menurunkan risiko kehabisan sedikit, sementara modal terkunci naik lebih cepat daripada tambahan margin yang diselamatkan.`,
  warnings: s.warns,
  status: "belum_diputuskan",
}));

export function unitCost(item: PlanItem) {
  return Math.round(item.required_cash_rp / Math.max(1, item.recommended_qty));
}

export interface RunRow {
  id: string;
  date: string;
  storeId: string;
  storeName: string;
  budget: number;
  approvedCount: number;
  total: number;
  status: "Selesai" | "Dibatalkan";
  items: Array<{ sku_id: string; sku_name: string; qty: number; subtotal: number }>;
}
