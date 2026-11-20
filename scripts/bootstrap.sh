#!/bin/bash
# Full stack bootstrap: build images, init DB, start all services
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== 5G Core Engine Bootstrap ==="

# 1. Environment
if [ ! -f .env ]; then
  echo "[bootstrap] Copying .env.example to .env"
  cp .env.example .env
fi

# 2. Build images
echo "[bootstrap] Building all images..."
docker-compose build

# 3. Start infra first (db, redis)
echo "[bootstrap] Starting database and cache..."
docker-compose up -d db redis

# 4. Wait for DB
echo "[bootstrap] Waiting for MariaDB..."
for i in $(seq 1 30); do
  if docker exec core-db mysqladmin ping -u root -p"${DB_ROOT_PASSWORD:-123456}" 2>/dev/null; then
    echo "[bootstrap] MariaDB ready"
    break
  fi
  sleep 1
done

# 5. Start remaining services
echo "[bootstrap] Starting STP, DRA, SCP, UDM, OAM..."
docker-compose up -d stp dra scp udm oam

# 6. Health check
echo "[bootstrap] Running health checks..."
docker-compose ps

echo "=== Bootstrap complete ==="
echo "Services:"
echo "  STP  : localhost:2905 (SCTP/M3UA)"
echo "  DRA  : localhost:3868 (Diameter)"
echo "  SCP  : localhost:3869 (Diameter/CAMEL)"
echo "  UDM  : localhost:8080 (REST)"
echo "  OAM  : localhost:8081 (Web)"
echo "  DB   : localhost:3306 (MariaDB)"
echo "  Redis: localhost:6379"
