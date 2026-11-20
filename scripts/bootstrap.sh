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
    core-custom-lmf core-custom-amf core-custom-mme
fi

compose ps

cat <<EOF

Custom-core host ports (values from .env; change them there, not in compose)
  ${DB_HOST_PORT:-3306} db            ${HSSDB_HOST_PORT:-3307} hssdb         ${REDIS_HOST_PORT:-6379} redis
  ${NRF_HOST_PORT:-8000} custom-nrf   ${SMF_HOST_PORT:-8002} custom-smf    ${PCF_HOST_PORT:-8004} custom-pcf     ${CUSTOM_UDM_HOST_PORT:-8007} custom-udm
  ${OAM_HOST_PORT:-8081} oam          ${HSS_HOST_PORT:-8090} hss
  ${AMF_HOST_PORT:-8001} custom-amf   ${LMF_HOST_PORT:-8003} custom-lmf    ${MME_HTTP_HOST_PORT:-8075} custom-mme http
  ${MME_SLG_HOST_PORT:-3875} custom-mme SLg Diameter (tcp)
  ${UPF_PFCP_HOST_PORT:-8805} upf PFCP  ${SMF_PFCP_HOST_PORT:-8806} smf PFCP  ${UPF_GTPU_HOST_PORT:-2152} upf GTP-U
  ${DRA_HOST_PORT:-3868} dra          ${DIAMETER_HOST_PORT:-3880} diameter-s6a-cx
  ${STP_HOST_PORT:-2905} osmo-stp     ${MAP_HOST_PORT:-2906} map-sccp      ${CAMEL_HOST_PORT:-2907} camel      ${SCP_SCTP_HOST_PORT:-2908} scp
  ${OCS_HOST_PORT:-3870} ocs          ${SCP_HOST_PORT:-3871} scp           ${PCF_GX_HOST_PORT:-3873} pcf Gx     ${PCF_GY_HOST_PORT:-3874} pcf Gy
  ${OAM_FRONTEND_PORT:-3001} oam-frontend  ${GRAFANA_HOST_PORT:-3000} grafana  ${PROMETHEUS_HOST_PORT:-9090} prometheus

Smoke test:
  curl -sf http://localhost:${NRF_HOST_PORT:-8000}/health   # nrf
  curl -sf http://localhost:${CUSTOM_UDM_HOST_PORT:-8007}/health   # udm
  curl -sf http://localhost:${LMF_HOST_PORT:-8003}/health   # lmf  (provider=none until configured)
  curl -sf http://localhost:${AMF_HOST_PORT:-8001}/health   # amf  (n2_ngap=not implemented)
  curl -sf http://localhost:${MME_HTTP_HOST_PORT:-8075}/scope    # mme  (SLg only)
  # The GMLC is a separate service: github.com/ssonkokevin/gmlc
EOF
