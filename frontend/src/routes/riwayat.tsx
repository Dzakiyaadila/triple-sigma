import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { formatRupiah } from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import { EmptyState, FlatBadge, Num, SectionTitle } from "@/components/restock/primitives";

export const Route = createFileRoute("/riwayat")({
  head: () => ({
    meta: [
      { title: "Riwayat Keputusan — RestockIQ" },
      {
        name: "description",
        content:
          "Daftar run restock sebelumnya beserta budget, jumlah SKU disetujui, dan ringkasan read-only.",
      },
      { property: "og:title", content: "Riwayat Keputusan — RestockIQ" },
      {
        property: "og:description",
        content: "Telusuri keputusan restock yang pernah dikonfirmasi.",
      },
    ],
  }),
  component: Riwayat,
});

function Riwayat() {
  const { historyError, historyLoading, runs } = useRestock();
  const [openId, setOpenId] = useState<string | null>(null);
  const open = runs.find((r) => r.id === openId);

  return (
    <div className="mx-auto max-w-4xl">
      <SectionTitle
        title="Riwayat keputusan"
        desc="Ringkasan run restock yang pernah dikonfirmasi"
      />
      {historyError ? (
        <p className="mb-4 rounded-[6px] border border-danger/40 bg-danger-soft px-3 py-2 text-sm text-danger">
          Riwayat server tidak dapat dimuat: {historyError}
        </p>
      ) : null}
      {historyLoading && runs.length === 0 ? (
        <EmptyState
          title="Memuat riwayat"
          desc="Mengambil run yang sudah dikonfirmasi dari backend."
        />
      ) : runs.length === 0 ? (
        <EmptyState
          title="Belum ada riwayat"
          desc="Selesaikan satu run restock untuk melihat catatannya di sini."
        />
      ) : (
        <div className="overflow-hidden rounded-[6px] border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="px-4 py-2 text-left font-normal">Tanggal</th>
                <th className="px-4 py-2 text-left font-normal">Toko</th>
                <th className="px-4 py-2 text-right font-normal">Budget</th>
                <th className="px-4 py-2 text-right font-normal">SKU disetujui</th>
                <th className="px-4 py-2 text-right font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setOpenId(r.id)}
                  className="cursor-pointer border-b border-border transition-colors duration-150 last:border-0 hover:bg-secondary/60"
                >
                  <td className="num px-4 py-2">{r.date}</td>
                  <td className="px-4 py-2">{r.storeName}</td>
                  <td className="num px-4 py-2 text-right">{formatRupiah(r.budget)}</td>
                  <td className="num px-4 py-2 text-right">{r.approvedCount}</td>
                  <td className="px-4 py-2 text-right">
                    <FlatBadge tone="safe">{r.status}</FlatBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {open ? (
        <div className="mt-6 rounded-[6px] border border-border bg-card p-5">
          <h2 className="font-display text-lg font-semibold">
            Ringkasan run {open.date} · {open.storeName}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">Tampilan hanya-baca.</p>
          <ul className="mt-3 space-y-1 text-sm">
            {open.items.map((i) => (
              <li key={i.sku_id} className="flex justify-between gap-2">
                <span>{i.sku_name}</span>
                <span>
                  <Num className="text-muted-foreground">{i.qty}x</Num>{" "}
                  <Num>{formatRupiah(i.subtotal)}</Num>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 flex justify-between border-t border-border pt-2 text-sm">
            <span className="text-muted-foreground">Total</span>
            <Num className="font-medium">{formatRupiah(open.total)}</Num>
          </p>
        </div>
      ) : null}
    </div>
  );
}
