# AI Customer Support Assistant

A retrieval-augmented (RAG) support chatbot that answers questions **only from a help center, cites
the exact passages it used, and says "I don't know" instead of guessing**.

It is not tied to one product: point it at any folder of markdown help articles, re-run the ingest
step, and it becomes a support assistant for that product (the product name is a setting). The demo
knowledge base is a help center for [InvoiceFlow](https://github.com/ambreen1038/invoiceflow), my AI
invoice processing app. This is a separate project from InvoiceFlow and shares no code with it.

> Status: backend, evaluation and tests are done; chat UI is built; not deployed yet.

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

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI, Pydantic v2 |
| Vector store | Postgres + pgvector (exact cosine search; no ANN index at this size) |
| Embeddings / generation | Google Gemini (`gemini-embedding-001`, `gemini-flash-lite-latest`) via `httpx` |
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
Median latency 2.6 s, p90 4.3 s (retrieval + one LLM call).

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
cp ../.env.example .env                      # then add your GEMINI_API_KEY
python -m app.ingest                         # chunk, embed and store the knowledge base
uvicorn app.main:app --reload                # API on :8000
python -m pytest                             # offline tests
python eval/run_eval.py                      # live evaluation
```

Frontend: `cd frontend && npm install && npm run dev` (set `NEXT_PUBLIC_API_URL` if the API isn't on :8000).

## Project layout

```
kb/                 12 help articles (the knowledge base)
backend/app/        config, chunking, gemini client, pgvector store, answer logic, FastAPI app
backend/eval/       questions, question builder, evaluation runner, results.json
backend/tests/      offline unit tests
frontend/           Next.js chat UI with citations and a clear "couldn't find that" state
```

## Limitations and roadmap

- The knowledge base is synthetic documentation I wrote from how InvoiceFlow actually behaves,
  not a real company's help center.
- No conversation memory: each question is answered independently.
- No rate limiting or authentication on the API yet.
- [ ] Deploy (Vercel + Render + Supabase Postgres with pgvector)
- [ ] Tool calling with human confirmation before any action (for example, look up an invoice's status)
- [ ] Evaluate on questions written by someone other than the author
