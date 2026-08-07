import { X } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DATA_DATE, MODEL_VERSION, formatPct, formatRupiah, unitCost } from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import { ConfidenceBadge, FlatBadge, Num, RiskBadge } from "./primitives";

export function PlanDrawer() {
  const { openSku, setOpenSku, items, qtyOf } = useRestock();
  const item = items.find((i) => i.sku_id === openSku);
  if (!item) return null;
  const qty = qtyOf(item);

  const data = Array.from({ length: 10 }, (_, i) => {
    const drift = 1 + i * 0.03;
    return {
      hari: `H+${i + 1}`,
      q10: Math.round(item.forecast_q10 * drift * 0.98),
      q50: Math.round(item.forecast_q50 * drift),
      q90: Math.round(item.forecast_q90 * drift * 1.02),
    };
  });

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-foreground/25" onClick={() => setOpenSku(null)} aria-hidden />
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
            <h3 className="mb-2 text-sm font-medium">Perkiraan permintaan (Q10/Q50/Q90)</h3>
            <div className="h-52 rounded-[6px] border border-border p-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -18 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="hari" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={{ stroke: "var(--border)" }} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 12 }} />
                  <Area type="monotone" dataKey="q90" stroke="var(--warn)" fill="var(--warn)" fillOpacity={0.12} />
                  <Area type="monotone" dataKey="q50" stroke="var(--accent-gold)" fill="var(--accent-gold)" fillOpacity={0.18} />
                  <Area type="monotone" dataKey="q10" stroke="var(--safe)" fill="var(--safe)" fillOpacity={0.12} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium">Posisi inventori</h3>
            <div className="rounded-[6px] border border-border p-4">
              <div className="flex h-3 w-full overflow-hidden rounded-[6px] bg-secondary">
                <div className="bg-safe" style={{ width: `${(item.inventory_on_hand / (item.effective_inventory + qty)) * 100}%` }} />
                <div className="bg-info" style={{ width: `${(item.inventory_on_order / (item.effective_inventory + qty)) * 100}%` }} />
                <div className="bg-accent-gold" style={{ width: `${(qty / (item.effective_inventory + qty)) * 100}%` }} />
              </div>
              <div className="mt-3 space-y-1 text-xs text-muted-foreground">
                <p>Hari ini · stok di rak <Num className="text-foreground">{item.inventory_on_hand} unit</Num></p>
                <p>H+<Num>{Math.max(1, item.supplier_p90_lead_time_days - 2)}</Num> · stok dalam perjalanan tiba <Num className="text-foreground">{item.inventory_on_order} unit</Num></p>
                <p>H+<Num>{item.supplier_p90_lead_time_days}</Num> · pesanan baru tiba <Num className="text-foreground">{qty} unit</Num></p>
              </div>
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium">Sebelum vs sesudah pesan</h3>
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
                  <td className="num py-2 text-right text-safe">{formatPct(item.stockout_risk_after)}</td>
                </tr>
                <tr className="border-b border-border">
                  <td className="py-2">Margin berisiko (LMAR)</td>
                  <td className="num py-2 text-right">{formatRupiah(item.lmar_before_rp)}</td>
                  <td className="num py-2 text-right text-safe">{formatRupiah(item.lmar_after_rp)}</td>
                </tr>
                <tr>
                  <td className="py-2">Modal terkunci (WCAR)</td>
                  <td className="num py-2 text-right">{formatRupiah(item.wcar_before_rp)}</td>
                  <td className="num py-2 text-right">{formatRupiah(item.wcar_after_rp)}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section className="rounded-[6px] border border-border p-4">
            <h3 className="text-sm font-medium">Keandalan supplier</h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-sm">{item.supplier_name}</span>
              <FlatBadge tone={item.supplier_on_time_probability >= 0.85 ? "safe" : "gold"}>
                Tepat waktu {formatPct(item.supplier_on_time_probability)}
              </FlatBadge>
              <FlatBadge>P90 lead time {item.supplier_p90_lead_time_days} hari</FlatBadge>
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
            <p className="text-sm text-muted-foreground">
              Total biaya pesanan ini <Num className="text-foreground">{formatRupiah(qty * unitCost(item))}</Num>.
            </p>
          </section>

          {item.warnings.length ? (
            <section className="rounded-[6px] border border-warn/40 bg-warn-soft p-3 text-xs">
              {item.warnings.map((w) => (
                <p key={w}>{w}</p>
              ))}
            </section>
          ) : null}

          <div className="flex justify-end pt-2">
            <FlatBadge>{MODEL_VERSION} · Data {DATA_DATE}</FlatBadge>
          </div>
        </div>
      </aside>
    </div>
  );
}
