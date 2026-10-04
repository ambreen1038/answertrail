"""Offline tests: no network, no database, no API key needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import answer, store  # noqa: E402
from app.chunking import chunk_markdown, load_kb  # noqa: E402
from app.config import settings  # noqa: E402
from eval.run_eval import phrase_correct, score  # noqa: E402

ARTICLE = """# Uploading files

## Supported file types

PDF and PNG only.

## File size limit

Up to 10 MB.
"""


def test_chunking_one_chunk_per_section_with_stable_ids():
    chunks = chunk_markdown("02-uploading", ARTICLE)
    assert [c.heading for c in chunks] == ["Supported file types", "File size limit"]
    assert [c.id for c in chunks] == ["02-uploading#0", "02-uploading#1"]
    assert chunks[0].doc_title == "Uploading files"
    # the embedding text carries the topic, the cited passage stays body-only
    assert chunks[1].embed_text.startswith("Uploading files - File size limit")
    assert chunks[1].content == "Up to 10 MB."


def test_real_knowledge_base_loads_and_ids_are_unique():
    chunks = load_kb(settings.kb_dir)
    assert len(chunks) >= 40
    assert len({c.id for c in chunks}) == len(chunks)
    assert all(c.content.strip() for c in chunks)


def _hit(i, score_):
    return store.Hit(f"doc#{i}", "doc", "Doc", f"Heading {i}", f"body {i}", score_)


def test_low_retrieval_score_refuses_without_calling_the_llm():
    def boom(*a):
        raise AssertionError("LLM must not be called below the threshold")

    r = answer.ask("anything", min_similarity=0.6,
                   retrieve_fn=lambda q, k: [_hit(0, 0.4)], generate_fn=boom)
    assert not r.answered and r.reason == "low_retrieval_score"
    assert r.answer == answer.REFUSAL


def test_model_declining_means_refusal_even_with_high_similarity():
    r = answer.ask("q", min_similarity=0.5, retrieve_fn=lambda q, k: [_hit(0, 0.9)],
                   generate_fn=lambda *a: {"answerable": False, "answer": "", "sources": []})
    assert not r.answered and r.reason == "model_declined"


def test_answer_without_a_valid_citation_is_refused():
    # An uncited answer is indistinguishable from an invented one, so it must not be shown.
    r = answer.ask("q", min_similarity=0.5, retrieve_fn=lambda q, k: [_hit(0, 0.9)],
                   generate_fn=lambda *a: {"answerable": True, "answer": "Sure.", "sources": ["S9"]})
    assert not r.answered and r.reason == "model_declined"


def test_grounded_answer_returns_only_the_cited_sources():
    hits = [_hit(0, 0.9), _hit(1, 0.8), _hit(2, 0.7)]
    r = answer.ask("q", min_similarity=0.5, retrieve_fn=lambda q, k: hits,
                   generate_fn=lambda *a: {"answerable": True, "answer": " 10 MB. ", "sources": ["S2"]})
    assert r.answered and r.answer == "10 MB."
    assert [c.id for c in r.citations] == ["doc#1"]
    assert len(r.retrieved) == 3  # everything fetched stays available for debugging


def test_phrase_grader_requires_every_group_and_ignores_case():
    assert phrase_correct("Up to 10 MB each", [["10 MB", "10MB"]])
    assert phrase_correct("you must acknowledge it", [["acknowledg"]])
    assert phrase_correct("you must acknowledge it", [["acknowledg"]]) is True
    assert not phrase_correct("PDF only", [["PDF"], ["PNG"]])


def test_score_counts_hallucinations_and_false_refusals():
    rows = [
        {"answerable": True, "model_answered": True, "top_score": 0.8, "answer": "10 MB",
         "any_of": [["10 MB"]], "gold_docs": ["a"], "cited_docs": ["a"],
         "retrieved_docs": ["a"], "split": "dev"},
        {"answerable": True, "model_answered": False, "top_score": 0.8, "answer": "",
         "any_of": [["x"]], "gold_docs": ["a"], "cited_docs": [], "retrieved_docs": ["a"], "split": "dev"},
        {"answerable": False, "model_answered": True, "top_score": 0.7, "answer": "made up",
         "gold_docs": [], "cited_docs": ["a"], "retrieved_docs": ["a"], "split": "dev"},
    ]
    s = score(rows, 0.0)
    assert s["correct_answers"] == 1
    assert s["false_refusals"] == 1
    assert s["hallucinated_answers"] == 1
    assert s["correct_behaviour"] == 1
    # raising the gate above every score turns the hallucination into a correct refusal
    assert score(rows, 0.9)["hallucinated_answers"] == 0
