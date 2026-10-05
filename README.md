# AnswerTrail

**Support answers you can trace to the source.** An AI customer support assistant.

A retrieval-augmented (RAG) support chatbot that answers questions **only from a help center, cites
the exact passages it used, and says "I don't know" instead of guessing**.

It is not tied to one product: upload your own help documents (PDF, Markdown or text) on the admin
page, or point it at a folder of markdown articles, and it becomes a support assistant for that
product (the product name is a setting). The demo knowledge base is a help center for
[InvoiceFlow](https://github.com/ambreen1038/invoiceflow), my AI invoice processing app. This is a
separate project from InvoiceFlow and shares no code with it.

**Live demo:** https://answertrail.vercel.app (website on Vercel, API on Render, database and sign-in on Supabase).
The API is on a free plan that sleeps when idle, so the first question after a quiet period can take up to a minute.

> Status: landing page, customer chat with saved conversations and follow-up questions, optional customer
> accounts, answer feedback, admin analytics, public evaluation page, document upload, admin login (Supabase),
> hybrid search (built, measured, off by default), rate limiting and tests are done. Deployment is next; there
> is deployed and running.

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

## What's in the app

| Page | Who | What it is |
|---|---|---|
| `/` | everyone | Landing page: what it does, how it works, and live evaluation numbers |
| `/chat` | everyone | The assistant: cited answers, or a clear "not in the help articles". Remembers the conversation, so follow-ups work; thumbs up/down on every answer |
| `/evaluation` | everyone | Every test question with its outcome, per-split results, and the limits of the evaluation |
| `/privacy` | everyone | Plain-language statement of what is stored, who can see it, what is sent to the AI service, and how to delete it |
| `/login` | everyone | Optional: create an account, sign in, or reset a password (`/reset-password` is where the email link lands) |
| `/admin` | administrators | Upload and delete documents (sign in at `/login` with an administrator account) |
| `/admin/analytics` | administrators | What customers ask, how often the articles couldn't answer, and which answers got a thumbs-down |

The landing page has a top navbar; the app pages share a top bar plus a side navbar (a slide-in drawer
on phones). The numbers on the landing and evaluation pages are never typed in: the backend serves them
from `backend/eval/results.json` (`GET /api/evaluation`) and recomputes each question's outcome with the
same grading rules and threshold as the evaluation script, so the pages cannot drift from the real results.

## Conversations, follow-ups and feedback

- **Saved conversations.** Every chat is stored (questions, answers, the sources used). The sidebar
  shows "Recent chats"; opening one reloads it from the server, and "Delete this chat" removes it
  permanently. Nothing identifying (no IP address) is stored with a message, and the page tells visitors
  that questions are saved.
- **Accounts are optional.** Without an account, a conversation's random id (a UUID in the URL) is its
  only key, and the browser remembers its own ids in `localStorage`. With a customer account (email and
  password through Supabase Auth, with email confirmation and password reset), new chats belong to the
  account: they follow the customer across devices and **only that account can open, rate or delete them**
  (anyone else, anonymous visitors included, gets "not found"). Chats started before signing in are
  carried into the account at sign-in; only chats that have no owner can be claimed. While signed in, the
  chat list is kept in memory only, so signing out of a shared computer leaves nothing behind.
- **Being signed in is not being an admin.** Anyone can create a customer account, so the admin pages are
  decided by the server: the account must have a confirmed email on the `ADMIN_EMAILS` allowlist. The
  browser asks `GET /api/me` and shows the Admin menu only when the server says so.
- **Follow-up questions.** "What about PDFs with many pages?" means nothing on its own. When a
  conversation has earlier turns, the latest message is first rewritten into a standalone question using
  the last few turns ("What is the maximum page limit for uploaded PDF files?") and *that* is what gets
  searched. The chat shows "Searched for: …" whenever the rewrite changed the question, so it is never
  hidden. The first question of a chat is never rewritten (no AI call). If the rewrite fails the original
  question is used; if the chat log is down, the answer is still returned.
- **Small touches for real visitors.** A copy button on answers; a "waking up" message when the hosting is slow to respond (free hosting
  sleeps when idle); "Delete this chat" and, when signed in, "Delete all my chats"; a link-preview image and tags for sharing the
  site on LinkedIn or Upwork (set `NEXT_PUBLIC_SITE_URL` once deployed); and a 90-second limit so a stuck request ends with a clear message.
- **Feedback.** Thumbs up/down on every answer, with an optional "what was wrong?" on thumbs-down. A
  rating can only be attached to an assistant reply *inside the conversation it belongs to*, so knowing a
  message number alone is not enough to rate someone else's chat.
- **Analytics (admin).** Totals, answered-vs-declined per day, the questions the articles couldn't
  answer (grouped, most asked first, which is the list of articles to write next) and the answers that
  got a thumbs-down with their comments.

| Endpoint | Purpose |
|---|---|
| `POST /api/ask` | `{question, conversation_id?}`; returns the answer plus `conversation_id`, `message_id`, `rewritten_query` |
| `GET /api/conversations/{id}` | reload a conversation (an anonymous one: anyone who holds the id; an owned one: only its owner) |
| `DELETE /api/conversations/{id}` | delete it, with its messages and feedback (same rule) |
| `POST /api/conversations/{id}/messages/{mid}/feedback` | `{rating: 1 or -1, comment?}` (same rule) |
| `GET /api/me` | who the token belongs to and whether they are an admin (needs `Authorization: Bearer <token>`) |
| `GET /api/me/conversations` | the signed-in customer's chats |
| `POST /api/me/claim` | `{ids: [...]}` move unowned chats into the account |
| `DELETE /api/me/conversations` | delete all of the signed-in customer's chats |
| `GET /api/admin/analytics` | admin only |

A signed-in request is verified by asking Supabase who owns the token (cached for 30 seconds on the
question path; admin endpoints are never cached). A token that is present but invalid is a 401 rather
than being silently treated as anonymous, and if Supabase is unreachable a token holder gets a 503
(anonymous asking keeps working).

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
  that anyone with the public anon key can call. All five tables (documents, chunks, conversations, messages, feedback) have RLS enabled with no policies and
  the `anon`/`authenticated` roles' privileges revoked, so that API cannot read or change documents
  and the admin login can't be bypassed. The backend connects as the table owner, which RLS doesn't
  restrict.

## Supabase setup

1. Create a Supabase project (separate from any other app).
2. **Authentication -> Sign In / Providers -> Email:** keep "Confirm email" **on**, turn "Allow new users
   to sign up" **on** (customers create their own accounts; the admin allowlist is what protects the admin
   pages), and set the minimum password length to 8.
3. **Authentication -> URL Configuration:** set the Site URL to the frontend's address
   (`http://localhost:3000` locally, your real domain once deployed) and add that address, plus
   `/chat` and `/reset-password` under it, to the Redirect URLs. Confirmation and reset emails link there.
4. **Authentication -> Users -> Add user:** create your admin account with "Auto Confirm User" ticked.
5. Put that email in `ADMIN_EMAILS`; copy the Project URL and anon key into `SUPABASE_URL` /
   `SUPABASE_ANON_KEY` (backend) and `NEXT_PUBLIC_SUPABASE_*` (frontend).
6. **Project Settings -> Database -> Connection string -> Session pooler:** use it as `DATABASE_URL`
   (the direct connection is IPv6-only on the free plan). Then load the knowledge base:
   `python -m app.ingest --reset`. The tables and their security settings are created automatically.

Two things to know before real customers use it: Supabase's built-in email sender is limited to a few
messages per hour per project, so sign-up and reset emails will be throttled until you configure your own
SMTP provider; and the free plan pauses a project after a week of inactivity.

Opening sign-ups does not open the database. Customer accounts use the `authenticated` role, which has no
privileges on any table here (the schema code revokes them and enables Row Level Security with no
policies), and the backend never holds the service-role key.

## Rate limiting

Every chat question costs Gemini quota (one embedding plus one generation), so the public endpoint is
limited before any AI call is made:

| Limit | Default | Setting |
|---|---|---|
| Per visitor (IP), per minute, sliding window | 10 | `RATE_LIMIT_PER_MINUTE` |
| Per visitor (IP), per UTC day | 150 | `RATE_LIMIT_PER_CLIENT_PER_DAY` |
| Everyone together, per UTC day (cost backstop) | 500 | `RATE_LIMIT_GLOBAL_PER_DAY` |

A refused request gets HTTP 429 with a `Retry-After` header and a plain message ("Please wait 39
seconds and try again", or "daily capacity reached"). Refused requests consume nothing, so being
blocked never lengthens the block, and invalid requests still count, so junk can't be used to dodge
the limit. The health check is not limited.

Known limits of this design:

- State is in memory: it is per server process and resets on restart. That suits a single free-tier
  instance; several instances would need a shared store such as Redis.
- The visitor key is the connection's IP. Behind a proxy it is only the real visitor if proxy
  headers are handled correctly, and a determined attacker can rotate addresses. The global daily cap
  is the backstop that still bounds total cost. The admin endpoints are protected by login instead.

## Performance note

Moving the database from local Docker to a remote Supabase project made each answer take about 9
seconds, because the code opened a new database connection for every question: roughly 2.3 s to
connect, ~5 s more to set up the `vector` type on it, and only 0.4 s for the query itself. A small
connection pool (connections opened once at start-up and reused) brought the database step from
7.6 s to 0.37 s and the median answer to 2.3 s. The pool's two failure modes are covered by tests
that run against a real Postgres (`RUN_INTEGRATION=1 python -m pytest tests/test_store_integration.py`):
a failed replacement upload leaves the existing document untouched, and a connection the server drops
while idle is replaced transparently. When deploying, put the backend in a region close to the database.

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
| Hard | 8 answerable + 8 unanswerable | 8/8 | 8/8 | 8/8 | 7/8 | 8/8 |

Hallucinated answers (a question the docs don't cover that got an answer anyway): **0/20**.
Median latency 2.3 s, p90 4.5 s, max 8.9 s (retrieval + one LLM call), measured from Lahore against a
Supabase database in Sydney.

Numbers are for the pinned model `gemini-3.5-flash-lite` on the Supabase database. Across runs of this
same pinned model, the hard set scored 7/8 once and 8/8 on later runs: one question ("what happens if I
upload the identical bill twice?") sometimes gets a vaguer answer that doesn't say what happens to the
duplicate. That is the run-to-run variation to expect from an LLM, and it is why single results should
be read as approximate.

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

### Hybrid search

Hybrid search merges the usual meaning-based (vector) ranking with a keyword ranking (Postgres full-text
search) using reciprocal rank fusion. It is implemented and tested, and **switched off by default
(`HYBRID_SEARCH=true` enables it)** because on this corpus it did not help. Measured with
[`backend/eval/compare_retrieval.py`](backend/eval/compare_retrieval.py), retrieval only, on the 40
answerable questions and on 14 short keyword-style queries ("xlsx", "WebP", "1.234,50"):

| Variant | Questions: gold article in top 5 | first chunk correct | share of the top 5 from a correct article | Keyword queries: top 5 / first |
|---|---|---|---|---|
| **Vector only (the app)** | 40/40 | 37/40 | 59% | 14/14, 13/14 |
| Hybrid, any word | 40/40 | 37/40 | 49% | 14/14, 13/14 |
| Hybrid, any distinctive word | 40/40 | 36/40 | 50% | 14/14, 13/14 |
| Hybrid, all distinctive words | 40/40 | 36/40 | 55% | 14/14, 13/14 |

What happened, and what it does and doesn't show:

- **The ceiling is the problem.** Vector search already finds a correct article for every question, so
  there was nothing for a keyword ranking to rescue. The keyword-style queries, where it should have its
  best chance, did not change at all.
- **The naive version was worse, and the article-level metric hid it.** Matching on any question word
  pulled generic chunks into the top 5 (Postgres full-text ranking has no sense of how rare a word is, so
  "invoice" and "upload" match everything) and pushed relevant chunks out: the top-5 share fell from 59% to
  49%. In a full 60-question run this version turned one answerable question into a refusal (a
  troubleshooting chunk was crowded out) and weakened two other answers; that run is kept in
  `eval/results_hybrid_naive.json`. Those answer-level differences are within the run-to-run variation I
  describe above, but the one refusal traced directly to the missing chunk.
- **Filtering to distinctive words and requiring all of them reduced the harm but did not remove it.** I
  stopped there on purpose. Every extra variant tried on the same 40 questions makes the winner look
  better than it really is, and I tried three; the table shows all of them, not just the best.
- **So the published evaluation (`results.json`) is the vector-only system**, which is what runs by default.
- **When to try it again:** a large corpus, exact identifiers (part numbers, error codes, product names), or
  a chunk-level labelled set that measures the whole top 5, not only whether one good chunk is present.

### Follow-up questions

A second, smaller evaluation checks the conversation memory: 14 two-turn cases in
[`backend/eval/followups.jsonl`](backend/eval/followups.jsonl) (11 answerable follow-ups such as "And what
does Failed mean?", 3 out-of-scope ones such as "Can I pay for a higher limit?"), run by
`python eval/run_followups.py`. Each follow-up is run twice: searched exactly as typed, and rewritten into
a standalone question first (what the app does). Each is repeated 3 times because the model varies.

| | Answerable follow-ups correct (11 cases x 3 runs) | Out-of-scope follow-ups declined (3 x 3) |
|---|---|---|
| Without rewriting | 30/33 | 9/9 |
| **With rewriting** | **32/33** | **9/9** |

What this does and doesn't show:

- **The gain is small and concentrated.** Rewriting rescued one case every time ("Does that include the
  ones still needing review?" is refused as typed, because it never names exports) and made no
  difference on most others. Many follow-ups already contain enough words to find the right article on
  a 12-article corpus, so this set can't show how much rewriting would matter on a large one.
- **Rewriting can hurt.** On "What about the totals?" after a question about the line item check, one
  run turned it into "What does the line item check do for the totals?", a muddled question that was then
  refused (a safe failure, but a failure). The other runs rewrote it correctly. The "Searched for: …"
  line in the chat exists partly so a bad rewrite is visible to the customer.
- **Out-of-scope follow-ups were never answered**, with or without rewriting.
- **I corrected my own test once.** In the first run, "Is that checked by the name only?" scored 0/3 without
  rewriting even though the answer ("checked by their contents, not just their name") was right: it cited
  the privacy article, which also says so, and I had listed only the uploading article as correct. I added
  the privacy article to that case and re-ran everything; the first run (27/33 vs 30/33) is kept as
  `followups_results_run1.json`. Both runs favour rewriting by a small margin; neither is a precise rate.
- Same limits as above: I wrote the cases, the grader is phrase-based, and 14 cases is a very small sample.
  The free Gemini quota also returned a few 429s during the runs; the client retried them.

## Deployment

Three pieces, each on its own free tier: the **database and sign-in** on Supabase (already there), the
**backend API** on Render, and the **website** on Vercel.

1. **Backend on Render.** Create a new Blueprint from this repository; it reads [`render.yaml`](render.yaml)
   (Python 3.12, Singapore region, health check `/api/health`). Render asks for the secrets one by one:
   `DATABASE_URL` (Supabase session-pooler string), `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `ADMIN_EMAILS` and `CORS_ORIGINS` (the website's address; set it after step 2, then redeploy). Never use
   the Supabase service-role key; this project does not need it.
2. **Website on Vercel.** Import the repository and set the **Root Directory** to `frontend`. Environment
   variables: `NEXT_PUBLIC_API_URL` (the Render address), `NEXT_PUBLIC_SUPABASE_URL`,
   `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SITE_URL` (the website's own address, for link previews).
3. **Tell Supabase the real address.** Authentication, URL Configuration: set the Site URL to the website's
   address and add `<address>/chat` and `<address>/reset-password` to the Redirect URLs.
4. **Check visitor addresses (important for the rate limits).** Behind Render's proxy the server must read
   each visitor's address from the `X-Forwarded-For` header, counting from the right by the number of trusted
   proxies (`TRUSTED_PROXY_HOPS`; see `backend/app/clientip.py`). I could not confirm Render's exact header layout
   from its documentation, so it was measured on the live site: the header held three addresses (the visitor, then
   Cloudflare, then Render's internal proxy), so the correct value is **3**, not 1. With 1 the server saw only
   Render's internal address, which would have put every visitor under one shared limit. Check it again after any hosting change: sign in as admin, open the Analytics
   page, and look at the **Server check** card at the bottom. "The server sees you as" must be your own public
   IP address (search "what is my IP" to compare). If it shows a Render or Cloudflare address instead, or if
   more than one address is listed in front of yours, change `TRUSTED_PROXY_HOPS` in Render and redeploy.
   Without this, every visitor could end up sharing one rate limit.
5. **Smoke test.** Ask a question on the live site; sign in as admin; create and delete a test chat; request a
   password reset; open the Evaluation and Privacy pages.

Things that will behave differently from a laptop:

- **Cold starts.** Render's free plan puts the API to sleep after 15 minutes without traffic, and waking it
  takes about a minute. The chat shows a "server is waking up" message after 6 seconds instead of looking broken.
- **Hours.** The free plan gives 750 instance hours a month and the service is suspended after that.
- **Rate limits are in memory** and reset whenever the server restarts or wakes up (see "Rate limiting").
- **Sign-up emails** go through Supabase's built-in sender, which allows only a few per hour per project.
  Configure your own email provider (SMTP) in Supabase before sharing the link widely.
- **Library versions are pinned** in `backend/requirements.txt` so a rebuild installs exactly what was tested.

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
python -m pytest                             # 125 offline tests (+14 optional DB integration tests)
python -m app.ingest --reset                 # clean state: only kb/ (required before the evaluation)
python eval/run_eval.py                      # live evaluation (refuses to run if extra documents exist)
```

Frontend: `cd frontend && npm install && npm run dev` (set `NEXT_PUBLIC_API_URL` if the API isn't on :8000).
Chat is at http://localhost:3000/chat, the admin pages at http://localhost:3000/admin and /admin/analytics.

## Project layout

```
kb/                 12 help articles (the knowledge base)
backend/app/        config, extraction, chunking, gemini client, pgvector store (vector + optional hybrid search), chat log, accounts/auth, ingestion, answer logic, FastAPI app
backend/eval/       questions, question builder, evaluation runners (answers, follow-ups), results.json
backend/tests/      offline unit tests
frontend/           Next.js: landing page, chat, evaluation page, admin (documents, analytics), in a shared app shell
```

## Limitations and roadmap

- The knowledge base is synthetic documentation I wrote from how InvoiceFlow actually behaves,
  not a real company's help center.
- Anonymous chats (no account) can be read by anyone holding the link, and clearing browser data forgets
  which chats were yours; signing in fixes both. Customer accounts have no profile page, and deleting an
  account itself needs the Supabase dashboard (the backend deliberately holds no service-role key); the
  "delete all my chats" endpoint exists but has no button yet.
- A revoked sign-in token can keep working on the question path for up to 30 seconds (the verification cache).
- Follow-up handling only looks at the last few turns and was measured on a small set (see below).
- **The evaluation covers the markdown knowledge base only.** PDF upload is covered by unit tests
  (including generated PDFs, a scanned/no-text PDF and a damaged one) and a manual end-to-end check,
  but retrieval quality on messy real-world PDFs has not been measured.
- Text-layer PDFs only; no OCR for scanned documents. Page-based chunking can split a fact across pages.
- Free-tier Supabase projects pause after a week of inactivity.
- Sessions use Supabase's default browser storage; there are two roles (customer, and administrator by allowlist), no finer permissions.
- [x] Deploy (Vercel + Render + Supabase Postgres with pgvector): see Deployment
- [ ] Tool calling with human confirmation before any action (for example, look up an invoice's status)
- [ ] Evaluate on questions written by someone other than the author
