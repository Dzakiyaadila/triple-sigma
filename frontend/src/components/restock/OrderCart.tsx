import { Link } from "@tanstack/react-router";
import { formatRupiah } from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import { GoldButton, Meter, Num, SimDataBadge } from "./primitives";

export function OrderCart() {
  const { cart, cartTotal, setup, overBudget } = useRestock();
  const sisa = setup.budget - cartTotal;

  return (
    <aside className="sticky top-4 rounded-[8px] border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-semibold">Keranjang pesanan</h2>
        <Num className="text-xs text-muted-foreground">{cart.length} SKU</Num>
      </div>

      {cart.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Belum ada item disetujui. Tekan "Setujui" pada rekomendasi untuk menambahkannya.
        </p>
      ) : (
        <ul className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1">
          {cart.map((c) => (
            <li key={c.item.sku_id} className="flex items-baseline justify-between gap-2 text-xs">
              <span className="min-w-0 flex-1 truncate">{c.item.sku_name}</span>
              <Num className="text-muted-foreground">{c.qty}x</Num>
              <Num>{formatRupiah(c.subtotal)}</Num>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 space-y-2 border-t border-border pt-3 text-sm">
        <div className="flex items-baseline justify-between">
          <span className="text-muted-foreground">Total</span>
          <Num className="font-medium">{formatRupiah(cartTotal)}</Num>
        </div>
        <Meter value={cartTotal} max={setup.budget} over={overBudget} />
        <div className="flex items-baseline justify-between text-xs">
          <span className="text-muted-foreground">Sisa modal</span>
          <Num className={overBudget ? "text-danger" : ""}>{formatRupiah(sisa)}</Num>
        </div>
        {overBudget ? (
          <p className="rounded-[4px] border border-danger/40 bg-danger-soft px-2 py-1 text-xs text-danger">
            Total melebihi modal tersedia. Kurangi jumlah atau tolak sebagian item.
          </p>
        ) : null}
      </div>

      <Link to="/konfirmasi" className="mt-4 block">
        <GoldButton className="w-full" disabled={cart.length === 0}>
          Lanjut ke konfirmasi
        </GoldButton>
      </Link>
      <div className="mt-3 flex justify-center">
        <SimDataBadge />
      </div>
    </aside>
  );
}
