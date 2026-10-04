"""The public evaluation report must be derived from the real results, with the real rules."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evaluation, main  # noqa: E402
from app.config import settings  # noqa: E402


def row(id_, answerable, model_answered, score, answer="", any_of=None, split="test"):
    return {"id": id_, "split": split, "question": f"q {id_}", "answerable": answerable,
            "model_answered": model_answered, "top_score": score, "answer": answer,
            "any_of": any_of or [], "gold_docs": ["doc-a"], "cited_docs": ["doc-a"] if model_answered else []}


def raw_report(rows, threshold=0.5):
    split = {"n_answerable": 1, "n_unanswerable": 1, "correct_answers": 1, "correct_refusals": 1,
             "hallucinated_answers": 0, "retrieval_hit_at_k": 1, "retrieval_hit_at_1": 1,
             "citation_ok": 1, "answered": 1, "false_refusals": 0, "correct_behaviour": 2, "n_total": 2, "threshold": threshold}
    return {"gen_model": "m", "embed_model": "e", "top_k": 5, "tuned_threshold": threshold, "rows": rows,
            "dev_at_tuned": split, "test_at_tuned": split, "hard_at_tuned": split}


@pytest.mark.parametrize("r, expected", [
    (row("a", True, True, 0.8, "Up to 10 MB", [["10 MB"]]), "correct"),
    (row("b", True, True, 0.8, "I think it is big", [["10 MB"]]), "wrong_answer"),
    (row("c", True, False, 0.8), "false_refusal"),
    (row("d", True, True, 0.4, "Up to 10 MB", [["10 MB"]]), "false_refusal"),   # below the retrieval threshold
    (row("e", False, False, 0.7), "correct_refusal"),
    (row("f", False, True, 0.7, "Made up"), "invented_answer"),
    (row("g", False, True, 0.3, "Made up"), "correct_refusal"),                 # the threshold gate caught it
])
def test_each_question_outcome_uses_the_same_rules_as_the_evaluation(r, expected):
    assert evaluation.outcome(r, 0.5) == expected


def test_report_totals_and_privacy_of_refused_answers():
    rows = [row("a", True, True, 0.8, "Up to 10 MB", [["10 MB"]]), row("b", False, False, 0.6),
            row("c", False, True, 0.7, "Invented!")]
    rep = evaluation.build_report(raw_report(rows))
    assert rep["totals"] == {"questions": 3, "passed": 2, "out_of_scope": 2, "invented_answers": 1}
    by_id = {q["id"]: q for q in rep["questions"]}
    assert by_id["a"]["passed"] and by_id["a"]["answer"] == "Up to 10 MB"
    assert by_id["b"]["answer"] is None            # a refusal has no answer to show
    assert not by_id["c"]["passed"] and by_id["c"]["outcome"] == "invented_answer"
    assert set(rep["splits"]) == {"dev", "test", "hard"}


def test_endpoint_serves_the_report_with_caching_and_404s_when_there_is_none(tmp_path, monkeypatch):
    c = TestClient(main.app)
    monkeypatch.setattr(settings, "eval_results_path", tmp_path / "missing.json")
    assert c.get("/api/evaluation").status_code == 404

    good = tmp_path / "results.json"
    good.write_text(json.dumps(raw_report([row("a", True, True, 0.8, "Up to 10 MB", [["10 MB"]])])), encoding="utf-8")
    monkeypatch.setattr(settings, "eval_results_path", good)
    r = c.get("/api/evaluation")
    assert r.status_code == 200 and r.json()["totals"]["questions"] == 1
    assert "max-age" in r.headers["cache-control"]

    good.write_text("{not json", encoding="utf-8")
    assert c.get("/api/evaluation").status_code == 404   # corrupt file: no crash, no partial data


def test_the_real_results_file_produces_a_consistent_report():
    raw = evaluation.load_raw(settings.eval_results_path)
    assert raw is not None, "backend/eval/results.json must be committed"
    rep = evaluation.build_report(raw)
    # the per-question outcomes recomputed here must agree with the numbers the eval script reported
    for split in ("dev", "test", "hard"):
        qs = [q for q in rep["questions"] if q["split"] == split]
        assert sum(q["outcome"] == "correct" for q in qs) == rep["splits"][split]["correct_answers"]
        assert sum(q["outcome"] == "correct_refusal" for q in qs) == rep["splits"][split]["correct_refusals"]
        assert sum(q["outcome"] == "invented_answer" for q in qs) == rep["splits"][split]["hallucinated_answers"]
