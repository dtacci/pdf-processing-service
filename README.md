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
| GET    | `/health`       | `{"status": "ok"}` — for K8s readiness/liveness probes             |
| GET    | `/`             | Tiny HTML upload form for browser demos                            |

## Project structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app + routes
│   └── pdf_ops.py       # Pure PDF functions (merge/split/compress/extract)
├── tests/
│   ├── conftest.py      # In-memory PDF fixtures (reportlab)
│   ├── test_pdf_ops.py  # Unit tests for the core functions
│   └── test_api.py      # TestClient smoke tests (health, index, merge)
├── k8s/
│   ├── deployment.yaml  # Deployment with /health probes
│   └── service.yaml     # ClusterIP service
├── Dockerfile           # Multi-stage, slim, non-root
├── .dockerignore
├── requirements.txt     # Runtime deps (pinned)
└── requirements-dev.txt # + pytest, reportlab, httpx
```

## Configuration

| Env var | Default | Purpose                        |
|---------|---------|--------------------------------|
| `PORT`  | `8000`  | Port uvicorn binds inside the container |

## Local development

Create a virtualenv and install dev dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Run the tests (no server needed)

```bash
pytest -q
```

### Run the app locally (without Docker)

```bash
uvicorn app.main:app --reload --port 8000
# then open http://localhost:8000/
```

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

## Kubernetes

Update the `image:` field in `k8s/deployment.yaml` to your pushed image, then:

```bash
kubectl apply -f k8s/
kubectl port-forward svc/pdf-service 8080:80
curl http://localhost:8080/health
```
