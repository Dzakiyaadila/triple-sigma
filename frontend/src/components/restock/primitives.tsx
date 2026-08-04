import { cn } from "@/lib/utils";
import {
  CONFIDENCE_LABEL,
  RISK_LABEL,
  riskLevel,
  type Confidence,
  type RiskLevel,
} from "@/lib/plan-data";

export function Num({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("num", className)}>{children}</span>;
}

const riskStyles: Record<RiskLevel, string> = {
  aman: "border-safe/40 bg-safe-soft text-safe",
  sedang: "border-warn/50 bg-warn-soft text-[oklch(0.55_0.11_81)]",
  tinggi: "border-danger/40 bg-danger-soft text-danger",
};

export function RiskBadge({ pct, className }: { pct: number; className?: string }) {
  const level = riskLevel(pct);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[4px] border px-2 py-0.5 text-[11px] font-medium tracking-wide uppercase",
        riskStyles[level],
        className,
      )}
    >
      Risiko {RISK_LABEL[level]}
    </span>
  );
}

const confStyles: Record<Confidence, string> = {
  tinggi: "border-safe/40 bg-safe-soft text-safe",
  sedang: "border-border bg-muted text-muted-foreground",
  rendah: "border-warn/50 bg-warn-soft text-[oklch(0.55_0.11_81)]",
};

export function ConfidenceBadge({
  level,
  className,
}: {
  level: Confidence;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[4px] border px-2 py-0.5 text-[11px] font-medium",
        confStyles[level],
        className,
      )}
      title={CONFIDENCE_LABEL[level]}
    >
      Kepercayaan {level.charAt(0).toUpperCase() + level.slice(1)}
    </span>
  );
}

export function FlatBadge({
  children,
  tone = "muted",
  className,
}: {
  children: React.ReactNode;
  tone?: "muted" | "gold" | "safe" | "warn" | "danger" | "info";
  className?: string;
}) {
  const tones = {
    muted: "border-border bg-muted text-muted-foreground",
    gold: "border-accent-gold/40 bg-accent-gold-soft text-accent-gold",
    safe: "border-safe/40 bg-safe-soft text-safe",
    warn: "border-warn/50 bg-warn-soft text-[oklch(0.55_0.11_81)]",
    danger: "border-danger/40 bg-danger-soft text-danger",
    info: "border-info/40 bg-info-soft text-info",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[4px] border px-2 py-0.5 text-[11px] font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function SimDataBadge({ className }: { className?: string }) {
  return (
    <FlatBadge tone="muted" className={cn("tracking-wide uppercase", className)}>
      Data Simulasi Terkendali
    </FlatBadge>
  );
}

export function Meter({
  value,
  max,
  over,
  className,
}: {
  value: number;
  max: number;
  over?: boolean;
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-[2px] bg-secondary", className)}>
      <div
        className={cn("h-full transition-all duration-200", over ? "bg-danger" : "bg-accent-gold")}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function SectionTitle({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {desc ? <p className="mt-1 text-sm text-muted-foreground">{desc}</p> : null}
    </div>
  );
}

export function Panel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-[8px] border border-border bg-card p-5", className)}>
      {children}
    </div>
  );
}

export function EmptyState({
  title,
  desc,
  action,
}: {
  title: string;
  desc: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-[8px] border border-dashed border-border bg-card px-6 py-12 text-center">
      <h3 className="font-display text-base font-semibold">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{desc}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function GoldButton({
  children,
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-[6px] bg-accent-gold px-5 text-sm font-medium text-primary-foreground transition-opacity duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function GhostButton({
  children,
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-[6px] border border-border bg-card px-4 text-sm font-medium transition-colors duration-150 hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-40",
        className,
      )}
    >
      {children}
    </button>
  );
}
