"use client";

import { useEffect, useState } from "react";
import AdminGate from "@/components/AdminGate";
import AdminHero from "@/components/AdminHero";
import CountUp from "@/components/CountUp";
import { ChatIcon, GaugeIcon, InsightIcon, ThumbUpIcon } from "@/components/Icons";
import { Kpi } from "@/components/Kpi";
import { AnalyticsSkeleton } from "@/components/Skeletons";
import { adminFetch, errorDetail } from "@/lib/adminApi";

type Analytics = {
  totals: {
    questions: number;
    answered: number;
    refused: number;
    answered_rate: number | null;
    conversations: number;
    avg_latency_ms: number | null;
    median_latency_ms: number | null;
    thumbs_up: number;
    thumbs_down: number;
  };
  daily: { date: string; questions: number; answered: number }[];
  unanswered: { question: string; count: number; last_seen: string }[];
  downvoted: { question: string; answer: string; comment: string | null; at: string }[];
};

export default function AnalyticsPage() {
  return (
    <div className="page wide">
      <AdminHero
        title="Analytics"
        subtitle="What customers ask and where the help articles fall short. The unanswered list is your to-do list of articles to write."
      />
      <AdminGate loading={<AnalyticsSkeleton />}>
        <Dashboard />
      </AdminGate>
    </div>
  );
}

const secs = (ms: number | null) => (ms === null ? "–" : `${(ms / 1000).toFixed(1)}s`);

function Dashboard() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await adminFetch("/api/admin/analytics");
        if (!res.ok) setError(await errorDetail(res, "Couldn't load analytics."));
        else setData(await res.json());
      } catch {
        setError("Couldn't reach the server.");
      }
    })();
  }, []);

  if (error) return <div className="notice error">{error}</div>;
  if (!data) return <AnalyticsSkeleton />;

  const t = data.totals;
  const peak = Math.max(1, ...data.daily.map((d) => d.questions));
  const rated = t.thumbs_up + t.thumbs_down;
  const answeredPct = t.answered_rate === null ? null : t.answered_rate * 100;
  const upPct = rated ? (t.thumbs_up / rated) * 100 : null;

  return (
    <>
      <div className="kpis">
        <Kpi icon={<ChatIcon size={18} />} label="Questions asked" sub={`${t.conversations} conversation${t.conversations === 1 ? "" : "s"}`} delay={0}>
          <CountUp value={t.questions} />
        </Kpi>
        <Kpi icon={<InsightIcon size={18} />} label="Answered from the articles" sub={`${t.refused} declined`} delay={80} ring={answeredPct}>
          {answeredPct === null ? "–" : <CountUp value={Math.round(answeredPct)} suffix="%" />}
        </Kpi>
        <Kpi icon={<GaugeIcon size={18} />} label="Median answer time" sub={`average ${secs(t.avg_latency_ms)}`} delay={160}>
          {t.median_latency_ms === null ? "–" : <CountUp value={t.median_latency_ms / 1000} decimals={1} suffix="s" />}
        </Kpi>
        <Kpi
          icon={<ThumbUpIcon size={18} />}
          label="Thumbs up"
          sub={rated ? `${t.thumbs_up} up, ${t.thumbs_down} down` : "no feedback yet"}
          delay={240}
          ring={upPct}
        >
          {upPct === null ? "–" : <CountUp value={Math.round(upPct)} suffix="%" />}
        </Kpi>
      </div>

      <section className="panel dash-panel" style={{ animationDelay: "300ms" }}>
        <div className="dash-panel-head">
          <strong>Questions per day</strong>
          <span className="legend">
            <span className="swatch ans" /> answered <span className="swatch dec" /> declined
          </span>
        </div>
        {data.daily.length === 0 ? (
          <p className="dash-empty">No questions yet. Ask the assistant something and it will appear here.</p>
        ) : (
          <div className="daily" role="list">
            {data.daily.map((d, i) => (
              <div
                key={d.date}
                className="daily-col"
                role="listitem"
                title={`${d.date}: ${d.questions} asked, ${d.answered} answered`}
                style={{ ["--i" as string]: i }}
              >
                <span className="daily-n">{d.questions}</span>
                <div className="daily-bar" style={{ height: `${Math.max(6, (d.questions / peak) * 100)}%` }}>
                  <div className="daily-ans" style={{ height: `${(d.answered / d.questions) * 100}%` }} />
                </div>
                <span className="daily-d">
                  {new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="dash-two">
        <section className="panel dash-panel" style={{ animationDelay: "380ms" }}>
          <div className="dash-panel-head">
            <strong>Questions the articles couldn&apos;t answer</strong>
            <span className="dash-hint">Most asked first. Best candidates for a new article.</span>
          </div>
          {data.unanswered.length === 0 ? (
            <p className="dash-empty">Nothing declined yet.</p>
          ) : (
            <ul className="gap-list">
              {data.unanswered.map((g) => (
                <li key={g.question + g.last_seen} className="gap-row">
                  <div>
                    <div className="doc-title">{g.question}</div>
                    <div className="doc-meta">last asked {new Date(g.last_seen).toLocaleString()}</div>
                  </div>
                  <span className="count-pill" aria-label={`asked ${g.count} times`}>
                    ×{g.count}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel dash-panel" style={{ animationDelay: "460ms" }}>
          <div className="dash-panel-head">
            <strong>Answers marked unhelpful</strong>
            <span className="dash-hint">What customers said was wrong.</span>
          </div>
          {data.downvoted.length === 0 ? (
            <p className="dash-empty">No thumbs-down yet.</p>
          ) : (
            <ul className="gap-list">
              {data.downvoted.map((d, i) => (
                <li key={i} className="gap-row block">
                  <div className="doc-title">{d.question}</div>
                  <div className="doc-answer">{d.answer}</div>
                  {d.comment && <div className="doc-comment">“{d.comment}”</div>}
                  <div className="doc-meta">{new Date(d.at).toLocaleString()}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
