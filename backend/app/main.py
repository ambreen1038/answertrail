from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import answer, documents, evaluation, store
from .auth import require_admin
from .ratelimit import RateLimiter
from .config import settings
from .extract import ExtractionError
from .gemini import GeminiError


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init_schema()  # creates/migrates tables; safe to run on every start-up
    store.get_pool()     # open the database connections now, so the first visitor doesn't pay for it
    yield
    store.close_pool()


app = FastAPI(title="AnswerTrail API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ customer


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=settings.max_question_chars)


@app.get("/api/health")
def health():
    return {"status": "ok", "chunks": store.count_chunks()}


limiter = RateLimiter.from_settings()


def rate_limit_ask(request: Request) -> None:
    """Refuse the request with 429 + Retry-After if this visitor (or the whole demo) is over a limit.
    Runs BEFORE any embedding or generation call, so a refused request costs no quota."""
    client = request.client.host if request.client else "unknown"
    decision = limiter.check(client)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=decision.message,
            headers={"Retry-After": str(decision.retry_after)},
        )


@app.post("/api/ask", dependencies=[Depends(rate_limit_ask)])
def ask(req: AskRequest):
    try:
        result = answer.ask(req.question.strip())
    except GeminiError as exc:
        # Don't leak upstream details to the client.
        raise HTTPException(status_code=502, detail="The answer service is temporarily unavailable.") from exc
    return result.to_dict()


@app.get("/api/evaluation")
def get_evaluation(response: Response):
    """The latest evaluation results, for the public Evaluation page and the landing page."""
    raw = evaluation.load_raw(settings.eval_results_path)
    if raw is None:
        raise HTTPException(status_code=404, detail="No evaluation results have been published yet.")
    response.headers["Cache-Control"] = "public, max-age=300"
    return evaluation.build_report(raw)


# ------------------------------------------------------------------ admin (Supabase login required)

def _doc_json(d: store.DocRecord) -> dict:
    return {
        "id": d.id, "slug": d.slug, "title": d.title, "filename": d.filename,
        "content_type": d.content_type, "n_chunks": d.n_chunks,
        "created_at": d.created_at.isoformat(), "replaced": d.replaced,
    }


@app.get("/api/admin/documents", dependencies=[Depends(require_admin)])
def list_documents():
    return [_doc_json(d) for d in store.list_documents()]


@app.post("/api/admin/documents", dependencies=[Depends(require_admin)], status_code=201)
def upload_document(file: UploadFile = File(...), title: str | None = Form(default=None)):
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)  # read one byte past the limit so we can tell it's too big
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"The file is larger than {settings.max_upload_mb} MB.")
    try:
        doc = documents.ingest_file(file.filename or "upload", data, title)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail="The embedding service is temporarily unavailable. Nothing was saved.") from exc
    return _doc_json(doc)


@app.delete("/api/admin/documents/{doc_id}", dependencies=[Depends(require_admin)], status_code=204)
def delete_document(doc_id: int):
    if not store.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found.")


