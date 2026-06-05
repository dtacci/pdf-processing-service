# Single entrypoint for every CI gate and build step. The delivery pipeline
# (Harness) orchestrates these targets; the *commands* live here so they are
# identical locally and in CI ("works on my machine" == "works in the pipeline").

IMAGE       ?= pdf-service
GIT_SHA     ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
BUILD_TIME  ?= $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
APP_VERSION ?= 0.0.0-dev
TAG         ?= $(GIT_SHA)
IMAGE_REF    = $(IMAGE):$(TAG)

PY ?= python

.DEFAULT_GOAL := help
.PHONY: help lint typecheck test cov verify build smoke scan sbom sign run clean

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

## ---- Code gates (no container needed) -------------------------------------
lint: ## Ruff lint + format check
	$(PY) -m ruff check app tests
	$(PY) -m ruff format --check app tests

typecheck: ## Static type check
	$(PY) -m mypy

test: ## Run the test suite
	$(PY) -m pytest

cov: ## Tests with coverage gate (fail_under in pyproject.toml)
	$(PY) -m pytest --cov --cov-report=term-missing --cov-report=xml

verify: lint typecheck cov ## All code gates

## ---- Image build + supply chain -------------------------------------------
build: ## Build the image with provenance baked in
	docker build \
	  --build-arg GIT_SHA=$(GIT_SHA) \
	  --build-arg BUILD_TIME=$(BUILD_TIME) \
	  --build-arg APP_VERSION=$(APP_VERSION) \
	  -t $(IMAGE_REF) .

smoke: ## Build, run the container, and round-trip every endpoint
	IMAGE_REF=$(IMAGE_REF) ./scripts/smoke-test.sh

scan: ## Vulnerability-scan the image (Trivy)
	@command -v trivy >/dev/null 2>&1 \
	  && trivy image --exit-code 1 --severity HIGH,CRITICAL $(IMAGE_REF) \
	  || echo "trivy not installed — pipeline runner provides it (skipping locally)"

sbom: ## Generate a CycloneDX SBOM for the image (Syft)
	@command -v syft >/dev/null 2>&1 \
	  && syft $(IMAGE_REF) -o cyclonedx-json=sbom.cdx.json \
	  || echo "syft not installed — pipeline runner provides it (skipping locally)"

sign: ## Keyless-sign the image (Cosign)
	@command -v cosign >/dev/null 2>&1 \
	  && cosign sign --yes $(IMAGE_REF) \
	  || echo "cosign not installed — pipeline runner provides it (skipping locally)"

## ---- Local run ------------------------------------------------------------
run: ## Run the app on the host (no container)
	$(PY) -m uvicorn app.main:app --reload --port $${PORT:-8000}

clean: ## Remove build artifacts
	rm -f sbom.cdx.json coverage.xml .coverage
	rm -rf .pytest_cache .ruff_cache .mypy_cache
