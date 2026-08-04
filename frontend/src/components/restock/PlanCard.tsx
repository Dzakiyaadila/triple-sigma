import { AlertTriangle, Check, Minus, Pencil, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  formatPct,
  formatRupiah,
  formatRupiahShort,
  unitCost,
  type PlanItem,
} from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import { ConfidenceBadge, FlatBadge, Num, RiskBadge } from "./primitives";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function QtyStepper({
  qty,
  onChange,
}: {
  qty: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="inline-flex items-center rounded-[6px] border border-border">
      <button
        type="button"
        aria-label="Kurangi jumlah"
        onClick={() => onChange(Math.max(0, qty - 1))}
        className="px-2 py-1.5 text-muted-foreground transition-colors duration-150 hover:text-foreground"
      >
        <Minus className="h-3.5 w-3.5" />
      </button>
      <input
        value={qty}
        aria-label="Jumlah unit"
        onChange={(e) => onChange(Math.max(0, parseInt(e.target.value.replace(/\D/g, "") || "0", 10)))}
        className="num w-14 border-x border-border bg-transparent py-1.5 text-center text-sm outline-none"
      />
      <button
        type="button"
        aria-label="Tambah jumlah"
        onClick={() => onChange(qty + 1)}
        className="px-2 py-1.5 text-muted-foreground transition-colors duration-150 hover:text-foreground"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

export function PlanCard({ item, editing, onEdit }: { item: PlanItem; editing: boolean; onEdit: () => void }) {
  const { qtyOf, statusOf, setQty, setStatus, setOpenSku, technical } = useRestock();
  const qty = qtyOf(item);
  const status = statusOf(item);
  const cost = qty * unitCost(item);

  return (
    <article
      className={cn(
        "rounded-[8px] border bg-card transition-colors duration-150",
        status === "disetujui"
          ? "border-safe/50"
          : status === "ditolak"
            ? "border-border opacity-60"
            : "border-border",
      )}
    >
      <button
        type="button"
        onClick={() => setOpenSku(item.sku_id)}
        className="w-full px-4 pt-4 text-left"
      >
        <div className="flex flex-wrap items-start gap-2">
          <span className="num mt-0.5 flex h-6 w-6 items-center justify-center rounded-[4px] border border-border bg-muted text-[11px] font-medium">
            {item.priority_rank}
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="font-display text-base font-semibold">{item.sku_name}</h3>
            <p className="text-xs text-muted-foreground">
              <span className="num">{item.sku_id}</span> · {item.category}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <ConfidenceBadge level={item.confidence} />
            <RiskBadge pct={item.stockout_risk_before * 100} />
            {item.warnings.length ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <FlatBadge tone="warn">
                      <AlertTriangle className="h-3 w-3" /> Perlu perhatian
                    </FlatBadge>
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-64 text-xs">
                  {item.warnings.join(" ")}
                </TooltipContent>
              </Tooltip>
            ) : null}
          </div>
        </div>
      </button>

      <div className="space-y-2 px-4 py-3">
        <Row label="Stok saat ini:">
          <Num>{item.inventory_on_hand}</Num>
          <span className="text-muted-foreground">· Stok dalam perjalanan:</span>
          <Num>{item.inventory_on_order}</Num>
          <span className="text-muted-foreground">· Posisi efektif:</span>
          <Num className="font-medium">{item.effective_inventory} unit</Num>
        </Row>
        <Row label="Rekomendasi beli:">
          <Num className="font-medium">{qty} unit</Num>
          <span className="text-muted-foreground">—</span>
          <Num className="font-medium">{formatRupiah(cost)}</Num>
        </Row>

        <div className="grid gap-2 rounded-[6px] border border-border bg-secondary/40 p-3 sm:grid-cols-2">
          <div className="text-xs">
            <p className="text-muted-foreground">Risiko kehabisan</p>
            <p className="mt-0.5">
              <Num className="text-danger">{formatPct(item.stockout_risk_before)}</Num>
              <span className="text-muted-foreground"> → </span>
              <Num className="font-medium text-safe">{formatPct(item.stockout_risk_after)}</Num>
            </p>
          </div>
          <div className="text-xs">
            <p className="text-muted-foreground">Margin berisiko</p>
            <p className="mt-0.5">
              <Num className="text-danger">{formatRupiahShort(item.lmar_before_rp)}</Num>
              <span className="text-muted-foreground"> → </span>
              <Num className="font-medium text-safe">{formatRupiahShort(item.lmar_after_rp)}</Num>
            </p>
          </div>
        </div>

        <Row label="Modal kerja tambahan terkunci:">
          <Num>{formatRupiah(item.incremental_wcar_added_rp)}</Num>
        </Row>

        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>
            Q10 <Num className="text-foreground">{item.forecast_q10}</Num> · Q50{" "}
            <Num className="text-foreground">{item.forecast_q50}</Num> · Q90{" "}
            <Num className="text-foreground">{item.forecast_q90}</Num>
          </span>
          <span className="hidden h-3 w-px bg-border sm:block" />
          <span>
            Kemungkinan tepat waktu{" "}
            <Num className="text-foreground">
              {formatPct(item.supplier_on_time_probability)}
            </Num>{" "}
            · Estimasi kedatangan{" "}
            <Num className="text-foreground">
              {Math.max(1, item.supplier_p90_lead_time_days - 2)}-{item.supplier_p90_lead_time_days}
            </Num>{" "}
            hari
          </span>
        </div>

        {technical ? (
          <div className="grid gap-x-4 gap-y-1 rounded-[6px] border border-info/30 bg-info-soft/60 p-3 text-xs sm:grid-cols-2">
            <p className="text-muted-foreground">
              LMAR dihindari: <Num className="text-foreground">{formatRupiah(item.incremental_lmar_avoided_rp)}</Num>
            </p>
            <p className="text-muted-foreground">
              WCAR: <Num className="text-foreground">{formatRupiah(item.wcar_before_rp)}</Num> →{" "}
              <Num className="text-foreground">{formatRupiah(item.wcar_after_rp)}</Num>
            </p>
            <p className="text-muted-foreground">
              Kontribusi NOV: <Num className="text-foreground">{formatRupiah(item.expected_nov_contribution_rp)}</Num>
            </p>
            <p className="text-muted-foreground">
              P90 lead time: <Num className="text-foreground">{item.supplier_p90_lead_time_days} hari</Num>
            </p>
            <p className="col-span-full text-muted-foreground">
              reason_codes: <span className="num text-foreground">{item.reason_codes.join(", ")}</span>
            </p>
          </div>
        ) : null}

        {editing ? (
          <div className="flex items-center gap-3 pt-1">
            <QtyStepper qty={qty} onChange={(n) => setQty(item.sku_id, n)} />
            <span className="text-xs text-muted-foreground">
              Subtotal <Num className="text-foreground">{formatRupiah(cost)}</Num>
            </span>
          </div>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3">
        <button
          type="button"
          onClick={() => setStatus(item.sku_id, status === "disetujui" ? "belum_diputuskan" : "disetujui")}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-[6px] px-3 text-sm font-medium transition-colors duration-150",
            status === "disetujui"
              ? "bg-safe text-primary-foreground"
              : "bg-accent-gold text-primary-foreground hover:opacity-90",
          )}
        >
          <Check className="h-4 w-4" />
          {status === "disetujui" ? "Disetujui" : "Setujui"}
        </button>
        <button
          type="button"
          onClick={onEdit}
          className="inline-flex h-9 items-center gap-1.5 rounded-[6px] border border-border px-3 text-sm transition-colors duration-150 hover:bg-secondary"
        >
          <Pencil className="h-3.5 w-3.5" />
          {editing ? "Selesai edit" : "Edit"}
        </button>
        <button
          type="button"
          onClick={() => setStatus(item.sku_id, status === "ditolak" ? "belum_diputuskan" : "ditolak")}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-[6px] border px-3 text-sm transition-colors duration-150",
            status === "ditolak"
              ? "border-danger/40 bg-danger-soft text-danger"
              : "border-border hover:bg-secondary",
          )}
        >
          <X className="h-3.5 w-3.5" />
          {status === "ditolak" ? "Ditolak" : "Tolak"}
        </button>
        <button
          type="button"
          onClick={onEdit}
          className="ml-auto text-xs text-muted-foreground underline underline-offset-2 transition-colors duration-150 hover:text-foreground"
        >
          Sesuaikan jumlah
        </button>
      </div>
    </article>
  );
}
