import { useMemo, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Loader2, AlertTriangle, Search } from "lucide-react";
import { CATEGORIES, MODEL_METRICS, formatPct, formatRupiah } from "@/lib/plan-data";
import { JOB_STEP_LABELS, useRestock } from "@/lib/restock-store";
import { PlanCard } from "@/components/restock/PlanCard";
import { OrderCart } from "@/components/restock/OrderCart";
import { EmptyState, FlatBadge, GhostButton, GoldButton, Meter, Num, SimDataBadge } from "@/components/restock/primitives";

export const Route = createFileRoute("/rencana")({
  head: () => ({
    meta: [
      { title: "Rencana Restock — RestockIQ" },
      { name: "description", content: "Rencana restock terurut prioritas dengan risiko sebelum-sesudah, kepercayaan model, dan alokasi modal." },
      { property: "og:title", content: "Rencana Restock — RestockIQ" },
      { property: "og:description", content: "Hasil optimasi alokasi modal restock untuk toko terpilih." },
    ],
  }),
  component: Rencana,
});

function Rencana() {
  const { job, jobStep, jobError, runPlan, items, setup, cart, cartTotal, technical, dataset } = useRestock();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("semua");
  const [risk, setRisk] = useState("semua");
  const [conf, setConf] = useState("semua");
  const [editing, setEditing] = useState<string | null>(null);

  const filtered = useMemo(
    () =>
      items.filter((i) => {
        if (q && !`${i.sku_name} ${i.sku_id}`.toLowerCase().includes(q.toLowerCase())) return false;
        if (cat !== "semua" && i.category !== cat) return false;
        if (conf !== "semua" && i.confidence !== conf) return false;
        if (risk !== "semua") {
          const p = i.stockout_risk_before * 100;
          const lvl = p >= 30 ? "tinggi" : p >= 15 ? "sedang" : "aman";
          if (lvl !== risk) return false;
        }
        return true;
      }),
    [items, q, cat, risk, conf],
  );

  if (!dataset || dataset.hasFatal) {
    return <EmptyState title="Data belum siap" desc="Kembali ke langkah pertama untuk memilih data." action={<GoldButton onClick={() => navigate({ to: "/" })}>Pilih data</GoldButton>} />;
  }

  if (job === "idle") {
    return <EmptyState title="Rencana belum dibuat" desc="Atur parameter keputusan lalu tekan Buat Rencana Restock." action={<GoldButton onClick={() => navigate({ to: "/atur" })}>Atur keputusan</GoldButton>} />;
  }

  if (job === "running") {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
        <Loader2 className="h-8 w-8 animate-spin text-accent-gold" />
        <p className="mt-4 text-sm font-medium">{JOB_STEP_LABELS[jobStep]}</p>
        <p className="mt-1 text-xs text-muted-foreground">Biasanya selesai dalam beberapa detik</p>
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
        desc={jobError === "solver_timeout" ? "Perhitungan memakan waktu lebih lama dari biasanya, coba lagi." : "Terjadi kesalahan tak terduga."}
        action={<GoldButton onClick={() => runPlan()}>Coba lagi</GoldButton>}
      />
    );
  }

  const used = cartTotal;
  const lowConf = items.filter((i) => i.confidence === "rendah").length;
  const fillRate = items.length ? 1 - items.reduce((s, i) => s + i.stockout_risk_after, 0) / items.length : 0;
  const nov = items.reduce((s, i) => s + i.expected_nov_contribution_rp, 0);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0">
        {setup.budget <= 0 ? (
          <EmptyState title="Rencana kosong" desc="Modal restock diisi Rp 0, jadi tidak ada pembelian yang disarankan. Ini bukan error — tambahkan modal untuk melihat rekomendasi." action={<GhostButton onClick={() => navigate({ to: "/atur" })}>Ubah modal</GhostButton>} />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">SKU direkomendasikan</p>
                <Num className="mt-1 block text-xl font-semibold">{items.length}</Num>
              </div>
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Modal terpakai / tersedia</p>
                <p className="mt-1 text-sm"><Num className="font-semibold">{formatRupiah(used)}</Num> <span className="text-muted-foreground">/</span> <Num>{formatRupiah(setup.budget)}</Num></p>
                <Meter className="mt-2" value={used} max={setup.budget} over={used > setup.budget} />
              </div>
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Kontribusi NOV bersih</p>
                <Num className="mt-1 block text-xl font-semibold text-safe">{formatRupiah(nov)}</Num>
              </div>
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Perkiraan fill rate</p>
                <Num className="mt-1 block text-xl font-semibold">{formatPct(fillRate, 1)}</Num>
              </div>
              <div className="rounded-[6px] border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">SKU kepercayaan rendah</p>
                <div className="mt-1"><FlatBadge tone="warn"><Num>{lowConf}</Num> SKU</FlatBadge></div>
              </div>
            </div>

            {technical ? (
              <div className="mt-4 rounded-[6px] border border-info/40 bg-info-soft/50 p-4">
                <div className="flex items-center gap-2">
                  <h2 className="font-display text-sm font-semibold">Panel evaluasi model</h2>
                  <FlatBadge tone="info">Teknis</FlatBadge>
                </div>
                <dl className="mt-3 grid gap-3 sm:grid-cols-3">
                  {MODEL_METRICS.map((m) => (
                    <div key={m.label} className="rounded-[6px] border border-border bg-card p-3">
                      <dt className="text-[11px] text-muted-foreground">{m.label}</dt>
                      <dd className="num mt-1 text-base font-semibold">{m.value}</dd>
                      <p className="mt-1 text-[11px] text-muted-foreground">{m.note}</p>
                    </div>
                  ))}
                </dl>
              </div>
            ) : null}

            {lowConf > 0 ? (
              <p className="mt-4 flex items-start gap-2 rounded-[6px] border border-warn/40 bg-warn-soft px-3 py-2 text-xs">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Data historis sebagian SKU kurang, sistem menggunakan perkiraan kategori.
              </p>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-[6px] border border-border bg-card p-3">
              <div className="relative min-w-40 flex-1">
                <Search className="absolute top-2.5 left-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari SKU" aria-label="Cari SKU" className="h-9 w-full rounded-[6px] border border-border bg-background pl-8 text-sm outline-none focus:border-accent-gold" />
              </div>
              <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Filter kategori" className="h-9 rounded-[6px] border border-border bg-background px-2 text-sm">
                <option value="semua">Semua kategori</option>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Filter risiko" className="h-9 rounded-[6px] border border-border bg-background px-2 text-sm">
                <option value="semua">Semua risiko</option>
                <option value="tinggi">Risiko tinggi</option>
                <option value="sedang">Risiko sedang</option>
                <option value="aman">Risiko aman</option>
              </select>
              <select value={conf} onChange={(e) => setConf(e.target.value)} aria-label="Filter kepercayaan" className="h-9 rounded-[6px] border border-border bg-background px-2 text-sm">
                <option value="semua">Semua kepercayaan</option>
                <option value="tinggi">Tinggi</option>
                <option value="sedang">Sedang</option>
                <option value="rendah">Rendah</option>
              </select>
              <SimDataBadge />
            </div>

            <div className="mt-4 space-y-3">
              {filtered.length === 0 ? (
                <EmptyState title="Tidak ada SKU cocok" desc="Ubah kata kunci atau filter untuk melihat rekomendasi lain." />
              ) : (
                filtered.map((item) => (
                  <PlanCard
                    key={item.sku_id}
                    item={item}
                    editing={editing === item.sku_id}
                    onEdit={() => setEditing(editing === item.sku_id ? null : item.sku_id)}
                  />
                ))
              )}
            </div>
          </>
        )}
      </div>

      <div className="lg:block">
        <OrderCart />
        <p className="mt-2 text-center text-xs text-muted-foreground"><Num>{cart.length}</Num> item disetujui</p>
      </div>
    </div>
  );
}
