import type { CSSProperties } from "react";

/** Grey shimmering placeholders shaped like the real content (the way LinkedIn does while a page loads),
 *  so the page has its final layout from the first moment and nothing jumps when the data arrives. */

function Sk({ w = "100%", h = 12, r = 6, style }: { w?: number | string; h?: number; r?: number; style?: CSSProperties }) {
  return <span className="sk" style={{ width: w, height: h, borderRadius: r, ...style }} />;
}

export function AnalyticsSkeleton() {
  const bars = [46, 70, 38, 84, 58, 92, 66];
  return (
    <div aria-busy="true" aria-label="Loading analytics" role="status">
      <div className="kpis">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="kpi kpi-sk" style={{ animationDelay: `${i * 60}ms` }}>
            <div className="kpi-top">
              <Sk w={36} h={36} r={10} />
              {i % 3 === 1 && <Sk w={38} h={38} r={19} />}
            </div>
            <Sk w="46%" h={28} r={8} style={{ marginTop: 4 }} />
            <Sk w="78%" h={12} style={{ marginTop: 12 }} />
            <Sk w="54%" h={10} style={{ marginTop: 8 }} />
          </div>
        ))}
      </div>

      <section className="panel dash-panel">
        <div className="dash-panel-head">
          <Sk w={150} h={16} />
          <Sk w={120} h={12} />
        </div>
        <div className="daily sk-daily">
          {bars.map((h, i) => (
            <div key={i} className="daily-col">
              <Sk w="100%" h={h * 1.2} r={6} style={{ maxWidth: 36 }} />
              <Sk w={28} h={9} />
            </div>
          ))}
        </div>
      </section>

      <div className="dash-two">
        {[0, 1].map((p) => (
          <section key={p} className="panel dash-panel">
            <div className="dash-panel-head">
              <Sk w={p ? 140 : 210} h={16} />
            </div>
            <ul className="gap-list">
              {[0, 1, 2, 3].map((i) => (
                <li key={i} className="gap-row sk-row">
                  <div style={{ flex: 1 }}>
                    <Sk w={`${72 - i * 8}%`} h={13} />
                    <Sk w="42%" h={10} style={{ marginTop: 8 }} />
                  </div>
                  <Sk w={34} h={22} r={11} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

export function DocumentsSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading documents" role="status">
      <DocStatsSkeleton />
      <section className="panel">
        <div className="dz-head">
          <Sk w={36} h={36} r={10} />
          <Sk w={150} h={16} />
        </div>
        <Sk w="86%" h={11} style={{ marginTop: 14 }} />
        <Sk w="100%" h={40} r={10} style={{ marginTop: 14 }} />
      </section>
      <DocListSkeleton />
    </div>
  );
}

export function DocStatsSkeleton() {
  return (
    <div className="stat-strip">
      {[0, 1].map((i) => (
        <div key={i} className="mini-stat">
          <Sk w={36} h={36} r={10} />
          <div style={{ flex: 1 }}>
            <Sk w={44} h={22} r={7} />
            <Sk w={92} h={10} style={{ marginTop: 8 }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function DocListSkeleton() {
  return (
    <section className="panel" aria-busy="true" aria-label="Loading documents">
      <Sk w={130} h={16} style={{ marginBottom: 14 }} />
      <ul className="doc-list">
        {[0, 1, 2, 3, 4].map((i) => (
          <li key={i} className="doc sk-doc">
            <Sk w={42} h={42} r={11} />
            <div style={{ flex: 1 }}>
              <Sk w={`${64 - i * 6}%`} h={14} />
              <Sk w="40%" h={10} style={{ marginTop: 8 }} />
            </div>
            <Sk w={64} h={30} r={8} />
          </li>
        ))}
      </ul>
    </section>
  );
}
