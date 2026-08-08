import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Scale, Shield, Wallet } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  POLICY_LABEL,
  formatRupiah,
  parseRupiah,
  type PolicyStyle,
} from "@/lib/plan-data";
import {
  latestSupportedDecisionDate,
  useRestock,
} from "@/lib/restock-store";
import {
  EmptyState,
  FlatBadge,
  GoldButton,
  SectionTitle,
} from "@/components/restock/primitives";

export const Route = createFileRoute("/atur")({
  head: () => ({
    meta: [
      { title: "Atur Keputusan — RestockIQ" },
      {
        name: "description",
        content: "Tentukan toko, tanggal keputusan, modal restock, horizon perkiraan, dan gaya kebijakan.",
      },
      { property: "og:title", content: "Atur Keputusan — RestockIQ" },
      {
        property: "og:description",
        content: "Langkah kedua wizard restock: parameter keputusan sebelum rencana dibuat.",
      },
    ],
  }),
  component: AturKeputusan,
});

const POLICIES: Array<{ id: PolicyStyle; icon: typeof Wallet; desc: string }> = [
  {
    id: "lindungi_kas",
    icon: Wallet,
    desc: "Prioritaskan hemat modal, terima risiko stok lebih tinggi",
  },
  {
    id: "seimbang",
    icon: Scale,
    desc: "Keseimbangan antara modal dan ketersediaan stok",
  },
  {
    id: "lindungi_ketersediaan",
    icon: Shield,
    desc: "Prioritaskan stok tersedia, gunakan modal lebih agresif",
  },
];

function AturKeputusan() {
  const {
    availableProducts,
    availableStores,
    dataset,
    productsError,
    productsLoading,
    runPlan,
    setup,
    updateSetup,
  } = useRestock();
  const navigate = useNavigate();
  const [raw, setRaw] = useState(formatRupiah(setup.budget));

  if (!dataset || dataset.hasFatal) {
    return (
      <div className="mx-auto max-w-3xl">
        <EmptyState
          title="Belum ada data siap"
          desc="Pilih data demo atau unggah data toko yang lolos validasi terlebih dahulu."
          action={
            <GoldButton onClick={() => navigate({ to: "/" })}>
              Kembali ke Pilih Data
            </GoldButton>
          }
        />
      </div>
    );
  }

  const latestDate = latestSupportedDecisionDate(
    dataset.maxDate,
    dataset.calendarMaxDate,
    setup.horizon,
  );
  const canRun = Boolean(
    setup.storeId
    && setup.date
    && latestDate
    && setup.date <= latestDate
    && (!dataset.minDate || setup.date >= dataset.minDate),
  );

  return (
    <div className="mx-auto max-w-3xl">
      <SectionTitle
        title="Atur keputusan"
        desc="Parameter ini menentukan bagaimana rencana restock dihitung"
      />

      <div className="space-y-5 rounded-[6px] border border-border bg-card p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-muted-foreground">Pilih toko</span>
            <select
              value={setup.storeId}
              onChange={(event) => updateSetup({ storeId: event.target.value })}
              className="mt-1 h-10 w-full rounded-[6px] border border-border bg-background px-3 text-sm outline-none focus:border-accent-gold"
            >
              {availableStores.map((store) => (
                <option key={store.store_id} value={store.store_id}>
                  {store.store_name}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="text-muted-foreground">Tanggal keputusan</span>
            <input
              type="date"
              value={setup.date}
              min={dataset.minDate ?? undefined}
              max={latestDate ?? undefined}
              onChange={(event) => updateSetup({ date: event.target.value })}
              className="num mt-1 h-10 w-full rounded-[6px] border border-border bg-background px-3 text-sm outline-none focus:border-accent-gold"
            />
          </label>

          <label className="block text-sm">
            <span className="text-muted-foreground">Modal restock tersedia</span>
            <input
              value={raw}
              placeholder="Rp 3.000.000"
              onChange={(event) => {
                const value = parseRupiah(event.target.value);
                setRaw(value ? formatRupiah(value) : "");
                updateSetup({ budget: value });
              }}
              className="num mt-1 h-10 w-full rounded-[6px] border border-border bg-background px-3 text-right text-sm outline-none focus:border-accent-gold"
            />
          </label>

          <label className="block text-sm">
            <span className="text-muted-foreground">Horizon perkiraan</span>
            <select
              value={setup.horizon}
              onChange={(event) => updateSetup({
                horizon: Number(event.target.value) === 14 ? 14 : 7,
              })}
              className="mt-1 h-10 w-full rounded-[6px] border border-border bg-background px-3 text-sm"
            >
              <option value={7}>7 hari</option>
              <option value={14}>14 hari</option>
            </select>
          </label>
        </div>

        <div>
          <p className="text-sm text-muted-foreground">Prioritas restock</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-3">
            {POLICIES.map((policy) => {
              const active = setup.policy === policy.id;
              return (
                <button
                  key={policy.id}
                  type="button"
                  onClick={() => updateSetup({ policy: policy.id })}
                  className={cn(
                    "rounded-[6px] border p-4 text-left transition-colors duration-150",
                    active
                      ? "border-accent-gold bg-accent-gold-soft"
                      : "border-border hover:bg-secondary/60",
                  )}
                >
                  <policy.icon
                    className={cn(
                      "h-5 w-5",
                      active ? "text-accent-gold" : "text-muted-foreground",
                    )}
                  />
                  <p className="mt-2 text-sm font-medium">
                    {POLICY_LABEL[policy.id]}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">{policy.desc}</p>
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-[6px] border border-border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm">
                Lindungi SKU tertentu{" "}
                <span className="text-xs text-muted-foreground">(opsional)</span>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                SKU yang kamu lindungi akan tetap direkomendasikan minimal 1 unit,
                selama masih ada risiko kehabisan stok. Kalau modal yang kamu masukkan
                ternyata belum cukup untuk memenuhi ini, sistem akan kasih tahu supaya
                kamu bisa naikkan modalnya.
              </p>
            </div>
            <FlatBadge>{setup.protectedSkus.length} dipilih</FlatBadge>
          </div>

          {productsLoading ? (
            <p className="mt-3 text-xs text-muted-foreground">Memuat SKU yang valid untuk keputusan ini…</p>
          ) : productsError ? (
            <p className="mt-3 rounded-[6px] border border-warn/40 bg-warn-soft px-3 py-2 text-xs text-muted-foreground">
              Opsi perlindungan SKU tidak tersedia: {productsError}. Rencana tetap dapat dibuat tanpa protected SKU.
            </p>
          ) : availableProducts.length === 0 ? (
            <p className="mt-3 text-xs text-muted-foreground">Tidak ada SKU yang tersedia untuk toko/tanggal ini.</p>
          ) : (
            <div className="mt-3 max-h-40 overflow-y-auto pr-1">
              <div className="flex flex-wrap gap-2">
                {availableProducts.map((product) => {
                const active = setup.protectedSkus.includes(product.sku_id);
                return (
                  <button
                    key={product.sku_id}
                    type="button"
                    onClick={() => updateSetup({
                      protectedSkus: active
                        ? setup.protectedSkus.filter((sku) => sku !== product.sku_id)
                        : [...setup.protectedSkus, product.sku_id],
                    })}
                    className={cn(
                      "rounded-[6px] border px-2 py-1 text-xs transition-colors duration-150",
                      active
                        ? "border-accent-gold bg-accent-gold-soft text-accent-gold"
                        : "border-border text-muted-foreground hover:bg-secondary",
                    )}
                  >
                    {product.product_name}
                    <span className="num ml-1 text-[10px] opacity-70">
                      {product.sku_id}
                    </span>
                  </button>
                );
                })}
              </div>
            </div>
          )}
        </div>

        {/* <div className="rounded-[6px] border border-info/30 bg-info-soft/40 px-3 py-2 text-xs text-muted-foreground">
          Target service level minimum belum diekspos karena exact optimizer saat ini belum
          menerapkan constraint tersebut. Kontrol sengaja disembunyikan agar UI tidak
          mengirim parameter yang diabaikan backend.
        </div> */}

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
          <GoldButton
            disabled={!canRun || productsLoading}
            onClick={() => {
              runPlan();
              navigate({ to: "/rencana" });
            }}
          >
            Buat Rencana Restock
          </GoldButton>
          <FlatBadge tone="muted">
            {dataset.kind === "demo" ? "Data demo terkendali" : "Data unggahan"}
          </FlatBadge>
        </div>
      </div>
    </div>
  );
}
