#!/usr/bin/env bash
# Hamiltel custom core — bootstrap.
#
#   ./scripts/bootstrap.sh                 build and start the custom stack
#   ./scripts/bootstrap.sh --no-build      start without rebuilding images
#   ./scripts/bootstrap.sh --reference     build and start the free5GC
#                                          reference profile instead
#
# The two stacks are mutually exclusive on one host. The custom stack is the
# product; free5GC exists for comparison and regression only.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MODE=custom
BUILD=1
for arg in "$@"; do
  case "$arg" in
    --reference) MODE=reference ;;
    --no-build)  BUILD=0 ;;
    -h|--help)   sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose v2 is required (profiles are not supported by v1)" >&2
  exit 1
fi

# --- environment -----------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "[bootstrap] created .env from .env.example — replace every change-me"
fi
# shellcheck disable=SC1091
set -a; . ./.env; set +a

# --- static contract checks ------------------------------------------------
PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then PYTHON_BIN=python
  fi
fi
if [ -n "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" scripts/check_stack.py || {
    echo "[bootstrap] stack contract checks failed; fix docker-compose.yml first" >&2
    exit 1
  }
else
  echo "[bootstrap] python not found; skipping static checks (install PyYAML to enable)"
fi

compose() {
  if [ "$MODE" = "reference" ]; then
    docker compose --profile free5gc "$@"
  else
    docker compose "$@"
  fi
}

wait_healthy() {
  local timeout="${HEALTH_TIMEOUT:-180}"
  local deadline=$((SECONDS + timeout))
  local pending=("$@")
  while [ ${#pending[@]} -gt 0 ]; do
    local still=()
    for c in "${pending[@]}"; do
      local status
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$c" 2>/dev/null || echo missing)"
      case "$status" in
        healthy|none) ;;
        missing) echo "[bootstrap] $c not created yet" >&2; still+=("$c") ;;
        *) still+=("$c") ;;
      esac
    done
    if [ ${#still[@]} -eq 0 ]; then return 0; fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "[bootstrap] timeout waiting for: ${still[*]}" >&2
      docker compose ps
      return 1
    fi
    pending=("${still[@]}")
    sleep 3
  done
}

# --- build -----------------------------------------------------------------
if [ "$BUILD" -eq 1 ]; then
  echo "[bootstrap] building images ($MODE)"
  compose build
fi

# --- data layer first ------------------------------------------------------
echo "[bootstrap] starting data layer"
compose up -d db hssdb redis
wait_healthy core-db core-hssdb core-redis

# --- application layer -----------------------------------------------------
if [ "$MODE" = "reference" ]; then
  echo "[bootstrap] starting free5GC reference profile"
  compose up -d
  echo "[bootstrap] reference stack published on 18xxx; custom stack is NOT running"
else
  echo "[bootstrap] starting custom core"
  compose up -d
  wait_healthy core-nrf-custom core-hss core-custom-udm core-custom-pcf core-custom-smf \
    core-gmlc core-custom-lmf core-custom-amf core-custom-mme
fi

compose ps

cat <<'EOF'

Custom-core host ports
  3306 db            3307 hssdb         6379 redis
  8000 custom-nrf    8002 custom-smf    8004 custom-pcf     8007 custom-udm
  8081 oam           8082 gmlc          8090 hss
  8001 custom-amf    8003 custom-lmf    8075 custom-mme http
  3875 custom-mme SLg Diameter (tcp)
  8805 upf PFCP      8806 smf PFCP      2152 upf GTP-U
  3868 dra           3880 diameter-s6a-cx
  2905 osmo-stp      2906 map-sccp      2907 camel          2908 scp
  3870 ocs           3871 scp           3873 pcf Gx         3874 pcf Gy
  3001 oam-frontend  3000 grafana       9090 prometheus

Smoke test:
  curl -sf http://localhost:8000/health   # nrf
  curl -sf http://localhost:8007/health   # udm
  curl -sf http://localhost:8082/health   # gmlc
  curl -sf http://localhost:8003/health   # lmf  (provider=none until configured)
  curl -sf http://localhost:8001/health   # amf  (n2_ngap=not implemented)
  curl -sf http://localhost:8075/scope    # mme  (SLg only)
  curl -s  -X POST http://localhost:8082/lcs/location-request \
       -H 'content-type: application/json' \
       -d '{"msisdn":"256700000001","request_type":"immediate"}'
  # expected: status=failed, error_code=NO_LCS_SOURCE
EOF
