"use client";

import { CSSProperties, useEffect, useState } from "react";
import CountUp from "@/components/CountUp";
import { BanIcon, ChatIcon, SearchIcon, ShieldIcon } from "@/components/Icons";
import { Kpi } from "@/components/Kpi";
import PageHero from "@/components/PageHero";
import { EvalQuestion, EvalReport, Outcome, fetchEvaluation } from "@/lib/evaluation";

const OUTCOME: Record<Outcome, string> = {
  correct: "Correct answer",
  wrong_answer: "Wrong answer",
  false_refusal: "Refused (should have answered)",
  correct_refusal: "Correctly refused",
  invented_answer: "Invented an answer",
};

const SPLIT_INFO = {
  dev: { title: "Dev", note: "Used to tune the retrieval threshold" },
  test: { title: "Test", note: "Held out: the headline numbers" },
  hard: { title: "Hard", note: "Paraphrases, false premises, prompt injection, off-topic" },
} as const;

type Filter = "all" | "dev" | "test" | "hard";

export default function Evaluation() {
  const [report, setReport] = useState<EvalReport | null | undefined>(undefined);
  const [filter, setFilter] = useState<Filter>("all");
  const [missesOnly, setMissesOnly] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchEvaluation().then((r) => alive && setReport(r));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="page wide">
      <PageHero
        eyebrow="Measured, not claimed"
        title="Evaluation"
        subtitle="How well the assistant answers when it should, and refuses when it should. Everything on this page is read from the real results file written by the evaluation script."
      />

      {report === undefined && (
        <div aria-busy="true" aria-label="Loading results" role="status">
          <div className="kpis">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="kpi skeleton" style={{ height: 128 }} />
            ))}
          </div>
          <div className="split-grid">
          {[0, 1, 2].map((i) => (
            <div key={i} className="split-card skeleton" style={{ height: 250 }} />
          ))}
          </div>
        </div>
      )}
      {report === null && (
        <div className="notice error">The evaluation results couldn&apos;t be loaded. Is the backend running?</div>
      )}
      {report && <Results report={report} filter={filter} setFilter={setFilter} missesOnly={missesOnly} setMissesOnly={setMissesOnly} />}
    </div>
  );
}

function Results({
  report,
  filter,
  setFilter,
  missesOnly,
  setMissesOnly,
}: {
  report: EvalReport;
  filter: Filter;
  setFilter: (f: Filter) => void;
  missesOnly: boolean;
  setMissesOnly: (v: boolean) => void;
}) {
  const rows = report.questions.filter((q) => (filter === "all" || q.split === filter) && (!missesOnly || !q.passed));

  const test = report.splits.test;
  const invented = report.splits.dev.hallucinated_answers + test.hallucinated_answers + report.splits.hard.hallucinated_answers;
  const unanswerable = report.splits.dev.n_unanswerable + test.n_unanswerable + report.splits.hard.n_unanswerable;
  const pct = (a: number, b: number) => (b ? (a / b) * 100 : null);

  return (
    <>
      <div className="kpis">
        <Kpi icon={<ChatIcon size={18} />} label="Correct answers" sub="held-out test split" ring={pct(test.correct_answers, test.n_answerable)}>
          <CountUp value={test.correct_answers} />/{test.n_answerable}
        </Kpi>
        <Kpi icon={<ShieldIcon size={18} />} label="Correct refusals" sub="held-out test split" delay={80} ring={pct(test.correct_refusals, test.n_unanswerable)}>
          <CountUp value={test.correct_refusals} />/{test.n_unanswerable}
        </Kpi>
        <Kpi icon={<BanIcon size={18} />} label="Invented answers" sub="across all three splits" delay={160} ring={pct(unanswerable - invented, unanswerable)}>
          <CountUp value={invented} />/{unanswerable}
        </Kpi>
        <Kpi icon={<SearchIcon size={18} />} label={`Right article in top ${report.top_k}`} sub="held-out test split" delay={240} ring={pct(test.retrieval_hit_at_k, test.n_answerable)}>
          <CountUp value={test.retrieval_hit_at_k} />/{test.n_answerable}
        </Kpi>
      </div>

      <div className="eval-meta">
        <span>Model: {report.gen_model}</span>
        <span>Embeddings: {report.embed_model}</span>
        <span>Passages retrieved: {report.top_k}</span>
        <span>
          {report.totals.passed}/{report.totals.questions} questions passed
        </span>
      </div>

      <div className="split-grid">
        {(["dev", "test", "hard"] as const).map((k, idx) => {
          const s = report.splits[k];
          return (
            <section key={k} className={`split-card${k === "test" ? " headline" : ""}`} style={{ "--i": idx } as CSSProperties}>
              <h2>{SPLIT_INFO[k].title}</h2>
              <p className="split-note">{SPLIT_INFO[k].note}</p>
              <div
                className="meter"
                role="img"
                aria-label={`${s.correct_answers + s.correct_refusals} of ${s.n_answerable + s.n_unanswerable} behaved correctly`}
              >
                <div className="meter-fill" style={{ width: `${((s.correct_answers + s.correct_refusals) / (s.n_answerable + s.n_unanswerable)) * 100}%` }} />
              </div>
              <dl>
                <div>
                  <dt>Correct answers</dt>
                  <dd>
                    {s.correct_answers}/{s.n_answerable}
                  </dd>
                </div>
                <div>
                  <dt>Correct refusals</dt>
                  <dd>
                    {s.correct_refusals}/{s.n_unanswerable}
                  </dd>
                </div>
                <div>
                  <dt>Invented answers</dt>
                  <dd>
                    {s.hallucinated_answers}/{s.n_unanswerable}
                  </dd>
                </div>
                <div>
                  <dt>Right article in top {report.top_k}</dt>
                  <dd>
                    {s.retrieval_hit_at_k}/{s.n_answerable}
                  </dd>
                </div>
                <div>
                  <dt>Citation points to right article</dt>
                  <dd>
                    {s.citation_ok}/{s.answered}
                  </dd>
                </div>
              </dl>
            </section>
          );
        })}
      </div>

      <section className="panel limits">
        <h2>What these numbers do and don&apos;t show</h2>
        <p>Read them as &ldquo;no failures found on this corpus&rdquo;, not as a general accuracy figure.</p>
        <ul>
          <li>
            <strong>Small and clean.</strong> 12 help articles, 58 passages. Retrieval is easy at this size.
          </li>
          <li>
            <strong>Same author.</strong> I wrote both the articles and the questions, so their wording overlaps,
            even in the hard set. Real customers write messier questions.
          </li>
          <li>
            <strong>Crude grading.</strong> An answer passes if it contains the required phrases. That can pass a
            sloppy answer and fail a good paraphrase.
          </li>
          <li>
            <strong>Run-to-run variation.</strong> The model is not perfectly deterministic: one hard question
            has flipped between runs, so single results are approximate.
          </li>
          <li>
            <strong>The similarity threshold barely matters.</strong> Answerable and unanswerable questions score in
            overlapping ranges, so the model&apos;s own &ldquo;do these sources answer it?&rdquo; check does the
            real refusing.
          </li>
          <li>
            <strong>Markdown only.</strong> These questions cover the written help articles. PDF upload is tested
            separately, but its answer quality hasn&apos;t been measured.
          </li>
        </ul>
      </section>

      <section className="panel">
        <div className="table-head">
          <h2>
            Every question <span>({rows.length})</span>
          </h2>
          <div className="filters" role="group" aria-label="Filter questions">
            {(["all", "dev", "test", "hard"] as const).map((f) => (
              <button key={f} className={`chip-btn${filter === f ? " on" : ""}`} onClick={() => setFilter(f)} aria-pressed={filter === f}>
                {f === "all" ? "All" : SPLIT_INFO[f].title}
              </button>
            ))}
            <label className="check">
              <input type="checkbox" checked={missesOnly} onChange={(e) => setMissesOnly(e.target.checked)} /> Misses only
            </label>
          </div>
        </div>

        {rows.length === 0 ? (
          <p className="hint">{missesOnly ? "No misses in this selection." : "No questions."}</p>
        ) : (
          <ul className="q-list">
            {rows.map((q, i) => (
              <Row key={q.id} q={q} i={i} />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function Row({ q, i }: { q: EvalQuestion; i: number }) {
  return (
    <li style={{ ["--i" as string]: Math.min(i, 14) }}>
      <details className="q">
        <summary>
          <span className="q-id">{q.id}</span>
          <span className="q-text">{q.question}</span>
          <span className={`pill ${q.passed ? "pass" : "miss"}`}>{OUTCOME[q.outcome]}</span>
        </summary>
        <div className="q-body">
          <p>
            <b>Kind:</b> {q.answerable ? "the help center can answer this" : "the help center does not cover this"} ·{" "}
            <b>Split:</b> {q.split} · <b>Best match score:</b> {q.top_score}
          </p>
          <p>
            <b>Assistant:</b> {q.answer ?? "Declined to answer."}
          </p>
          {q.gold_docs.length > 0 && (
            <p>
              <b>Expected source:</b> {q.gold_docs.join(", ")}
              {q.cited_docs.length > 0 && (
                <>
                  {" "}
                  · <b>Cited:</b> {q.cited_docs.join(", ")}
                </>
              )}
            </p>
          )}
        </div>
      </details>
    </li>
  );
}
