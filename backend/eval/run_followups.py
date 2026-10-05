"""Measure follow-up questions, with and without the rewriting step.  Run from backend/:

    ../.venv/Scripts/python eval/run_followups.py

Each case is a two-turn conversation: a first question, then a follow-up that only makes sense with
the first one in mind ("And what does Failed mean?"). For every case we run the follow-up two ways:

  without rewriting   the follow-up is searched exactly as typed (what a chatbot with no memory does)
  with rewriting      the follow-up is first turned into a standalone question using the conversation,
                      exactly as /api/ask does it

Both use the production retrieval threshold and the same pinned model. The follow-up stage is repeated
REPEATS times because the model's output varies slightly from run to run; we report every repeat rather
than the best one. Calls the real Gemini API (metered), so it is a manual script, not part of the tests.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import answer  # noqa: E402
from app.config import settings  # noqa: E402
from app.grading import phrase_correct  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import check_knowledge_base_is_pristine  # noqa: E402

HERE = Path(__file__).parent
REPEATS = 3


def retry(fn, label):
    for attempt in range(3):
        try:
            return fn()
        except Exception as exc:  # network / quota; retry politely
            if attempt == 2:
                raise
            print(f"  retry {label} after error: {exc}")
            time.sleep(5)


def behaved(case: dict, r: answer.Result) -> bool:
    """Answerable: answered, correct by phrase, and cited a gold article. Out of scope: declined."""
    if not case["answerable"]:
        return not r.answered
    cited = {c.id.split("#")[0] for c in r.citations}
    return r.answered and phrase_correct(r.answer, case["any_of"]) and bool(cited & set(case["gold_docs"]))


def main() -> None:
    check_knowledge_base_is_pristine()
    cases = [json.loads(l) for l in (HERE / "followups.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(cases)} two-turn cases x {REPEATS} repeats on {settings.gen_model}\n")

    rows = []
    for case in cases:
        first = retry(lambda: answer.ask(case["first"]), case["id"] + " first")
        history = [{"role": "user", "content": case["first"]}, {"role": "assistant", "content": first.answer}]
        runs = []
        for rep in range(REPEATS):
            raw = retry(lambda: answer.ask(case["followup"]), case["id"] + " raw")
            standalone = retry(lambda: answer.rewrite_question(history, case["followup"]), case["id"] + " rewrite")
            rew = retry(lambda: answer.ask(standalone), case["id"] + " rewritten")
            runs.append({
                "standalone": standalone,
                "without_rewriting": {"ok": behaved(case, raw), "answered": raw.answered, "answer": raw.answer,
                                      "cited": [c.id for c in raw.citations]},
                "with_rewriting": {"ok": behaved(case, rew), "answered": rew.answered, "answer": rew.answer,
                                   "cited": [c.id for c in rew.citations]},
            })
            time.sleep(0.4)
        w = sum(r["without_rewriting"]["ok"] for r in runs)
        r_ = sum(r["with_rewriting"]["ok"] for r in runs)
        print(f"  {case['id']} {'answerable' if case['answerable'] else 'out-of-scope':<12} "
              f"without {w}/{REPEATS}   with {r_}/{REPEATS}   -> {runs[0]['standalone']!r}")
        rows.append({**case, "first_answered": first.answered, "runs": runs})

    def totals(kind: str, answerable: bool) -> tuple[int, int]:
        sel = [r for r in rows if r["answerable"] == answerable]
        return sum(run[kind]["ok"] for r in sel for run in r["runs"]), len(sel) * REPEATS

    report = {"gen_model": settings.gen_model, "repeats": REPEATS, "n_cases": len(rows), "rows": rows}
    for kind in ("without_rewriting", "with_rewriting"):
        a_ok, a_n = totals(kind, True)
        o_ok, o_n = totals(kind, False)
        report[kind] = {"answerable_ok": a_ok, "answerable_total": a_n, "out_of_scope_ok": o_ok, "out_of_scope_total": o_n}
    (HERE / "followups_results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 70)
    for kind, label in (("without_rewriting", "WITHOUT rewriting"), ("with_rewriting", "WITH rewriting   ")):
        s = report[kind]
        print(f"{label}  follow-ups answered correctly {s['answerable_ok']}/{s['answerable_total']}   "
              f"out-of-scope declined {s['out_of_scope_ok']}/{s['out_of_scope_total']}")
    print("\nPer-run detail in eval/followups_results.json")


if __name__ == "__main__":
    main()
