# ---- Builder stage: install dependencies into an isolated virtualenv ----
# Base image pinned by digest (not a floating tag) for reproducible, tamper-
# evident builds — a supply-chain requirement, not a nicety.
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS builder

# Build deps into a venv so we can copy a single self-contained dir to the
# final image (keeps the runtime layer free of pip/build caches).
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ---- Final stage: slim runtime, non-root ----
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

# Build provenance — passed by CI (`--build-arg GIT_SHA=$(git rev-parse HEAD)`
# etc.). Baked into the image so /version can prove what is deployed, and
# surfaced as OCI labels for registry tooling / SBOM correlation.
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ARG APP_VERSION=0.0.0-dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME} \
    APP_VERSION=${APP_VERSION}

LABEL org.opencontainers.image.title="pdf-service" \
      org.opencontainers.image.description="FastAPI microservice for basic PDF operations" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_TIME}" \
      org.opencontainers.image.source="https://github.com/dtacci/pdf-processing-service"

# Create an unprivileged user to run the app.
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app

# Copy the prebuilt virtualenv and only the application source.
COPY --from=builder /opt/venv /opt/venv
COPY app ./app

USER app

EXPOSE 8000

# Container-native liveness check (no curl in the slim image; use stdlib).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health').status==200 else 1)"]

# PORT is configurable at runtime (defaults to 8000). Shell form lets the
# variable expand; uvicorn is the entrypoint.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
