# 5G Core Engine

Open-source 5G SA core architecture template with STP/DRA/SCP/UDM, PCF/SMF/UPF build scaffolds, and PaiCore-aligned LBS/GMLC pilot documentation.

## Architecture

| Component | Tech | Port | Role |
|-----------|------|------|------|
| STP | osmo-stp / SIGTRAN M3UA | 2905 | SS7/SIGTRAN routing (STP plane) |
| DRA | Python Diameter agent (stub) | 3868 | Diameter routing/translation (separate plane from STP) |
| SCP | Python CAMEL/INAP (stub) | 3869, 2906 | Service control plane (SCP-IN / CAMEL context) |
| NRF | Python, Redis/memory | 8000 | NF registry and discovery (TS 29.510 subset) |
| UDM | REST + MariaDB | 8007 (container 8080) | Tri-mode subscriber data, Milenage vectors, SUCI Profiles A/B |
| PCF/PCRF | Python stub + PCC configs | 7777, 3873/3874 | Policy/charging scaffold (Npcf/Gx/Gy template) |
| SMF | Python stub + PFCP profile | 8002, 8806 | Session control scaffold (N4 PFCP) |
| UPF/PGW | Python datapath stub + DPE/CPE configs | 2152, 8805, 42050 | Unified PGW/UPF datapath scaffold |
| GMLC | Python + Redis | 8082 | LCS API; answers NO_LCS_SOURCE until SLg/SLh/MAP exists |
| AMF | Python SBI proxy | 8001 | NRF registration, Namf_Location to the LMF; no NGAP |
| LMF | Python SBI | 8003 | Nlmf_Location to a configured provider; 501 without one |
| MME | Python Diameter SLg | 3875, 8075 | PLR answered 5012; no S1AP/S11/S6a |
| OAM | Placeholder service | 8081 | Operations & maintenance |
| DB | MariaDB | 3306 | Core database |
| Cache | Redis | 6379 | Session / routing cache |
| Observability | Prometheus / Grafana | 9090 / 3000 | Metrics & dashboards |

## Status

The stack is a **signalling and data-layer testbed**, not yet a deployable core.
There is no UE attach on the custom stack until the AMF gains NGAP/N2 and NAS.

- Service-by-service truth table: [docs/PHASE1_IMPLEMENTATION_GAPS.md](docs/PHASE1_IMPLEMENTATION_GAPS.md)
- Phased plan (5GC -> EPC/2G/3G -> EIR/SMS/IMS), acceptance gates, ports to reserve, and effort: same document.

## Quick Start

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

> PCF/SMF/UPF and the local DRA/SCP are **buildable scaffolds/stubs** (config, APIs, and interface placeholders), not protocol-complete or production-ready network functions. Integrate and validate real protocol stacks, simulators, and security controls before any lab interop beyond basic health checks.

## Directory Layout

```
5g-core-engine/
├── stp/            # SIGTRAN/M3UA STP (osmo-stp configs + build)
├── dra/            # Diameter Routing Agent stub/config
├── scp/            # Service Control Plane (CAMEL/INAP) stub
├── udm/            # Unified Data Management reference
├── pcf/            # PCF/PCRF scaffold (pcf.yaml, PCC, Diameter peers)
├── smf/            # SMF scaffold (smf.yaml, N4 PFCP profile)
├── upf/            # UPF/Unified PGW scaffold (upf/dpe/cpe/dpeMgr configs)
├── gmlc/docs/      # PaiCore-aligned GMLC pilot notes
├── database/       # SQL schemas (srg_db.sql, hssdbInitial.sql)
├── docker/         # Dockerfiles (stp,dra,scp,udm,oam,pcf,smf,upf)
├── scripts/        # Build/bootstrap/provision/health scripts
├── config/         # Shared configuration templates
├── tests/          # Unit + integration tests
├── observability/  # Prometheus/Grafana config
└── docs/           # Architecture & runbooks
```

## PaiCore / GMLC Notes

- **jSS7 alignment:** PaiCore jSS7 provides SS7/SIGTRAN building blocks (M3UA/SCCP/TCAP/MAP/CAP). Use behind a narrow adapter boundary for SS7 logic; it is not an operator-ready STP by itself. Keep STP (SIGTRAN routing) and DRA (Diameter routing) as distinct planes.
- **GMLC pilot:** see `gmlc/docs/GMLC-PILOT.md` and template section 44 for deployment, SS7 MAP/Diameter/MongoDB integration, JSON/MLP APIs, and test flows derived from `PaiCore/kevin/Documentation/GMLC_Documentation.md`.
- **License/safety:** review exact `LICENSE` files for pinned PaiCore/jSS7/GMLC components before adoption; sanitize credentials/IMSI/MSISDN/IP in configs and captures.

## License

Internal/lab template. Third-party components retain their own licenses.
