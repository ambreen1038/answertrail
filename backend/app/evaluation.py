"""Turn the raw evaluation output (backend/eval/results.json) into what the public page shows.

The numbers shown on the website are never typed in by hand: they are read from the same file the
evaluation script writes, and each question's outcome is recomputed here with the same rules
(including the tuned retrieval threshold), so the page can't drift from the real results.
"""
import json
from pathlib import Path

from .grading import phrase_correct

SPLITS = ("dev", "test", "hard")


def load_raw(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def outcome(row: dict, threshold: float) -> str:
    answered = bool(row["model_answered"]) and row["top_score"] >= threshold
    if row["answerable"]:
        if not answered:
            return "false_refusal"
        return "correct" if phrase_correct(row["answer"], row["any_of"]) else "wrong_answer"
    return "invented_answer" if answered else "correct_refusal"


def build_report(raw: dict) -> dict:
    threshold = raw["tuned_threshold"]
    questions = []
    for row in raw["rows"]:
        out = outcome(row, threshold)
        answered = out in ("correct", "wrong_answer", "invented_answer")
        questions.append({
            "id": row["id"],
            "split": row["split"],
            "question": row["question"],
            "answerable": row["answerable"],
            "outcome": out,
            "passed": out in ("correct", "correct_refusal"),
            "answer": row["answer"] if answered else None,
            "top_score": round(row["top_score"], 3),
            "gold_docs": row.get("gold_docs", []),
            "cited_docs": row.get("cited_docs", []),
        })
    out_of_scope = [q for q in questions if not q["answerable"]]
    return {
        "gen_model": raw["gen_model"],
        "embed_model": raw["embed_model"],
        "top_k": raw["top_k"],
        "threshold": threshold,
        "splits": {s: raw[f"{s}_at_tuned"] for s in SPLITS},
        "totals": {
            "questions": len(questions),
            "passed": sum(q["passed"] for q in questions),
            "out_of_scope": len(out_of_scope),
            "invented_answers": sum(q["outcome"] == "invented_answer" for q in out_of_scope),
        },
        "questions": questions,
    }
