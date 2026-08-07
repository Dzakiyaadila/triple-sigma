import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Wallet, Scale, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { PLAN_ITEMS, POLICY_LABEL, formatRupiah, parseRupiah, type PolicyStyle } from "@/lib/plan-data";
import { latestSupportedDecisionDate, useRestock } from "@/lib/restock-store";
import { EmptyState, GoldButton, Num, SectionTitle, SimDataBadge } from "@/components/restock/primitives";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";

export const Route = createFileRoute("/atur")({
  head: () => ({
    meta: [
      { title: "Atur Keputusan — RestockIQ" },
      { name: "description", content: "Tentukan toko, tanggal keputusan, modal restock, horizon perkiraan, dan gaya kebijakan." },
      { property: "og:title", content: "Atur Keputusan — RestockIQ" },
      { property: "og:description", content: "Langkah kedua wizard restock: parameter keputusan sebelum rencana dibuat." },
    ],
  }),
  component: AturKeputusan,
});

const POLICIES: Array<{ id: PolicyStyle; icon: typeof Wallet; desc: string }> = [
  { id: "lindungi_kas", icon: Wallet, desc: "Prioritaskan hemat modal, terima risiko stok lebih tinggi" },
  { id: "seimbang", icon: Scale, desc: "Keseimbangan antara modal dan ketersediaan stok" },
  { id: "lindungi_ketersediaan", icon: Shield, desc: "Prioritaskan stok selalu tersedia, gunakan modal lebih besar" },
];

function AturKeputusan() {
  const { dataset, setup, updateSetup, runPlan, availableStores } = useRestock();
  const navigate = useNavigate();
  const [raw, setRaw] = useState(formatRupiah(setup.budget));

  if (!dataset || dataset.hasFatal) {
    return (
      <div className="mx-auto max-w-3xl">
        <EmptyState
          title="Belum ada data siap"
          desc="Pilih data demo atau unggah data toko yang lolos validasi terlebih dahulu."
          action={<GoldButton onClick={() => navigate({ to: "/" })}>Kembali ke Pilih Data</GoldButton>}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <SectionTitle title="Atur keputusan" desc="Parameter ini menentukan bagaimana rencana restock dihitung" />

      <div className="space-y-5 rounded-[6px] border border-border bg-card p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-muted-foreground">Pilih toko</span>
            <select
              value={setup.storeId}
              onChange={(e) => updateSetup({ storeId: e.target.value })}
              className="mt-1 h-10 w-full rounded-[6px] border border-border bg-background px-3 text-sm outline-none focus:border-accent-gold"
            >
              {availableStores.map((s) => (
                <option key={s.store_id} value={s.store_id}>{s.store_name}</option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="text-muted-foreground">Tanggal keputusan</span>
            <input
              type="date"
              value={setup.date}
              min={dataset.minDate ?? undefined}
              max={
                latestSupportedDecisionDate(
                  dataset.maxDate,
                  dataset.calendarMaxDate,
                  setup.horizon,
                ) ?? undefined
              }
              onChange={(e) => updateSetup({ date: e.target.value })}
              className="num mt-1 h-10 w-full rounded-[6px] border border-border bg-background px-3 text-sm outline-none focus:border-accent-gold"
            />
          </label>

          <label className="block text-sm">
            <span className="text-muted-foreground">Modal restock tersedia</span>
            <input
              value={raw}
              placeholder="Rp 3.000.000"
              onChange={(e) => {
                const n = parseRupiah(e.target.value);
                setRaw(n ? formatRupiah(n) : "");
                updateSetup({ budget: n });
              }}
              className="num mt-1 h-10 w-full rounded-[6px] border border-border bg-background px-3 text-right text-sm outline-none focus:border-accent-gold"
            />
          </label>

          <label className="block text-sm">
            <span className="text-muted-foreground">Horizon perkiraan</span>
            <select
              value={setup.horizon}
              onChange={(e) => updateSetup({ horizon: Number(e.target.value) === 14 ? 14 : 7 })}
              className="mt-1 h-10 w-full rounded-[6px] border border-border bg-background px-3 text-sm outline-none focus:border-accent-gold"
            >
              <option value={7}>7 hari</option>
              <option value={14}>14 hari</option>
            </select>
          </label>
        </div>

        <div>
          <p className="text-sm text-muted-foreground">Prioritas restock</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-3">
            {POLICIES.map((p) => {
              const active = setup.policy === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => updateSetup({ policy: p.id })}
                  className={cn(
                    "rounded-[6px] border p-4 text-left transition-colors duration-150",
                    active ? "border-accent-gold bg-accent-gold-soft" : "border-border hover:bg-secondary/60",
                  )}
                >
                  <p.icon className={cn("h-5 w-5", active ? "text-accent-gold" : "text-muted-foreground")} />
                  <p className="mt-2 text-sm font-medium">{POLICY_LABEL[p.id]}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{p.desc}</p>
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-[6px] border border-border p-4">
          <label className="flex items-center justify-between text-sm">
            Tentukan target ketersediaan stok minimum
            <Switch
              checked={setup.serviceLevelOn}
              onCheckedChange={(v) => updateSetup({ serviceLevelOn: v })}
              aria-label="Target service level"
            />
          </label>
          {setup.serviceLevelOn ? (
            <div className="mt-4 flex items-center gap-4">
              <Slider
                value={[setup.serviceLevel]}
                min={70}
                max={99}
                step={1}
                onValueChange={(v) => updateSetup({ serviceLevel: v[0] ?? 90 })}
                className="flex-1"
              />
              <Num className="w-14 text-right text-sm font-medium">{setup.serviceLevel}%</Num>
            </div>
          ) : null}
        </div>

        <div className="rounded-[6px] border border-border p-4">
          <p className="text-sm">Lindungi SKU tertentu <span className="text-xs text-muted-foreground">(opsional)</span></p>
          <p className="mt-1 text-xs text-muted-foreground">SKU ini akan selalu direkomendasikan, meski secara finansial belum tentu paling menguntungkan.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {PLAN_ITEMS.slice(0, 10).map((it) => {
              const active = setup.protectedSkus.includes(it.sku_id);
              return (
                <button
                  key={it.sku_id}
                  type="button"
                  onClick={() =>
                    updateSetup({
                      protectedSkus: active
                        ? setup.protectedSkus.filter((s) => s !== it.sku_id)
                        : [...setup.protectedSkus, it.sku_id],
                    })
                  }
                  className={cn(
                    "rounded-[6px] border px-2 py-1 text-xs transition-colors duration-150",
                    active ? "border-accent-gold bg-accent-gold-soft text-accent-gold" : "border-border text-muted-foreground hover:bg-secondary",
                  )}
                >
                  {it.sku_name}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
          <GoldButton
            onClick={() => {
              runPlan();
              navigate({ to: "/rencana" });
            }}
          >
            Buat Rencana Restock
          </GoldButton>
          <SimDataBadge />
        </div>
      </div>
    </div>
  );
}
