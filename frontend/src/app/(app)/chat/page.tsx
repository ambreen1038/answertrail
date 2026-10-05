"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAccount } from "@/components/AccountProvider";
import { Mark } from "@/components/Brand";
import { ThumbDownIcon, ThumbUpIcon, TrashIcon } from "@/components/Icons";
import PageHero from "@/components/PageHero";
import { forgetChat, rememberChat, touchChat } from "@/lib/history";
import { apiFetch } from "@/lib/api";

type Citation = { id: string; doc_title: string; heading: string; content: string; score: number };
type Answer = { answered: boolean; answer: string; reason: string; citations: Citation[] };
type Turn = {
  question: string;
  result?: Answer;
  error?: string;
  messageId?: number;
  rating?: 1 | -1 | null;
  rewritten?: string | null; // what the assistant actually searched for, when it differed from the question
  slow?: boolean; // the answer is taking long: probably a sleeping free-tier server
};

type SavedMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  answered: boolean | null;
  reason: string | null;
  citations: Citation[];
  rewritten_query: string | null;
  rating: 1 | -1 | null;
};

const EXAMPLES = [
  "How big can an uploaded file be?",
  "Can I approve an invoice that still fails a check?",
  "How does duplicate detection work?",
  "How much does InvoiceFlow cost?",
];

/** Turn the saved flat message list (user, assistant, user, assistant, ...) back into question/answer pairs. */
function toTurns(messages: SavedMessage[]): Turn[] {
  const turns: Turn[] = [];
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.role !== "user") continue;
    const reply = messages[i + 1]?.role === "assistant" ? messages[i + 1] : undefined;
    turns.push({
      question: m.content,
      result: reply && {
        answered: !!reply.answered,
        answer: reply.content,
        reason: reply.reason ?? "",
        citations: reply.citations ?? [],
      },
      messageId: reply?.id,
      rating: reply?.rating ?? null,
      rewritten: reply?.rewritten_query ?? null,
    });
  }
  return turns;
}

export default function ChatPage() {
  // useSearchParams needs a Suspense boundary so the rest of the page can render statically.
  return (
    <Suspense fallback={null}>
      <Chat />
    </Suspense>
  );
}

function Chat() {
  const router = useRouter();
  const account = useAccount();
  const params = useSearchParams();
  const urlChat = params.get("c");
  const view = urlChat ?? (params.get("new") ? "new" : ""); // which screen the address bar is asking for

  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [opening, setOpening] = useState(urlChat !== null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cid, setCid] = useState<string | null>(null);
  const [prevView, setPrevView] = useState(view);
  const cidRef = useRef<string | null>(null);
  const viewRef = useRef(view); // lets a slow reply notice that the visitor has moved to another chat meanwhile
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    cidRef.current = cid;
    viewRef.current = view;
  });

  const scrollDown = () => setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);

  // The address bar decides which chat is on screen: /chat?c=<id> opens that chat, plain /chat starts fresh.
  // Switching chats clears the screen right away (adjusting state while rendering, as React recommends).
  if (prevView !== view) {
    setPrevView(view);
    if (urlChat === null || urlChat !== cid) {
      // (when urlChat === cid we created that chat ourselves a moment ago, so there is nothing to clear)
      setCid(null);
      setTurns([]);
      setNotice(null);
      setLoading(false);
      setOpening(urlChat !== null);
    }
  }

  useEffect(() => {
    if (!urlChat || urlChat === cidRef.current) return;
    let stale = false;
    apiFetch(`/api/conversations/${urlChat}`)
      .then(async (res) => {
        if (stale) return;
        if (res.status === 404 || res.status === 422) {
          forgetChat(urlChat);
          setNotice("That chat no longer exists. It may have been deleted.");
          return;
        }
        if (!res.ok) throw new Error();
        const convo: { id: string; messages: SavedMessage[] } = await res.json();
        if (stale) return;
        setCid(convo.id);
        setTurns(toTurns(convo.messages));
        scrollDown();
      })
      .catch(() => !stale && setNotice("Couldn't open that chat. Is the server running?"))
      .finally(() => !stale && setOpening(false));
    return () => {
      stale = true;
    };
  }, [urlChat]);

  async function ask(q: string) {
    const text = q.trim();
    if (text.length < 3 || loading || opening) return;
    const startView = viewRef.current;
    const isCurrent = () => viewRef.current === startView;
    setQuestion("");
    setNotice(null);
    setLoading(true);
    setTurns((t) => [...t, { question: text }]);
    const patchLast = (patch: Partial<Turn>) =>
      isCurrent() && setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, ...patch } : x)));
    // Free hosting puts an idle server to sleep; its first answer can take up to a minute. Say so.
    const slowTimer = setTimeout(() => patchLast({ slow: true }), 6000);
    try {
      const res = await apiFetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, conversation_id: cidRef.current }),
        signal: AbortSignal.timeout(90_000), // never leave a visitor waiting forever
      });
      if (res.status === 429) {
        // The server's message says exactly what happened and how long to wait.
        const body = await res.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : "You're asking too quickly. Please wait a moment.");
      }
      if (res.status === 401) throw new Error("Your session has expired, so you've been signed out. Ask again to continue without an account, or sign in again.");
      if (!res.ok) throw new Error(res.status === 502 || res.status === 503 ? "The answer service is temporarily unavailable." : "Something went wrong.");
      const data: Answer & { conversation_id: string | null; message_id: number | null; rewritten_query: string | null } =
        await res.json();
      if (!isCurrent()) return;
      patchLast({
        result: data,
        messageId: data.message_id ?? undefined,
        rating: null,
        rewritten: data.rewritten_query && data.rewritten_query !== text ? data.rewritten_query : null,
      });
      if (data.conversation_id) {
        if (data.conversation_id !== cidRef.current) {
          // First message of a new chat (or the server started a fresh one): remember it and put it in the URL.
          setCid(data.conversation_id);
          rememberChat(data.conversation_id, text.slice(0, 60));
          router.replace(`/chat?c=${data.conversation_id}`, { scroll: false });
        } else {
          touchChat(data.conversation_id);
        }
      }
    } catch (e) {
      const timedOut = e instanceof DOMException && e.name === "TimeoutError";
      patchLast({
        error: timedOut
          ? "The server took too long to answer. Please try again in a moment."
          : e instanceof TypeError
            ? "Couldn't reach the server."
            : (e as Error).message,
      });
    } finally {
      clearTimeout(slowTimer);
      if (isCurrent()) {
        setLoading(false);
        scrollDown();
      }
    }
  }

  async function rate(index: number, rating: 1 | -1, comment?: string) {
    const turn = turns[index];
    if (!cid || !turn?.messageId) return;
    setTurns((t) => t.map((x, i) => (i === index ? { ...x, rating } : x)));
    try {
      const res = await apiFetch(`/api/conversations/${cid}/messages/${turn.messageId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating, comment: comment?.trim() || null }),
      });
      if (!res.ok) throw new Error();
    } catch {
      setTurns((t) => t.map((x, i) => (i === index ? { ...x, rating: turn.rating ?? null } : x)));
      setNotice("Couldn't save your feedback. Please try again.");
    }
  }

  async function deleteChat() {
    if (!cid || !window.confirm("Delete this chat? Its questions and answers will be removed permanently.")) return;
    try {
      const res = await apiFetch(`/api/conversations/${cid}`, { method: "DELETE" });
      if (!res.ok && res.status !== 404) throw new Error();
      forgetChat(cid);
      router.replace("/chat?new=1");
    } catch {
      setNotice("Couldn't delete the chat. Please try again.");
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  return (
    <div className="page chat-page">
      <PageHero
        compact
        eyebrow="Demo knowledge base: the InvoiceFlow help center"
        title="Ask the assistant"
        subtitle="Answers come only from the help articles, with sources. If the articles don't cover it, it says so instead of guessing."
      >
        {cid && (
          <button className="ghost-btn on-dark" onClick={() => void deleteChat()}>
            <TrashIcon size={15} /> Delete this chat
          </button>
        )}
      </PageHero>

      {notice && <div className="notice error">{notice}</div>}

      <section className="thread" aria-live="polite">
        {opening && <p className="hint">Opening chat…</p>}
        {turns.length === 0 && !opening && (
          <div className="empty">
            <span className="empty-mark" aria-hidden="true">
              <Mark size={44} />
            </span>
            <p>Try a question:</p>
            <div className="chips">
              {EXAMPLES.map((ex, i) => (
                <button key={ex} className="chip" style={{ ["--i" as string]: i }} onClick={() => void ask(ex)}>
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
            {t.result && (
              <>
                <AnswerCard a={t.result} searched={t.rewritten} />
                {t.messageId && cid && <Feedback turn={t} onRate={(r, c) => void rate(i, r, c)} />}
              </>
            )}
            {!t.result && !t.error && (
              <div className="bubble bot muted typing">
                <span className="dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                {t.slow
                  ? "The server is waking up (free hosting sleeps when idle). The first answer can take up to a minute…"
                  : "Searching the help articles…"}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </section>

      {account.ready && !account.signedIn && turns.length > 0 && (
        <div className="signin-nudge">
          Without an account, anyone who has this page&apos;s link can read this chat.{" "}
          <Link href={`/login?next=${encodeURIComponent(cid ? `/chat?c=${cid}` : "/chat")}`}>
            Sign in to keep your chats private
          </Link>{" "}
          and see them on any device.
        </div>
      )}

      <form className="composer" onSubmit={onSubmit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={turns.length ? "Ask a follow-up…" : "Ask about uploads, checks, exports…"}
          maxLength={500}
          aria-label="Your question"
        />
        <button type="submit" disabled={loading || opening || question.trim().length < 3}>
          {loading ? <span className="spinner" aria-label="Working" /> : "Ask"}
        </button>
      </form>
      <p className="privacy-note">
        Answers are written by AI (Google Gemini) from the help articles and can be wrong, so check the sources.
        Questions are saved so the assistant can be improved; please don&apos;t include personal or payment details.{" "}
        <Link href="/privacy">Privacy</Link>
      </p>
    </div>
  );
}

function Feedback({ turn, onRate }: { turn: Turn; onRate: (rating: 1 | -1, comment?: string) => void }) {
  const [asking, setAsking] = useState(false);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);

  return (
    <div className="feedback">
      <span className="feedback-label">{turn.rating ? "Thanks for the feedback" : "Was this helpful?"}</span>
      <button
        className={`thumb${turn.rating === 1 ? " on" : ""}`}
        aria-label="Helpful"
        aria-pressed={turn.rating === 1}
        onClick={() => {
          setAsking(false);
          onRate(1);
        }}
      >
        <ThumbUpIcon size={15} />
      </button>
      <button
        className={`thumb${turn.rating === -1 ? " on bad" : ""}`}
        aria-label="Not helpful"
        aria-pressed={turn.rating === -1}
        onClick={() => {
          setAsking(true);
          setSent(false);
          onRate(-1);
        }}
      >
        <ThumbDownIcon size={15} />
      </button>
      {asking && turn.rating === -1 && !sent && (
        <form
          className="feedback-form"
          onSubmit={(e) => {
            e.preventDefault();
            onRate(-1, comment);
            setSent(true);
          }}
        >
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What was wrong? (optional)"
            maxLength={500}
            aria-label="What was wrong with this answer?"
          />
          <button type="submit">Send</button>
        </form>
      )}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");

  async function copy() {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      // Some browsers and embedded views block the clipboard API; try the older way before giving up.
      const box = document.createElement("textarea");
      box.value = text;
      box.style.position = "fixed";
      box.style.opacity = "0";
      document.body.appendChild(box);
      box.select();
      try {
        ok = document.execCommand("copy");
      } catch {
        ok = false;
      }
      box.remove();
    }
    setState(ok ? "done" : "failed");
    setTimeout(() => setState("idle"), 1800);
  }

  return (
    <button className="copy-btn" onClick={() => void copy()} aria-live="polite">
      {state === "done" ? "Copied" : state === "failed" ? "Couldn't copy" : "Copy answer"}
    </button>
  );
}

function AnswerCard({ a, searched }: { a: Answer; searched?: string | null }) {
  const note = searched ? (
    <div className="searched">
      Searched for: <em>{searched}</em>
    </div>
  ) : null;
  if (!a.answered) {
    return (
      <div className="bubble declined">
        <strong>Not in the help articles</strong>
        <p>{a.answer}</p>
        {note}
      </div>
    );
  }
  return (
    <div className="bubble bot">
      <p>{a.answer}</p>
      {note}
      <CopyButton text={a.answer} />
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
