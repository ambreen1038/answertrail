"use client";

import { FormEvent, useRef, useState } from "react";
import { API } from "@/lib/site";

type Citation = { id: string; doc_title: string; heading: string; content: string; score: number };
type Answer = {
  answered: boolean;
  answer: string;
  reason: string;
  citations: Citation[];
  latency_ms: number;
};
type Turn = { question: string; result?: Answer; error?: string };

const EXAMPLES = [
  "How big can an uploaded file be?",
  "Can I approve an invoice that still fails a check?",
  "How does duplicate detection work?",
  "How much does InvoiceFlow cost?",
];

export default function Home() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  async function ask(q: string) {
    const text = q.trim();
    if (text.length < 3 || loading) return;
    setQuestion("");
    setLoading(true);
    setTurns((t) => [...t, { question: text }]);
    try {
      const res = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });
      if (res.status === 429) {
        // The server's message says exactly what happened and how long to wait.
        const body = await res.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : "You're asking too quickly. Please wait a moment.");
      }
      if (!res.ok) throw new Error(res.status === 502 ? "The answer service is temporarily unavailable." : "Something went wrong.");
      const result: Answer = await res.json();
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, result } : x)));
    } catch (e) {
      const msg = e instanceof TypeError ? "Couldn't reach the server." : (e as Error).message;
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error: msg } : x)));
    } finally {
      setLoading(false);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  return (
    <div className="page chat-page">
      <header className="page-head">
        <h1 className="page-title">Ask the assistant</h1>
        <p className="page-sub">
          Answers come only from the help articles, with sources. If the articles don&apos;t cover it, it says so
          instead of guessing.
        </p>
        <p className="demo-note">Demo knowledge base: the InvoiceFlow help center.</p>
      </header>

      <section className="thread" aria-live="polite">
        {turns.length === 0 && (
          <div className="empty">
            <p>Try a question:</p>
            <div className="chips">
              {EXAMPLES.map((ex) => (
                <button key={ex} className="chip" onClick={() => void ask(ex)}>
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className="turn">
            <div className="bubble user">{t.question}</div>
            {t.error && <div className="bubble error">{t.error}</div>}
            {t.result && <AnswerCard a={t.result} />}
            {!t.result && !t.error && <div className="bubble bot muted typing">
                <span className="dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                Searching the help articles…
              </div>}
          </div>
        ))}
        <div ref={endRef} />
      </section>

      <form className="composer" onSubmit={onSubmit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about uploads, checks, exports…"
          maxLength={500}
          aria-label="Your question"
        />
        <button type="submit" disabled={loading || question.trim().length < 3}>
          {loading ? <span className="spinner" aria-label="Working" /> : "Ask"}
        </button>
      </form>
    </div>
  );
}

function AnswerCard({ a }: { a: Answer }) {
  if (!a.answered) {
    return (
      <div className="bubble declined">
        <strong>Not in the help articles</strong>
        <p>{a.answer}</p>
      </div>
    );
  }
  return (
    <div className="bubble bot">
      <p>{a.answer}</p>
      <div className="sources">
        <div className="sources-label">Sources</div>
        {a.citations.map((c) => (
          <details key={c.id} className="source">
            <summary>
              {c.doc_title} <span className="dot">·</span> {c.heading}
              <span className="score">{c.score.toFixed(2)}</span>
            </summary>
            <p>{c.content}</p>
          </details>
        ))}
      </div>
    </div>
  );
}
