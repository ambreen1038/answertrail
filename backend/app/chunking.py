"""Turn documents into retrievable chunks.

Three strategies, chosen by what structure the document actually has:

* Markdown with ## headings: one chunk per section. The help articles are short and every
  section covers one idea, so a section is the natural unit. Sections longer than
  section_max_chars are split further so one huge section can't become one huge chunk.
* Plain text or markdown with no headings: paragraphs are packed into ~chunk_max_chars chunks.
* PDFs: one or more chunks per page ("Page 3"), because PDF text has no reliable headings or
  paragraph breaks and the page number is a citation a human can actually look up.

The article title and section heading are prepended to the text that gets embedded, so the
embedding sees the topic and not just the body.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from .config import settings


@dataclass
class Chunk:
    id: str
    doc_slug: str
    doc_title: str
    heading: str
    content: str  # body only, shown to the user as the cited passage

    @property
    def embed_text(self) -> str:
        return f"{self.doc_title} - {self.heading}\n\n{self.content}"


# ---------------------------------------------------------------- packing helpers


def _split_long(unit: str, max_chars: int) -> list[str]:
    """Break one oversized unit on sentence ends, then hard-split anything still too long."""
    if len(unit) <= max_chars:
        return [unit]
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", unit):
        while len(sentence) > max_chars:  # no punctuation at all: split on a space near the limit
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            out.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            out.append(sentence)
    return out


def pack(units: list[str], max_chars: int, overlap: int) -> list[str]:
    """Greedily pack units into chunks of about max_chars, repeating a little text between
    neighbouring chunks (overlap) so a fact that straddles a boundary is not cut in half.
    max_chars is a soft cap: the carried-over overlap can push a chunk slightly past it."""
    flat: list[str] = []
    for u in units:
        u = u.strip()
        if u:
            flat.extend(_split_long(u, max_chars))

    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for u in flat:
        if cur and cur_len + len(u) + 1 > max_chars:
            chunks.append(" ".join(cur))
            carry: list[str] = []
            n = 0
            for prev in reversed(cur):
                if n + len(prev) > overlap:
                    break
                carry.insert(0, prev)
                n += len(prev) + 1
            cur, cur_len = carry, sum(len(x) + 1 for x in carry)
        cur.append(u)
        cur_len += len(u) + 1
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def _paragraphs(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _make(slug: str, title: str, parts: list[tuple[str, str]]) -> list[Chunk]:
    return [Chunk(f"{slug}#{i}", slug, title, heading, content) for i, (heading, content) in enumerate(parts)]


# ---------------------------------------------------------------- strategies


def chunk_markdown(slug: str, text: str, title: str | None = None) -> list[Chunk]:
    lines = text.strip().splitlines()
    doc_title = title or slug
    if lines and lines[0].startswith("# "):
        doc_title = title or lines[0][2:].strip()
        lines = lines[1:]

    sections: list[tuple[str, list[str]]] = []
    heading, body = "Overview", []
    for line in lines:
        m = re.match(r"^##\s+(.*)", line)
        if m:
            if "".join(body).strip():
                sections.append((heading, body))
            heading, body = m.group(1).strip(), []
        else:
            body.append(line)
    if "".join(body).strip():
        sections.append((heading, body))

    has_headings = any(h != "Overview" for h, _ in sections) or len(sections) > 1
    if not has_headings:
        return chunk_plain(slug, text, title=doc_title)

    parts: list[tuple[str, str]] = []
    for heading, body_lines in sections:
        content = "\n".join(body_lines).strip()
        if len(content) <= settings.section_max_chars:
            parts.append((heading, content))
        else:
            pieces = pack(_paragraphs(content), settings.chunk_max_chars, settings.chunk_overlap_chars)
            parts.extend((f"{heading} (part {k})", p) for k, p in enumerate(pieces, 1))
    return _make(slug, doc_title, parts)


def chunk_plain(slug: str, text: str, title: str | None = None) -> list[Chunk]:
    pieces = pack(_paragraphs(text), settings.chunk_max_chars, settings.chunk_overlap_chars)
    return _make(slug, title or slug, [(f"Part {k}", p) for k, p in enumerate(pieces, 1)])


def chunk_pages(slug: str, title: str, pages: list[str]) -> list[Chunk]:
    parts: list[tuple[str, str]] = []
    for number, page_text in enumerate(pages, 1):
        flat = re.sub(r"\s+", " ", page_text).strip()
        if not flat:
            continue
        pieces = pack([flat], settings.chunk_max_chars, settings.chunk_overlap_chars)
        for k, piece in enumerate(pieces, 1):
            heading = f"Page {number}" if len(pieces) == 1 else f"Page {number} (part {k})"
            parts.append((heading, piece))
    return _make(slug, title, parts)


def load_kb(kb_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(kb_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path.stem, path.read_text(encoding="utf-8")))
    return chunks
