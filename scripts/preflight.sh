#!/usr/bin/env bash
# Host preflight for the Hamiltel custom core.
#
#   scripts/preflight.sh            report only; port conflicts are warnings
#   scripts/preflight.sh --strict   port conflicts are fatal (use before a
#                                   first deploy or in CI on a clean host)
#
# Checks: RAM, disk, every published host port from docker-compose.yml (with
# .env overrides), SCTP kernel support, Docker/Compose versions, hugepages,
# and overlap with the 172.20.0.0/16 core network.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/docker-compose.yml"
ENV_FILE="$ROOT/.env"

STRICT=0
[[ "${1:-}" == "--strict" ]] && STRICT=1

errors=0
warnings=0

ok()   { printf 'OK    %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL  %s\n' "$*"; errors=$((errors + 1)); }
info() { printf 'INFO  %s\n' "$*"; }

[[ -f "$COMPOSE" ]] || { echo "FAIL  not found: $COMPOSE"; exit 1; }

echo "== Host =="
info "kernel $(uname -r) on $(uname -m)"

# --------------------------------------------------------------------------
# Memory and disk
# --------------------------------------------------------------------------
mem_avail_mb=$(awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo 2>/dev/null)
mem_avail_mb="${mem_avail_mb:-0}"
if [[ "$mem_avail_mb" -lt 3072 ]]; then
  fail "only ${mem_avail_mb} MB RAM available; the default stack needs ~4 GB and free5GC adds 2-3 GB"
else
  ok "${mem_avail_mb} MB RAM available"
fi

disk_path=/var/lib/docker
[[ -d "$disk_path" ]] || disk_path=/
disk_avail_gb=$(df -Pk "$disk_path" 2>/dev/null | awk 'NR==2 {print int($4 / 1024 / 1024)}')
disk_avail_gb="${disk_avail_gb:-0}"
if [[ "$disk_avail_gb" -lt 10 ]]; then
  fail "only ${disk_avail_gb} GB free on $disk_path; images alone need ~10 GB"
else
  ok "${disk_avail_gb} GB free on $disk_path"
fi

# --------------------------------------------------------------------------
# Docker
# --------------------------------------------------------------------------
echo "== Docker =="
if command -v docker >/dev/null 2>&1; then
  ok "docker $(docker --version | awk '{print $3}' | tr -d ,)"
  if docker compose version >/dev/null 2>&1; then
    ok "docker compose $(docker compose version --short)"
  else
    fail "Docker Compose v2 plugin missing (docker compose)"
  fi
  if docker info >/dev/null 2>&1; then
    ok "docker daemon reachable"
  else
    fail "docker daemon not reachable by $(id -un); add the user to the docker group"
  fi
else
  fail "docker not installed"
fi

# --------------------------------------------------------------------------
# Kernel modules
# --------------------------------------------------------------------------
echo "== Kernel modules =="
if [[ "$(id -u)" -eq 0 ]]; then
  if modprobe sctp 2>/dev/null; then
    ok "sctp module loaded"
  else
    fail "cannot load sctp (needed by osmo-stp, DRA and MAP over M3UA)"
  fi
elif ! command -v lsmod >/dev/null 2>&1; then
  info "lsmod unavailable on this platform; cannot confirm sctp (expected on Linux only)"
elif lsmod | grep -q '^sctp'; then
  ok "sctp module loaded"
elif modprobe -n sctp >/dev/null 2>&1; then
  info "sctp available but not loaded; run: sudo modprobe sctp"
else
  fail "sctp not available; install linux-modules-extra for $(uname -r)"
fi

if command -v lsmod >/dev/null 2>&1 && lsmod | grep -q '^gtp'; then
  info "gtp module loaded (needed only for the UPF kernel datapath, WP6)"
else
  info "gtp module not loaded; the UPF kernel datapath needs it later (WP6)"
fi

# --------------------------------------------------------------------------
# Hugepages (informational; only the DPDK datapath needs them)
# --------------------------------------------------------------------------
echo "== Hugepages (informational) =="
hp_total=$(awk '/HugePages_Total/ {print $2}' /proc/meminfo 2>/dev/null)
hp_free=$(awk '/HugePages_Free/ {print $2}' /proc/meminfo 2>/dev/null)
info "hugepages total=${hp_total:-0} free=${hp_free:-0}; DPDK stage 2 (WP6) typically wants 2 x 1 GB pages"

# --------------------------------------------------------------------------
# Network overlap
# --------------------------------------------------------------------------
echo "== Network =="
if ip route 2>/dev/null | grep -Eq '^172\.20\.'; then
  fail "a host route already covers 172.20.0.0/16; change the core-net subnet in docker-compose.yml"
else
  ok "172.20.0.0/16 is free for core-net"
fi

# --------------------------------------------------------------------------
# Published host ports
# --------------------------------------------------------------------------
echo "== Published host ports =="

declare -A envmap=()
if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r key value; do
    key="${key#"${key%%[![:space:]]*}"}"
    [[ -z "$key" || "$key" == \#* ]] && continue
    value="${value%%#*}"
    value="${value//[[:space:]]/}"
    envmap["$key"]="$value"
  done < "$ENV_FILE"
  ok "using overrides from .env"
else
  info "no .env; using docker-compose.yml defaults (copy .env.example first)"
fi

# ss output once: every listening TCP/UDP socket.
ss_out=$(ss -H -lntu 2>/dev/null || true)
if [[ -z "$ss_out" ]]; then
  warn "ss produced no output; port checks skipped"
fi

port_re='\$\{([A-Za-z0-9_]+):-([0-9]+)\}:([0-9]+)(/([a-z]+))?'
seen_ports=()

while IFS= read -r line; do
  [[ "$line" =~ $port_re ]] || continue
  var="${BASH_REMATCH[1]}"
  default_port="${BASH_REMATCH[2]}"
  container_port="${BASH_REMATCH[3]}"
  proto="${BASH_REMATCH[5]:-tcp}"

  port="$default_port"
  [[ -n "${envmap[$var]:-}" ]] && port="${envmap[$var]}"

  seen_ports+=("$port/$proto")

  if [[ -z "$ss_out" ]]; then
    continue
  fi

  if printf '%s\n' "$ss_out" | grep -Eq "[:.]${port}[[:space:]]"; then
    owner=$(printf '%s\n' "$ss_out" | grep -E "[:.]${port}[[:space:]]" | head -n1 | awk '{print $NF}')
    if [[ $STRICT -eq 1 ]]; then
      fail "host port ${port}/${proto} already in use (${owner:-unknown}); set ${var} in .env"
    else
      warn "host port ${port}/${proto} already in use (${owner:-unknown}); set ${var} in .env"
    fi
  fi
done < <(grep -E '^[[:space:]]+- "\$\{[A-Za-z0-9_]+_PORT:-[0-9]+\}:[0-9]+' "$COMPOSE")

# Every published port must be a variable, otherwise .env cannot move it.
hardcoded=$(grep -nE '^[[:space:]]+- "[0-9]+:[0-9]+' "$COMPOSE" || true)
if [[ -n "$hardcoded" ]]; then
  fail "hard-coded host port(s) remain in docker-compose.yml:"
  printf '%s\n' "$hardcoded"
else
  ok "all published ports are ${VAR:-default} variables"
fi

ok "${#seen_ports[@]} host ports checked"

echo
echo "${errors} error(s), ${warnings} warning(s)"
[[ "$errors" -eq 0 ]]
