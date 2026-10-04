"""Thin Gemini REST client: embeddings and JSON-mode generation, with retry on 429/5xx."""
import json
import time

import httpx
import numpy as np

from .config import settings

BASE = "https://generativelanguage.googleapis.com/v1beta"
_RETRYABLE = {429, 500, 502, 503, 504}


class GeminiError(RuntimeError):
    pass


def _post(path: str, payload: dict, attempts: int = 4) -> dict:
    if not settings.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY is not set (see .env.example)")
    headers = {"x-goog-api-key": settings.gemini_api_key, "content-type": "application/json"}
    delay = 2.0
    last = ""
    for attempt in range(attempts):
        resp = httpx.post(f"{BASE}/{path}", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        last = f"{resp.status_code}: {resp.text[:300]}"
        if resp.status_code not in _RETRYABLE or attempt == attempts - 1:
            break
        time.sleep(delay)
        delay *= 2
    raise GeminiError(f"Gemini request failed ({last})")


def embed_texts(texts: list[str], task_type: str) -> np.ndarray:
    """Return L2-normalised embeddings, shape (len(texts), embed_dim).

    task_type is RETRIEVAL_DOCUMENT for chunks and RETRIEVAL_QUERY for questions. Embeddings are
    truncated to embed_dim, which makes them non-unit length, so we normalise them ourselves.
    """
    out: list[list[float]] = []
    for start in range(0, len(texts), 50):
        batch = texts[start : start + 50]
        payload = {
            "requests": [
                {
                    "model": f"models/{settings.embed_model}",
                    "content": {"parts": [{"text": t}]},
                    "taskType": task_type,
                    "outputDimensionality": settings.embed_dim,
                }
                for t in batch
            ]
        }
        data = _post(f"models/{settings.embed_model}:batchEmbedContents", payload)
        out.extend(e["values"] for e in data["embeddings"])
    arr = np.asarray(out, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norms, 1e-12, None)


def generate_json(system: str, prompt: str, schema: dict) -> dict:
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    data = _post(f"models/{settings.gen_model}:generateContent", payload)
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise GeminiError(f"Unexpected Gemini response shape: {exc}") from exc
