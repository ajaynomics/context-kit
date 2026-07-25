#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
IMAGE="${CONTEXT_KIT_DOCS_CANDIDATE_IMAGE:-context-kit/docs-mcp:quality-20260724}"
MODELS="${CONTEXT_KIT_DOCS_TEST_MODELS:-${CONTEXT_KIT_DATA_DIR:-${HOME}/.local/share/context-kit}/models}"
TMP_DIR="$(mktemp -d)"
CONTAINER="context-kit-docs-quality-$RANDOM-$$"

cleanup() {
  docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

mkdir -p "${TMP_DIR}/data"
docker run -d --name "${CONTAINER}" \
  --user "$(id -u):$(id -g)" \
  -p 127.0.0.1::8000 \
  -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  -e DOCS_MCP_PREINDEX=0 \
  -v "${TMP_DIR}/data:/data" \
  -v "${MODELS}:/models:ro" \
  -v "${ROOT}/scripts/fixtures/docs/sources.txt:/etc/context-kit/docs-sources.txt:ro" \
  -v "${ROOT}/scripts/fixtures/docs/local-sources:/etc/context-kit/local-sources:ro" \
  "${IMAGE}" >/dev/null

binding="$(docker port "${CONTAINER}" 8000/tcp)"
port="${binding##*:}"
for _ in {1..120}; do
  if curl -fsS "http://127.0.0.1:${port}/status" >/dev/null 2>&1; then
    node "${ROOT}/scripts/test-docs-candidate.mjs" "http://127.0.0.1:${port}/mcp"
    exit 0
  fi
  sleep 0.25
done

docker logs "${CONTAINER}" >&2
exit 1
