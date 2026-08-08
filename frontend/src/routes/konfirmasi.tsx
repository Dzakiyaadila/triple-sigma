import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { CheckCircle2, Download, Loader2 } from "lucide-react";
import { formatRupiah } from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import { exportCsvUrl } from "@/lib/api";
import {
  EmptyState,
  GhostButton,
  GoldButton,
  Num,
  SectionTitle,
} from "@/components/restock/primitives";

export const Route = createFileRoute("/konfirmasi")({
  head: () => ({
    meta: [
      { title: "Konfirmasi & Ekspor — RestockIQ" },
      {
        name: "description",
        content: "Tinjau item disetujui, validasi terhadap modal, lalu ekspor atau konfirmasi pesanan restock.",
      },
      { property: "og:title", content: "Konfirmasi & Ekspor — RestockIQ" },
      {
        property: "og:description",
        content: "Langkah terakhir wizard restock: konfirmasi pesanan dan ekspor daftar pembelian.",
      },
    ],
  }),
  component: Konfirmasi,
});

function Konfirmasi() {
  const {
    cart,
    cartTotal,
    confirmError,
    confirmOrder,
    confirmPending,
    hasPendingMutations,
    overBudget,
    resetRun,
    runId,
    setup,
  } = useRestock();
  const navigate = useNavigate();
  const [done, setDone] = useState<{ count: number; total: number } | null>(null);

  if (done) {
    return (
      <div className="mx-auto max-w-lg text-center">
        <CheckCircle2 className="mx-auto h-10 w-10 text-safe" />
        <h1 className="mt-4 font-display text-2xl font-semibold">Pesanan dikonfirmasi</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Backend mengonfirmasi <Num>{done.count}</Num> SKU senilai{" "}
          <Num>{formatRupiah(done.total)}</Num> untuk {setup.date}.
        </p>
        <div className="mt-6 flex justify-center">
          <GoldButton
            onClick={() => {
              resetRun();
              navigate({ to: "/" });
            }}
          >
            Kembali ke Beranda
          </GoldButton>
        </div>
      </div>
    );
  }

  if (cart.length === 0) {
    return (
      <EmptyState
        title="Belum ada item disetujui"
        desc="Setujui minimal satu rekomendasi pada Rencana Restock."
        action={
          <GoldButton onClick={() => navigate({ to: "/rencana" })}>
            Buka rencana
          </GoldButton>
        }
      />
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <SectionTitle
        title="Konfirmasi & ekspor"
        desc="Daftar ini hanya berisi keputusan yang sudah diterima backend"
      />

      <div className="rounded-[6px] border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th className="px-4 py-2 text-left font-normal">Produk</th>
              <th className="px-4 py-2 text-right font-normal">Jumlah</th>
              <th className="px-4 py-2 text-right font-normal">Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {cart.map((entry) => (
              <tr key={entry.item.sku_id} className="border-b border-border last:border-0">
                <td className="px-4 py-2">{entry.item.sku_name}</td>
                <td className="num px-4 py-2 text-right">{entry.qty}</td>
                <td className="num px-4 py-2 text-right">
                  {formatRupiah(entry.subtotal)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="space-y-1 border-t border-border px-4 py-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Total biaya</span>
            <Num className="font-medium">{formatRupiah(cartTotal)}</Num>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Sisa budget</span>
            <Num className={overBudget ? "text-danger" : ""}>
              {formatRupiah(setup.budget - cartTotal)}
            </Num>
          </div>
        </div>
      </div>

      {overBudget ? (
        <p className="mt-3 rounded-[6px] border border-danger/40 bg-danger-soft px-3 py-2 text-sm text-danger">
          State lokal melebihi budget. Kembali ke Rencana Restock dan sinkronkan keputusan sebelum konfirmasi.
        </p>
      ) : null}

      {hasPendingMutations ? (
        <p className="mt-3 rounded-[6px] border border-info/30 bg-info-soft px-3 py-2 text-sm text-muted-foreground">
          Tunggu perubahan SKU selesai disimpan di backend sebelum ekspor atau konfirmasi.
        </p>
      ) : null}

      {confirmError ? (
        <p className="mt-3 rounded-[6px] border border-danger/40 bg-danger-soft px-3 py-2 text-sm text-danger">
          {confirmError}
        </p>
      ) : null}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <GhostButton
          disabled={!runId || confirmPending || hasPendingMutations}
          onClick={() => {
            if (runId) window.open(exportCsvUrl(runId), "_blank");
          }}
        >
          <Download className="h-4 w-4" />
          Ekspor CSV
        </GhostButton>
        <GoldButton
          disabled={overBudget || confirmPending || hasPendingMutations || !runId}
          onClick={() => {
            void confirmOrder()
              .then((run) => {
                setDone({ count: run.approvedCount, total: run.total });
              })
              .catch(() => {
                // Error text is owned by the provider and rendered above.
              });
          }}
        >
          {confirmPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {confirmPending ? "Mengonfirmasi..." : "Konfirmasi Pesanan"}
        </GoldButton>
      </div>
    </div>
  );
}
