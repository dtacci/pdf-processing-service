"""HTTP-level smoke tests using FastAPI's TestClient (no live server needed)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


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
