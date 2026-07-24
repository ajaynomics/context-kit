#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

git -C "${ROOT}" show origin/main:compose.yml > "${tmp_dir}/origin-compose.yml"
CONTEXT_KIT_DATA_DIR="${tmp_dir}/data" docker compose \
  --project-directory "${ROOT}" \
  --env-file /dev/null \
  -p "context-kit-upgrade-check-$$" \
  -f "${tmp_dir}/origin-compose.yml" \
  config --format json > "${tmp_dir}/origin.json"
CONTEXT_KIT_DATA_DIR="${tmp_dir}/data" CONTEXT_KIT_HOST_UID="$(id -u)" docker compose \
  --project-directory "${ROOT}" \
  --env-file /dev/null \
  -p "context-kit-upgrade-check-$$" \
  -f "${ROOT}/compose.yml" \
  config --format json > "${tmp_dir}/current.json"

node - "${tmp_dir}/origin.json" "${tmp_dir}/current.json" <<'NODE'
const fs = require("node:fs");
const [beforePath, afterPath] = process.argv.slice(2);
const before = JSON.parse(fs.readFileSync(beforePath, "utf8"));
const after = JSON.parse(fs.readFileSync(afterPath, "utf8"));
for (const service of ["searxng", "docs-mcp"]) {
  if (JSON.stringify(before.services[service]) !== JSON.stringify(after.services[service])) {
    throw new Error(`${service} changed from origin/main and could be destructively recreated`);
  }
}
for (const key of ["networks", "volumes"]) {
  if (JSON.stringify(before[key]) !== JSON.stringify(after[key])) {
    throw new Error(`${key} changed from origin/main`);
  }
}
NODE

printf 'pass origin/main Compose upgrade contract\n'
