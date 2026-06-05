"""HTTP-level smoke tests using FastAPI's TestClient (no live server needed)."""

from __future__ import annotations

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_returns_ready():
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


def test_version_exposes_build_metadata():
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"version", "git_sha", "build_time"}


def test_metrics_endpoint_is_prometheus_exposition():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    # Prometheus text exposition format starts each metric family with # HELP.
    assert "# HELP" in resp.text


def test_response_carries_request_id_header():
    resp = client.get("/health")
    assert resp.headers.get("x-request-id")


def test_index_serves_html_form():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<form" in resp.text


def test_merge_endpoint_returns_pdf(one_page_pdf, three_page_pdf):
    resp = client.post(
        "/merge",
        files=[
            ("files", ("a.pdf", one_page_pdf, "application/pdf")),
            ("files", ("b.pdf", three_page_pdf, "application/pdf")),
        ],
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_merge_requires_two_files(one_page_pdf):
    resp = client.post(
        "/merge",
        files=[("files", ("a.pdf", one_page_pdf, "application/pdf"))],
    )
    assert resp.status_code == 400
    assert "at least two" in resp.json()["detail"]


def test_merge_rejects_non_pdf(one_page_pdf):
    resp = client.post(
        "/merge",
        files=[
            ("files", ("junk.pdf", b"not a pdf", "application/pdf")),
            ("files", ("a.pdf", one_page_pdf, "application/pdf")),
        ],
    )
    assert resp.status_code == 400
    assert "Failed to merge" in resp.json()["detail"]


def test_split_endpoint_returns_pdf(three_page_pdf):
    resp = client.post(
        "/split",
        files=[("file", ("b.pdf", three_page_pdf, "application/pdf"))],
        data={"pages": "1-2"},
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_split_endpoint_rejects_out_of_range(three_page_pdf):
    resp = client.post(
        "/split",
        files=[("file", ("b.pdf", three_page_pdf, "application/pdf"))],
        data={"pages": "1-9"},
    )
    assert resp.status_code == 400
    assert "out of bounds" in resp.json()["detail"]


def test_split_endpoint_rejects_malformed_range(three_page_pdf):
    resp = client.post(
        "/split",
        files=[("file", ("b.pdf", three_page_pdf, "application/pdf"))],
        data={"pages": "abc"},
    )
    assert resp.status_code == 400


def test_compress_endpoint_returns_pdf(three_page_pdf):
    resp = client.post(
        "/compress",
        files=[("file", ("b.pdf", three_page_pdf, "application/pdf"))],
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_compress_endpoint_rejects_non_pdf():
    resp = client.post(
        "/compress",
        files=[("file", ("junk.pdf", b"not a pdf", "application/pdf"))],
    )
    assert resp.status_code == 400


def test_extract_text_endpoint_returns_json(three_page_pdf):
    resp = client.post(
        "/extract-text",
        files=[("file", ("b.pdf", three_page_pdf, "application/pdf"))],
    )
    assert resp.status_code == 200
    pages = resp.json()["pages"]
    assert len(pages) == 3
    assert "page 1" in pages[0]["text"].lower()


def test_extract_text_endpoint_rejects_non_pdf():
    resp = client.post(
        "/extract-text",
        files=[("file", ("junk.pdf", b"not a pdf", "application/pdf"))],
    )
    assert resp.status_code == 400
