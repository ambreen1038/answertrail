"""Turn an uploaded file into text, or refuse it with a message a human can act on."""
import io
import re
from dataclasses import dataclass
from pathlib import PurePath

from pypdf import PdfReader

from .config import settings

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}
MIN_TEXT_CHARS = 50  # below this we treat the file as having no usable text


class ExtractionError(ValueError):
    """The file can't be turned into searchable text. The message is safe to show the admin."""


@dataclass
class Extracted:
    title: str
    kind: str  # "pdf" | "markdown" | "text"
    pages: list[str]  # PDFs: one entry per page. Markdown/text: a single entry.


def slugify(filename: str) -> str:
    stem = PurePath(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug or "document"


def _pretty(filename: str) -> str:
    return re.sub(r"[-_]+", " ", PurePath(filename).stem).strip().title() or "Untitled"


def extract(filename: str, data: bytes) -> Extracted:
    ext = PurePath(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ExtractionError("Only PDF, Markdown (.md) or text (.txt) files can be uploaded.")
    if not data:
        raise ExtractionError("The file is empty.")

    if ext == ".pdf":
        return _extract_pdf(filename, data)

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExtractionError("The file isn't valid UTF-8 text.") from None
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise ExtractionError("The file has almost no text in it.")

    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first[2:].strip() if first.startswith("# ") else _pretty(filename)
    return Extracted(title=title, kind="markdown" if ext == ".md" else "text", pages=[text])


def _extract_pdf(filename: str, data: bytes) -> Extracted:
    # Check the file's contents, not just its name: a renamed file must not get this far.
    if not data.startswith(b"%PDF"):
        raise ExtractionError("This file has a .pdf name but isn't a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("The PDF is password-protected.")
        n_pages = len(reader.pages)
        if n_pages > settings.max_pdf_pages:
            raise ExtractionError(
                f"The PDF has {n_pages} pages; the limit is {settings.max_pdf_pages}."
            )
        pages = [(page.extract_text() or "") for page in reader.pages]
        meta_title = (reader.metadata.title or "").strip() if reader.metadata else ""
    except ExtractionError:
        raise
    except Exception:  # pypdf raises many different errors for damaged files
        raise ExtractionError("The PDF couldn't be read. It may be damaged.") from None

    if sum(len(p.strip()) for p in pages) < MIN_TEXT_CHARS:
        raise ExtractionError(
            "No text could be extracted. This looks like a scanned PDF (images of pages). "
            "Scanned documents need OCR, which isn't supported."
        )
    return Extracted(title=meta_title or _pretty(filename), kind="pdf", pages=pages)
