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
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PDF Processing Service</title>
  <style>
    :root {
      --ink: #111111;
      --paper: #efe9dd;
      --red: #d62828;
      --blue: #1d4e89;
      --yellow: #f4b400;
      --rule: 4px;
    }
    * { box-sizing: border-box; }
    html { -webkit-text-size-adjust: 100%; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-weight: 400;
      line-height: 1.1;
      letter-spacing: -0.01em;
      /* faint grid texture, very Bauhaus print */
      background-image:
        linear-gradient(rgba(17,17,17,.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(17,17,17,.035) 1px, transparent 1px);
      background-size: 28px 28px;
    }
    .wrap { max-width: 1080px; margin: 0 auto; padding: clamp(1.25rem, 4vw, 3rem); }

    /* ---- Masthead ------------------------------------------------------ */
    header {
      border: var(--rule) solid var(--ink);
      background: var(--paper);
      display: grid;
      grid-template-columns: 1fr auto;
      align-items: stretch;
    }
    .title { padding: clamp(1rem, 3vw, 2.25rem); border-right: var(--rule) solid var(--ink); }
    .title h1 {
      margin: 0;
      font-size: clamp(2.6rem, 9vw, 6.5rem);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: -0.04em;
      line-height: 0.86;
    }
    .title h1 em { font-style: normal; color: var(--red); }
    .title p {
      margin: 1rem 0 0;
      max-width: 46ch;
      font-size: clamp(.85rem, 1.6vw, 1rem);
      line-height: 1.35;
      letter-spacing: 0;
    }
    /* geometric primary-color motif: square / circle / triangle */
    .motif { display: grid; grid-template-rows: 1fr 1fr 1fr; min-width: clamp(64px, 12vw, 132px); }
    .motif > div { border-bottom: var(--rule) solid var(--ink); position: relative; }
    .motif > div:last-child { border-bottom: 0; }
    .motif .sq { background: var(--blue); }
    .motif .ci { background: var(--paper); }
    .motif .ci::after {
      content: ""; position: absolute; inset: 22%;
      border-radius: 50%; background: var(--yellow);
    }
    .motif .tr { background: var(--paper); overflow: hidden; }
    .motif .tr::after {
      content: ""; position: absolute; inset: 0;
      background: var(--red);
      clip-path: polygon(50% 18%, 100% 100%, 0 100%);
    }

    /* ---- Operations grid ---------------------------------------------- */
    .grid {
      margin-top: var(--rule);
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: var(--rule);
      background: var(--ink); /* gap shows as black rules */
      border: var(--rule) solid var(--ink);
    }
    .cell {
      background: var(--paper);
      padding: clamp(1.1rem, 2.6vw, 1.9rem);
      display: flex;
      flex-direction: column;
      gap: 1rem;
      min-height: 220px;
    }
    .cell .num {
      font-size: .8rem; font-weight: 700; letter-spacing: .18em;
      display: flex; align-items: center; gap: .6rem;
    }
    .cell .num b { font-size: 1rem; }
    .swatch { width: 14px; height: 14px; background: var(--ink); display: inline-block; }
    .cell--merge   .swatch { background: var(--red); }
    .cell--split   .swatch { background: var(--blue); border-radius: 50%; }
    .cell--compress .swatch { background: var(--yellow); }
    .cell--extract .swatch { background: var(--ink); clip-path: polygon(50% 0, 100% 100%, 0 100%); }
    .cell h2 {
      margin: 0;
      font-size: clamp(1.5rem, 3.4vw, 2.3rem);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: -0.03em;
    }
    .cell .desc { margin: -.4rem 0 0; font-size: .82rem; line-height: 1.35; max-width: 34ch; }
    form { margin-top: auto; display: flex; flex-direction: column; gap: .7rem; }

    /* ---- Controls ------------------------------------------------------ */
    input[type=file], input[type=text] {
      font: inherit;
      width: 100%;
      padding: .55rem .65rem;
      background: var(--paper);
      border: 2px solid var(--ink);
      color: var(--ink);
      letter-spacing: 0;
    }
    input[type=file]::file-selector-button {
      font: inherit; font-weight: 700;
      text-transform: uppercase; letter-spacing: .04em;
      margin: -.55rem .7rem -.55rem -.65rem;
      padding: .55rem .8rem;
      border: 0; border-right: 2px solid var(--ink);
      background: var(--ink); color: var(--paper);
      cursor: pointer;
    }
    input[type=file]::file-selector-button:hover { background: var(--red); }
    input::placeholder { color: #6b675e; }
    input:focus-visible { outline: 3px solid var(--yellow); outline-offset: 2px; }

    button[type=submit] {
      font: inherit; font-weight: 700;
      text-transform: uppercase; letter-spacing: .06em;
      padding: .7rem 1rem;
      background: var(--ink); color: var(--paper);
      border: 2px solid var(--ink);
      cursor: pointer;
      transition: transform .08s ease, background .12s ease;
      align-self: flex-start;
    }
    .cell--merge   button[type=submit]:hover { background: var(--red); }
    .cell--split   button[type=submit]:hover { background: var(--blue); }
    .cell--compress button[type=submit]:hover { background: var(--yellow); color: var(--ink); }
    .cell--extract button[type=submit]:hover { background: var(--ink); }
    button[type=submit]:active { transform: translateY(2px); }

    footer {
      margin-top: var(--rule);
      border: var(--rule) solid var(--ink);
      background: var(--ink); color: var(--paper);
      padding: .8rem 1.2rem;
      font-size: .72rem; letter-spacing: .22em; text-transform: uppercase;
      display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
    }

    @media (max-width: 720px) {
      header { grid-template-columns: 1fr; }
      .title { border-right: 0; border-bottom: var(--rule) solid var(--ink); }
      .motif { grid-template-rows: none; grid-template-columns: 1fr 1fr 1fr; min-height: 80px; }
      .motif > div { border-bottom: 0; border-right: var(--rule) solid var(--ink); }
      .motif > div:last-child { border-right: 0; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="title">
        <h1>PDF<br>Process<em>.</em></h1>
        <p>A small utility service. Each operation posts a multipart upload and
           returns the processed file — merge, split, compress, or read the text out.</p>
      </div>
      <div class="motif" aria-hidden="true">
        <div class="sq"></div>
        <div class="ci"></div>
        <div class="tr"></div>
      </div>
    </header>

    <main class="grid">
      <section class="cell cell--merge">
        <div class="num"><span class="swatch"></span><b>01</b>&nbsp;OPERATION</div>
        <h2>Merge</h2>
        <p class="desc">Stitch two or more PDFs into a single document, in order.</p>
        <form action="/merge" method="post" enctype="multipart/form-data">
          <input type="file" name="files" accept="application/pdf" multiple required>
          <button type="submit">Merge &rarr;</button>
        </form>
      </section>

      <section class="cell cell--split">
        <div class="num"><span class="swatch"></span><b>02</b>&nbsp;OPERATION</div>
        <h2>Split</h2>
        <p class="desc">Carve out a page range from a single PDF.</p>
        <form action="/split" method="post" enctype="multipart/form-data">
          <input type="file" name="file" accept="application/pdf" required>
          <input type="text" name="pages" placeholder="PAGES — e.g. 1-3" required>
          <button type="submit">Split &rarr;</button>
        </form>
      </section>

      <section class="cell cell--compress">
        <div class="num"><span class="swatch"></span><b>03</b>&nbsp;OPERATION</div>
        <h2>Compress</h2>
        <p class="desc">Shrink file size while keeping the document intact.</p>
        <form action="/compress" method="post" enctype="multipart/form-data">
          <input type="file" name="file" accept="application/pdf" required>
          <button type="submit">Compress &rarr;</button>
        </form>
      </section>

      <section class="cell cell--extract">
        <div class="num"><span class="swatch"></span><b>04</b>&nbsp;OPERATION</div>
        <h2>Extract</h2>
        <p class="desc">Pull the text out, page by page, as JSON.</p>
        <form action="/extract-text" method="post" enctype="multipart/form-data">
          <input type="file" name="file" accept="application/pdf" required>
          <button type="submit">Extract &rarr;</button>
        </form>
      </section>
    </main>

    <footer>
      <span>PDF Processing Service</span>
      <span>Form &middot; Function &middot; Primary Colour</span>
    </footer>
  </div>
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
