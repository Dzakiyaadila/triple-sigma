export type RiskLevel = "aman" | "sedang" | "tinggi";
export type Confidence = "tinggi" | "sedang" | "rendah";
export type ItemStatus = "belum_diputuskan" | "disetujui" | "diedit" | "ditolak";
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

export function riskLevel(pct: number): RiskLevel {
  if (pct >= 30) return "tinggi";
  if (pct >= 15) return "sedang";
  return "aman";
}

export function formatRupiah(n: number) {
  return "Rp " + Math.round(n).toLocaleString("id-ID");
}

export function formatRupiahShort(n: number) {
  if (n >= 1_000_000) {
    return "Rp" + (n / 1_000_000).toFixed(1).replace(".", ",") + "jt";
  }
  if (n >= 1_000) return "Rp" + Math.round(n / 1000) + "rb";
  return "Rp" + Math.round(n);
}

export function parseRupiah(s: string) {
  const digits = s.replace(/\D/g, "");
  return digits ? parseInt(digits, 10) : 0;
}

export function formatPct(v: number, digits = 0) {
  return (v * 100).toFixed(digits).replace(".", ",") + "%";
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
  items: Array<{
    sku_id: string;
    sku_name: string;
    qty: number;
    subtotal: number;
  }>;
}
