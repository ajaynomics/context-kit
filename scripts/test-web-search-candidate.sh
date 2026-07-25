#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
IMAGE="${CONTEXT_KIT_WEB_SEARCH_CANDIDATE_IMAGE:-context-kit/web-search-mcp:quality-20260724}"
NETWORK="context-kit-web-quality-$RANDOM-$$"
MOCK="${NETWORK}-mock"
SERVER="${NETWORK}-server"

cleanup() {
  docker rm -f "${SERVER}" "${MOCK}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create --subnet 203.0.113.0/24 "${NETWORK}" >/dev/null
docker run -d --name "${MOCK}" --network "${NETWORK}" --ip 203.0.113.10 \
  --network-alias mock-search.test \
  -v "${ROOT}/scripts/fixtures/web/mock-server.mjs:/fixture/mock-server.mjs:ro" \
  node:22-bookworm-slim node /fixture/mock-server.mjs >/dev/null
docker run -d --name "${SERVER}" --network "${NETWORK}" --ip 203.0.113.11 \
  -p 127.0.0.1::8000 \
  -e SEARXNG_URL=http://mock-search.test:8080 \
  -e DEFAULT_SEARCH_PROVIDER=searxng \
  "${IMAGE}" >/dev/null

binding="$(docker port "${SERVER}" 8000/tcp)"
port="${binding##*:}"
for _ in {1..120}; do
  if curl -fsS "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
    node "${ROOT}/scripts/test-web-search-candidate.mjs" "http://127.0.0.1:${port}/mcp"
    exit 0
  fi
  sleep 0.25
done

docker logs "${SERVER}" >&2
exit 1
