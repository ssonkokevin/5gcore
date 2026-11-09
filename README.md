# 5G Core Engine

Open-source 5G SA core architecture template with STP/DRA pilot, SCP integration, and UDM reference.

## Architecture

| Component | Tech | Port | Role |
|-----------|------|------|------|
| STP | osmo-stp / sigtran | 2905 | SIGTRAN M3UA routing |
| DRA | Python Diameter agent | 3868 | Diameter routing & translation |
| SCP | Python CAMEL/INAP | 3868/2905 | Service control plane |
| UDM | REST + MariaDB | 8080 | Unified data management |
| OAM | Vue 2 + Django | 8081 | Operations & maintenance |
| DB | MariaDB | 3306 | Core database |
| Cache | Redis | 6379 | Session / routing cache |

## Quick Start

```bash
# Copy environment
cp .env.example .env

# Build all images
docker-compose build

# Start stack
docker-compose up -d

# Verify
docker-compose ps
```

## Directory Layout

```
5g-core-engine/
├── stp/            # SIGTRAN / M3UA STP (osmo-stp configs + build)
├── dra/            # Diameter Routing Agent (Python engine)
├── scp/            # Service Control Plane (CAMEL/INAP)
├── udm/            # Unified Data Management (schema + REST)
├── database/       # SQL schemas (srg_db.sql, hssdbInitial.sql)
├── docker/         # Dockerfiles + compose
├── scripts/        # Build / bootstrap / provision scripts
├── config/         # Shared configuration templates
├── tests/          # Unit + integration tests
├── observability/  # Prometheus / Grafana / logging
└── docs/           # Architecture & runbooks
```

## Storage Estimate

| Component | Disk (installed) | Notes |
|-----------|------------------|-------|
| Base images (python, debian, mariadb, redis) | ~2 GB | Shared layers |
| STP (osmo-stp build) | ~500 MB | Build tools included |
| DRA (Python app) | ~100 MB | Runtime only |
| SCP (Python app) | ~100 MB | Runtime only |
| UDM (Python app + schema) | ~100 MB | Runtime only |
| MariaDB data dir | ~1 GB | Grows with subscribers |
| Redis data | ~100 MB | Ephemeral |
| Source / configs | ~50 MB | Git-tracked |
| **Total initial** | **~4 GB** | Docker images + code |
| **Running runtime** | **~2–4 GB** | Depends on subscriber count |

A full production build including build tools and container images fits comfortably under 10 GB.

## License

Internal use.
