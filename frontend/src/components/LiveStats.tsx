"use client";

import { useEffect, useState } from "react";
import CountUp from "./CountUp";
import { EvalReport, fetchEvaluation } from "@/lib/evaluation";

/** The landing page's headline numbers, read live from the backend's real evaluation results
 *  rather than typed in, so they cannot drift from what was actually measured. */
export default function LiveStats() {
  const [report, setReport] = useState<EvalReport | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    fetchEvaluation().then((r) => alive && setReport(r));
    return () => {
      alive = false;
    };
  }, []);

  if (report === undefined) {
    return (
      <div className="stat-row" aria-busy="true" aria-label="Loading results">
        {[0, 1, 2].map((i) => (
          <div key={i} className="stat-tile skeleton-dark" />
        ))}
      </div>
    );
  }
  if (report === null) {
    return <p className="proof-note">The latest evaluation results couldn&apos;t be loaded right now.</p>;
  }

  const t = report.splits.test;
  const tiles = [
    { n: t.correct_answers, of: t.n_answerable, label: "correct, cited answers", sub: "held-out test questions" },
    { n: t.correct_refusals, of: t.n_unanswerable, label: "correct refusals", sub: "questions the docs don't cover" },
    { n: report.totals.invented_answers, of: report.totals.out_of_scope, label: "invented answers", sub: "across every out-of-scope question" },
  ];
  return (
    <div className="stat-row">
      {tiles.map((s, i) => (
        <div key={s.label} className="stat-tile pop" style={{ animationDelay: `${i * 110}ms` }}>
          <div className="stat-big">
            <CountUp value={s.n} />/{s.of}
          </div>
          <div className="stat-label">{s.label}</div>
          <div className="stat-sub">{s.sub}</div>
        </div>
      ))}
    </div>
  );
}
