#!/bin/bash
# DRA Diameter Routing Agent - bootstrap
set -euo pipefail

echo "[dra] Checking dependencies..."
docker-compose up -d db redis stp

echo "[dra] Building DRA image..."
docker-compose build dra

echo "[dra] Starting DRA..."
docker-compose up -d dra

echo "[dra] Waiting for DRA on port 3868..."
for i in $(seq 1 30); do
  if docker exec core-dra python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 3868)); s.close()" 2>/dev/null; then
    echo "[dra] DRA listening on 3868"
    exit 0
  fi
  sleep 1
done

echo "[dra] ERROR: DRA did not become ready" >&2
exit 1
