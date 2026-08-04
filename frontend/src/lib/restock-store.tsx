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
  DEMO_ISSUES,
  DEMO_SUMMARY,
  PLAN_ITEMS,
  STORES,
  UPLOAD_ISSUES,
  UPLOAD_SUMMARY,
  unitCost,
  type ItemStatus,
  type PlanItem,
  type PolicyStyle,
  type RunRow,
} from "./plan-data";

export type DatasetKind = "demo" | "upload";
export type ValidationPhase = "idle" | "running" | "done";
export type JobPhase = "idle" | "running" | "done" | "error";
export type JobError = "solver_timeout" | null;

export interface DatasetState {
  kind: DatasetKind;
  fileName?: string;
  summary: typeof DEMO_SUMMARY;
  issues: typeof DEMO_ISSUES;
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
  chooseDataset: (kind: DatasetKind, fileName?: string) => void;
  resetDataset: () => void;

  setup: SetupState;
  updateSetup: (patch: Partial<SetupState>) => void;

  job: JobPhase;
  jobStep: number;
  jobError: JobError;
  runPlan: (opts?: { fail?: boolean }) => void;
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

const RestockCtx = createContext<Ctx | null>(null);

const POLICY_FACTOR: Record<PolicyStyle, number> = {
  lindungi_kas: 0.75,
  seimbang: 1,
  lindungi_ketersediaan: 1.2,
};

export function RestockProvider({ children }: { children: ReactNode }) {
  const [technical, setTechnical] = useState(false);
  const [dataset, setDataset] = useState<DatasetState | null>(null);
  const [validation, setValidation] = useState<ValidationPhase>("idle");
  const [validationStep, setValidationStep] = useState(0);
  const timers = useRef<number[]>([]);

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
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [openSku, setOpenSku] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunRow[]>([]);

  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };

  const chooseDataset = useCallback((kind: DatasetKind, fileName?: string) => {
    clearTimers();
    setValidation("running");
    setValidationStep(0);
    VALIDATION_STEP_LABELS.forEach((_, i) => {
      timers.current.push(window.setTimeout(() => setValidationStep(i), i * 650));
    });
    timers.current.push(
      window.setTimeout(() => {
        const issues = kind === "demo" ? DEMO_ISSUES : UPLOAD_ISSUES;
        setDataset({
          kind,
          ...(fileName ? { fileName } : {}),
          summary: kind === "demo" ? DEMO_SUMMARY : UPLOAD_SUMMARY,
          issues,
          hasFatal: issues.some((i) => i.severity === "error"),
        });
        setValidation("done");
      }, VALIDATION_STEP_LABELS.length * 650),
    );
  }, []);

  const resetDataset = useCallback(() => {
    clearTimers();
    setDataset(null);
    setValidation("idle");
    setValidationStep(0);
  }, []);

  const updateSetup = useCallback((patch: Partial<SetupState>) => {
    setSetup((s) => ({ ...s, ...patch }));
  }, []);

  const runPlan = useCallback((opts?: { fail?: boolean }) => {
    clearTimers();
    setJobError(null);
    setJob("running");
    setJobStep(0);
    JOB_STEPS.forEach((_, i) => {
      timers.current.push(window.setTimeout(() => setJobStep(i), i * 700));
    });
    timers.current.push(
      window.setTimeout(() => {
        if (opts?.fail) {
          setJob("error");
          setJobError("solver_timeout");
        } else {
          setJob("done");
        }
      }, JOB_STEPS.length * 700),
    );
  }, []);

  const resetRun = useCallback(() => {
    clearTimers();
    setJob("idle");
    setJobStep(0);
    setJobError(null);
    setDecisions({});
  }, []);

  // Budget + policy aware allocation.
  const items = useMemo(() => {
    if (job !== "done") return [];
    if (setup.budget <= 0) return [];
    const factor = POLICY_FACTOR[setup.policy] * (setup.horizon === 14 ? 1.35 : 1);
    const scaled = PLAN_ITEMS.map((it) => {
      const qty = Math.max(1, Math.round(it.recommended_qty * factor));
      return { ...it, recommended_qty: qty, required_cash_rp: qty * unitCost(it) };
    });
    const list: PlanItem[] = [];
    let spent = 0;
    for (const it of scaled) {
      const isProtected = setup.protectedSkus.includes(it.sku_id);
      if (!isProtected && spent + it.required_cash_rp > setup.budget) continue;
      spent += it.required_cash_rp;
      list.push(it);
    }
    return list.map((it, i) => ({ ...it, priority_rank: i + 1 }));
  }, [job, setup.budget, setup.policy, setup.horizon, setup.protectedSkus]);

  const qtyOf = useCallback(
    (item: PlanItem) => decisions[item.sku_id]?.qty ?? item.recommended_qty,
    [decisions],
  );
  const statusOf = useCallback(
    (item: PlanItem) => decisions[item.sku_id]?.status ?? "belum_diputuskan",
    [decisions],
  );

  const setQty = useCallback((sku: string, qty: number) => {
    setDecisions((d) => ({
      ...d,
      [sku]: { status: d[sku]?.status ?? "belum_diputuskan", qty: Math.max(0, qty) },
    }));
  }, []);

  const setStatus = useCallback((sku: string, status: ItemStatus) => {
    setDecisions((d) => ({ ...d, [sku]: { status, qty: d[sku]?.qty ?? 0 } }));
  }, []);

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
    const store = STORES.find((s) => s.id === setup.storeId)!;
    const run: RunRow = {
      id: `RUN-${Date.now()}`,
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
  }, [cart, cartTotal, setup.budget, setup.date, setup.storeId]);

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
  };

  return <RestockCtx.Provider value={value}>{children}</RestockCtx.Provider>;
}

export function useRestock() {
  const ctx = useContext(RestockCtx);
  if (!ctx) throw new Error("useRestock must be used within RestockProvider");
  return ctx;
}
