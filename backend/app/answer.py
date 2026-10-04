"""Retrieve, decide whether we can answer, and generate a grounded, cited answer.

Two independent guards against inventing an answer:
  1. Retrieval gate: if even the best chunk is not similar enough, refuse without calling the LLM.
  2. Model gate: the model must itself report whether the sources actually answer the question.
A question only gets an answer if both agree.
"""
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from . import store
from .config import settings
from .gemini import embed_texts, generate_json

REFUSAL = (
    "I couldn't find that in the help articles, so I don't want to guess. "
    "Try rephrasing your question, or contact support."
)

SYSTEM = (
    f"You are a customer support assistant for {settings.product_name}. Answer ONLY using the numbered "
    "sources provided. If the sources do not contain the answer, set answerable to false and "
    "leave answer empty. Never use outside knowledge and never guess. Do not say a feature "
    "does not exist just because the sources are silent about it. Be concise (1-4 sentences) "
    "and list the ids of the sources you used, such as S1 or S3."
)

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "answerable": {"type": "BOOLEAN"},
        "answer": {"type": "STRING"},
        "sources": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["answerable", "answer", "sources"],
}


@dataclass
class Citation:
    id: str
    doc_title: str
    heading: str
    content: str
    score: float


@dataclass
class Result:
    answered: bool
    answer: str
    reason: str  # "answered" | "low_retrieval_score" | "model_declined"
    citations: list[Citation] = field(default_factory=list)
    retrieved: list[Citation] = field(default_factory=list)  # everything fetched, for debugging/eval
    top_score: float = 0.0
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _cite(h: store.Hit) -> Citation:
    return Citation(h.id, h.doc_title, h.heading, h.content, round(h.score, 4))


def ask(
    question: str,
    *,
    min_similarity: float | None = None,
    retrieve_fn: Callable[[str, int], list[store.Hit]] | None = None,
    generate_fn: Callable[[str, str, dict], dict] | None = None,
) -> Result:
    started = time.perf_counter()
    threshold = settings.min_similarity if min_similarity is None else min_similarity
    retrieve = retrieve_fn or _default_retrieve
    generate = generate_fn or generate_json

    hits = retrieve(question, settings.top_k)
    retrieved = [_cite(h) for h in hits]
    top = hits[0].score if hits else 0.0

    def done(answered, answer, reason, citations=None) -> Result:
        return Result(
            answered=answered,
            answer=answer,
            reason=reason,
            citations=citations or [],
            retrieved=retrieved,
            top_score=round(top, 4),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    if not hits or top < threshold:
        return done(False, REFUSAL, "low_retrieval_score")

    labelled = {f"S{i + 1}": h for i, h in enumerate(hits)}
    context = "\n\n".join(
        f"[{label}] ({h.doc_title} - {h.heading})\n{h.content}" for label, h in labelled.items()
    )
    prompt = f"Sources:\n{context}\n\nQuestion: {question}"
    out = generate(SYSTEM, prompt, SCHEMA)

    cited = [labelled[s] for s in out.get("sources", []) if s in labelled]
    if not out.get("answerable") or not out.get("answer", "").strip() or not cited:
        return done(False, REFUSAL, "model_declined")
    return done(True, out["answer"].strip(), "answered", [_cite(h) for h in cited])


def _default_retrieve(question: str, k: int) -> list[store.Hit]:
    vec = embed_texts([question], "RETRIEVAL_QUERY")[0]
    return store.search(vec, k)
