import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  detail,
  accent = false,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={`stat-card ${accent ? "border-lime/30 bg-lime/[0.07]" : ""}`}>
      <p className="eyebrow">{label}</p>
      <div className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white tabular">{value}</div>
      {detail && <div className="mt-2 text-xs text-slate-400">{detail}</div>}
    </div>
  );
}

export function Panel({
  title,
  kicker,
  children,
  className = "",
}: {
  title: string;
  kicker?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          {kicker && <p className="eyebrow mb-1">{kicker}</p>}
          <h2 className="text-lg font-semibold tracking-tight text-white">{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}
