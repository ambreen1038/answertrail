from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import answer, store
from .config import settings
from .gemini import GeminiError

app = FastAPI(title="AI Customer Support Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


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
