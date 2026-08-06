const API_BASE =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v2";

interface FastApiValidationError {
  loc?: unknown[];
  msg?: string;
}

interface ApiErrorBody {
  detail?: string | FastApiValidationError[];
  error?: {
    message?: string;
  };
}

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const message =
      extractErrorMessage(body) ?? `Request gagal (${res.status})`;

    throw new Error(message);
  }

  return res.json() as Promise<T>;
}

function extractErrorMessage(body: unknown): string | null {
  if (!body || typeof body !== "object") {
    return null;
  }

  const parsed = body as ApiErrorBody;

  // Format validasi Pydantic FastAPI:
  // { detail: [{ loc, msg, type }, ...] }
  if (Array.isArray(parsed.detail)) {
    return parsed.detail
      .map((item) => {
        const field = item.loc?.slice(1).join(".") ?? "";
        const message = item.msg ?? "Validasi gagal";

        return field ? `${field}: ${message}` : message;
      })
      .join("; ");
  }

  if (typeof parsed.detail === "string") {
    return parsed.detail;
  }

  if (parsed.error?.message) {
    return parsed.error.message;
  }

  return null;
}

export interface DatasetReadinessResponse {
  dataset_id: string;
  source_type: string;
  days_covered: number;
  store_count: number;
  sku_count: number;
  supplier_count: number;
  transaction_count: number;
  is_ready: boolean;
  warnings: string[];
}

export function getDemoDatasetReadiness() {
  return request<DatasetReadinessResponse>("/datasets/demo/readiness");
}

export interface ForecastPoint {
  date: string;
  q10: number;
  q50: number;
  q90: number;
}

export type PolicyPreset =
  | "lindungi_kas"
  | "seimbang"
  | "lindungi_ketersediaan";

export interface ApiRecommendation {
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
  forecast_daily_series?: ForecastPoint[];
  stockout_risk_before: number;
  stockout_risk_after: number;
  lmar_before_rp: number;
  lmar_after_rp: number;
  incremental_lmar_avoided_rp: number;
  wcar_before_rp: number;
  wcar_after_rp: number;
  incremental_wcar_added_rp: number;
  supplier_name: string;
  supplier_note: string;
  supplier_on_time_probability: number;
  supplier_p90_lead_time_days: number;
  expected_nov_contribution_rp: number;
  confidence: "tinggi" | "sedang" | "rendah";
  reason_codes: string[];
  reasoning_short: string;
  reason_more: string;
  reason_not_more: string;
  warnings: string[];
  status: string;
}

export interface RestockPlanResponse {
  run_id: string;
  model_version: string;
  data_hash: string;
  budget_allocated_rp: number;
  expected_nov_contribution_rp: number;
  estimated_lmar_avoided_rp: number;
  estimated_wcar_added_rp: number;
  estimated_fill_rate: number;
  data_quality: string;
  warnings: string[];
  runtime_ms: number;
  recommendations: ApiRecommendation[];
}

export interface CreateDecisionRunPayload {
  dataset_id: string;
  store_id: string;
  decision_date: string;
  budget_rp: number;
  horizon_days: number;
  policy_preset: PolicyPreset;
}

export function createDecisionRun(payload: CreateDecisionRunPayload) {
  return request<RestockPlanResponse>("/decision-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateRecommendation(
  runId: string,
  skuId: string,
  payload: { status: string; adjusted_qty?: number },
) {
  return request(`/decision-runs/${runId}/recommendations/${skuId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function confirmDecisionRun(runId: string) {
  return request<{ confirmed_count: number; confirmed_at: string; total_cost_rp: number }>(
    `/decision-runs/${runId}/confirm`,
    { method: "POST" },
  );
}

export function exportCsvUrl(runId: string) {
  return `${API_BASE}/decision-runs/${runId}/export.csv`;
}

export interface UploadIssue {
  where: string;
  message: string;
  severity: "warning" | "error";
}

export interface DatasetUploadResponse {
  dataset_id: string;
  source_type: string;
  days_covered: number;
  store_count: number;
  sku_count: number;
  supplier_count: number;
  transaction_count: number;
  is_ready: boolean;
  issues: UploadIssue[];
}

export async function uploadDataset(file: File): Promise<DatasetUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/datasets/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = extractErrorMessage(body) ?? `Upload gagal (${res.status})`;
    throw new Error(message);
  }
  return res.json();
}
export interface StoreOption {
  store_id: string;
  store_name: string;
  city?: string;
}

export function getDatasetStores(datasetId: string) {
  return request<StoreOption[]>(`/datasets/${datasetId}/stores`);
}