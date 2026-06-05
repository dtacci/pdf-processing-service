"""Core PDF operations.

Kept deliberately small and dependency-light: everything works on in-memory
``bytes`` so the same functions are easy to unit-test without a running server
and without touching the filesystem or network.
"""

from __future__ import annotations

import io
from collections.abc import Iterable

from pypdf import PdfReader, PdfWriter


def merge_pdfs(streams: Iterable[bytes]) -> bytes:
    """Merge several PDFs (in order) into a single PDF, returned as bytes."""
    writer = PdfWriter()
    for data in streams:
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def parse_page_range(spec: str, page_count: int) -> list[int]:
    """Parse a 1-indexed page spec into 0-indexed page numbers.

    Accepts forms like ``"2"``, ``"1-3"`` and ``"1-3,5"``. Raises ``ValueError``
    on anything out of bounds or malformed so callers can return a clean 400.
    """
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start, end = int(start_s), int(end_s)
            else:
                start = end = int(part)
        except ValueError:
            raise ValueError(f"Invalid page range segment: {part!r}") from None

        if start < 1 or end < start or end > page_count:
            raise ValueError(
                f"Page range {part!r} is out of bounds for a {page_count}-page document"
            )
        pages.extend(range(start - 1, end))

    if not pages:
        raise ValueError("No pages selected")
    return pages


def split_pdf(data: bytes, page_range: str) -> bytes:
    """Extract the given page range from a PDF, returned as bytes."""
    reader = PdfReader(io.BytesIO(data))
    indices = parse_page_range(page_range, len(reader.pages))

    writer = PdfWriter()
    for i in indices:
        writer.add_page(reader.pages[i])

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def compress_pdf(data: bytes) -> bytes:
    """Return a size-reduced copy of the PDF.

    Uses pypdf's built-in content-stream compression (lossless flate). This is
    intentionally modest — no external binaries — which keeps the container
    image small. For heavier image-recompression you would reach for pikepdf.
    """
    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    for page in writer.pages:
        page.compress_content_streams()

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def extract_text(data: bytes) -> list[dict]:
    """Extract text per page. Returns a list of ``{"page": n, "text": str}``."""
    reader = PdfReader(io.BytesIO(data))
    return [
        {"page": i + 1, "text": page.extract_text() or ""} for i, page in enumerate(reader.pages)
    ]
