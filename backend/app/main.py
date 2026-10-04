from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import answer, documents, store
from .auth import require_admin
from .config import settings
from .extract import ExtractionError
from .gemini import GeminiError


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init_schema()  # creates/migrates tables; safe to run on every start-up
    yield


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


@app.post("/api/ask")
def ask(req: AskRequest):
    try:
        result = answer.ask(req.question.strip())
    except GeminiError as exc:
        # Don't leak upstream details to the client.
        raise HTTPException(status_code=502, detail="The answer service is temporarily unavailable.") from exc
    return result.to_dict()


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


