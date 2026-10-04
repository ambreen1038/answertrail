"""Build tiny, valid PDFs in memory for tests (no extra dependency, no fixture files)."""


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str]) -> bytes:
    """One text line per '\\n'. A page given as '' has no text at all, which is what a scanned PDF
    (a picture of a page) looks like to a text extractor."""
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, text in enumerate(pages):
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i} 0 R "
            "/Resources << /Font << /F1 3 0 R >> >> >>"
        )
        lines = [ln for ln in text.split("\n") if ln != ""]
        body = "BT /F1 12 Tf 50 750 Td 14 TL " + " T* ".join(f"({_esc(ln)}) Tj" for ln in lines) + " ET" if lines else ""
        objs.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
