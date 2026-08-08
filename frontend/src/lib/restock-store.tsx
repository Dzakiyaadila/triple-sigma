import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  DATA_DATE_ISO,
  STORES,
  unitCost,
  type ItemStatus,
  type PlanItem,
  type PolicyStyle,
  type RunRow,
} from "./plan-data";
import {
  getDemoDatasetReadiness,
  createDecisionRun,
  updateRecommendation as apiUpdateRecommendation,
  confirmDecisionRun,
  uploadDataset,
  getDatasetStores,
  type ApiRecommendation,
  type StoreOption,
  type UploadIssue,
} from "./api";

export type DatasetKind = "demo" | "upload";
export type ValidationPhase = "idle" | "running" | "done";
export type JobPhase = "idle" | "running" | "done" | "error";
export type JobError = "solver_timeout" | null;

export interface DatasetSummary {
  days: number;
  stores: number;
  skus: number;
  suppliers: number;
  rows: number;
}

export interface DatasetState {
  kind: DatasetKind;
  fileName?: string;
  datasetId: string;
  dataHash?: string;
  minDate: string | null;
  maxDate: string | null;
  calendarMinDate: string | null;
  calendarMaxDate: string | null;
  summary: DatasetSummary;
  issues: UploadIssue[];
  hasFatal: boolean;
}

export interface SetupState {
  storeId: string;
  date: string;
  budget: number;
  horizon: 7 | 14;
  policy: PolicyStyle;
  serviceLevelOn: boolean;
  serviceLevel: number;
  protectedSkus: string[];
}

interface Decision {
  status: ItemStatus;
  qty: number;
}

interface Ctx {
  technical: boolean;
  setTechnical: (v: boolean) => void;

  dataset: DatasetState | null;
  validation: ValidationPhase;
  validationStep: number;
  chooseDataset: (kind: DatasetKind, file?: File) => void;
  resetDataset: () => void;

  setup: SetupState;
  updateSetup: (patch: Partial<SetupState>) => void;

  job: JobPhase;
  jobStep: number;
  jobError: JobError;
  runId: string | null;
  runPlan: () => void;
  resetRun: () => void;

  items: PlanItem[];
  decisions: Record<string, Decision>;
  qtyOf: (item: PlanItem) => number;
  statusOf: (item: PlanItem) => ItemStatus;
  setQty: (sku: string, qty: number) => void;
  setStatus: (sku: string, status: ItemStatus) => void;

  cart: Array<{ item: PlanItem; qty: number; subtotal: number }>;
  cartTotal: number;
  overBudget: boolean;

  openSku: string | null;
  setOpenSku: (v: string | null) => void;

  runs: RunRow[];
  confirmOrder: () => RunRow;
  hasCompletedRun: boolean;
  lastRun: RunRow | null;
  availableStores: StoreOption[];
}

const JOB_STEPS = [
  "Memvalidasi data...",
  "Menghitung perkiraan permintaan...",
  "Menganalisis risiko...",
  "Mengoptimalkan alokasi modal...",
];

export const JOB_STEP_LABELS = JOB_STEPS;
export const VALIDATION_STEP_LABELS = [
  "Memvalidasi struktur data...",
  "Memeriksa kelengkapan kolom...",
  "Menyiapkan ringkasan...",
];

function shiftIsoDate(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) return isoDate;

  const value = new Date(Date.UTC(year, month - 1, day));
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

export function latestSupportedDecisionDate(
  datasetMaxDate: string | null,
  calendarMaxDate: string | null,
  horizonDays: number,
): string | null {
  if (!datasetMaxDate || !calendarMaxDate) return null;

  const calendarBound = shiftIsoDate(calendarMaxDate, -horizonDays);
  return datasetMaxDate < calendarBound ? datasetMaxDate : calendarBound;
}

const RestockCtx = createContext<Ctx | null>(null);

function toPlanItem(r: ApiRecommendation): PlanItem {
  return {
    sku_id: r.sku_id,
    sku_name: r.sku_name,
    category: r.category,
    priority_rank: r.priority_rank,
    recommended_qty: r.recommended_qty,
    required_cash_rp: r.required_cash_rp,
    inventory_on_hand: r.inventory_on_hand,
    inventory_on_order: r.inventory_on_order,
    effective_inventory: r.effective_inventory,
    forecast_q10: r.forecast_q10,
    forecast_q50: r.forecast_q50,
    forecast_q90: r.forecast_q90,
    stockout_risk_before: r.stockout_risk_before,
    stockout_risk_after: r.stockout_risk_after,
    lmar_before_rp: r.lmar_before_rp,
    lmar_after_rp: r.lmar_after_rp,
    incremental_lmar_avoided_rp: r.incremental_lmar_avoided_rp,
    wcar_before_rp: r.wcar_before_rp,
    wcar_after_rp: r.wcar_after_rp,
    incremental_wcar_added_rp: r.incremental_wcar_added_rp,
    supplier_name: r.supplier_name,
    supplier_on_time_probability: r.supplier_on_time_probability,
    supplier_p90_lead_time_days: r.supplier_p90_lead_time_days,
    supplier_note: r.supplier_note,
    expected_nov_contribution_rp: r.expected_nov_contribution_rp,
    confidence: r.confidence,
    reason_codes: r.reason_codes,
    reasoning_short: r.reasoning_short,
    reason_more: r.reason_more,
    reason_not_more: r.reason_not_more,
    warnings: r.warnings,
    status: "belum_diputuskan",
  };
}

export function RestockProvider({ children }: { children: ReactNode }) {
  const [technical, setTechnical] = useState(false);
  const [dataset, setDataset] = useState<DatasetState | null>(null);
  const [availableStores, setAvailableStores] = useState<StoreOption[]>([]);
  const [validation, setValidation] = useState<ValidationPhase>("idle");
  const [validationStep, setValidationStep] = useState(0);
  const timers = useRef<number[]>([]);
  const validationRequestId = useRef(0);

  const [setup, setSetup] = useState<SetupState>({
    storeId: STORES[0]!.id,
    date: DATA_DATE_ISO,
    budget: 3000000,
    horizon: 7,
    policy: "seimbang",
    serviceLevelOn: false,
    serviceLevel: 90,
    protectedSkus: [],
  });

  const [job, setJob] = useState<JobPhase>("idle");
  const [jobStep, setJobStep] = useState(0);
  const [jobError, setJobError] = useState<JobError>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [openSku, setOpenSku] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunRow[]>([]);

  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };
  const chooseDataset = useCallback((kind: DatasetKind, file?: File) => {
    clearTimers();
    const requestId = ++validationRequestId.current;
    setValidation("running");
    setValidationStep(0);
    setAvailableStores([]);

    VALIDATION_STEP_LABELS.forEach((_, index) => {
      timers.current.push(
        window.setTimeout(() => {
          if (validationRequestId.current === requestId) {
            setValidationStep(index);
          }
        }, index * 400),
      );
    });

    const applyStores = (stores: StoreOption[], datasetState: DatasetState) => {
      if (validationRequestId.current !== requestId) return;

      setAvailableStores(stores);
      setSetup((current) => {
        const latestDate = latestSupportedDecisionDate(
          datasetState.maxDate,
          datasetState.calendarMaxDate,
          current.horizon,
        );

        return {
          ...current,
          storeId: stores.some((store) => store.store_id === current.storeId)
            ? current.storeId
            : (stores[0]?.store_id ?? current.storeId),
          date: latestDate ?? current.date,
        };
      });
    };

    const showFailure = (message: string, fileName?: string) => {
      if (validationRequestId.current !== requestId) return;

      setDataset({
        kind,
        ...(fileName ? { fileName } : {}),
        datasetId: "",
        minDate: null,
        maxDate: null,
        calendarMinDate: null,
        calendarMaxDate: null,
        summary: { days: 0, stores: 0, skus: 0, suppliers: 0, rows: 0 },
        issues: [
          {
            where: fileName ?? "Data demo",
            message,
            severity: "error",
          },
        ],
        hasFatal: true,
      });
      setValidation("done");
    };

    if (kind === "demo") {
      getDemoDatasetReadiness()
        .then(async (res) => {
          if (validationRequestId.current !== requestId) return;

          const nextDataset: DatasetState = {
            kind: "demo",
            datasetId: res.dataset_id,
            minDate: res.min_date,
            maxDate: res.max_date,
            calendarMinDate: res.calendar_min_date,
            calendarMaxDate: res.calendar_max_date,
            summary: {
              days: res.days_covered,
              stores: res.store_count,
              skus: res.sku_count,
              suppliers: res.supplier_count,
              rows: res.transaction_count,
            },
            issues: res.warnings.map((warning) => ({
              where: "Data demo",
              message: warning,
              severity: "warning" as const,
            })),
            hasFatal: !res.is_ready,
          };

          setDataset(nextDataset);
          setValidation("done");

          if (!res.is_ready) return;
          const stores = await getDatasetStores(res.dataset_id);
          applyStores(stores, nextDataset);
        })
        .catch((error: unknown) => {
          const message = error instanceof Error
            ? error.message
            : "Gagal memuat data demo.";
          showFailure(message);
        });
      return;
    }

    if (!file) {
      setValidation("idle");
      return;
    }

    uploadDataset(file)
      .then(async (res) => {
        if (validationRequestId.current !== requestId) return;

        const nextDataset: DatasetState = {
          kind: "upload",
          fileName: file.name,
          datasetId: res.dataset_id,
          ...(res.data_hash ? { dataHash: res.data_hash } : {}),
          minDate: res.min_date,
          maxDate: res.max_date,
          calendarMinDate: res.calendar_min_date,
          calendarMaxDate: res.calendar_max_date,
          summary: {
            days: res.days_covered,
            stores: res.store_count,
            skus: res.sku_count,
            suppliers: res.supplier_count,
            rows: res.transaction_count,
          },
          issues: res.issues,
          hasFatal: !res.is_ready,
        };

        setDataset(nextDataset);
        setValidation("done");

        // Structured validation failures intentionally return HTTP 200 so the
        // report stays visible. There is no dataset identity/store lookup yet.
        if (!res.is_ready || !res.dataset_id) return;

        const stores = await getDatasetStores(res.dataset_id);
        applyStores(stores, nextDataset);
      })
      .catch((error: unknown) => {
        const message = error instanceof Error
          ? error.message
          : "Upload gagal diproses.";
        showFailure(message, file.name);
      });
  }, []);

  const resetDataset = useCallback(() => {
    clearTimers();
    validationRequestId.current += 1;
    setDataset(null);
    setAvailableStores([]);
    setValidation("idle");
    setValidationStep(0);
  }, []);

  const updateSetup = useCallback((patch: Partial<SetupState>) => {
    setSetup((current) => {
      const next = { ...current, ...patch };
      const latestDate = latestSupportedDecisionDate(
        dataset?.maxDate ?? null,
        dataset?.calendarMaxDate ?? null,
        next.horizon,
      );

      if (latestDate && next.date > latestDate) {
        next.date = latestDate;
      }
      if (dataset?.minDate && next.date < dataset.minDate) {
        next.date = dataset.minDate;
      }

      return next;
    });
  }, [dataset]);

  const runPlan = useCallback(() => {
    if (!dataset || dataset.hasFatal || !dataset.datasetId || !setup.storeId) return;
    clearTimers();
    setJobError(null);
    setJob("running");
    setJobStep(0);
    JOB_STEPS.forEach((_, i) => {
      timers.current.push(window.setTimeout(() => setJobStep(i), i * 500));
    });

    createDecisionRun({
      dataset_id: dataset.datasetId,
      store_id: setup.storeId,
      decision_date: setup.date,
      budget_rp: setup.budget,
      horizon_days: setup.horizon,
      policy_preset: setup.policy,
      min_fill_rate: setup.serviceLevelOn ? setup.serviceLevel / 100 : null,
      protected_sku_ids: setup.protectedSkus,
    })
      .then((res) => {
        setRunId(res.run_id);
        setPlanItems(res.recommendations.map(toPlanItem));
        setJob("done");
      })
      .catch((err) => {
        console.error("Gagal membuat rencana restock:", err);
        setJob("error");
        setJobError("solver_timeout");
      });
  }, [dataset, setup]);

  const resetRun = useCallback(() => {
    clearTimers();
    setJob("idle");
    setJobStep(0);
    setJobError(null);
    setRunId(null);
    setPlanItems([]);
    setDecisions({});
  }, []);

  const items = useMemo(() => {
    if (job !== "done") return [];
    return planItems;
  }, [job, planItems]);

  const qtyOf = useCallback(
    (item: PlanItem) => decisions[item.sku_id]?.qty ?? item.recommended_qty,
    [decisions],
  );
  const statusOf = useCallback(
    (item: PlanItem) => decisions[item.sku_id]?.status ?? "belum_diputuskan",
    [decisions],
  );

  const setQty = useCallback(
    (sku: string, qty: number) => {
      setDecisions((d) => {
        const status = d[sku]?.status ?? "belum_diputuskan";
        const next = { ...d, [sku]: { status, qty: Math.max(0, qty) } };
        if (runId && status === "disetujui") {
          apiUpdateRecommendation(runId, sku, { status, adjusted_qty: Math.max(0, qty) }).catch(
            (err) => console.error("Gagal menyimpan perubahan jumlah:", err),
          );
        }
        return next;
      });
    },
    [runId],
  );

  const setStatus = useCallback(
    (sku: string, status: ItemStatus) => {
      setDecisions((d) => {
        const item = items.find((i) => i.sku_id === sku);
        const qty = d[sku]?.qty ?? item?.recommended_qty ?? 0;
        const next = { ...d, [sku]: { status, qty } };
        if (runId) {
          apiUpdateRecommendation(runId, sku, { status, adjusted_qty: qty }).catch((err) =>
            console.error("Gagal menyimpan status keputusan:", err),
          );
        }
        return next;
      });
    },
    [runId, items],
  );

  const cart = useMemo(
    () =>
      items
        .filter((i) => statusOf(i) === "disetujui")
        .map((item) => {
          const qty = qtyOf(item);
          return { item, qty, subtotal: qty * unitCost(item) };
        }),
    [items, statusOf, qtyOf],
  );
  const cartTotal = cart.reduce((s, c) => s + c.subtotal, 0);
  const overBudget = cartTotal > setup.budget;

  const confirmOrder = useCallback(() => {
    const store = availableStores.find((s) => s.store_id === setup.storeId);

    if (runId) {
      confirmDecisionRun(runId).catch((err) =>
        console.error("Gagal konfirmasi ke server:", err),
      );
    }

    const run: RunRow = {
      id: runId ?? `RUN-${Date.now()}`,
      date: setup.date,
      storeId: setup.storeId,
      storeName: store.name,
      budget: setup.budget,
      approvedCount: cart.length,
      total: cartTotal,
      status: "Selesai",
      items: cart.map((c) => ({
        sku_id: c.item.sku_id,
        sku_name: c.item.sku_name,
        qty: c.qty,
        subtotal: c.subtotal,
      })),
    };
    setRuns((r) => [run, ...r]);
    return run;
  }, [cart, cartTotal, setup.budget, setup.date, setup.storeId, runId]);

  const value: Ctx = {
    technical,
    setTechnical,
    dataset,
    validation,
    validationStep,
    chooseDataset,
    resetDataset,
    setup,
    updateSetup,
    job,
    jobStep,
    jobError,
    runId,
    runPlan,
    resetRun,
    items,
    decisions,
    qtyOf,
    statusOf,
    setQty,
    setStatus,
    cart,
    cartTotal,
    overBudget,
    openSku,
    setOpenSku,
    runs,
    confirmOrder,
    hasCompletedRun: runs.length > 0,
    lastRun: runs[0] ?? null,
    availableStores,
  };

  return <RestockCtx.Provider value={value}>{children}</RestockCtx.Provider>;
}

export function useRestock() {
  const ctx = useContext(RestockCtx);
  if (!ctx) throw new Error("useRestock must be used within RestockProvider");
  return ctx;
}