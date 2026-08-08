import type { ReactNode } from "react";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { Home, History, FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRestock } from "@/lib/restock-store";
import { PlanDrawer } from "./PlanDrawer";
import { Switch } from "@/components/ui/switch";
import { TooltipProvider } from "@/components/ui/tooltip";
import { FlatBadge } from "./primitives";

const WIZARD = [
  { to: "/", label: "Pilih Data" },
  { to: "/atur", label: "Atur Keputusan" },
  { to: "/rencana", label: "Rencana Restock" },
  { to: "/konfirmasi", label: "Konfirmasi & Ekspor" },
] as const;

const SIDEBAR = [
  { to: "/", label: "Beranda", icon: Home },
  { to: "/riwayat", label: "Riwayat Keputusan", icon: History },
  { to: "/evaluasi", label: "Mode Evaluasi", icon: FlaskConical, badge: "Teknis" },
] as const;

function WizardProgress({ path }: { path: string }) {
  const { dataset, job } = useRestock();
  const navigate = useNavigate();
  const current = Math.max(
    0,
    WIZARD.findIndex((w) => w.to === path),
  );

  const reachable = (i: number) => {
    if (i === 0) return true;
    if (i === 1) return !!dataset && !dataset.hasFatal;
    if (i === 2) return !!dataset && !dataset.hasFatal && job !== "idle";
    return job === "done";
  };

  return (
    <div className="border-b border-border bg-card">
      <ol className="mx-auto flex max-w-5xl items-center gap-2 px-4 py-4 lg:px-6">
        {WIZARD.map((w, i) => {
          const active = i === current;
          const done = i < current;
          const can = reachable(i);
          return (
            <li key={w.to} className="flex min-w-0 flex-1 items-center gap-2">
              <button
                type="button"
                disabled={!can}
                onClick={() => can && navigate({ to: w.to })}
                className={cn(
                  "flex min-w-0 items-center gap-2 text-left transition-colors duration-150",
                  can ? "cursor-pointer" : "cursor-not-allowed",
                )}
              >
                <span
                  className={cn(
                    "num flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px] border text-[11px] font-medium",
                    active
                      ? "border-accent-gold bg-accent-gold text-primary-foreground"
                      : done
                        ? "border-safe/50 bg-safe-soft text-safe"
                        : "border-border bg-muted text-muted-foreground",
                  )}
                >
                  {i + 1}
                </span>
                <span
                  className={cn(
                    "truncate text-xs sm:text-sm",
                    active ? "font-medium text-foreground" : "text-muted-foreground",
                  )}
                >
                  {w.label}
                </span>
              </button>
              {i < WIZARD.length - 1 ? (
                <span
                  className={cn("hidden h-px flex-1 sm:block", done ? "bg-safe/50" : "bg-border")}
                />
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function TopBar() {
  const { dataset, planMeta, setup, technical, setTechnical } = useRestock();
  return (
    <div className="flex items-center gap-3 border-b border-border bg-card/95 px-4 py-2.5 backdrop-blur lg:px-6">
      <Link to="/" className="font-display text-base font-semibold tracking-tight">
        RestockIQ
      </Link>
      <span className="hidden text-[11px] text-muted-foreground sm:inline">
        Asisten keputusan restock
      </span>
      <div className="ml-auto flex items-center gap-3">
        {dataset ? (
          <span className="hidden rounded-[6px] border border-border bg-muted px-2 py-1 text-[11px] text-muted-foreground sm:inline">
            {planMeta ? "Keputusan" : "Data s.d."}{" "}
            <span className="num">{planMeta ? setup.date : (dataset.maxDate ?? "—")}</span>
          </span>
        ) : null}
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <FlatBadge tone="info">Teknis</FlatBadge>
          <Switch
            checked={technical}
            onCheckedChange={setTechnical}
            aria-label="Mode evaluasi teknis"
          />
        </label>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const isWizard = WIZARD.some((w) => w.to === path);

  return (
    <TooltipProvider delayDuration={150}>
      <div className="min-h-screen bg-background">
        <div className="flex">
          
            <nav className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-border bg-card px-3 py-5 md:flex">
              <div className="px-2 pb-6">
                <span className="font-display text-lg font-semibold tracking-tight">RestockIQ</span>
                <p className="mt-1 text-[11px] text-muted-foreground">Asisten keputusan restock</p>
              </div>
              {SIDEBAR.map((n) => {
                const active = path === n.to;
                return (
                  <Link
                    key={n.to}
                    to={n.to}
                    className={cn(
                      "mb-1 flex items-center gap-3 rounded-[6px] px-3 py-2 text-sm transition-colors duration-150",
                      active
                        ? "bg-secondary font-medium text-foreground"
                        : "text-muted-foreground hover:bg-secondary/60",
                    )}
                  >
                    <n.icon className="h-4 w-4" />
                    {n.label}
                    {"badge" in n && n.badge ? (
                      <span className="num ml-auto rounded-[6px] border border-info/40 bg-info-soft px-1.5 py-0.5 text-[10px] font-medium text-info">
                        {n.badge}
                      </span>
                    ) : null}
                  </Link>
                );
              })}
            </nav>
          

          <div className="min-w-0 flex-1">
            <TopBar />
            {isWizard ? <WizardProgress path={path} /> : null}
            <main className="px-4 py-6 lg:px-6">{children}</main>
          </div>
        </div>

        
          <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-card md:hidden">
            {SIDEBAR.map((n) => {
              const active = path === n.to;
              return (
                <Link
                  key={n.to}
                  to={n.to}
                  className={cn(
                    "flex flex-1 flex-col items-center gap-1 py-2 text-[10px] transition-colors duration-150",
                    active ? "text-accent-gold" : "text-muted-foreground",
                  )}
                >
                  <n.icon className="h-4 w-4" />
                  {n.label}
                </Link>
              );
            })}
          </nav>
        

        <PlanDrawer />
      </div>
    </TooltipProvider>
  );
}
