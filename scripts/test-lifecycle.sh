#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT_KIT="${ROOT}/bin/context-kit"
RELEASE_CHECK="${ROOT}/scripts/release-check"
TEST_ROOT="$(mktemp -d)"
TEST_PROJECT="context-kit-lifecycle-$$"
LOCK_DIR="/tmp/context-kit-${TEST_PROJECT}.lock"
RELEASE_LOCK_TEST_PROJECT="context-kit-release-$((900000000 + $$))"
RELEASE_LOCK_DIR="/tmp/context-kit-${RELEASE_LOCK_TEST_PROJECT}.lock"
LOCK_HOLDER_PID=''
cleanup() {
  if [[ -n "${LOCK_HOLDER_PID}" ]]; then
    kill "${LOCK_HOLDER_PID}" 2>/dev/null || true
    wait "${LOCK_HOLDER_PID}" 2>/dev/null || true
  fi
  rm -rf "${TEST_ROOT}"
  if [[ -d "${LOCK_DIR}" && "$(stat -c %u "${LOCK_DIR}")" == "$(id -u)" ]]; then
    rm -rf "${LOCK_DIR}"
  fi
  if [[ -L "${RELEASE_LOCK_DIR}" ]]; then
    rm -f "${RELEASE_LOCK_DIR}"
  elif [[ -d "${RELEASE_LOCK_DIR}" && "$(stat -c %u "${RELEASE_LOCK_DIR}")" == "$(id -u)" ]]; then
    rm -rf "${RELEASE_LOCK_DIR}"
  fi
}
trap cleanup EXIT

fail_test() {
  printf 'lifecycle test: %s\n' "$*" >&2
  exit 1
}

fake_log() {
  printf '%s\n' "$*" >> "${FAKE_DOCKER_LOG}"
}

fake_service_for_container() {
  local container_id="$1" file
  for file in "${FAKE_DOCKER_STATE}"/service.*.id; do
    [[ -f "${file}" ]] || continue
    if [[ "$(<"${file}")" == "${container_id}" ]]; then
      file="${file##*/service.}"
      printf '%s' "${file%.id}"
      return 0
    fi
  done
  return 1
}

assert_docs_sources_restored_before_state_change() {
  if [[ -n "${FAKE_EXPECT_DOCS_SOURCES:-}" ]]; then
    cmp -s "${FAKE_EXPECT_DOCS_SOURCES}" "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" \
      || fail_test "container state restoration ran before prior docs sources content was restored"
  elif [[ "${FAKE_EXPECT_DOCS_SOURCES_ABSENT:-0}" -eq 1 ]]; then
    [[ ! -e "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" && ! -L "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" ]] \
      || fail_test "container state restoration ran before prior docs sources absence was restored"
  fi
}

fake_compose() {
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      -p|-f) shift 2 ;;
      *) break ;;
    esac
  done

  local command="${1:-}"
  shift || true
  case "${command}" in
    ps)
      local service="${!#}"
      if [[ -f "${FAKE_DOCKER_STATE}/service.${service}.id" ]]; then
        printf '%s\n' "$(<"${FAKE_DOCKER_STATE}/service.${service}.id")"
      fi
      ;;
    up)
      local no_recreate=0 service
      local services=()
      for service in "$@"; do
        case "${service}" in
          -d) ;;
          --no-recreate) no_recreate=1 ;;
          *) services+=("${service}") ;;
        esac
      done
      if [[ -n "${FAKE_REPLACEMENT_REQUIRED:-}" && "${no_recreate}" -eq 1 && -f "${FAKE_DOCKER_STATE}/service.${FAKE_REPLACEMENT_REQUIRED}.id" ]]; then
        return 17
      fi
      if ! mkdir "${FAKE_DOCKER_STATE}/up.guard" 2>/dev/null; then
        fake_log RACE
        return 75
      fi
      /bin/sleep 0.2
      touch "${FAKE_DOCKER_STATE}/network" "${FAKE_DOCKER_STATE}/volume"
      for service in "${services[@]}"; do
        if [[ ! -f "${FAKE_DOCKER_STATE}/service.${service}.id" ]]; then
          printf 'cid-%s\n' "${service}" > "${FAKE_DOCKER_STATE}/service.${service}.id"
        fi
        touch "${FAKE_DOCKER_STATE}/service.${service}.running"
      done
      if [[ -n "${FAKE_DROP_RUNNING:-}" ]]; then
        rm -f "${FAKE_DOCKER_STATE}/service.${FAKE_DROP_RUNNING}.running"
      fi
      rmdir "${FAKE_DOCKER_STATE}/up.guard"
      ;;
    restart)
      local service
      for service in "$@"; do
        if [[ -f "${FAKE_DOCKER_STATE}/service.${service}.id" ]]; then
          touch "${FAKE_DOCKER_STATE}/service.${service}.running"
        fi
      done
      if [[ -n "${FAKE_DROP_RUNNING:-}" ]]; then
        rm -f "${FAKE_DOCKER_STATE}/service.${FAKE_DROP_RUNNING}.running"
      fi
      [[ "${FAKE_RESTART_FAIL:-0}" -eq 0 ]]
      ;;
    stop)
      local service
      for service in "$@"; do
        rm -f "${FAKE_DOCKER_STATE}/service.${service}.running"
      done
      ;;
    build|version) ;;
    *) fail_test "unsupported fake compose command: ${command}" ;;
  esac
}

docker() {
  fake_log "docker $*"
  local object="${1:-}"
  shift || true
  case "${object}" in
    info|pull) ;;
    image) ;;
    compose) fake_compose "$@" ;;
    network|volume)
      local action="${1:-}"
      [[ "${action}" == inspect && -f "${FAKE_DOCKER_STATE}/${object}" ]]
      ;;
    inspect)
      local container_id="${!#}" service
      service="$(fake_service_for_container "${container_id}" 2>/dev/null)" || {
        [[ -f "${FAKE_DOCKER_STATE}/owner.${container_id}" ]] || return 1
        if [[ "$*" == *"dev.context-kit.owner"* ]]; then
          printf '%s\n' "$(<"${FAKE_DOCKER_STATE}/owner.${container_id}")"
        fi
        return
      }
      if [[ "$*" == *".State.Running"* ]]; then
        [[ -f "${FAKE_DOCKER_STATE}/service.${service}.running" ]] && printf 'true\n' || printf 'false\n'
      elif [[ "$*" == *"com.docker.compose.project"* ]]; then
        printf '%s:%s\n' "${CONTEXT_KIT_COMPOSE_PROJECT}" "${service}"
      elif [[ "$*" == *".Config.User"* ]]; then
        printf '%s:1000\n' "${FAKE_DOCS_UID:-$(id -u)}"
      elif [[ "$*" == *"dev.context-kit.uid"* ]]; then
        printf '%s\n' "${FAKE_WEB_UID:-$(id -u)}"
      fi
      ;;
    create)
      local name='' owner='' argument container_id
      while [[ "$#" -gt 0 ]]; do
        argument="$1"
        case "${argument}" in
          --name) name="$2"; shift 2 ;;
          --label)
            [[ "$2" == dev.context-kit.owner=* ]] && owner="${2#*=}"
            shift 2
            ;;
          --network|-e|-v|--workdir|--entrypoint) shift 2 ;;
          -i|--rm) shift ;;
          *) shift ;;
        esac
      done
      [[ -n "${name}" && -n "${owner}" ]] || fail_test "client container lacks a deterministic name or owner"
      container_id="cid-${name}"
      if [[ "${FAKE_CLIENT_OWNER_MISMATCH:-0}" -eq 1 ]]; then
        printf 'unrelated-owner\n' > "${FAKE_DOCKER_STATE}/owner.${container_id}"
      else
        printf '%s\n' "${owner}" > "${FAKE_DOCKER_STATE}/owner.${container_id}"
      fi
      printf '%s\n' "${container_id}"
      ;;
    start)
      local container_id="${!#}" service
      if service="$(fake_service_for_container "${container_id}" 2>/dev/null)"; then
        assert_docs_sources_restored_before_state_change
        touch "${FAKE_DOCKER_STATE}/service.${service}.running"
      elif [[ -f "${FAKE_DOCKER_STATE}/owner.${container_id}" && "${FAKE_CLIENT_START_BLOCK:-0}" -eq 1 ]]; then
        /bin/sh -c '
          touch "$1"
          while [ -f "$2" ] && [ ! -f "$3" ]; do /bin/sleep 0.02; done
        ' sh \
          "${FAKE_DOCKER_STATE}/client-attach.started" \
          "${FAKE_DOCKER_STATE}/owner.${container_id}" \
          "${FAKE_DOCKER_STATE}/client-attach.release"
      fi
      ;;
    rm)
      local container_id="${!#}" service
      if service="$(fake_service_for_container "${container_id}" 2>/dev/null)"; then
        assert_docs_sources_restored_before_state_change
        rm -f "${FAKE_DOCKER_STATE}/service.${service}.id" "${FAKE_DOCKER_STATE}/service.${service}.running"
      fi
      rm -f "${FAKE_DOCKER_STATE}/owner.${container_id}"
      ;;
    stop)
      local container_id="${!#}" service
      service="$(fake_service_for_container "${container_id}")" || return 1
      assert_docs_sources_restored_before_state_change
      rm -f "${FAKE_DOCKER_STATE}/service.${service}.running"
      ;;
    ps)
      if [[ "$*" == *"label=dev.context-kit=true"* && "${FAKE_LEGACY_CONTAINER:-0}" -eq 1 ]]; then
        printf 'legacy-web-search\tCreated\t\t\n'
      fi
      ;;
    *) fail_test "unsupported fake docker command: ${object}" ;;
  esac
}

curl() {
  local argument url='' data=''
  while [[ "$#" -gt 0 ]]; do
    argument="$1"
    case "${argument}" in
      --data) data="$2"; shift 2 ;;
      http://*|https://*) url="${argument}"; shift ;;
      *) shift ;;
    esac
  done
  case "${url}" in
    *:8099/healthz) [[ "${FAKE_SEARXNG_FAIL:-0}" -eq 0 ]] ;;
    *:8777/mcp)
      [[ "${FAKE_WEB_SEARCH_FAIL:-0}" -eq 0 ]] || return 1
      if [[ "${data}" == *'"method":"initialize"'* ]]; then
        printf '{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"web"}}}\n'
      else
        printf '{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"search_web"},{"name":"fetch_url"}]}}\n'
      fi
      ;;
    *:8776/status) [[ "${FAKE_DOCS_FAIL:-0}" -eq 0 ]] ;;
    *) fail_test "unexpected fake curl URL: ${url}" ;;
  esac
}

sleep() { return 0; }
export -f fail_test fake_log fake_service_for_container assert_docs_sources_restored_before_state_change fake_compose docker curl sleep

new_case() {
  local name="$1"
  export CASE_ROOT="${TEST_ROOT}/${name}"
  export FAKE_DOCKER_STATE="${CASE_ROOT}/docker"
  export FAKE_DOCKER_LOG="${CASE_ROOT}/docker.log"
  export HOME="${CASE_ROOT}/home"
  export CONTEXT_KIT_DATA_DIR="${CASE_ROOT}/data"
  export CONTEXT_KIT_COMPOSE_PROJECT="${TEST_PROJECT}"
  export CONTEXT_KIT_SEARXNG_PORT=8099
  export CONTEXT_KIT_WEB_SEARCH_PORT=8777
  export CONTEXT_KIT_WEB_SEARCH_HTTP_URL=http://127.0.0.1:8777/mcp
  export CONTEXT_KIT_DOCS_PORT=8776
  export CONTEXT_KIT_DOCS_HTTP_URL=http://127.0.0.1:8776/mcp
  export CONTEXT_KIT_DOCS_SOURCES=config/sources.default.txt
  unset CONTEXT_KIT_DOCKER_CIDFILE CONTEXT_KIT_RUNTIME_DIR FAKE_DOCS_UID FAKE_WEB_UID \
    FAKE_REPLACEMENT_REQUIRED FAKE_RESTART_FAIL FAKE_DROP_RUNNING FAKE_SEARXNG_FAIL \
    FAKE_WEB_SEARCH_FAIL FAKE_DOCS_FAIL FAKE_LEGACY_CONTAINER FAKE_CLIENT_OWNER_MISMATCH \
    FAKE_CLIENT_START_BLOCK FAKE_EXPECT_DOCS_SOURCES FAKE_EXPECT_DOCS_SOURCES_ABSENT \
    CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR
  mkdir -p "${FAKE_DOCKER_STATE}" "${HOME}"
  : > "${FAKE_DOCKER_LOG}"
}

seed_service() {
  local service="$1" state="${2:-running}"
  printf 'cid-%s\n' "${service}" > "${FAKE_DOCKER_STATE}/service.${service}.id"
  if [[ "${state}" == running ]]; then
    touch "${FAKE_DOCKER_STATE}/service.${service}.running"
  fi
}

assert_no_docs_sources_artifacts() {
  if compgen -G "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt.lifecycle-backup.*" >/dev/null \
    || compgen -G "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt.tmp.*" >/dev/null; then
    fail_test "docs sources transaction left backup or render artifacts"
  fi
}

mkdir -m 700 "${RELEASE_LOCK_DIR}"
: > "${RELEASE_LOCK_DIR}/lifecycle"
chmod 755 "${RELEASE_LOCK_DIR}"
if "${RELEASE_CHECK}" --cleanup-ephemeral-lock "${RELEASE_LOCK_TEST_PROJECT}" >"${TEST_ROOT}/unsafe-lock.out" 2>&1; then
  fail_test "release lock cleanup accepted an unsafe mode"
fi
[[ -d "${RELEASE_LOCK_DIR}" ]] || fail_test "release lock cleanup removed an unsafe lock"
chmod 700 "${RELEASE_LOCK_DIR}"
"${RELEASE_CHECK}" --cleanup-ephemeral-lock "${RELEASE_LOCK_TEST_PROJECT}"

release_lock_target="${TEST_ROOT}/release-lock-symlink-target"
mkdir -m 700 "${release_lock_target}"
touch "${release_lock_target}/sentinel"
ln -s "${release_lock_target}" "${RELEASE_LOCK_DIR}"
if "${RELEASE_CHECK}" --cleanup-ephemeral-lock "${RELEASE_LOCK_TEST_PROJECT}" >"${TEST_ROOT}/symlink-lock.out" 2>&1; then
  fail_test "release lock cleanup followed a symlink"
fi
[[ -f "${release_lock_target}/sentinel" ]] || fail_test "release lock cleanup changed a symlink target"
rm -f "${RELEASE_LOCK_DIR}"
rm -rf "${release_lock_target}"

mkdir -m 700 "${RELEASE_LOCK_DIR}"
: > "${RELEASE_LOCK_DIR}/lifecycle"
(
  flock -x 9
  touch "${TEST_ROOT}/release-lock-held"
  /bin/sleep 30
) 9>"${RELEASE_LOCK_DIR}/lifecycle" &
LOCK_HOLDER_PID=$!
for _ in {1..100}; do
  [[ -f "${TEST_ROOT}/release-lock-held" ]] && break
  /bin/sleep 0.01
done
[[ -f "${TEST_ROOT}/release-lock-held" ]] || fail_test "release lock holder did not start"
if "${RELEASE_CHECK}" --cleanup-ephemeral-lock "${RELEASE_LOCK_TEST_PROJECT}" >"${TEST_ROOT}/held-lock.out" 2>&1; then
  fail_test "release lock cleanup removed a held lock"
fi
grep -F 'still held' "${TEST_ROOT}/held-lock.out" >/dev/null || fail_test "held lock refusal was not explicit"
kill "${LOCK_HOLDER_PID}"
wait "${LOCK_HOLDER_PID}" 2>/dev/null || true
LOCK_HOLDER_PID=''
"${RELEASE_CHECK}" --cleanup-ephemeral-lock "${RELEASE_LOCK_TEST_PROJECT}"
[[ ! -e "${RELEASE_LOCK_DIR}" && ! -L "${RELEASE_LOCK_DIR}" ]] || fail_test "successful release lock cleanup left the lock path"

mkdir -m 700 "${RELEASE_LOCK_DIR}"
: > "${RELEASE_LOCK_DIR}/lifecycle"
"${RELEASE_CHECK}" --cleanup-ephemeral-lock "${RELEASE_LOCK_TEST_PROJECT}"
[[ ! -e "${RELEASE_LOCK_DIR}" && ! -L "${RELEASE_LOCK_DIR}" ]] || fail_test "release lock cleanup did not remove its known ephemeral lock"

new_case snippets
"${CONTEXT_KIT}" install opencode > "${CASE_ROOT}/opencode.json"
"${CONTEXT_KIT}" install claude > "${CASE_ROOT}/claude.json"
grep -F '"url": "http://127.0.0.1:8777/mcp"' "${CASE_ROOT}/opencode.json" >/dev/null || fail_test "OpenCode web search is not remote HTTP"
grep -F '"url": "http://127.0.0.1:8777/mcp"' "${CASE_ROOT}/claude.json" >/dev/null || fail_test "Claude web search is not HTTP"

new_case stdio-bridge
touch "${FAKE_DOCKER_STATE}/network"
seed_service web-search-mcp
"${CONTEXT_KIT}" web-search </dev/null
grep -E 'docker create .*dev.context-kit.lifecycle=client .*--entrypoint mcp-proxy .*http://web-search-mcp:8000/mcp' "${FAKE_DOCKER_LOG}" >/dev/null || fail_test "stdio bridge does not reuse the shared service"
grep -F 'docker create -i --rm --init' "${FAKE_DOCKER_LOG}" >/dev/null || fail_test "stdio bridge container does not use Docker init"
[[ -f "${FAKE_DOCKER_STATE}/service.web-search-mcp.running" ]] || fail_test "stdio bridge stopped the shared service"
if compgen -G "${FAKE_DOCKER_STATE}/owner.*" >/dev/null; then
  fail_test "stdio bridge did not clean up its own container"
fi

new_case client-signal-cleanup
touch "${FAKE_DOCKER_STATE}/network"
seed_service web-search-mcp
export FAKE_CLIENT_START_BLOCK=1
"${CONTEXT_KIT}" web-search </dev/null >"${CASE_ROOT}/client.out" 2>&1 &
client_pid=$!
for _ in {1..100}; do
  [[ -f "${FAKE_DOCKER_STATE}/client-attach.started" ]] && break
  /bin/sleep 0.01
done
[[ -f "${FAKE_DOCKER_STATE}/client-attach.started" ]] || fail_test "blocking stdio attach did not start"
kill -TERM "${client_pid}"
owner_removed=0
for _ in {1..50}; do
  if ! compgen -G "${FAKE_DOCKER_STATE}/owner.*" >/dev/null; then
    owner_removed=1
    break
  fi
  /bin/sleep 0.01
done
touch "${FAKE_DOCKER_STATE}/client-attach.release"
set +e
wait "${client_pid}"
client_status=$?
set -e
[[ "${owner_removed}" -eq 1 ]] || fail_test "SIGTERM did not promptly remove the owned stdio container"
[[ "${client_status}" -eq 143 ]] || fail_test "SIGTERM returned ${client_status} instead of 143"

new_case client-owner-isolation
touch "${FAKE_DOCKER_STATE}/network"
seed_service web-search-mcp
export FAKE_CLIENT_OWNER_MISMATCH=1
"${CONTEXT_KIT}" web-search </dev/null
compgen -G "${FAKE_DOCKER_STATE}/owner.*" >/dev/null \
  || fail_test "stdio bridge removed a container whose owner label did not match"
grep -F 'docker rm' "${FAKE_DOCKER_LOG}" >/dev/null \
  && fail_test "stdio bridge attempted to remove a container whose owner label did not match"

new_case differing-environments
mkdir -p "${CASE_ROOT}/runtime-a" "${CASE_ROOT}/runtime-b" "${CASE_ROOT}/tmp-a" "${CASE_ROOT}/tmp-b"
XDG_RUNTIME_DIR="${CASE_ROOT}/runtime-a" TMPDIR="${CASE_ROOT}/tmp-a" "${CONTEXT_KIT}" start >"${CASE_ROOT}/start-a.out" 2>&1 &
first_pid=$!
XDG_RUNTIME_DIR="${CASE_ROOT}/runtime-b" TMPDIR="${CASE_ROOT}/tmp-b" "${CONTEXT_KIT}" start >"${CASE_ROOT}/start-b.out" 2>&1 &
second_pid=$!
wait "${first_pid}" || fail_test "first concurrent start failed"
wait "${second_pid}" || fail_test "second concurrent start failed"
grep -F RACE "${FAKE_DOCKER_LOG}" >/dev/null && fail_test "environment-specific locks allowed a startup race"
[[ -f "${LOCK_DIR}/lifecycle" ]] || fail_test "canonical project lock was not used"

new_case unsafe-lock-mode
chmod 755 "${LOCK_DIR}"
if "${CONTEXT_KIT}" start >"${CASE_ROOT}/start.out" 2>&1; then
  fail_test "unsafe lock mode unexpectedly succeeded"
fi
grep -F 'expected uid' "${CASE_ROOT}/start.out" >/dev/null || fail_test "unsafe lock rejection was not explicit"
grep -F ' up ' "${FAKE_DOCKER_LOG}" >/dev/null && fail_test "unsafe lock rejection happened after Compose startup"
chmod 700 "${LOCK_DIR}"

new_case origin-upgrade
touch "${FAKE_DOCKER_STATE}/network" "${FAKE_DOCKER_STATE}/volume"
seed_service searxng
seed_service docs-mcp
"${CONTEXT_KIT}" start
[[ "$(<"${FAKE_DOCKER_STATE}/service.searxng.id")" == cid-searxng ]] || fail_test "origin searxng was replaced"
[[ "$(<"${FAKE_DOCKER_STATE}/service.docs-mcp.id")" == cid-docs-mcp ]] || fail_test "origin docs-mcp was replaced"
[[ -f "${FAKE_DOCKER_STATE}/service.web-search-mcp.running" ]] || fail_test "upgrade did not create shared web search"
grep -F 'up -d --no-recreate searxng web-search-mcp docs-mcp' "${FAKE_DOCKER_LOG}" >/dev/null || fail_test "upgrade omitted --no-recreate"
grep -E 'docker (network|volume) rm' "${FAKE_DOCKER_LOG}" >/dev/null && fail_test "upgrade removed an origin resource"

new_case replacement-required
seed_service searxng
seed_service web-search-mcp
seed_service docs-mcp
export FAKE_REPLACEMENT_REQUIRED=docs-mcp
if "${CONTEXT_KIT}" start >"${CASE_ROOT}/start.out" 2>&1; then
  fail_test "replacement-required start unexpectedly succeeded"
fi
for service in searxng web-search-mcp docs-mcp; do
  [[ -f "${FAKE_DOCKER_STATE}/service.${service}.running" ]] || fail_test "replacement failure left ${service} down"
  [[ "$(<"${FAKE_DOCKER_STATE}/service.${service}.id")" == "cid-${service}" ]] || fail_test "replacement failure changed ${service}"
done

new_case readiness-failure
touch "${FAKE_DOCKER_STATE}/network" "${FAKE_DOCKER_STATE}/volume"
seed_service searxng
seed_service docs-mcp stopped
mkdir -p "${CONTEXT_KIT_DATA_DIR}"
printf 'prior docs sources\nwith exact content\n' > "${CASE_ROOT}/prior-docs-sources.txt"
cp "${CASE_ROOT}/prior-docs-sources.txt" "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt"
printf 'https://new.example.test/llms.txt\n' > "${CASE_ROOT}/new-sources.txt"
export CONTEXT_KIT_DOCS_SOURCES="${CASE_ROOT}/new-sources.txt"
export FAKE_EXPECT_DOCS_SOURCES="${CASE_ROOT}/prior-docs-sources.txt"
export FAKE_DROP_RUNNING=searxng
export FAKE_WEB_SEARCH_FAIL=1
if "${CONTEXT_KIT}" start >"${CASE_ROOT}/start.out" 2>&1; then
  fail_test "readiness failure unexpectedly succeeded"
fi
[[ -f "${FAKE_DOCKER_STATE}/service.searxng.running" ]] || fail_test "readiness rollback did not restart prior searxng"
[[ ! -f "${FAKE_DOCKER_STATE}/service.docs-mcp.running" ]] || fail_test "readiness rollback did not restore prior stopped docs state"
[[ "$(<"${FAKE_DOCKER_STATE}/service.docs-mcp.id")" == cid-docs-mcp ]] || fail_test "readiness rollback changed the prior docs container ID"
cmp -s "${CASE_ROOT}/prior-docs-sources.txt" "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" || fail_test "readiness rollback did not restore prior docs sources content"
assert_no_docs_sources_artifacts
[[ ! -f "${FAKE_DOCKER_STATE}/service.web-search-mcp.id" ]] || fail_test "readiness rollback left its new web container"
[[ -f "${FAKE_DOCKER_STATE}/network" && -f "${FAKE_DOCKER_STATE}/volume" ]] || fail_test "readiness rollback removed origin resources"

new_case restart-sources
seed_service searxng
seed_service web-search-mcp
seed_service docs-mcp
printf 'https://example.test/llms.txt\n' > "${CASE_ROOT}/sources.txt"
export CONTEXT_KIT_DOCS_SOURCES="${CASE_ROOT}/sources.txt"
"${CONTEXT_KIT}" restart
grep -F 'https://example.test/llms.txt' "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" >/dev/null \
  || fail_test "restart did not regenerate the bind-mounted docs source list"
assert_no_docs_sources_artifacts

new_case snapshot-promotion
seed_service searxng
seed_service web-search-mcp
seed_service docs-mcp
export CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR="${CASE_ROOT}/local-sources"
mkdir -p "${CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR}/immich"
printf '# source menu\n' > "${CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR}/immich/llms.txt"
printf '# generated snapshot\n' > "${CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR}/immich/llms-full.txt"
menu_hash="$(sha256sum "${CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR}/immich/llms.txt")"
menu_hash="${menu_hash%% *}"
output_hash="$(sha256sum "${CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR}/immich/llms-full.txt")"
output_hash="${output_hash%% *}"
printf '{"menu":"llms.txt","menu_sha256":"%s","output_sha256":"%s"}\n' \
  "${menu_hash}" "${output_hash}" \
  > "${CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR}/immich/llms-full.provenance.json"
printf 'http://127.0.0.1:8769/immich/llms.txt\n' > "${CASE_ROOT}/sources.txt"
export CONTEXT_KIT_DOCS_SOURCES="${CASE_ROOT}/sources.txt"
"${CONTEXT_KIT}" restart
grep -F 'http://127.0.0.1:8769/immich/llms-full.txt' "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" >/dev/null \
  || fail_test "restart did not promote a local menu to its generated full snapshot"
if grep -Fx 'http://127.0.0.1:8769/immich/llms.txt' "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" >/dev/null; then
  fail_test "restart retained the menu URL despite an available full snapshot"
fi
printf '# inconsistent snapshot\n' > "${CONTEXT_KIT_DOCS_LOCAL_SOURCES_DIR}/immich/llms-full.txt"
"${CONTEXT_KIT}" restart
grep -Fx 'http://127.0.0.1:8769/immich/llms.txt' "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" >/dev/null \
  || fail_test "restart promoted a snapshot whose provenance hash did not match"

new_case restart-failure
seed_service searxng stopped
seed_service web-search-mcp
seed_service docs-mcp stopped
mkdir -p "${CONTEXT_KIT_DATA_DIR}"
printf 'prior restart sources\n' > "${CASE_ROOT}/prior-docs-sources.txt"
cp "${CASE_ROOT}/prior-docs-sources.txt" "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt"
printf 'https://restart.example.test/llms.txt\n' > "${CASE_ROOT}/new-sources.txt"
export CONTEXT_KIT_DOCS_SOURCES="${CASE_ROOT}/new-sources.txt"
export FAKE_EXPECT_DOCS_SOURCES="${CASE_ROOT}/prior-docs-sources.txt"
export FAKE_DOCS_FAIL=1
if "${CONTEXT_KIT}" restart >"${CASE_ROOT}/restart.out" 2>&1; then
  fail_test "restart failure unexpectedly succeeded"
fi
[[ ! -f "${FAKE_DOCKER_STATE}/service.docs-mcp.running" ]] || fail_test "restart rollback did not restore prior stopped docs state"
[[ "$(<"${FAKE_DOCKER_STATE}/service.docs-mcp.id")" == cid-docs-mcp ]] || fail_test "restart rollback changed the prior docs container ID"
[[ ! -f "${FAKE_DOCKER_STATE}/service.searxng.running" ]] || fail_test "restart rollback did not restore prior stopped SearXNG state"
cmp -s "${CASE_ROOT}/prior-docs-sources.txt" "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" || fail_test "restart rollback did not restore prior docs sources content"
assert_no_docs_sources_artifacts
grep -F 'docker rm' "${FAKE_DOCKER_LOG}" >/dev/null && fail_test "restart rollback removed a shared container"

new_case render-error
mkdir -p "${CONTEXT_KIT_DATA_DIR}"
printf 'prior render-error sources\n' > "${CASE_ROOT}/prior-docs-sources.txt"
cp "${CASE_ROOT}/prior-docs-sources.txt" "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt"
export CONTEXT_KIT_DOCS_SOURCES="${CASE_ROOT}/missing-sources.txt"
if "${CONTEXT_KIT}" start >"${CASE_ROOT}/start.out" 2>&1; then
  fail_test "docs sources render error unexpectedly succeeded"
fi
cmp -s "${CASE_ROOT}/prior-docs-sources.txt" "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" || fail_test "render error did not restore prior docs sources"
assert_no_docs_sources_artifacts
grep -F ' up ' "${FAKE_DOCKER_LOG}" >/dev/null && fail_test "render error reached Compose startup"

new_case cross-user
seed_service docs-mcp
export FAKE_DOCS_UID="$(( $(id -u) + 1 ))"
if "${CONTEXT_KIT}" start >"${CASE_ROOT}/start.out" 2>&1; then
  fail_test "cross-user ownership unexpectedly succeeded"
fi
grep -F 'cross-user ownership is unsupported' "${CASE_ROOT}/start.out" >/dev/null || fail_test "cross-user rejection was not explicit"
grep -F ' up ' "${FAKE_DOCKER_LOG}" >/dev/null && fail_test "cross-user rejection happened after Compose startup"

new_case bounded-failure
export FAKE_WEB_SEARCH_FAIL=1
export FAKE_EXPECT_DOCS_SOURCES_ABSENT=1
[[ ! -e "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" && ! -L "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" ]] \
  || fail_test "prior-absence case unexpectedly began with docs sources"
if "${CONTEXT_KIT}" start >"${CASE_ROOT}/start.out" 2>&1; then
  fail_test "fresh readiness failure unexpectedly succeeded"
fi
for service in searxng web-search-mcp docs-mcp; do
  [[ ! -f "${FAKE_DOCKER_STATE}/service.${service}.id" ]] || fail_test "fresh failure left ${service}"
done
[[ ! -e "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" && ! -L "${CONTEXT_KIT_DATA_DIR}/docs-sources.txt" ]] \
  || fail_test "fresh readiness rollback did not restore prior docs sources absence"
assert_no_docs_sources_artifacts
[[ -f "${FAKE_DOCKER_STATE}/network" && -f "${FAKE_DOCKER_STATE}/volume" ]] || fail_test "bounded shared resources were destructively removed"

new_case legacy-status
export FAKE_LEGACY_CONTAINER=1
"${CONTEXT_KIT}" status >"${CASE_ROOT}/status.out"
grep -F 'Legacy unlabeled Context Kit containers' "${CASE_ROOT}/status.out" >/dev/null || fail_test "status omitted legacy diagnostics"
grep -F 'legacy-web-search' "${CASE_ROOT}/status.out" >/dev/null || fail_test "status omitted the legacy container"

printf 'pass lifecycle and origin-upgrade tests\n'
