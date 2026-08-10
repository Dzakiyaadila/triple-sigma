import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { type ItemStatus, type PlanItem, type PolicyStyle, type RunRow } from "./plan-data";
import {
  confirmDecisionRun,
  createDecisionRun,
  getDecisionHistory,
  getDatasetProducts,
  getDatasetStores,
  getDemoDatasetReadiness,
  updateRecommendation as apiUpdateRecommendation,
  uploadDataset,
  type ApiRecommendation,
  type DecisionHistoryRowResponse,
  type ProductOption,
  type RecommendationStatus,
  type RestockPlanResponse,
  type StoreOption,
  type UploadIssue,
} from "./api";

export type DatasetKind = "demo" | "upload";
export type ValidationPhase = "idle" | "running" | "done";
export type JobPhase = "idle" | "running" | "done" | "error";

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
  protectedSkus: string[];
}

export interface PlanMeta {
  modelVersion: string;
  dataHash: string;
  budgetAllocatedRp: number;
  expectedNovContributionRp: number;
  estimatedLmarAvoidedRp: number;
  estimatedWcarAddedRp: number;
  estimatedFillRate: number;
  dataQuality: string;
  warnings: string[];
  runtimeMs: number;
}

interface Decision {
  status: ItemStatus;
  qty: number;
  requiredCashRp: number;
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
  jobError: string | null;
  runId: string | null;
  planMeta: PlanMeta | null;
  runPlan: () => void;
  resetRun: () => void;

  items: PlanItem[];
  decisions: Record<string, Decision>;
  qtyOf: (item: PlanItem) => number;
  cashOf: (item: PlanItem) => number;
  statusOf: (item: PlanItem) => ItemStatus;
  setQty: (sku: string, qty: number) => Promise<boolean>;
  setStatus: (sku: string, status: ItemStatus) => Promise<boolean>;
  decisionPending: (sku: string) => boolean;
  decisionError: (sku: string) => string | null;

  cart: Array<{ item: PlanItem; qty: number; subtotal: number }>;
  cartTotal: number;
  overBudget: boolean;

  openSku: string | null;
  setOpenSku: (v: string | null) => void;

  runs: RunRow[];
  historyLoading: boolean;
  historyError: string | null;
  confirmOrder: () => Promise<RunRow>;
  confirmPending: boolean;
  confirmError: string | null;
  hasCompletedRun: boolean;
  lastRun: RunRow | null;
  availableStores: StoreOption[];
  availableProducts: ProductOption[];
  productsLoading: boolean;
  productsError: string | null;
  hasPendingMutations: boolean;
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
    status: r.status as ItemStatus,
  };
}

function toPlanMeta(response: RestockPlanResponse): PlanMeta {
  return {
    modelVersion: response.model_version,
    dataHash: response.data_hash,
    budgetAllocatedRp: response.budget_allocated_rp,
    expectedNovContributionRp: response.expected_nov_contribution_rp,
    estimatedLmarAvoidedRp: response.estimated_lmar_avoided_rp,
    estimatedWcarAddedRp: response.estimated_wcar_added_rp,
    estimatedFillRate: response.estimated_fill_rate,
    dataQuality: response.data_quality,
    warnings: response.warnings,
    runtimeMs: response.runtime_ms,
  };
}

function toRunRow(response: DecisionHistoryRowResponse): RunRow {
  return {
    id: response.id,
    date: response.date,
    storeId: response.store_id,
    storeName: response.store_name,
    budget: response.budget,
    approvedCount: response.approved_count,
    total: response.total,
    status: response.status,
    items: response.items,
  };
}

const RestockCtx = createContext<Ctx | null>(null);

export function RestockProvider({ children }: { children: ReactNode }) {
  const [technical, setTechnical] = useState(false);
  const [dataset, setDataset] = useState<DatasetState | null>(null);
  const [availableStores, setAvailableStores] = useState<StoreOption[]>([]);
  const [availableProducts, setAvailableProducts] = useState<ProductOption[]>([]);
  const [validation, setValidation] = useState<ValidationPhase>("idle");
  const [validationStep, setValidationStep] = useState(0);
  const timers = useRef<number[]>([]);
  const validationRequestId = useRef(0);
  const productRequestId = useRef(0);
  const runRequestId = useRef(0);
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsError, setProductsError] = useState<string | null>(null);

  const [setup, setSetup] = useState<SetupState>({
    storeId: "",
    date: "",
    budget: 3_000_000,
    horizon: 7,
    policy: "seimbang",
    protectedSkus: [],
  });

  const [job, setJob] = useState<JobPhase>("idle");
  const [jobStep, setJobStep] = useState(0);
  const [jobError, setJobError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [planMeta, setPlanMeta] = useState<PlanMeta | null>(null);
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [decisionPendingMap, setDecisionPendingMap] = useState<Record<string, boolean>>({});
  const [decisionErrorMap, setDecisionErrorMap] = useState<Record<string, string | null>>({});
  const decisionInFlight = useRef(new Set<string>());
  const [openSku, setOpenSku] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [confirmPending, setConfirmPending] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const confirmInFlight = useRef(false);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await getDecisionHistory();
      setRuns(response.map(toRunRow));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Riwayat keputusan gagal dimuat.";
      setHistoryError(message);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  const clearTimers = useCallback(() => {
    timers.current.forEach((timer) => window.clearTimeout(timer));
    timers.current = [];
  }, []);

  const clearRunState = useCallback(() => {
    clearTimers();
    runRequestId.current += 1;
    setJob("idle");
    setJobStep(0);
    setJobError(null);
    setRunId(null);
    setPlanMeta(null);
    setPlanItems([]);
    setDecisions({});
    setDecisionPendingMap({});
    setDecisionErrorMap({});
    decisionInFlight.current.clear();
    setOpenSku(null);
    confirmInFlight.current = false;
    setConfirmPending(false);
    setConfirmError(null);
  }, [clearTimers]);

  const chooseDataset = useCallback(
    (kind: DatasetKind, file?: File) => {
      clearRunState();
      const requestId = ++validationRequestId.current;
      setValidation("running");
      setValidationStep(0);
      productRequestId.current += 1;
      setAvailableStores([]);
      setAvailableProducts([]);
      setProductsLoading(false);
      setProductsError(null);

      VALIDATION_STEP_LABELS.forEach((_, index) => {
        timers.current.push(
          window.setTimeout(() => {
            if (validationRequestId.current === requestId) {
              setValidationStep(index);
            }
          }, index * 400),
        );
      });

      const fetchDatasetOptions = async (datasetId: string, datasetState: DatasetState) => {
        const stores = await getDatasetStores(datasetId);
        const selectedStoreId = stores[0]?.store_id ?? "";
        if (!selectedStoreId) {
          throw new Error("Dataset tidak memiliki toko yang dapat dipilih.");
        }
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
            storeId: selectedStoreId,
            date: latestDate ?? "",
            protectedSkus: [],
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
            await fetchDatasetOptions(res.dataset_id, nextDataset);
          })
          .catch((error: unknown) => {
            const message = error instanceof Error ? error.message : "Gagal memuat data demo.";
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

          if (!res.is_ready || !res.dataset_id) return;
          await fetchDatasetOptions(res.dataset_id, nextDataset);
        })
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : "Upload gagal diproses.";
          showFailure(message, file.name);
        });
    },
    [clearRunState],
  );

  const resetDataset = useCallback(() => {
    clearRunState();
    validationRequestId.current += 1;
    productRequestId.current += 1;
    setDataset(null);
    setAvailableStores([]);
    setAvailableProducts([]);
    setProductsLoading(false);
    setProductsError(null);
    setValidation("idle");
    setValidationStep(0);
    setSetup((current) => ({
      ...current,
      storeId: "",
      date: "",
      protectedSkus: [],
    }));
  }, [clearRunState]);

  const updateSetup = useCallback(
    (patch: Partial<SetupState>) => {
      clearRunState();
      setSetup((current) => {
        const next = { ...current, ...patch };
        if (patch.storeId && patch.storeId !== current.storeId) {
          next.protectedSkus = [];
        }
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
    },
    [clearRunState, dataset],
  );

  useEffect(() => {
    if (!dataset || dataset.hasFatal || !dataset.datasetId || !setup.storeId || !setup.date) {
      productRequestId.current += 1;
      setAvailableProducts([]);
      setProductsLoading(false);
      setProductsError(null);
      return;
    }

    const requestId = ++productRequestId.current;
    setAvailableProducts([]);
    setProductsLoading(true);
    setProductsError(null);

    getDatasetProducts(dataset.datasetId, setup.storeId, setup.date)
      .then((products) => {
        if (productRequestId.current !== requestId) return;
        setAvailableProducts(products);
        setProductsLoading(false);
        const validSkuIds = new Set(products.map((product) => product.sku_id));
        setSetup((current) => ({
          ...current,
          protectedSkus: current.protectedSkus.filter((sku) => validSkuIds.has(sku)),
        }));
      })
      .catch((error: unknown) => {
        if (productRequestId.current !== requestId) return;
        const message =
          error instanceof Error ? error.message : "Gagal memuat SKU untuk toko/tanggal terpilih.";
        setAvailableProducts([]);
        setProductsLoading(false);
        setProductsError(message);
        setSetup((current) => ({ ...current, protectedSkus: [] }));
      });
  }, [dataset, setup.date, setup.storeId]);

  const runPlan = useCallback(() => {
    if (!dataset || dataset.hasFatal || !dataset.datasetId || !setup.storeId || !setup.date) {
      return;
    }

    clearTimers();
    const requestId = ++runRequestId.current;
    setJobError(null);
    setJob("running");
    setJobStep(0);
    setRunId(null);
    setPlanMeta(null);
    setPlanItems([]);
    setDecisions({});
    setDecisionPendingMap({});
    setDecisionErrorMap({});
    setConfirmError(null);

    JOB_STEPS.forEach((_, index) => {
      timers.current.push(window.setTimeout(() => setJobStep(index), index * 500));
    });

    createDecisionRun({
      dataset_id: dataset.datasetId,
      store_id: setup.storeId,
      decision_date: setup.date,
      budget_rp: setup.budget,
      horizon_days: setup.horizon,
      policy_preset: setup.policy,
      protected_sku_ids: setup.protectedSkus,
    })
      .then((response) => {
        if (runRequestId.current !== requestId) return;
        setRunId(response.run_id);
        setPlanMeta(toPlanMeta(response));
        setPlanItems(response.recommendations.map(toPlanItem));
        setJob("done");
      })
      .catch((error: unknown) => {
        if (runRequestId.current !== requestId) return;
        const message = error instanceof Error ? error.message : "Gagal membuat rencana restock.";
        setJob("error");
        setJobError(message);
      });
  }, [clearTimers, dataset, setup]);

  const resetRun = useCallback(() => {
    clearRunState();
  }, [clearRunState]);

  const items = useMemo(() => {
    if (job !== "done") return [];
    return planItems;
  }, [job, planItems]);

  const qtyOf = useCallback(
    (item: PlanItem) => decisions[item.sku_id]?.qty ?? item.recommended_qty,
    [decisions],
  );

  const cashOf = useCallback(
    (item: PlanItem) => decisions[item.sku_id]?.requiredCashRp ?? item.required_cash_rp,
    [decisions],
  );

  const statusOf = useCallback(
    (item: PlanItem) => decisions[item.sku_id]?.status ?? item.status,
    [decisions],
  );

  const mutateDecision = useCallback(
    async (sku: string, status: ItemStatus, qty: number): Promise<boolean> => {
      if (!runId || decisionInFlight.current.has(sku)) return false;

      decisionInFlight.current.add(sku);
      const normalizedQty = Math.max(0, Math.trunc(qty));
      setDecisionPendingMap((current) => ({ ...current, [sku]: true }));
      setDecisionErrorMap((current) => ({ ...current, [sku]: null }));

      try {
        const response = await apiUpdateRecommendation(runId, sku, {
          status: status as RecommendationStatus,
          adjusted_qty: normalizedQty,
        });

        setDecisions((current) => ({
          ...current,
          [sku]: {
            status: response.status as ItemStatus,
            qty: response.adjusted_qty ?? normalizedQty,
            requiredCashRp: response.required_cash_rp,
          },
        }));
        return true;
      } catch (error: unknown) {
        const message =
          error instanceof Error ? error.message : "Perubahan keputusan gagal disimpan.";
        setDecisionErrorMap((current) => ({ ...current, [sku]: message }));
        return false;
      } finally {
        decisionInFlight.current.delete(sku);
        setDecisionPendingMap((current) => ({ ...current, [sku]: false }));
      }
    },
    [runId],
  );

  const setQty = useCallback(
    async (sku: string, qty: number) => {
      const item = items.find((candidate) => candidate.sku_id === sku);
      if (!item) return false;
      const currentStatus = statusOf(item);
      const nextStatus: ItemStatus = currentStatus === "disetujui" ? "disetujui" : "diedit";
      return mutateDecision(sku, nextStatus, qty);
    },
    [items, mutateDecision, statusOf],
  );

  const setStatus = useCallback(
    async (sku: string, status: ItemStatus) => {
      const item = items.find((candidate) => candidate.sku_id === sku);
      if (!item) return false;
      return mutateDecision(sku, status, qtyOf(item));
    },
    [items, mutateDecision, qtyOf],
  );

  const decisionPending = useCallback(
    (sku: string) => Boolean(decisionPendingMap[sku]),
    [decisionPendingMap],
  );

  const decisionError = useCallback(
    (sku: string) => decisionErrorMap[sku] ?? null,
    [decisionErrorMap],
  );

  const hasPendingMutations = Object.values(decisionPendingMap).some(Boolean);

  const cart = useMemo(
    () =>
      items
        .filter((item) => statusOf(item) === "disetujui")
        .map((item) => ({
          item,
          qty: qtyOf(item),
          subtotal: cashOf(item),
        })),
    [cashOf, items, qtyOf, statusOf],
  );

  const cartTotal = cart.reduce((sum, entry) => sum + entry.subtotal, 0);
  const overBudget = cartTotal > setup.budget;

  const confirmOrder = useCallback(async () => {
    if (!runId) throw new Error("Run belum tersedia untuk dikonfirmasi.");
    if (hasPendingMutations) {
      throw new Error("Tunggu perubahan SKU selesai disimpan sebelum konfirmasi.");
    }
    if (confirmInFlight.current) throw new Error("Konfirmasi sedang diproses.");

    confirmInFlight.current = true;
    setConfirmPending(true);
    setConfirmError(null);

    try {
      const response = await confirmDecisionRun(runId);
      const store = availableStores.find((candidate) => candidate.store_id === setup.storeId);
      const run: RunRow = {
        id: runId,
        date: setup.date,
        storeId: setup.storeId,
        storeName: store?.store_name ?? setup.storeId,
        budget: setup.budget,
        approvedCount: response.confirmed_count,
        total: response.total_cost_rp,
        status: "Selesai",
        items: cart.map((entry) => ({
          sku_id: entry.item.sku_id,
          sku_name: entry.item.sku_name,
          qty: entry.qty,
          subtotal: entry.subtotal,
        })),
      };

      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      void refreshHistory();
      return run;
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Konfirmasi pesanan gagal.";
      setConfirmError(message);
      throw error;
    } finally {
      confirmInFlight.current = false;
      setConfirmPending(false);
    }
  }, [availableStores, cart, hasPendingMutations, refreshHistory, runId, setup]);

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
    planMeta,
    runPlan,
    resetRun,
    items,
    decisions,
    qtyOf,
    cashOf,
    statusOf,
    setQty,
    setStatus,
    decisionPending,
    decisionError,
    cart,
    cartTotal,
    overBudget,
    openSku,
    setOpenSku,
    runs,
    historyLoading,
    historyError,
    confirmOrder,
    confirmPending,
    confirmError,
    hasCompletedRun: runs.length > 0,
    lastRun: runs[0] ?? null,
    availableStores,
    availableProducts,
    productsLoading,
    productsError,
    hasPendingMutations,
  };

  return <RestockCtx.Provider value={value}>{children}</RestockCtx.Provider>;
}

export function useRestock() {
  const ctx = useContext(RestockCtx);
  if (!ctx) throw new Error("useRestock must be used within RestockProvider");
  return ctx;
}
