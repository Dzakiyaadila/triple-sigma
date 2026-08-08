import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { formatPct, formatRupiah } from "@/lib/plan-data";
import { useRestock } from "@/lib/restock-store";
import {
  EmptyState,
  FlatBadge,
  GoldButton,
  Num,
  SectionTitle,
} from "@/components/restock/primitives";
import { Switch } from "@/components/ui/switch";

export const Route = createFileRoute("/evaluasi")({
  head: () => ({
    meta: [
      { title: "Mode Evaluasi — RestockIQ" },
      {
        name: "description",
        content: "Provenance run dan metrik keputusan nyata dari planner RestockIQ.",
      },
      { property: "og:title", content: "Mode Evaluasi — RestockIQ" },
      {
        property: "og:description",
        content: "Panel teknis untuk memeriksa provenance dan output planner nyata.",
      },
    ],
  }),
  component: Evaluasi,
});

function Evaluasi() {
  const { dataset, planMeta, setup, technical, setTechnical } = useRestock();
  const navigate = useNavigate();

  if (!planMeta) {
    return (
      <div className="mx-auto max-w-4xl">
        <EmptyState
          title="Belum ada run untuk dievaluasi"
          desc="Panel ini hanya menampilkan metadata dan metrik yang benar-benar dikembalikan backend. Buat rencana terlebih dahulu."
          action={
            <GoldButton onClick={() => navigate({ to: dataset ? "/atur" : "/" })}>
              {dataset ? "Buat rencana" : "Pilih data"}
            </GoldButton>
          }
        />
      </div>
    );
  }

  const metrics = [
    {
      label: "Estimated fill rate",
      value: formatPct(planMeta.estimatedFillRate, 1),
      note: "Output risk engine pada allocation terpilih.",
    },
    {
      label: "LMAR dihindari",
      value: formatRupiah(planMeta.estimatedLmarAvoidedRp),
      note: "Expected lost margin risk yang dihindari oleh rencana.",
    },
    {
      label: "WCAR ditambah",
      value: formatRupiah(planMeta.estimatedWcarAddedRp),
      note: "Expected working-capital risk tambahan dari rencana.",
    },
    {
      label: "NOV model",
      value: formatRupiah(planMeta.expectedNovContributionRp),
      note: "Policy-adjusted Rupiah utility yang dipakai exact optimizer.",
    },
    {
      label: "Alokasi model",
      value: formatRupiah(planMeta.budgetAllocatedRp),
      note: `Dari budget ${formatRupiah(setup.budget)}.`,
    },
    {
      label: "Runtime",
      value: `${planMeta.runtimeMs} ms`,
      note: "Runtime planner yang dilaporkan backend untuk run ini.",
    },
  ];

  return (
    <div className="mx-auto max-w-4xl">
      <SectionTitle
        title="Mode evaluasi"
        desc="Provenance dan output teknis run nyata — tanpa metrik placeholder"
      />
      <div className="flex flex-wrap items-center gap-3 rounded-[6px] border border-border bg-card p-4">
        <span className="text-sm">Tampilkan detail teknis lengkap di halaman Rencana Restock</span>
        <Switch checked={technical} onCheckedChange={setTechnical} aria-label="Mode teknis" />
        <FlatBadge tone="info">Teknis</FlatBadge>
        <FlatBadge className="ml-auto">{planMeta.dataQuality}</FlatBadge>
      </div>

      <dl className="mt-4 grid gap-3 sm:grid-cols-3">
        {metrics.map((metric) => (
          <div key={metric.label} className="rounded-[6px] border border-border bg-card p-4">
            <dt className="text-xs text-muted-foreground">{metric.label}</dt>
            <dd className="num mt-1 text-xl font-semibold">{metric.value}</dd>
            <p className="mt-1 text-[11px] text-muted-foreground">{metric.note}</p>
          </div>
        ))}
      </dl>

      <div className="mt-4 rounded-[6px] border border-border bg-card p-4 text-xs text-muted-foreground">
        <p>
          Model: <Num className="break-all text-foreground">{planMeta.modelVersion}</Num>
        </p>
        <p className="mt-1">
          Data hash: <Num className="break-all text-foreground">{planMeta.dataHash}</Num>
        </p>
        <p className="mt-1">
          Decision date: <Num className="text-foreground">{setup.date}</Num>
        </p>
        <p className="mt-3">
          Akurasi backtest (WMAPE, coverage, bias, oracle gap) tidak ditampilkan di halaman ini
          sampai evidence freeze menghasilkan artefak evaluasi yang reproducible. Tidak ada angka
          simulasi yang dipakai sebagai evidence.
        </p>
      </div>
    </div>
  );
}
