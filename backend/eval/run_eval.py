"""Evaluate retrieval, answer correctness, citations and refusals.  Run from backend/:

    ../.venv/Scripts/python eval/run_eval.py

Calls the real Gemini API (metered), so it is a manual script, not part of the test suite.

Method
------
1. Every question is run ONCE with the retrieval gate disabled, so we always get the model's own
   answer/decline plus the top retrieval score.
2. The retrieval-gate threshold is then applied offline: a question counts as "answered" only if
   top_score >= T AND the model answered. This lets us sweep T without extra API calls.
3. T is chosen on the DEV split only. Headline numbers are reported on the TEST split.
4. We also report the model-gate-only result (T = 0) so the retrieval gate's actual contribution
   is visible instead of assumed.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import answer  # noqa: E402
from app.config import settings  # noqa: E402

HERE = Path(__file__).parent


def load_questions() -> list[dict]:
    return [json.loads(l) for l in (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def phrase_correct(text: str, any_of: list[list[str]]) -> bool:
    t = text.lower()
    return all(any(p.lower() in t for p in group) for group in any_of)


def run_all(questions: list[dict]) -> list[dict]:
    rows = []
    for q in questions:
        for attempt in range(3):
            try:
                r = answer.ask(q["question"], min_similarity=-1.0)  # gate off
                break
            except Exception as exc:  # network / quota; retry politely
                if attempt == 2:
                    raise
                print(f"  retry {q['id']} after error: {exc}")
                time.sleep(5)
        retrieved_docs = [c.id.split("#")[0] for c in r.retrieved]
        cited_docs = [c.id.split("#")[0] for c in r.citations]
        rows.append({
            **q,
            "top_score": r.top_score,
            "model_answered": r.answered,
            "answer": r.answer,
            "retrieved_docs": retrieved_docs,
            "cited_docs": cited_docs,
            "latency_ms": r.latency_ms,
        })
        print(f"  {q['id']} score={r.top_score:.3f} model_answered={r.answered}")
        time.sleep(0.4)
    return rows


def score(rows: list[dict], threshold: float) -> dict:
    ans = [r for r in rows if r["answerable"]]
    una = [r for r in rows if not r["answerable"]]

    def answered(r):
        return r["model_answered"] and r["top_score"] >= threshold

    answered_a = [r for r in ans if answered(r)]
    correct_a = [r for r in answered_a if phrase_correct(r["answer"], r["any_of"])]
    cited_ok = [r for r in answered_a if set(r["cited_docs"]) & set(r["gold_docs"])]
    refused_u = [r for r in una if not answered(r)]
    behaved = len(correct_a) + len(refused_u)
    return {
        "threshold": round(threshold, 3),
        "n_answerable": len(ans),
        "n_unanswerable": len(una),
        "retrieval_hit_at_k": sum(1 for r in ans if set(r["retrieved_docs"]) & set(r["gold_docs"])),
        "retrieval_hit_at_1": sum(1 for r in ans if r["retrieved_docs"] and r["retrieved_docs"][0] in r["gold_docs"]),
        "answered": len(answered_a),
        "false_refusals": len(ans) - len(answered_a),
        "correct_answers": len(correct_a),
        "citation_ok": len(cited_ok),
        "correct_refusals": len(refused_u),
        "hallucinated_answers": len(una) - len(refused_u),
        "correct_behaviour": behaved,
        "n_total": len(rows),
    }


def tune_threshold(dev_rows: list[dict]) -> float:
    best_t, best = 0.0, -1
    grid = [round(0.30 + 0.01 * i, 2) for i in range(0, 56)]  # 0.30 .. 0.85
    results = [(t, score(dev_rows, t)["correct_behaviour"]) for t in grid]
    top = max(s for _, s in results)
    plateau = [t for t, s in results if s == top]
    best_t = plateau[len(plateau) // 2]  # middle of the best plateau, not its fragile edge
    return best_t


def fmt(label: str, s: dict) -> str:
    a, u = s["n_answerable"], s["n_unanswerable"]
    return (
        f"{label} (T={s['threshold']}, {a} answerable + {u} unanswerable)\n"
        f"  retrieval: gold article in top-5   {s['retrieval_hit_at_k']}/{a}   |   ranked #1   {s['retrieval_hit_at_1']}/{a}\n"
        f"  answered {s['answered']}/{a}   false refusals {s['false_refusals']}/{a}\n"
        f"  correct answers      {s['correct_answers']}/{a}\n"
        f"  citation points at a gold article  {s['citation_ok']}/{s['answered']} of answered\n"
        f"  correct refusals     {s['correct_refusals']}/{u}   hallucinated answers {s['hallucinated_answers']}/{u}\n"
        f"  correct behaviour    {s['correct_behaviour']}/{s['n_total']}"
    )


def check_knowledge_base_is_pristine() -> None:
    """The questions were written against kb/ only. Extra uploaded documents (or missing ones)
    would quietly change what is retrievable and make the numbers meaningless, so refuse to run."""
    from app import store

    expected = {p.stem for p in settings.kb_dir.glob("*.md")}
    present = {d.slug for d in store.list_documents()}
    extra, missing = sorted(present - expected), sorted(expected - present)
    if extra or missing:
        print("The database does not match kb/, so these results would not be valid.")
        if extra:
            print("  extra documents:", ", ".join(extra))
        if missing:
            print("  missing documents:", ", ".join(missing))
        print("Fix: run  python -m app.ingest --reset  and then re-run the evaluation.")
        raise SystemExit(1)


def main() -> None:
    check_knowledge_base_is_pristine()
    questions = load_questions()
    print(f"Running {len(questions)} questions against {settings.gen_model} ...")
    rows = run_all(questions)

    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]
    hard = [r for r in rows if r["split"] == "hard"]
    t = tune_threshold(dev)

    report = {
        "gen_model": settings.gen_model,
        "embed_model": settings.embed_model,
        "top_k": settings.top_k,
        "tuned_threshold": t,
        "dev_at_tuned": score(dev, t),
        "test_at_tuned": score(test, t),
        "test_model_gate_only": score(test, 0.0),
        "dev_model_gate_only": score(dev, 0.0),
        "hard_at_tuned": score(hard, t),
        "hard_model_gate_only": score(hard, 0.0),
        "rows": rows,
    }
    (HERE / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 70)
    print(fmt("DEV   model gate only", report["dev_model_gate_only"]))
    print(fmt("DEV   tuned threshold", report["dev_at_tuned"]))
    print(fmt("TEST  model gate only", report["test_model_gate_only"]))
    print(fmt("TEST  tuned threshold  <-- headline", report["test_at_tuned"]))
    print(fmt("HARD  model gate only", report["hard_model_gate_only"]))
    print(fmt("HARD  tuned threshold (not tuned on this set)", report["hard_at_tuned"]))
    print(f"\nTuned on dev: T={t}. Full per-question detail in eval/results.json")


if __name__ == "__main__":
    main()
