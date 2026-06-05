# ---- Builder stage: install dependencies into an isolated virtualenv ----
FROM python:3.12-slim AS builder

# Build deps into a venv so we can copy a single self-contained dir to the
# final image (keeps the runtime layer free of pip/build caches).
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ---- Final stage: slim runtime, non-root ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Create an unprivileged user to run the app.
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app

# Copy the prebuilt virtualenv and only the application source.
COPY --from=builder /opt/venv /opt/venv
COPY app ./app

USER app

EXPOSE 8000

# PORT is configurable at runtime (defaults to 8000). Shell form lets the
# variable expand; uvicorn is the entrypoint.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
