import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, Minus, Pencil, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  formatPct,
  formatRupiah,
  formatRupiahShort,
  type PlanItem,
} from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import { ConfidenceBadge, FlatBadge, Num, RiskBadge } from "./primitives";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function QtyStepper({
  qty,
  onChange,
  disabled = false,
}: {
  qty: number;
  onChange: (n: number) => void;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState(String(qty));

  useEffect(() => {
    setDraft(String(qty));
  }, [qty]);

  const commitDraft = () => {
    const next = Math.max(0, Number.parseInt(draft || "0", 10) || 0);
    setDraft(String(next));
    if (next !== qty) onChange(next);
  };

  return (
    <div className="inline-flex items-center rounded-[6px] border border-border">
      <button
        type="button"
        aria-label="Kurangi jumlah"
        disabled={disabled}
        onClick={() => onChange(Math.max(0, qty - 1))}
        className="px-2 py-1.5 text-muted-foreground transition-colors duration-150 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Minus className="h-3.5 w-3.5" />
      </button>
      <input
        value={draft}
        inputMode="numeric"
        aria-label="Jumlah unit"
        disabled={disabled}
        onChange={(event) => {
          setDraft(event.target.value.replace(/\D/g, ""));
        }}
        onBlur={commitDraft}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setDraft(String(qty));
            event.currentTarget.blur();
          }
        }}
        className="num w-14 border-x border-border bg-transparent py-1.5 text-center text-sm outline-none disabled:cursor-not-allowed disabled:opacity-50"
      />
      <button
        type="button"
        aria-label="Tambah jumlah"
        disabled={disabled}
        onClick={() => onChange(qty + 1)}
        className="px-2 py-1.5 text-muted-foreground transition-colors duration-150 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
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

export function PlanCard({
  item,
  editing,
  onEdit,
}: {
  item: PlanItem;
  editing: boolean;
  onEdit: () => void;
}) {
  const {
    cashOf,
    decisionError,
    decisionPending,
    qtyOf,
    setOpenSku,
    setQty,
    setStatus,
    statusOf,
    technical,
  } = useRestock();
  const qty = qtyOf(item);
  const status = statusOf(item);
  const cost = cashOf(item);
  const pending = decisionPending(item.sku_id);
  const mutationError = decisionError(item.sku_id);
  const isAdjusted = qty !== item.recommended_qty;

  return (
    <article
      className={cn(
        "rounded-[6px] border bg-card transition-colors duration-150",
        status === "disetujui"
          ? "border-safe/50"
          : status === "ditolak"
            ? "border-border opacity-70"
            : "border-border",
      )}
    >
      <button
        type="button"
        onClick={() => setOpenSku(item.sku_id)}
        className="w-full px-4 pt-4 text-left"
      >
        <div className="flex flex-wrap items-start gap-2">
          <span className="num mt-0.5 flex h-6 w-6 items-center justify-center rounded-[6px] border border-border bg-muted text-[11px] font-medium">
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
          <Num className="font-medium">{item.effective_inventory.toFixed(1)} unit</Num>
        </Row>
        <Row label={isAdjusted ? "Jumlah dipilih:" : "Rekomendasi beli:"}>
          <Num className="font-medium">{qty} unit</Num>
          <span className="text-muted-foreground">—</span>
          <Num className="font-medium">{formatRupiah(cost)}</Num>
          {isAdjusted ? (
            <FlatBadge tone="info">Rekomendasi awal {item.recommended_qty} unit</FlatBadge>
          ) : null}
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
          {isAdjusted ? (
            <p className="col-span-full text-[11px] text-muted-foreground">
              Dampak risiko “sesudah” di atas berasal dari rekomendasi model awal {item.recommended_qty} unit.
              Perubahan jumlah manual saat ini hanya mengubah keputusan dan biaya pesanan, bukan menghitung ulang kurva risiko.
            </p>
          ) : null}
        </div>

        <Row label="Modal kerja tambahan terkunci:">
          <Num>{formatRupiah(item.incremental_wcar_added_rp)}</Num>
        </Row>

        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>
            Q10 <Num className="text-foreground">{item.forecast_q10.toFixed(1)}</Num> · Q50{" "}
            <Num className="text-foreground">{item.forecast_q50.toFixed(1)}</Num> · Q90{" "}
            <Num className="text-foreground">{item.forecast_q90.toFixed(1)}</Num>
          </span>
          <span className="hidden h-3 w-px bg-border sm:block" />
          <span>
            Tepat waktu{" "}
            <Num className="text-foreground">
              {formatPct(item.supplier_on_time_probability)}
            </Num>{" "}
            · P90 lead time{" "}
            <Num className="text-foreground">
              {item.supplier_p90_lead_time_days.toFixed(1)} hari
            </Num>
          </span>
        </div>

        {technical ? (
          <div className="grid gap-x-4 gap-y-1 rounded-[6px] border border-info/30 bg-info-soft/60 p-3 text-xs sm:grid-cols-2">
            <p className="text-muted-foreground">
              LMAR dihindari:{" "}
              <Num className="text-foreground">
                {formatRupiah(item.incremental_lmar_avoided_rp)}
              </Num>
            </p>
            <p className="text-muted-foreground">
              WCAR: <Num className="text-foreground">{formatRupiah(item.wcar_before_rp)}</Num> →{" "}
              <Num className="text-foreground">{formatRupiah(item.wcar_after_rp)}</Num>
            </p>
            <p className="text-muted-foreground">
              Kontribusi NOV model:{" "}
              <Num className="text-foreground">
                {formatRupiah(item.expected_nov_contribution_rp)}
              </Num>
            </p>
            <p className="text-muted-foreground">
              P90 lead time:{" "}
              <Num className="text-foreground">
                {item.supplier_p90_lead_time_days.toFixed(1)} hari
              </Num>
            </p>
            <p className="col-span-full text-muted-foreground">
              reason_codes:{" "}
              <span className="num text-foreground">{item.reason_codes.join(", ")}</span>
            </p>
          </div>
        ) : null}

        {editing ? (
          <div className="flex items-center gap-3 pt-1">
            <QtyStepper
              qty={qty}
              disabled={pending}
              onChange={(next) => {
                void setQty(item.sku_id, next);
              }}
            />
            <span className="text-xs text-muted-foreground">
              Subtotal server <Num className="text-foreground">{formatRupiah(cost)}</Num>
            </span>
          </div>
        ) : null}

        {mutationError ? (
          <p className="rounded-[6px] border border-danger/40 bg-danger-soft px-3 py-2 text-xs text-danger">
            {mutationError}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3">
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            void setStatus(
              item.sku_id,
              status === "disetujui" ? "belum_diputuskan" : "disetujui",
            );
          }}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-[6px] px-3 text-sm font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50",
            status === "disetujui"
              ? "bg-safe text-primary-foreground"
              : "bg-accent-gold text-primary-foreground hover:opacity-90",
          )}
        >
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          {status === "disetujui" ? "Disetujui" : "Setujui"}
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={onEdit}
          className="inline-flex h-9 items-center gap-1.5 rounded-[6px] border border-border px-3 text-sm transition-colors duration-150 hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Pencil className="h-3.5 w-3.5" />
          {editing ? "Selesai edit" : "Edit"}
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            void setStatus(
              item.sku_id,
              status === "ditolak" ? "belum_diputuskan" : "ditolak",
            );
          }}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-[6px] border px-3 text-sm transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50",
            status === "ditolak"
              ? "border-danger/40 bg-danger-soft text-danger"
              : "border-border hover:bg-secondary",
          )}
        >
          {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
          {status === "ditolak" ? "Ditolak" : "Tolak"}
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={onEdit}
          className="ml-auto text-xs text-muted-foreground underline underline-offset-2 transition-colors duration-150 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          Sesuaikan jumlah
        </button>
      </div>
    </article>
  );
}
