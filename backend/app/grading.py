"""Answer grading shared by the evaluation script and the public evaluation page."""


def phrase_correct(text: str, any_of: list[list[str]]) -> bool:
    """An answer counts as correct only if EVERY group has at least one of its phrases present
    (case-insensitive). Deliberately crude: it can pass a sloppy answer and fail a good paraphrase,
    which is a stated limitation of the evaluation."""
    t = text.lower()
    return all(any(p.lower() in t for p in group) for group in any_of)
