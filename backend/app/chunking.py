"""Split markdown help articles into one chunk per section.

The articles are short and every section covers one idea, so a section is the natural unit:
small enough to retrieve precisely, big enough to answer on its own. The article title and
section heading are prepended to the chunk text so the embedding sees the topic, not just the body.
"""
import re
from dataclasses import dataclass
from pathlib import Path


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


def chunk_markdown(slug: str, text: str) -> list[Chunk]:
    lines = text.strip().splitlines()
    title = slug
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
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

    return [
        Chunk(
            id=f"{slug}#{i}",
            doc_slug=slug,
            doc_title=title,
            heading=heading,
            content="\n".join(b).strip(),
        )
        for i, (heading, b) in enumerate(sections)
    ]


def load_kb(kb_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(kb_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path.stem, path.read_text(encoding="utf-8")))
    return chunks
