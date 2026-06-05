"""Shared pytest fixtures.

PDF fixtures are generated entirely in memory with reportlab so the test suite
needs no external files and no network — it runs cleanly in a CI stage.
"""

from __future__ import annotations

import io

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _make_pdf(pages_lines: list[list[str]]) -> bytes:
    """Build a multi-page PDF where each page renders the given lines of text."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for lines in pages_lines:
        text = c.beginText(72, 720)
        for line in lines:
            text.textLine(line)
        c.drawText(text)
        c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture
def one_page_pdf() -> bytes:
    return _make_pdf([["Hello PDF world"]])


@pytest.fixture
def three_page_pdf() -> bytes:
    return _make_pdf([[f"This is page {n}"] for n in (1, 2, 3)])
