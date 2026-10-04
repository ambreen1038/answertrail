"use client";

import type { Session } from "@supabase/supabase-js";
import { FormEvent, useEffect, useRef, useState } from "react";
import { API } from "@/lib/site";
import { getSupabase } from "@/lib/supabase";

type Doc = {
  id: number;
  slug: string;
  title: string;
  filename: string;
  content_type: string;
  n_chunks: number;
  created_at: string;
};
type Notice = { kind: "ok" | "error"; text: string };

async function detail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export default function Admin() {
  const supabase = getSupabase();
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false); // false until we know whether someone is signed in
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [docs, setDocs] = useState<Doc[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  /** A fresh access token for every request: supabase-js refreshes it before it expires. */
  async function authHeaders(): Promise<Record<string, string>> {
    const { data } = await supabase!.auth.getSession();
    return { Authorization: `Bearer ${data.session?.access_token ?? ""}` };
  }

  async function load(): Promise<void> {
    const res = await fetch(`${API}/api/admin/documents`, { headers: await authHeaders() });
    if (res.status === 401) {
      await supabase!.auth.signOut();
      setNotice({ kind: "error", text: "Your session expired. Please sign in again." });
      return;
    }
    if (!res.ok) {
      // 403 = signed in but not an admin, 503 = admin login not configured on the server
      setNotice({ kind: "error", text: await detail(res, "Couldn't load documents.") });
      setDocs([]);
      return;
    }
    setDocs(await res.json());
  }

  useEffect(() => {
    if (!supabase) return;
    // Fires once straight away with the current session, then on every sign-in / sign-out.
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setReady(true);
      if (next) void load();
      else setDocs([]);
    });
    return () => data.subscription.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function signIn(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setNotice(null);
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (error) {
      // Deliberately vague: don't reveal whether the email exists.
      setNotice({ kind: "error", text: "Those sign-in details didn't work." });
    }
    setPassword("");
    setBusy(false);
  }

  async function signOut() {
    await supabase?.auth.signOut();
    setNotice(null);
  }

  async function upload(e: FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    if (title.trim()) form.append("title", title.trim());
    setBusy(true);
    setNotice(null);
    try {
      const res = await fetch(`${API}/api/admin/documents`, {
        method: "POST",
        headers: await authHeaders(),
        body: form,
        signal: AbortSignal.timeout(150_000), // never leave the page waiting forever
      });
      if (!res.ok) {
        setNotice({ kind: "error", text: await detail(res, "Upload failed.") });
        return;
      }
      const doc: Doc & { replaced?: boolean } = await res.json();
      setNotice({
        kind: "ok",
        text: `${doc.replaced ? "Updated" : "Added"} “${doc.title}”: ${doc.n_chunks} searchable chunk${doc.n_chunks === 1 ? "" : "s"}.`,
      });
      if (fileRef.current) fileRef.current.value = "";
      setTitle("");
      await load();
    } catch (err) {
      const timedOut = err instanceof DOMException && err.name === "TimeoutError";
      setNotice({
        kind: "error",
        text: timedOut
          ? "The upload is taking too long. Check the document list below before trying again."
          : "Couldn't reach the server.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function remove(doc: Doc) {
    if (!window.confirm(`Delete “${doc.title}”? Its ${doc.n_chunks} chunks will stop being searchable.`)) return;
    setBusy(true);
    setNotice(null);
    try {
      const res = await fetch(`${API}/api/admin/documents/${doc.id}`, {
        method: "DELETE",
        headers: await authHeaders(),
      });
      if (!res.ok && res.status !== 404) {
        setNotice({ kind: "error", text: await detail(res, "Delete failed.") });
        return;
      }
      setNotice({ kind: "ok", text: `Deleted “${doc.title}”.` });
      await load();
    } catch {
      setNotice({ kind: "error", text: "Couldn't reach the server." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1 className="page-title">Documents</h1>
        <p className="page-sub">
          Upload help documents (PDF, Markdown or text). They are split into chunks and become searchable for the
          assistant within seconds. Administrators only.
        </p>
      </header>

      {notice && <div className={`notice ${notice.kind}`}>{notice.text}</div>}

      {!supabase ? (
        <div className="panel">
          <strong>Sign-in isn&apos;t configured.</strong>
          <p className="hint">
            Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local, then
            restart the frontend.
          </p>
        </div>
      ) : !ready ? (
        <p className="hint">Checking your session…</p>
      ) : !session ? (
        <form className="panel" onSubmit={signIn}>
          <label htmlFor="email">Admin sign-in</label>
          <p className="hint">Only the administrator accounts set up for this project can manage documents.</p>
          <div className="row">
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              autoComplete="username"
              required
            />
          </div>
          <div className="row">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              aria-label="Password"
              required
            />
            <button type="submit" disabled={busy}>
              {busy ? "…" : "Sign in"}
            </button>
          </div>
        </form>
      ) : (
        <>
          <div className="signed-in">
            <span>
              Signed in as <strong>{session.user.email}</strong>
            </span>
            <button className="link" onClick={() => void signOut()}>
              Sign out
            </button>
          </div>

          <form className="panel" onSubmit={upload}>
            <label htmlFor="file">Upload a document</label>
            <p className="hint">
              PDF, .md or .txt, up to 10 MB. Uploading a file with the same name replaces the old version.
              Scanned PDFs (images of pages) aren&apos;t supported.
            </p>
            <div className="row">
              <input id="file" ref={fileRef} type="file" accept=".pdf,.md,.txt" required />
            </div>
            <div className="row">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Optional title (defaults to the file's title or name)"
                maxLength={120}
                aria-label="Optional title"
              />
              <button type="submit" disabled={busy}>
                {busy ? "Working…" : "Upload"}
              </button>
            </div>
            {busy && <div className="progress" role="progressbar" aria-label="Uploading" />}
            {busy && (
              <p className="hint">
                Reading and indexing the file. This usually takes a few seconds but can take up to a
                minute when the AI service is slow.
              </p>
            )}
          </form>

          <section className="panel">
            <div className="panel-head">
              <strong>Documents ({docs.length})</strong>
            </div>
            {docs.length === 0 ? (
              <p className="hint">No documents to show.</p>
            ) : (
              <ul className="doc-list">
                {docs.map((d) => (
                  <li key={d.id} className="doc">
                    <div>
                      <div className="doc-title">{d.title}</div>
                      <div className="doc-meta">
                        {d.filename} · {d.n_chunks} chunk{d.n_chunks === 1 ? "" : "s"} ·{" "}
                        {new Date(d.created_at).toLocaleString()}
                      </div>
                    </div>
                    <button className="danger" onClick={() => void remove(d)} disabled={busy}>
                      Delete
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
