import { createFileRoute } from "@tanstack/react-router";
import { MODEL_METRICS, MODEL_VERSION, DATA_DATE } from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import { FlatBadge, Num, SectionTitle, SimDataBadge } from "@/components/restock/primitives";
import { Switch } from "@/components/ui/switch";

export const Route = createFileRoute("/evaluasi")({
  head: () => ({
    meta: [
      { title: "Mode Evaluasi — RestockIQ" },
      { name: "description", content: "Metrik model restock: WMAPE, coverage kuantil, bias, dan service level backtest." },
      { property: "og:title", content: "Mode Evaluasi — RestockIQ" },
      { property: "og:description", content: "Panel teknis untuk memeriksa kualitas perkiraan dan optimasi." },
    ],
  }),
  component: Evaluasi,
});

function Evaluasi() {
  const { technical, setTechnical } = useRestock();
  return (
    <div className="mx-auto max-w-4xl">
      <SectionTitle title="Mode evaluasi" desc="Metrik model dan kualitas perkiraan untuk pengguna teknis" />
      <div className="flex flex-wrap items-center gap-3 rounded-[6px] border border-border bg-card p-4">
        <span className="text-sm">Tampilkan detail teknis lengkap di halaman Rencana Restock</span>
        <Switch checked={technical} onCheckedChange={setTechnical} aria-label="Mode teknis" />
        <FlatBadge tone="info">Teknis</FlatBadge>
        <SimDataBadge className="ml-auto" />
      </div>

      <dl className="mt-4 grid gap-3 sm:grid-cols-3">
        {MODEL_METRICS.map((m) => (
          <div key={m.label} className="rounded-[6px] border border-border bg-card p-4">
            <dt className="text-xs text-muted-foreground">{m.label}</dt>
            <dd className="num mt-1 text-xl font-semibold">{m.value}</dd>
            <p className="mt-1 text-[11px] text-muted-foreground">{m.note}</p>
          </div>
        ))}
      </dl>

      <p className="mt-4 text-xs text-muted-foreground">
        <Num>{MODEL_VERSION}</Num> · Data {DATA_DATE}. Angka di halaman ini masih placeholder, memakai data simulasi terkendali.
      </p>
    </div>
  );
}
