#!/bin/bash
# Build and provision STP container from source
set -euo pipefail

echo "[stp] Building osmo-stp image..."
docker-compose build stp

echo "[stp] Starting STP..."
docker-compose up -d stp

echo "[stp] Waiting for STP on port 2905..."
for i in $(seq 1 30); do
  if ss -lun | grep -q 2905; then
    echo "[stp] STP listening on 2905"
    exit 0
  fi
  sleep 1
done

echo "[stp] ERROR: STP did not become ready" >&2
exit 1
