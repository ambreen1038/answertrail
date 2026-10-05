import logging
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import answer, chatlog, documents, evaluation, store
from .auth import User, current_user, require_admin, require_user
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


log = logging.getLogger("answertrail")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=settings.max_question_chars)
    conversation_id: UUID | None = None


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
def ask(req: AskRequest, user: User | None = Depends(current_user)):
    text = req.question.strip()
    cid = str(req.conversation_id) if req.conversation_id else None
    uid = user.id if user else None

    # Conversation memory is a convenience, never a requirement: if the chat log is unavailable the
    # visitor still gets an answer (just without history), and the failure is logged for us.
    history: list[dict[str, str]] = []
    if cid:
        try:
            if chatlog.conversation_visible(cid, uid):
                history = chatlog.recent_turns(cid)
            else:
                cid = None  # unknown, deleted, or someone else's conversation: start a fresh one
        except Exception:
            log.warning("could not load conversation history", exc_info=True)

    # A follow-up like "what about PDFs?" is rewritten into a standalone question before searching.
    query, rewritten = text, None
    if history:
        try:
            standalone = answer.rewrite_question(history, text)
            if standalone and standalone.strip().lower() != text.lower():
                query, rewritten = standalone, standalone
        except GeminiError:
            log.warning("question rewrite failed; searching with the original wording")

    try:
        result = answer.ask(query)
    except GeminiError as exc:
        # Don't leak upstream details to the client.
        raise HTTPException(status_code=502, detail="The answer service is temporarily unavailable.") from exc

    payload = result.to_dict()
    message_id = None
    try:
        if cid is None:
            cid = chatlog.create_conversation(text, uid)
        message_id = chatlog.add_turn(cid, text, result, rewritten)
    except Exception:
        log.warning("could not save the conversation turn", exc_info=True)
    payload.update(conversation_id=cid if message_id is not None else None, message_id=message_id, rewritten_query=rewritten)
    return payload


# ------------------------------------------------------------------ conversations and feedback
# An anonymous conversation's random UUID is its only key. A conversation that belongs to a signed-in
# customer is visible only to them (everyone else gets 404). Message numbers alone are useless: every
# message route also requires the conversation id.


class FeedbackRequest(BaseModel):
    rating: Literal[1, -1]
    comment: str | None = Field(default=None, max_length=500)


@app.get("/api/conversations/{cid}")
def get_conversation(cid: UUID, response: Response, user: User | None = Depends(current_user)):
    convo = chatlog.get_conversation(str(cid), user.id if user else None)
    if convo is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    response.headers["Cache-Control"] = "no-store"
    return convo


@app.delete("/api/conversations/{cid}", status_code=204)
def delete_conversation(cid: UUID, user: User | None = Depends(current_user)):
    if not chatlog.delete_conversation(str(cid), user.id if user else None):
        raise HTTPException(status_code=404, detail="Conversation not found.")


@app.post("/api/conversations/{cid}/messages/{mid}/feedback", status_code=204)
def give_feedback(cid: UUID, mid: int, req: FeedbackRequest, user: User | None = Depends(current_user)):
    if not chatlog.set_feedback(str(cid), mid, req.rating, req.comment, user.id if user else None):
        raise HTTPException(status_code=404, detail="Message not found.")


# ------------------------------------------------------------------ the signed-in customer


@app.get("/api/me")
def me(response: Response, user: User = Depends(require_user)):
    """Who the token belongs to, and whether they may use the admin pages (the browser uses this to
    decide what to show; every admin endpoint still checks for itself)."""
    response.headers["Cache-Control"] = "no-store"
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin}


@app.get("/api/me/conversations")
def my_conversations(response: Response, user: User = Depends(require_user)):
    response.headers["Cache-Control"] = "no-store"
    return chatlog.list_conversations(user.id)


class ClaimRequest(BaseModel):
    ids: list[UUID] = Field(max_length=30)


@app.post("/api/me/claim")
def claim_conversations(req: ClaimRequest, user: User = Depends(require_user)):
    """Carry chats started before signing in into the account. Only unowned conversations move."""
    return {"claimed": chatlog.claim_conversations(user.id, [str(i) for i in req.ids])}


@app.delete("/api/me/conversations", status_code=204)
def delete_my_conversations(user: User = Depends(require_user)):
    chatlog.delete_all_for_user(user.id)


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


@app.get("/api/admin/analytics", dependencies=[Depends(require_admin)])
def get_analytics(response: Response):
    """Usage and quality numbers for the admin: answered vs refused, latency, feedback, and the
    questions the documents could not answer (a to-do list of missing documentation)."""
    response.headers["Cache-Control"] = "no-store"
    return chatlog.analytics()


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


