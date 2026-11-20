#!/bin/bash
# Provision subscribers into UDM database
set -euo pipefail

SUBSCRIBER_FILE="${1:-./database/seed_subscribers.sql}"

echo "[provision] Loading subscriber seed data..."
docker exec -i core-db mysql -u root -p"${DB_ROOT_PASSWORD:-123456}" hssdb < "$SUBSCRIBER_FILE"

echo "[provision] Done."
