# PDF Processing Service

A small, container-friendly FastAPI microservice for basic PDF operations.
Built for a CI/CD lab (build → test → push image → canary deploy on Kubernetes).

## Endpoints

| Method | Path            | Description                                                        |
|--------|-----------------|--------------------------------------------------------------------|
| POST   | `/merge`        | Multiple PDFs → one merged PDF (streaming download)                |
| POST   | `/split`        | One PDF + `pages` form field (e.g. `1-3`) → extracted pages        |
| POST   | `/compress`     | One PDF → size-reduced PDF (lossless content-stream compression)   |
| POST   | `/extract-text` | One PDF → `{"pages": [{"page": n, "text": "..."}]}` JSON           |
| GET    | `/health`       | `{"status": "ok"}` — liveness probe target                         |
| GET    | `/readyz`       | `{"status": "ready"}` — readiness probe target                     |
| GET    | `/version`      | Build provenance: `{version, git_sha, build_time}` (baked at build)|
| GET    | `/metrics`      | Prometheus RED metrics — feeds automated canary verification       |
| GET    | `/`             | Tiny HTML upload form for browser demos                            |

## Project structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app + routes
│   ├── pdf_ops.py       # Pure PDF functions (merge/split/compress/extract)
│   ├── config.py        # Env-driven settings + baked build metadata
│   └── observability.py # JSON logging, request IDs, Prometheus /metrics
├── tests/
│   ├── conftest.py      # In-memory PDF fixtures (reportlab)
│   ├── test_pdf_ops.py  # Unit tests for the core functions
│   └── test_api.py      # TestClient smoke tests (routes, metrics, version)
├── deploy/helm/pdf-service/  # Helm chart: hardened, templated, canary-ready
├── scripts/smoke-test.sh     # Container build→run→round-trip smoke test
├── Dockerfile           # Multi-stage, slim, non-root, digest-pinned base
├── Makefile             # One entrypoint per CI gate (lint/type/test/build/...)
├── pyproject.toml       # ruff + mypy + pytest + coverage config
├── .dockerignore
├── requirements.txt     # Runtime deps (pinned)
└── requirements-dev.txt # + pytest, ruff, mypy, coverage, reportlab, httpx
```

## Configuration

| Env var | Default | Purpose                        |
|---------|---------|--------------------------------|
| `PORT`  | `8000`  | Port uvicorn binds inside the container |

## Local development

The **canonical, reproducible** build-and-test path is Docker (see below) — that
is exactly what CI runs, so "works in the container" == "works in the pipeline".
No host Python state to drift, no `pip install` on the host.

For a quick inner-loop on the host, if the dev dependencies
(`requirements-dev.txt`) are already importable, just run the tooling directly:

```bash
python -m pytest -q                              # run the test suite
python -m uvicorn app.main:app --reload --port 8000   # run the app, then open http://localhost:8000/
```

<details>
<summary>Isolated host environment (only if deps aren't already installed)</summary>

Modern Pythons (e.g. Homebrew) block global `pip install` (PEP 668), so use a
virtualenv to install into:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

</details>

## Docker

### Build the image

```bash
docker build -t pdf-service:latest .
```

### Run the container

```bash
docker run --rm -p 8000:8000 pdf-service:latest
# Override the port if you like:
# docker run --rm -e PORT=9000 -p 9000:9000 pdf-service:latest
```

### Hit the health check and the upload form

```bash
curl http://localhost:8000/health        # -> {"status":"ok"}
open http://localhost:8000/               # upload form in the browser
```

## CI gates (the Makefile is the contract)

Every pipeline stage maps to one `make` target, so the commands are identical
locally and in CI. The delivery pipeline stays a thin orchestration layer over
these:

```bash
make verify     # lint + typecheck + tests with coverage gate
make build      # build image with git SHA / build time / version baked in
make smoke      # run the container and round-trip every endpoint
make scan       # Trivy image vuln scan (HIGH,CRITICAL fail the gate)
make sbom       # Syft CycloneDX SBOM
make sign       # Cosign keyless signature
make help       # list everything
```

`build` stamps provenance into the image via build args:

```bash
make build GIT_SHA=$(git rev-parse --short HEAD) APP_VERSION=1.0.0
curl http://localhost:8000/version   # -> {"version":"1.0.0","git_sha":"...","build_time":"..."}
```

## Kubernetes (Helm)

The chart in `deploy/helm/pdf-service` is hardened (non-root, read-only root FS,
all capabilities dropped, seccomp `RuntimeDefault`), ships split
startup/liveness/readiness probes, a PodDisruptionBudget, and optional HPA +
Prometheus `ServiceMonitor`. Deploy by **immutable git-SHA tag** (never
`:latest`) so canary/rollback can distinguish versions:

```bash
helm upgrade --install pdf-service deploy/helm/pdf-service \
  --set image.repository=docker.io/youruser/pdf-service \
  --set image.tag=$(git rev-parse --short HEAD)

kubectl port-forward svc/pdf-service 8080:80
curl http://localhost:8080/health
```

Render locally without a cluster to eyeball the manifests:

```bash
helm template pdf-service deploy/helm/pdf-service --set image.tag=dev
```
