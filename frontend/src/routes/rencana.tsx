import { useMemo, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { AlertTriangle, Loader2, Search } from "lucide-react";
import { formatPct, formatRupiah } from "@/lib/plan-data";
import { JOB_STEP_LABELS, useRestock } from "@/lib/restock-store";
import { PlanCard } from "@/components/restock/PlanCard";
import { OrderCart } from "@/components/restock/OrderCart";
import {
  EmptyState,
  FlatBadge,
  GhostButton,
  GoldButton,
  Meter,
  Num,
} from "@/components/restock/primitives";

export const Route = createFileRoute("/rencana")({
  head: () => ({
    meta: [
      { title: "Rencana Restock — RestockIQ" },
      {
        name: "description",
        content: "Rencana restock terurut prioritas berdasarkan demand, supplier risk, dan batas modal.",
      },
      { property: "og:title", content: "Rencana Restock — RestockIQ" },
      {
        property: "og:description",
        content: "Hasil optimasi alokasi modal restock untuk toko terpilih.",
      },
    ],
  }),
  component: Rencana,
});

function Rencana() {
  const {
    cart,
    cartTotal,
    dataset,
    items,
    job,
    jobError,
    jobStep,
    planMeta,
    runPlan,
    setup,
    technical,
  } = useRestock();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("semua");
  const [risk, setRisk] = useState("semua");
  const [conf, setConf] = useState("semua");
  const [editing, setEditing] = useState<string | null>(null);

  const categories = useMemo(
    () => Array.from(new Set(items.map((item) => item.category))).sort(),
    [items],
  );

  const filtered = useMemo(
    () =>
      items.filter((item) => {
        if (
          q
          && !`${item.sku_name} ${item.sku_id}`
            .toLowerCase()
            .includes(q.toLowerCase())
        ) {
          return false;
        }
        if (cat !== "semua" && item.category !== cat) return false;
        if (conf !== "semua" && item.confidence !== conf) return false;
        if (risk !== "semua") {
          const probability = item.stockout_risk_before * 100;
          const level = probability >= 30
            ? "tinggi"
            : probability >= 15
              ? "sedang"
              : "aman";
          if (level !== risk) return false;
        }
        return true;
      }),
    [items, q, cat, risk, conf],
  );

  if (!dataset || dataset.hasFatal) {
    return (
      <EmptyState
        title="Data belum siap"
        desc="Kembali ke langkah pertama untuk memilih data."
        action={<GoldButton onClick={() => navigate({ to: "/" })}>Pilih data</GoldButton>}
      />
    );
  }

  if (job === "idle") {
    return (
      <EmptyState
        title="Rencana belum dibuat"
        desc="Atur parameter keputusan lalu tekan Buat Rencana Restock."
        action={
          <GoldButton onClick={() => navigate({ to: "/atur" })}>
            Atur keputusan
          </GoldButton>
        }
      />
    );
  }

  if (job === "running") {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
        <Loader2 className="h-8 w-8 animate-spin text-accent-gold" />
        <p className="mt-4 text-sm font-medium">{JOB_STEP_LABELS[jobStep]}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Backend sedang menjalankan pipeline demand → supplier risk → MCKP.
        </p>
        <div className="mt-4 w-64">
          <Meter value={jobStep + 1} max={JOB_STEP_LABELS.length} />
        </div>
      </div>
    );
  }

  if (job === "error") {
    return (
      <EmptyState
        title="Perhitungan gagal"
        desc={jobError ?? "Terjadi kesalahan tak terduga."}
        action={<GoldButton onClick={() => runPlan()}>Coba lagi</GoldButton>}
      />
    );
  }

  if (!planMeta) {
    return (
      <EmptyState
        title="Metadata rencana tidak tersedia"
        desc="Response backend tidak lengkap. Jalankan ulang rencana sebelum mengambil keputusan."
        action={<GoldButton onClick={() => runPlan()}>Jalankan ulang</GoldButton>}
      />
    );
  }

  const lowConf = items.filter((item) => item.confidence === "rendah").length;
  const recommendedCount = items.filter((item) => item.recommended_qty > 0).length;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0">
        {setup.budget <= 0 ? (
          <EmptyState
            title="Rencana kosong"
            desc="Modal restock diisi Rp 0, jadi tidak ada pembelian yang disarankan. Tambahkan modal untuk melihat rekomendasi."
            action={
              <GhostButton onClick={() => navigate({ to: "/atur" })}>
                Ubah modal
              </GhostButton>
            }
          />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">SKU dengan qty rekomendasi &gt; 0</p>
                <Num className="mt-1 block text-xl font-semibold">{recommendedCount}</Num>
              </div>
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Alokasi model / modal tersedia</p>
                <p className="mt-1 text-sm">
                  <Num className="font-semibold">
                    {formatRupiah(planMeta.budgetAllocatedRp)}
                  </Num>{" "}
                  <span className="text-muted-foreground">/</span>{" "}
                  <Num>{formatRupiah(setup.budget)}</Num>
                </p>
                <Meter
                  className="mt-2"
                  value={planMeta.budgetAllocatedRp}
                  max={setup.budget}
                  over={planMeta.budgetAllocatedRp > setup.budget}
                />
              </div>
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Kontribusi NOV model</p>
                <Num className="mt-1 block text-xl font-semibold text-safe">
                  {formatRupiah(planMeta.expectedNovContributionRp)}
                </Num>
              </div>
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Perkiraan fill rate</p>
                <Num className="mt-1 block text-xl font-semibold">
                  {formatPct(planMeta.estimatedFillRate, 1)}
                </Num>
              </div>
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">SKU kepercayaan rendah</p>
                <div className="mt-1">
                  <FlatBadge tone={lowConf > 0 ? "warn" : "safe"}>
                    <Num>{lowConf}</Num> SKU
                  </FlatBadge>
                </div>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <FlatBadge tone="muted">
                {dataset.kind === "demo" ? "Data demo terkendali" : "Data unggahan"}
              </FlatBadge>
              <span>
                Pesanan yang sudah disetujui user:{" "}
                <Num className="text-foreground">{formatRupiah(cartTotal)}</Num> ·{" "}
                <Num className="text-foreground">{cart.length}</Num> SKU
              </span>
            </div>

            {technical ? (
              <div className="mt-4 rounded-[6px] border border-info/40 bg-info-soft/50 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-display text-sm font-semibold">Provenance run</h2>
                  <FlatBadge tone="info">Teknis</FlatBadge>
                  <FlatBadge className="ml-auto">{planMeta.dataQuality}</FlatBadge>
                </div>
                <dl className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  <div className="rounded-[6px] border border-border bg-card p-3">
                    <dt className="text-[11px] text-muted-foreground">Model</dt>
                    <dd className="num mt-1 break-all text-xs font-medium">
                      {planMeta.modelVersion}
                    </dd>
                  </div>
                  <div className="rounded-[6px] border border-border bg-card p-3">
                    <dt className="text-[11px] text-muted-foreground">Runtime</dt>
                    <dd className="num mt-1 text-base font-semibold">
                      {planMeta.runtimeMs} ms
                    </dd>
                  </div>
                  <div className="rounded-[6px] border border-border bg-card p-3">
                    <dt className="text-[11px] text-muted-foreground">Data hash</dt>
                    <dd className="num mt-1 break-all text-xs font-medium">
                      {planMeta.dataHash.slice(0, 16)}…
                    </dd>
                  </div>
                  <div className="rounded-[6px] border border-border bg-card p-3">
                    <dt className="text-[11px] text-muted-foreground">LMAR dihindari</dt>
                    <dd className="num mt-1 text-base font-semibold">
                      {formatRupiah(planMeta.estimatedLmarAvoidedRp)}
                    </dd>
                  </div>
                  <div className="rounded-[6px] border border-border bg-card p-3">
                    <dt className="text-[11px] text-muted-foreground">WCAR ditambah</dt>
                    <dd className="num mt-1 text-base font-semibold">
                      {formatRupiah(planMeta.estimatedWcarAddedRp)}
                    </dd>
                  </div>
                  <div className="rounded-[6px] border border-border bg-card p-3">
                    <dt className="text-[11px] text-muted-foreground">Decision date</dt>
                    <dd className="num mt-1 text-base font-semibold">{setup.date}</dd>
                  </div>
                </dl>
              </div>
            ) : null}

            {lowConf > 0 ? (
              <p className="mt-4 flex items-start gap-2 rounded-[6px] border border-warn/40 bg-warn-soft px-3 py-2 text-xs">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Sebagian SKU memiliki confidence rendah. Buka detail SKU untuk melihat warning model.
              </p>
            ) : null}

            {planMeta.warnings.length ? (
              <div className="mt-4 rounded-[6px] border border-warn/40 bg-warn-soft px-3 py-2 text-xs">
                {planMeta.warnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-[6px] border border-border bg-card p-3">
              <div className="relative min-w-40 flex-1">
                <Search className="absolute top-2.5 left-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <input
                  value={q}
                  onChange={(event) => setQ(event.target.value)}
                  placeholder="Cari SKU"
                  aria-label="Cari SKU"
                  className="h-9 w-full rounded-[6px] border border-border bg-background pl-8 text-sm outline-none focus:border-accent-gold"
                />
              </div>
              <select
                value={cat}
                onChange={(event) => setCat(event.target.value)}
                aria-label="Filter kategori"
                className="h-9 rounded-[6px] border border-border bg-background px-2 text-sm"
              >
                <option value="semua">Semua kategori</option>
                {categories.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
              <select
                value={risk}
                onChange={(event) => setRisk(event.target.value)}
                aria-label="Filter risiko"
                className="h-9 rounded-[6px] border border-border bg-background px-2 text-sm"
              >
                <option value="semua">Semua risiko</option>
                <option value="tinggi">Risiko tinggi</option>
                <option value="sedang">Risiko sedang</option>
                <option value="aman">Risiko aman</option>
              </select>
              <select
                value={conf}
                onChange={(event) => setConf(event.target.value)}
                aria-label="Filter kepercayaan"
                className="h-9 rounded-[6px] border border-border bg-background px-2 text-sm"
              >
                <option value="semua">Semua kepercayaan</option>
                <option value="tinggi">Tinggi</option>
                <option value="sedang">Sedang</option>
                <option value="rendah">Rendah</option>
              </select>
            </div>

            <div className="mt-4 space-y-3">
              {filtered.length === 0 ? (
                <EmptyState
                  title="Tidak ada SKU cocok"
                  desc="Ubah kata kunci atau filter untuk melihat rekomendasi lain."
                />
              ) : (
                filtered.map((item) => (
                  <PlanCard
                    key={item.sku_id}
                    item={item}
                    editing={editing === item.sku_id}
                    onEdit={() => setEditing(
                      editing === item.sku_id ? null : item.sku_id,
                    )}
                  />
                ))
              )}
            </div>
          </>
        )}
      </div>

      <div className="lg:block">
        <OrderCart />
        <p className="mt-2 text-center text-xs text-muted-foreground">
          <Num>{cart.length}</Num> item disetujui dan tersimpan di backend
        </p>
      </div>
    </div>
  );
}
