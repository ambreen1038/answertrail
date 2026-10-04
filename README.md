# AnswerTrail

**Support answers you can trace to the source.** An AI customer support assistant.

A retrieval-augmented (RAG) support chatbot that answers questions **only from a help center, cites
the exact passages it used, and says "I don't know" instead of guessing**.

It is not tied to one product: upload your own help documents (PDF, Markdown or text) on the admin
page, or point it at a folder of markdown articles, and it becomes a support assistant for that
product (the product name is a setting). The demo knowledge base is a help center for
[InvoiceFlow](https://github.com/ambreen1038/invoiceflow), my AI invoice processing app. This is a
separate project from InvoiceFlow and shares no code with it.

> Status: customer chat, document upload, admin page with Supabase login, evaluation and tests are
> done. Rate limiting and deployment are next; there is no live demo yet.

## Why this exists

Most "chat with your docs" demos answer confidently whether or not the documents contain the answer.
For customer support that is the dangerous failure: a made-up refund policy is worse than no answer.
So the interesting parts of this project are the refusal behaviour and the measurement of it, not the
chat box.

## How it works

```
help articles (kb/*.md)
   │  split into one chunk per section
   ▼
Gemini embeddings (768-dim) ──▶ Postgres + pgvector

question ──▶ embed ──▶ cosine search (top 5)
                          │
              gate 1: best chunk similar enough?  ──no──▶ refuse (LLM never called)
                          │ yes
              Gemini, JSON mode: "do these sources answer it?" + which ones used
                          │
              gate 2: model says answerable AND cites a valid source?  ──no──▶ refuse
                          │ yes
                  answer + citations (article, section, passage, score)
```

Refusal is deliberately two independent checks, and an answer with no valid citation is dropped,
because an uncited answer is indistinguishable from an invented one.

## Adding documents (admin)

Open `/admin`, sign in with an administrator account, and upload a PDF, `.md` or `.txt` file (up to 10 MB). The
backend extracts the text, splits it into chunks, embeds them and stores them; the file is
searchable as soon as the upload finishes. Uploading a file with the same name replaces the old
version, and deleting a document removes all of its chunks.

| Endpoint (header `Authorization: Bearer <Supabase access token>`) | Purpose |
|---|---|
| `GET /api/admin/documents` | list documents |
| `POST /api/admin/documents` | upload (multipart `file`, optional `title`) |
| `DELETE /api/admin/documents/{id}` | delete a document and its chunks |

Design decisions worth knowing:

- **Three chunking strategies.** Markdown with headings is split per section; headingless text is
  packed into ~800-character chunks with a small overlap; PDFs are chunked per page, so citations
  read "Page 3" and a human can look them up.
- **Atomic ingestion.** Embeddings are computed *before* anything is written, and the write is one
  transaction, so a failed upload (bad file, AI-service outage) never leaves a half-indexed document.
- **Upload validation.** Extension and file signature are both checked, plus size, page and chunk
  limits (which also bound embedding cost). Scanned PDFs with no text layer are rejected with a clear
  message; OCR is not supported.
- **Resilient AI calls.** Each call has a short timeout and retries timeouts, dropped connections,
  429s and 5xx responses, then fails with a clean error (HTTP 502) instead of hanging. This was added
  after one upload stalled for 97 seconds on a slow Gemini response.
- **Real admin login, verified by Supabase.** The browser signs in with Supabase Auth and sends its
  access token; the backend does not trust or decode it itself, it asks Supabase who the token
  belongs to. An account must also have a *confirmed* email on the `ADMIN_EMAILS` allowlist.
  Responses are deliberately distinct: 401 not signed in, 403 signed in but not an admin, 503 if
  login isn't configured or Supabase is unreachable (it fails closed, never open). The backend holds
  no password and no service-role key.
- **Row Level Security on every table.** Supabase exposes public-schema tables through a REST API
  that anyone with the public anon key can call. Both tables have RLS enabled with no policies and
  the `anon`/`authenticated` roles' privileges revoked, so that API cannot read or change documents
  and the admin login can't be bypassed. The backend connects as the table owner, which RLS doesn't
  restrict.

## Supabase setup

1. Create a Supabase project (separate from any other app).
2. **Authentication -> Sign In / Providers -> Email:** turn **off** "Allow new users to sign up"
   (this is a single-admin tool) and keep "Confirm email" on.
3. **Authentication -> Users -> Add user:** create your admin account with "Auto Confirm User" ticked.
4. Put that email in `ADMIN_EMAILS`; copy the Project URL and anon key into `SUPABASE_URL` /
   `SUPABASE_ANON_KEY` (backend) and `NEXT_PUBLIC_SUPABASE_*` (frontend).
5. **Project Settings -> Database -> Connection string -> Session pooler:** use it as `DATABASE_URL`
   (the direct connection is IPv6-only on the free plan). Then load the knowledge base:
   `python -m app.ingest --reset`. The tables and their security settings are created automatically.

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI, Pydantic v2 |
| Vector store | Postgres + pgvector (exact cosine search; no ANN index at this size) |
| Embeddings / generation | Google Gemini API (`gemini-embedding-001`, pinned `gemini-3.5-flash-lite`) via `httpx` |
| Frontend | Next.js (App Router, TypeScript) |
| Tests | pytest (offline: no network, DB or API key) |

## Evaluation

60 hand-written questions in [`backend/eval/questions.jsonl`](backend/eval/questions.jsonl), built by
[`build_questions.py`](backend/eval/build_questions.py). Run with `python eval/run_eval.py`
(calls the real, metered API; it is a manual script, not part of CI).

| Split | Questions | Correct answers | Correct refusals | Gold article in top-5 | Ranked #1 | Citation points at gold article |
|---|---|---|---|---|---|---|
| Dev | 16 answerable + 6 unanswerable | 16/16 | 6/6 | 16/16 | 15/16 | 16/16 |
| **Test** | 16 answerable + 6 unanswerable | **16/16** | **6/6** | 16/16 | 15/16 | 16/16 |
| Hard | 8 answerable + 8 unanswerable | 7/8 | 8/8 | 8/8 | 7/8 | 8/8 |

Hallucinated answers (a question the docs don't cover that got an answer anyway): **0/20**.
Median latency 1.9 s, p90 2.5 s (retrieval + one LLM call).

Numbers are for the pinned model `gemini-3.5-flash-lite`. An earlier run used the moving alias
`gemini-flash-lite-latest` and got 8/8 on the hard set. The one difference is a question where the new
model answered "InvoiceFlow looks for duplicates" without saying what happens to them. That is one
question, within run-to-run noise, but I report what I measured and pinned the model so the published
numbers stay reproducible.

**Unanswerable** means the help center is silent on the topic. The correct behaviour is to decline,
*not* to claim the feature doesn't exist. Several are deliberate near-misses that sit close to a real
article (changing the account email, public API, team accounts, encryption at rest, retention).
The **hard** set adds paraphrased and multi-article questions, a false premise ("why does it charge
5 dollars"), a prompt-injection attempt, and an off-topic question.

### What the numbers do and don't show

Read these as "no failures found on this corpus", not as a general accuracy figure.

- **Small, clean corpus**: 12 articles, 58 chunks. Retrieval is easy at this size.
- **Same author for articles and questions.** I wrote both, so vocabulary overlaps even in the hard set.
  Questions from real users would be messier.
- **Crude grader.** Answers are graded by required phrases, which can pass a sloppy answer and fail a
  good paraphrase. One real example: my first run scored 15/16 on test because the grader looked for
  "acknowledge" and the (correct) answer said "acknowledging". I fixed the matcher and re-ran; I did not
  change anything else to make it pass.
- **The hard set was added after the first run**, because 22/22 on the original set told me the set was
  too easy. The threshold was tuned on dev only and *not* on the hard set.
- **Single run, 60 questions.** One miss would be 1.7 points, and the model is not perfectly deterministic.
- **The retrieval-similarity gate does almost nothing here.** Across all 60 questions the best-chunk
  score is 0.67-0.85 for answerable questions and 0.52-0.74 for unanswerable ones, so the ranges
  overlap and similarity alone cannot separate them. Every threshold from 0.30 to 0.65 gives identical
  results (60/60), and raising it to 0.68 or above starts refusing questions that should be answered.
  The model's own check is what refuses correctly. I keep the gate (default 0.5) only as a cheap
  sanity floor that skips the LLM call when nothing relevant was retrieved at all.

## Run it locally

Prerequisites: Python 3.10+, Node 20+, Docker, a free Gemini API key
([aistudio.google.com](https://aistudio.google.com/apikey)).

```bash
docker compose up -d db                      # Postgres with pgvector on :5433
cd backend
python -m venv ../.venv && ../.venv/Scripts/pip install -r requirements-dev.txt
cp ../.env.example .env                      # then fill in GEMINI_API_KEY and the Supabase values
python -m app.ingest                         # chunk, embed and store the knowledge base
uvicorn app.main:app --reload                # API on :8000
python -m pytest                             # 55 offline tests
python -m app.ingest --reset                 # clean state: only kb/ (required before the evaluation)
python eval/run_eval.py                      # live evaluation (refuses to run if extra documents exist)
```

Frontend: `cd frontend && npm install && npm run dev` (set `NEXT_PUBLIC_API_URL` if the API isn't on :8000).
Chat is at http://localhost:3000 and the admin page at http://localhost:3000/admin.

## Project layout

```
kb/                 12 help articles (the knowledge base)
backend/app/        config, extraction, chunking, gemini client, pgvector store, ingestion, answer logic, FastAPI app
backend/eval/       questions, question builder, evaluation runner, results.json
backend/tests/      offline unit tests
frontend/           Next.js: chat UI with citations and a clear "couldn't find that" state, plus /admin
```

## Limitations and roadmap

- The knowledge base is synthetic documentation I wrote from how InvoiceFlow actually behaves,
  not a real company's help center.
- No conversation memory: each question is answered independently.
- **The evaluation covers the markdown knowledge base only.** PDF upload is covered by unit tests
  (including generated PDFs, a scanned/no-text PDF and a damaged one) and a manual end-to-end check,
  but retrieval quality on messy real-world PDFs has not been measured.
- Text-layer PDFs only; no OCR for scanned documents. Page-based chunking can split a fact across pages.
- No rate limiting on the public chat endpoint yet. Free-tier Supabase projects pause after a week of inactivity.
- Admin login uses Supabase's default browser session storage; there is a single admin role, no per-user permissions.
- [ ] Rate limiting
- [ ] Evaluation dashboard page
- [ ] Deploy (Vercel + Render + Supabase Postgres with pgvector)
- [ ] Tool calling with human confirmation before any action (for example, look up an invoice's status)
- [ ] Evaluate on questions written by someone other than the author
