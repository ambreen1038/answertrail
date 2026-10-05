import type { ReactNode } from "react";

const CIRC = 2 * Math.PI * 16;

/** A summary card: icon chip, a big number (pass a CountUp as children), a label, a note, and
 *  optionally a progress ring that draws itself in. */
export function Kpi({
  icon,
  label,
  sub,
  delay = 0,
  ring,
  children,
}: {
  icon: ReactNode;
  label: string;
  sub: string;
  delay?: number;
  ring?: number | null;
  children: ReactNode;
}) {
  return (
    <div className="kpi" style={{ animationDelay: `${delay}ms` }}>
      <div className="kpi-top">
        <span className="kpi-icon">{icon}</span>
        {ring !== undefined && ring !== null && <Ring percent={ring} />}
      </div>
      <div className="kpi-value">{children}</div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-sub">{sub}</div>
    </div>
  );
}

export function Ring({ percent }: { percent: number }) {
  const p = Math.max(0, Math.min(100, percent));
  return (
    <svg className="ring" viewBox="0 0 40 40" aria-hidden="true">
      <circle className="ring-bg" cx="20" cy="20" r="16" />
      <circle className="ring-fg" cx="20" cy="20" r="16" strokeDasharray={CIRC} strokeDashoffset={CIRC * (1 - p / 100)} />
    </svg>
  );
}
