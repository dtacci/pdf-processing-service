#!/usr/bin/env bash
# Container smoke test: run the built image and exercise every endpoint over
# real HTTP. This is the gate that makes "the image works" a verified fact, not
# an assumption. Intended to run in CI right after `make build`.
#
#   IMAGE_REF=pdf-service:abc123 ./scripts/smoke-test.sh
set -euo pipefail

IMAGE_REF="${IMAGE_REF:-pdf-service:latest}"
PORT="${PORT:-8001}"
NAME="pdf-smoke-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> starting $IMAGE_REF as $NAME on :$PORT"
docker run -d --name "$NAME" -p "$PORT:8000" "$IMAGE_REF" >/dev/null

base="http://localhost:$PORT"
echo "==> waiting for readiness"
for _ in $(seq 1 30); do
  if curl -fs "$base/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

fail() { echo "SMOKE FAIL: $1" >&2; docker logs "$NAME" >&2 || true; exit 1; }

echo "==> /health"
curl -fs "$base/health"  | grep -q '"status":"ok"'    || fail "/health"
echo "==> /readyz"
curl -fs "$base/readyz"  | grep -q '"status":"ready"' || fail "/readyz"
echo "==> /version (build provenance present)"
curl -fs "$base/version" | grep -q '"git_sha"'        || fail "/version"
echo "==> /metrics (Prometheus exposition)"
curl -fs "$base/metrics" | grep -q '# HELP'           || fail "/metrics"

echo "==> /merge round-trip (2 one-page PDFs -> a valid PDF)"
workdir="$(mktemp -d)"
# Minimal but valid one-page PDF, written twice.
printf '%%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n170\n%%%%EOF\n' > "$workdir/p.pdf"
code=$(curl -s -o "$workdir/out.pdf" -w '%{http_code}' \
  -F "files=@$workdir/p.pdf;type=application/pdf" \
  -F "files=@$workdir/p.pdf;type=application/pdf" "$base/merge")
[ "$code" = "200" ] || fail "/merge returned HTTP $code"
head -c4 "$workdir/out.pdf" | grep -q '%PDF' || fail "/merge did not return a PDF"
rm -rf "$workdir"

echo "SMOKE OK: $IMAGE_REF"
