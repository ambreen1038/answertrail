"""Compare retrieval with and without hybrid search.  Run from backend/:

    ../.venv/Scripts/python eval/compare_retrieval.py

Retrieval only: no answers are generated, so this costs one batch of embedding calls and finishes in
seconds. For every answerable question we ask "is a chunk from a correct article in the top 5?"
(hit@5), "is the very first chunk from a correct article?" (hit@1), the mean reciprocal rank of
the first correct chunk (MRR: 1.0 = always first, 0.5 = typically second, 0 = never in the top 5)
and what share of the 5 chunks come from a correct article (crowding by junk chunks shows up here).
Four variants run side by side: vector only; hybrid matching ANY question word (naive); hybrid
matching any DISTINCTIVE word; and hybrid requiring ALL distinctive words (what the app does).

Two question sets are used:
  * the 40 answerable questions from questions.jsonl (written as full sentences), and
  * KEYWORD-STYLE queries: short fragments an impatient customer might type ("xlsx", "WebP",
    "1.234,50"). These are where a keyword ranking has the best chance of helping, so they are
    the fairest place to look for a benefit. I wrote them after seeing how the first set behaved
    (so they are not a blind test) and each has a hand-assigned correct article.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store  # noqa: E402
from app.config import settings  # noqa: E402
from app.gemini import embed_texts  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import check_knowledge_base_is_pristine, load_questions  # noqa: E402

HERE = Path(__file__).parent

KEYWORD_QUERIES = [
    ("xlsx", ["07-exporting-data"]),
    ("WebP", ["02-uploading-files"]),
    ("1.234,50", ["12-troubleshooting"]),
    ("formula injection", ["07-exporting-data"]),
    ("0.02 tolerance", ["04-automatic-checks"]),
    ("thermal receipts", ["05-reviewing-invoices"]),
    ("spam folder", ["09-account-and-passwords"]),
    ("row-level security", ["11-privacy-and-security"]),
    ("Delete selected", ["08-deleting-invoices"]),
    ("desktop notification", ["10-notifications"]),
    ("leading zeros", ["07-exporting-data"]),
    ("three attempts", ["03-invoice-statuses", "12-troubleshooting"]),
    ("same vendor same invoice number same total", ["06-duplicates"]),
    ("Sentry error monitoring", ["11-privacy-and-security"]),
]


def rank_of_first_correct(hits, gold):
    for i, h in enumerate(hits):
        if h.doc_slug in gold:
            return i + 1
    return None


def gold_share(hits, gold):
    """Fraction of the 5 returned chunks that come from a correct article. This is the metric that
    shows crowding: hit@5 stays 100% as long as ONE good chunk is present, even if four junk chunks
    have pushed out the other relevant ones the answer needed."""
    return sum(h.doc_slug in gold for h in hits) / max(len(hits), 1)


def run_variant(name, items, vecs):
    """Return per-query (first correct rank, gold share) for one retrieval variant."""
    saved = (settings.hybrid_max_term_share, settings.hybrid_match_all)
    results = []
    try:
        if name == "hybrid_naive":  # every word counts and any one of them is enough
            settings.hybrid_max_term_share, settings.hybrid_match_all = 1.0, False
        elif name == "hybrid_distinctive_any":  # only distinctive words, but any one of them is enough
            settings.hybrid_match_all = False
        for (text, gold), vec in zip(items, vecs):
            hits = store.search(vec, settings.top_k) if name == "vector_only" else store.search(vec, settings.top_k, text)
            results.append((rank_of_first_correct(hits, gold), gold_share(hits, gold)))
    finally:
        settings.hybrid_max_term_share, settings.hybrid_match_all = saved
    return results


def summarize(results):
    n = len(results)
    ranks = [r for r, _ in results]
    return {
        "n": n,
        "hit_at_5": sum(r is not None for r in ranks),
        "hit_at_1": sum(r == 1 for r in ranks),
        "mrr": round(sum(1 / r for r in ranks if r) / n, 3),
        "relevant_share_of_top5": round(sum(g for _, g in results) / n, 3),
    }


VARIANTS = (
    ("vector_only", "vector only"),
    ("hybrid_naive", "hybrid: any word"),
    ("hybrid_distinctive_any", "hybrid: any distinctive word"),
    ("hybrid_distinctive_all", "hybrid: all distinctive words (app)"),
)


def main() -> None:
    store.init_schema()
    check_knowledge_base_is_pristine()
    answerable = [q for q in load_questions() if q["answerable"]]
    sets = {
        "questions": [(q["question"], q["gold_docs"]) for q in answerable],
        "keyword_queries": KEYWORD_QUERIES,
    }
    report = {"top_k": settings.top_k, "hybrid_candidates": settings.hybrid_candidates, "rrf_k": settings.rrf_k,
              "hybrid_max_term_share": settings.hybrid_max_term_share, "sets": {}}
    for set_name, items in sets.items():
        vecs = embed_texts([t for t, _ in items], "RETRIEVAL_QUERY")
        per_variant = {name: run_variant(name, items, vecs) for name, _ in VARIANTS}
        report["sets"][set_name] = {name: summarize(res) for name, res in per_variant.items()}
        print(f"\n{set_name} ({len(items)} queries)")
        for name, label in VARIANTS:
            m = report["sets"][set_name][name]
            print(f"  {label:<38} hit@5 {m['hit_at_5']}/{m['n']}  hit@1 {m['hit_at_1']}/{m['n']}  "
                  f"MRR {m['mrr']}  relevant share of top-5 {m['relevant_share_of_top5']:.0%}")
    (HERE / "retrieval_comparison.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    store.close_pool()


if __name__ == "__main__":
    main()
