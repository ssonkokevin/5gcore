#!/bin/sh
# Render the osmo-stp configuration from .env at container start.
#
# Every value that identifies the operator (point code, network indicator,
# routes) is read here, so the repository never carries production point
# codes. Defaults are lab/mock values and are safe to run on a test bench.
set -eu

STP_INSTANCE_ID="${STP_INSTANCE_ID:-srg01}"
STP_LOCAL_PC="${STP_LOCAL_PC:?STP_LOCAL_PC is required}"
STP_NI="${STP_NI:-natl}"
STP_ASP_MODE="${STP_ASP_MODE:-server}"
STP_LOCAL_IP="${STP_LOCAL_IP:-0.0.0.0}"
STP_LOCAL_PORT="${STP_LOCAL_PORT:-2905}"
STP_REMOTE_IP="${STP_REMOTE_IP:-0.0.0.0}"
STP_REMOTE_PCS="${STP_REMOTE_PCS:-}"
STP_ROUTES="${STP_ROUTES:-}"

TEMPLATE="${STP_TEMPLATE:-/etc/osmocom/stp/osmo-stp.cfg.template}"
OUTPUT="${STP_OUTPUT:-/etc/osmocom/osmo-stp.generated.cfg}"

if [ -n "$STP_ROUTES" ]; then
  routes="$STP_ROUTES"
else
  routes=""
  for pc in $STP_REMOTE_PCS; do
    routes="${routes}route ${pc} ${STP_LOCAL_PC} 3 0 as core-stp-as
route ${STP_LOCAL_PC} ${pc} 3 8 as core-stp-as
"
  done
  routes="${routes}route 0.0.0 0.0.0 3 0 as core-stp-as"
fi

STP_ROUTES="$routes"
export STP_INSTANCE_ID STP_LOCAL_PC STP_NI STP_ASP_MODE STP_LOCAL_IP \
  STP_LOCAL_PORT STP_REMOTE_IP STP_ROUTES

if [ ! -f "$TEMPLATE" ]; then
  echo "stp-entrypoint: template not found: $TEMPLATE" >&2
  exit 1
fi

envsubst '$STP_INSTANCE_ID $STP_LOCAL_PC $STP_NI $STP_ASP_MODE $STP_LOCAL_IP $STP_LOCAL_PORT $STP_REMOTE_IP $STP_ROUTES' \
  < "$TEMPLATE" > "$OUTPUT"

echo "stp-entrypoint: rendered $OUTPUT (instance $STP_INSTANCE_ID, pc $STP_LOCAL_PC, ni $STP_NI)"

exec /usr/bin/osmo-stp -c "$OUTPUT"
