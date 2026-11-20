#!/bin/bash
# Health check for all core services
set -euo pipefail

check_port() {
  local host="$1" port="$2" proto="${3:-tcp}"
  if [ "$proto" = "sctp" ]; then
    ss -l"$proto"n | grep -q ":$port "
  else
    ss -l"$proto"n | grep -q ":$port "
  fi
}

echo "=== 5G Core Engine Health Check ==="

for svc in core-db core-redis core-stp core-dra core-scp core-udm core-oam; do
  if docker inspect -f '{{.State.Running}}' "$svc" 2>/dev/null | grep -q true; then
    echo "[OK]   $svc is running"
  else
    echo "[FAIL] $svc is NOT running"
  fi
done

echo ""
echo "Ports:"
ss -lntu | grep -E ':(2905|3868|3869|8080|8081|3306|6379)' || true

echo "=== Health check complete ==="
