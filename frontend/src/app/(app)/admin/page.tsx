"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import AdminGate from "@/components/AdminGate";
import AdminHero from "@/components/AdminHero";
import CountUp from "@/components/CountUp";
import { FilesIcon, SearchIcon, UploadIcon } from "@/components/Icons";
import { DocListSkeleton, DocStatsSkeleton, DocumentsSkeleton } from "@/components/Skeletons";
import { adminFetch, errorDetail } from "@/lib/adminApi";

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

export default function Admin() {
  return (
    <div className="page wide">
      <AdminHero
        title="Documents"
        subtitle="Upload help documents (PDF, Markdown or text). They are split into chunks and become searchable for the assistant within seconds."
      />
      <AdminGate loading={<DocumentsSkeleton />}>
        <Documents />
      </AdminGate>
    </div>
  );
}

function fileType(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return ext === "md" ? "md" : ext === "pdf" ? "pdf" : "txt";
}

function Documents() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loaded, setLoaded] = useState(false); // false until the first list has arrived
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  /** Ask the server for the list. Returns the outcome instead of setting state, so it can be used both
   *  when the page opens and after an upload or delete. */
  const fetchDocs = useCallback(async (): Promise<{ docs: Doc[] } | { error: string }> => {
    try {
      const res = await adminFetch("/api/admin/documents");
      if (res.status === 401) return { error: "Your session expired. Please sign in again." };
      // 403 = signed in but not an admin, 503 = admin login not configured on the server
      if (!res.ok) return { error: await errorDetail(res, "Couldn't load documents.") };
      return { docs: await res.json() };
    } catch {
      return { error: "Couldn't reach the server." };
    }
  }, []);

  const show = useCallback((r: { docs: Doc[] } | { error: string }) => {
    setLoaded(true);
    if ("docs" in r) setDocs(r.docs);
    else {
      setNotice({ kind: "error", text: r.error });
      setDocs([]);
    }
  }, []);

  const load = useCallback(async () => show(await fetchDocs()), [fetchDocs, show]);

  useEffect(() => {
    void fetchDocs().then(show);
  }, [fetchDocs, show]);

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
      const res = await adminFetch("/api/admin/documents", {
        method: "POST",
        body: form,
        signal: AbortSignal.timeout(150_000), // never leave the page waiting forever
      });
      if (!res.ok) {
        setNotice({ kind: "error", text: await errorDetail(res, "Upload failed.") });
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
      const res = await adminFetch(`/api/admin/documents/${doc.id}`, { method: "DELETE" });
      if (!res.ok && res.status !== 404) {
        setNotice({ kind: "error", text: await errorDetail(res, "Delete failed.") });
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
    <>
      {notice && <div className={`notice ${notice.kind}`}>{notice.text}</div>}

      {!loaded ? <DocStatsSkeleton /> : <div className="stat-strip">
        <div className="mini-stat">
          <span className="kpi-icon">
            <FilesIcon size={18} />
          </span>
          <div>
            <div className="mini-value">
              <CountUp value={docs.length} />
            </div>
            <div className="mini-label">documents</div>
          </div>
        </div>
        <div className="mini-stat">
          <span className="kpi-icon">
            <SearchIcon size={18} />
          </span>
          <div>
            <div className="mini-value">
              <CountUp value={docs.reduce((n, d) => n + d.n_chunks, 0)} />
            </div>
            <div className="mini-label">searchable chunks</div>
          </div>
        </div>
      </div>}

      <form className="panel dropzone" onSubmit={upload}>
        <div className="dz-head">
          <span className="kpi-icon">
            <UploadIcon size={18} />
          </span>
          <label htmlFor="file">Upload a document</label>
        </div>
        <p className="hint">
          PDF, .md or .txt, up to 10 MB. Uploading a file with the same name replaces the old version. Scanned PDFs
          (images of pages) aren&apos;t supported.
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
            Reading and indexing the file. This usually takes a few seconds but can take up to a minute when the AI
            service is slow.
          </p>
        )}
      </form>

      {!loaded ? <DocListSkeleton /> : <section className="panel">
        <div className="panel-head">
          <strong>Documents ({docs.length})</strong>
        </div>
        {docs.length === 0 ? (
          <p className="hint">No documents to show.</p>
        ) : (
          <ul className="doc-list">
            {docs.map((d) => (
              <li key={d.id} className="doc">
                <span className={`ftype ${fileType(d.filename)}`}>{fileType(d.filename)}</span>
                <div className="doc-main">
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
      </section>}
    </>
  );
}
