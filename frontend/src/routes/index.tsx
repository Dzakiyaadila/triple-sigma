import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Store, Upload, CheckCircle2, AlertTriangle, Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRestock, VALIDATION_STEP_LABELS } from "@/lib/restock-store";
import { FlatBadge, GhostButton, GoldButton, Num, SectionTitle, SimDataBadge } from "@/components/restock/primitives";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Pilih Data — RestockIQ" },
      { name: "description", content: "Mulai run restock dengan data simulasi bawaan atau unggah data transaksi toko sendiri." },
      { property: "og:title", content: "Pilih Data — RestockIQ" },
      { property: "og:description", content: "Langkah pertama: pilih sumber data dan periksa laporan kesiapan data." },
    ],
  }),
  component: PilihData,
});

function PilihData() {
  const { dataset, validation, validationStep, chooseDataset, resetDataset } = useRestock();
  const [drag, setDrag] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="mx-auto max-w-5xl">
      <SectionTitle title="Mulai dengan data toko" desc="Gunakan data simulasi atau unggah data toko kamu sendiri" />

      <div className="grid gap-4 md:grid-cols-2">
        <div className={cn("relative rounded-[8px] border bg-card p-5", dataset?.kind === "demo" ? "border-accent-gold" : "border-border")}>
          <SimDataBadge className="absolute top-4 right-4" />
          <Store className="h-6 w-6 text-accent-gold" />
          <h2 className="mt-3 font-display text-lg font-semibold">Gunakan Data Demo</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            <Num>5</Num> toko simulasi, <Num>31</Num> produk, siap pakai
          </p>
          <GoldButton className="mt-4" onClick={() => chooseDataset("demo")}>
            Pilih Data Demo
          </GoldButton>
        </div>

        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const file = e.dataTransfer.files[0];
            if (file) chooseDataset("upload", file);
          }}
          className={cn("rounded-[8px] border bg-card p-5", dataset?.kind === "upload" ? "border-accent-gold" : "border-border")}
        >
          <Upload className="h-6 w-6 text-accent-gold" />
          <h2 className="mt-3 font-display text-lg font-semibold">Unggah Data Toko</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            CSV histori transaksi harian untuk toko dan produk yang sudah terdaftar di sistem
          </p>
          <label
            className={cn(
              "mt-4 flex cursor-pointer flex-col items-center justify-center rounded-[6px] border border-dashed px-4 py-6 text-center text-xs transition-colors duration-150",
              drag ? "border-accent-gold bg-accent-gold-soft" : "border-border bg-secondary/40",
            )}
          >
            <Upload className="mb-2 h-4 w-4 text-muted-foreground" />
            Tarik file ke sini atau klik untuk memilih
            <input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) chooseDataset("upload", file);
              }}
            />
          </label>
          <button
            type="button"
            className="mt-3 text-xs text-accent-gold underline underline-offset-2"
            onClick={() => {
              const header = "date,store_id,sku_id,units_sold,stock_on_hand_start,stock_on_hand_end,stockout_flag,promo_flag";
              const example = "2024-01-01,S01,SKU001,12,50,38,False,False";
              const blob = new Blob([header + "\n" + example], { type: "text/csv" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = "template_upload_restockiq.csv";
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download className="mr-1 inline h-3 w-3" />Unduh template
          </button>
        </div>
      </div>

      {validation === "running" ? (
        <div className="mt-6 rounded-[8px] border border-border bg-card p-5">
          <p className="text-sm">{VALIDATION_STEP_LABELS[validationStep]}</p>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-[2px] bg-secondary">
            <div
              className="h-full bg-accent-gold transition-all duration-200"
              style={{ width: `${((validationStep + 1) / VALIDATION_STEP_LABELS.length) * 100}%` }}
            />
          </div>
        </div>
      ) : null}

      {validation === "done" && dataset ? (
        <div className="mt-6 rounded-[8px] border border-border bg-card p-5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-lg font-semibold">Laporan Kesiapan Data</h2>
            {dataset.fileName ? <FlatBadge>{dataset.fileName}</FlatBadge> : <SimDataBadge />}
            <GhostButton className="ml-auto h-8" onClick={resetDataset}>Ganti sumber data</GhostButton>
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[
              ["Hari tercakup", dataset.summary.days],
              ["Toko", dataset.summary.stores],
              ["SKU", dataset.summary.skus],
              ["Supplier", dataset.summary.suppliers],
              ["Baris transaksi", dataset.summary.rows],
            ].map(([label, val]) => (
              <div key={label as string} className="rounded-[6px] border border-border p-3">
                <dt className="text-[11px] text-muted-foreground">{label}</dt>
                <dd className="num mt-1 text-lg font-semibold">{(val as number).toLocaleString("id-ID")}</dd>
              </div>
            ))}
          </dl>

          {dataset.issues.length ? (
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted-foreground">
                  <th className="py-2 text-left font-normal">Lokasi</th>
                  <th className="py-2 text-left font-normal">Keterangan</th>
                  <th className="py-2 text-right font-normal">Tingkat</th>
                </tr>
              </thead>
              <tbody>
                {dataset.issues.map((iss) => (
                  <tr key={iss.where} className="border-b border-border last:border-0">
                    <td className="py-2 align-top text-xs">{iss.where}</td>
                    <td className="py-2 align-top text-xs text-muted-foreground">{iss.message}</td>
                    <td className="py-2 text-right">
                      <FlatBadge tone={iss.severity === "error" ? "danger" : "warn"}>
                        {iss.severity === "error" ? "Error" : "Warning"}
                      </FlatBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">Tidak ada isu validasi ditemukan.</p>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <GoldButton disabled={dataset.hasFatal} onClick={() => navigate({ to: "/atur" })}>
              Lanjutkan
            </GoldButton>
            {dataset.hasFatal ? (
              <p className="flex items-center gap-2 text-xs text-danger">
                <AlertTriangle className="h-4 w-4" />
                Perbaiki dulu: isi kolom unit_cost yang kosong dan hapus SKU yang belum dikenal sistem, lalu unggah ulang.
              </p>
            ) : (
              <p className="flex items-center gap-2 text-xs text-safe">
                <CheckCircle2 className="h-4 w-4" /> Data siap dipakai untuk membuat rencana restock.
              </p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
