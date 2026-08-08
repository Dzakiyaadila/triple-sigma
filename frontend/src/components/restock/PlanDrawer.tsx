import { X } from "lucide-react";
import { formatPct, formatRupiah } from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import { ConfidenceBadge, FlatBadge, Num, RiskBadge } from "./primitives";

export function PlanDrawer() {
  const { cashOf, items, openSku, planMeta, qtyOf, setOpenSku, setup } = useRestock();

  if (!openSku) return null;
  const item = items.find((candidate) => candidate.sku_id === openSku);
  if (!item) return null;

  const qty = qtyOf(item);
  const cash = cashOf(item);
  const isAdjusted = qty !== item.recommended_qty;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-foreground/25"
        onClick={() => setOpenSku(null)}
        aria-hidden
      />
      <aside className="relative flex h-full w-full flex-col overflow-y-auto border-l border-border bg-card md:w-[44%] md:min-w-[440px]">
        <div className="flex items-start gap-3 border-b border-border p-5">
          <button
            type="button"
            onClick={() => setOpenSku(null)}
            aria-label="Tutup detail"
            className="mt-1 rounded-[6px] border border-border p-1 text-muted-foreground transition-colors duration-150 hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-xl font-semibold">{item.sku_name}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              <span className="num">{item.sku_id}</span> · {item.category}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <RiskBadge pct={item.stockout_risk_before * 100} />
            <ConfidenceBadge level={item.confidence} />
          </div>
        </div>

        <div className="space-y-6 p-5">
          <section>
            <h3 className="text-sm font-medium">
              Perkiraan permintaan kumulatif H+{setup.horizon}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Model produksi memprediksi kuantil kumulatif langsung. Sistem tidak membuat trajektori
              harian sintetis dari angka kumulatif ini.
            </p>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <div className="rounded-[6px] border border-border p-3">
                <p className="text-xs text-muted-foreground">Q10</p>
                <Num className="mt-1 block text-lg font-semibold">
                  {item.forecast_q10.toFixed(1)}
                </Num>
                <p className="text-[11px] text-muted-foreground">unit</p>
              </div>
              <div className="rounded-[6px] border border-accent-gold/40 bg-accent-gold-soft p-3">
                <p className="text-xs text-muted-foreground">Q50</p>
                <Num className="mt-1 block text-lg font-semibold">
                  {item.forecast_q50.toFixed(1)}
                </Num>
                <p className="text-[11px] text-muted-foreground">unit</p>
              </div>
              <div className="rounded-[6px] border border-border p-3">
                <p className="text-xs text-muted-foreground">Q90</p>
                <Num className="mt-1 block text-lg font-semibold">
                  {item.forecast_q90.toFixed(1)}
                </Num>
                <p className="text-[11px] text-muted-foreground">unit</p>
              </div>
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium">Posisi inventori</h3>
            <div className="grid gap-2 rounded-[6px] border border-border p-4 sm:grid-cols-2">
              <div>
                <p className="text-xs text-muted-foreground">Stok di tangan</p>
                <Num className="mt-1 block text-base font-medium">
                  {item.inventory_on_hand.toFixed(1)} unit
                </Num>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">PO outstanding</p>
                <Num className="mt-1 block text-base font-medium">
                  {item.inventory_on_order.toFixed(1)} unit
                </Num>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Posisi efektif</p>
                <Num className="mt-1 block text-base font-medium">
                  {item.effective_inventory.toFixed(1)} unit
                </Num>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Sudah memasukkan probabilitas kedatangan PO existing.
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">
                  {isAdjusted ? "Jumlah dipilih" : "Rekomendasi baru"}
                </p>
                <Num className="mt-1 block text-base font-medium">{qty} unit</Num>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  P90 lead time supplier {item.supplier_p90_lead_time_days.toFixed(1)} hari.
                </p>
              </div>
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium">Sebelum vs sesudah rekomendasi model</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted-foreground">
                  <th className="py-2 text-left font-normal">Ukuran</th>
                  <th className="py-2 text-right font-normal">Sebelum</th>
                  <th className="py-2 text-right font-normal">Sesudah</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-border">
                  <td className="py-2">Risiko kehabisan</td>
                  <td className="num py-2 text-right">{formatPct(item.stockout_risk_before)}</td>
                  <td className="num py-2 text-right text-safe">
                    {formatPct(item.stockout_risk_after)}
                  </td>
                </tr>
                <tr className="border-b border-border">
                  <td className="py-2">Margin berisiko (LMAR)</td>
                  <td className="num py-2 text-right">{formatRupiah(item.lmar_before_rp)}</td>
                  <td className="num py-2 text-right text-safe">
                    {formatRupiah(item.lmar_after_rp)}
                  </td>
                </tr>
                <tr>
                  <td className="py-2">Modal terkunci (WCAR)</td>
                  <td className="num py-2 text-right">{formatRupiah(item.wcar_before_rp)}</td>
                  <td className="num py-2 text-right">{formatRupiah(item.wcar_after_rp)}</td>
                </tr>
              </tbody>
            </table>
            {isAdjusted ? (
              <p className="mt-2 rounded-[6px] border border-info/30 bg-info-soft/50 px-3 py-2 text-xs text-muted-foreground">
                Nilai “sesudah” dihitung untuk rekomendasi awal {item.recommended_qty} unit. Jumlah
                manual {qty} unit sudah tersimpan di server, tetapi kurva risiko tidak dihitung
                ulang pada endpoint edit saat ini.
              </p>
            ) : null}
          </section>

          <section className="rounded-[6px] border border-border p-4">
            <h3 className="text-sm font-medium">Keandalan supplier</h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-sm">{item.supplier_name}</span>
              <FlatBadge tone={item.supplier_on_time_probability >= 0.85 ? "safe" : "gold"}>
                Tepat waktu {formatPct(item.supplier_on_time_probability)}
              </FlatBadge>
              <FlatBadge>
                P90 lead time {item.supplier_p90_lead_time_days.toFixed(1)} hari
              </FlatBadge>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{item.supplier_note}</p>
          </section>

          <section className="space-y-3">
            <div>
              <h3 className="text-sm font-medium">Kenapa jumlah ini?</h3>
              <p className="mt-1 text-sm text-muted-foreground">{item.reason_more}</p>
            </div>
            <div>
              <h3 className="text-sm font-medium">Kenapa bukan lebih banyak?</h3>
              <p className="mt-1 text-sm text-muted-foreground">{item.reason_not_more}</p>
            </div>
            {isAdjusted ? (
              <p className="text-xs text-muted-foreground">
                Penjelasan di atas merujuk rekomendasi model awal {item.recommended_qty} unit.
              </p>
            ) : null}
            <p className="text-sm text-muted-foreground">
              Biaya keputusan saat ini <Num className="text-foreground">{formatRupiah(cash)}</Num>.
            </p>
          </section>

          {item.warnings.length ? (
            <section className="rounded-[6px] border border-warn/40 bg-warn-soft p-3 text-xs">
              {item.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </section>
          ) : null}

          <div className="flex justify-end pt-2">
            <FlatBadge>
              {planMeta?.modelVersion ?? "Model belum tersedia"} · Keputusan {setup.date}
            </FlatBadge>
          </div>
        </div>
      </aside>
    </div>
  );
}
