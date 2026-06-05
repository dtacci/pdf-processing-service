"""FastAPI application exposing the PDF operations over HTTP."""

from __future__ import annotations

import io

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app import observability, pdf_ops
from app.config import get_settings

settings = get_settings()
observability.setup_logging(settings.log_level)

app = FastAPI(title="PDF Processing Service", version=settings.app_version)
app.add_middleware(observability.RequestContextMiddleware)
observability.instrument(app)  # exposes /metrics


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PDF Processing Service</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px;
           margin: 2rem auto; padding: 0 1rem; }
    fieldset { margin-bottom: 1.25rem; border: 1px solid #ccc; border-radius: 8px; }
    legend { font-weight: 600; }
    button { padding: .4rem .8rem; }
    input[type=text] { padding: .3rem; }
  </style>
</head>
<body>
  <h1>PDF Processing Service</h1>
  <p>Tiny demo UI. Each form posts a multipart upload and returns the processed file.</p>

  <fieldset>
    <legend>Merge</legend>
    <form action="/merge" method="post" enctype="multipart/form-data">
      <input type="file" name="files" accept="application/pdf" multiple required>
      <button type="submit">Merge</button>
    </form>
  </fieldset>

  <fieldset>
    <legend>Split</legend>
    <form action="/split" method="post" enctype="multipart/form-data">
      <input type="file" name="file" accept="application/pdf" required>
      <input type="text" name="pages" placeholder="e.g. 1-3" required>
      <button type="submit">Split</button>
    </form>
  </fieldset>

  <fieldset>
    <legend>Compress</legend>
    <form action="/compress" method="post" enctype="multipart/form-data">
      <input type="file" name="file" accept="application/pdf" required>
      <button type="submit">Compress</button>
    </form>
  </fieldset>

  <fieldset>
    <legend>Extract text (JSON)</legend>
    <form action="/extract-text" method="post" enctype="multipart/form-data">
      <input type="file" name="file" accept="application/pdf" required>
      <button type="submit">Extract</button>
    </form>
  </fieldset>
</body>
</html>
"""


def _pdf_response(data: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Tiny HTML upload form for browser-based demos."""
    return INDEX_HTML


@app.get("/health")
def health() -> dict:
    """Liveness probe target — is the process up and serving?"""
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict:
    """Readiness probe target — is the app ready to take traffic?

    Stateless today (no upstream deps), so readiness == liveness. Kept as a
    distinct endpoint so dependency checks (DB, cache, …) can be added here
    later without disturbing the liveness signal.
    """
    return {"status": "ready"}


@app.get("/version")
def version() -> dict:
    """Build provenance baked into the image — lets a rollout prove *which*
    build is serving on each pod during a canary."""
    return {
        "version": settings.app_version,
        "git_sha": settings.git_sha,
        "build_time": settings.build_time,
    }


@app.post("/merge")
async def merge(files: list[UploadFile] = File(...)) -> StreamingResponse:
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="merge requires at least two PDF files")
    streams = [await f.read() for f in files]
    try:
        merged = pdf_ops.merge_pdfs(streams)
    except Exception as exc:  # malformed PDF -> client error
        raise HTTPException(status_code=400, detail=f"Failed to merge PDFs: {exc}") from exc
    return _pdf_response(merged, "merged.pdf")


@app.post("/split")
async def split(
    file: UploadFile = File(...),
    pages: str = Form(..., description="Page range, e.g. '1-3'"),
) -> StreamingResponse:
    data = await file.read()
    try:
        result = pdf_ops.split_pdf(data, pages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to split PDF: {exc}") from exc
    return _pdf_response(result, "split.pdf")


@app.post("/compress")
async def compress(file: UploadFile = File(...)) -> StreamingResponse:
    data = await file.read()
    try:
        result = pdf_ops.compress_pdf(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to compress PDF: {exc}") from exc
    return _pdf_response(result, "compressed.pdf")


@app.post("/extract-text")
async def extract_text(file: UploadFile = File(...)) -> JSONResponse:
    data = await file.read()
    try:
        pages = pdf_ops.extract_text(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to extract text: {exc}") from exc
    return JSONResponse({"pages": pages})
