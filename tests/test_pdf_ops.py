"""Unit tests for the core PDF operations.

These exercise the pure functions directly (no HTTP server required), so they
are fast and deterministic in CI.
"""

from __future__ import annotations

import io

import pytest
from app import pdf_ops
from pypdf import PdfReader


def _page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


def test_merge_concatenates_all_pages(one_page_pdf, three_page_pdf):
    merged = pdf_ops.merge_pdfs([one_page_pdf, three_page_pdf])
    assert _page_count(merged) == 4


def test_split_extracts_requested_range(three_page_pdf):
    result = pdf_ops.split_pdf(three_page_pdf, "1-2")
    assert _page_count(result) == 2

    text = pdf_ops.extract_text(result)
    assert "page 1" in text[0]["text"].lower()
    assert "page 2" in text[1]["text"].lower()


def test_extract_text_reads_content(one_page_pdf):
    pages = pdf_ops.extract_text(one_page_pdf)
    assert len(pages) == 1
    assert "Hello PDF world" in pages[0]["text"]


def test_split_rejects_out_of_range(three_page_pdf):
    with pytest.raises(ValueError):
        pdf_ops.split_pdf(three_page_pdf, "1-9")


def test_split_single_page_and_comma_list(three_page_pdf):
    assert _page_count(pdf_ops.split_pdf(three_page_pdf, "2")) == 1
    assert _page_count(pdf_ops.split_pdf(three_page_pdf, "1,3")) == 2


def test_parse_page_range_forms():
    assert pdf_ops.parse_page_range("2", 3) == [1]
    assert pdf_ops.parse_page_range("1-3", 3) == [0, 1, 2]
    assert pdf_ops.parse_page_range("1-2,3", 3) == [0, 1, 2]


def test_parse_page_range_rejects_malformed():
    with pytest.raises(ValueError, match="Invalid page range segment"):
        pdf_ops.parse_page_range("abc", 3)


def test_parse_page_range_rejects_empty_selection():
    with pytest.raises(ValueError, match="No pages selected"):
        pdf_ops.parse_page_range(" , ", 3)


def test_compress_preserves_pages_and_returns_valid_pdf(three_page_pdf):
    out = pdf_ops.compress_pdf(three_page_pdf)
    assert out[:4] == b"%PDF"
    assert _page_count(out) == 3
