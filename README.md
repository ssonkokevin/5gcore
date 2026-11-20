# 5G Core Engine

Hamiltel in-house core: SS7/Diameter planes, tri-mode UDM/HSS/HLR, PCF/SMF/UPF
scaffolds, and the location functions that belong on the core side - the MME
LCS function, the E-SMLC and the LMF.

The GMLC is **not** in this repository. It is a separate Java/Spring service at
`github.com/ssonkokevin/gmlc`, because its hard work is SS7 MAP and Diameter and
it reuses the SS7 stack already proven in the SMSC gateway. The two services
talk over standard 3GPP interfaces only.

## Architecture

| Component | Tech | Port | Role |
|-----------|------|------|------|
| STP | osmo-stp / SIGTRAN M3UA | 2905 | SS7/SIGTRAN routing (STP plane) |
| DRA | Python Diameter agent (stub) | 3868 | Diameter routing/translation (separate plane from STP) |
| SCP | Python CAMEL/INAP (stub) | 3869, 2906 | Service control plane (SCP-IN / CAMEL context) |
| NRF | Python, Redis/memory | 8000 | NF registry and discovery (TS 29.510 subset) |
| UDM | REST + MariaDB | 8007 (container 8080) | Tri-mode subscriber data, Milenage vectors, SUCI Profiles A/B |
| UDR | REST + MariaDB | 8006 | Nudr authentication subscription with ETag/If-Match conditional writes |
| HSS | Python, Diameter + MAP | 3868 | S6a and MAP answering for 4G/3G/2G access |
| PCF/PCRF | Python stub + PCC configs | 7777, 3873/3874 | Policy/charging scaffold (Npcf/Gx/Gy template) |
| SMF | Python stub + PFCP profile | 8002, 8806 | Session control scaffold (N4 PFCP) |
| UPF/PGW | Python datapath stub + DPE/CPE configs | 2152, 8805, 42050 | Unified PGW/UPF datapath scaffold |
| AMF | Python SBI proxy | 8001 | NRF registration, Namf_Location to the LMF; no NGAP |
| LMF | Python SBI | 8003 | Nlmf_Location to a configured provider; 501 without one |
| MME | Python Diameter SLg | 3875, 8075 | LCS function only: PLR answered 5012; no S1AP/S11/S6a |
| E-SMLC | - | 9082 | **Not built yet** - this is the current work |
| GMLC | Java/Spring, separate repo | 8082 | Le API, MAP and Diameter towards HLR/HSS/MME |
| OAM | Placeholder service | 8081 | Operations & maintenance |
| DB | MariaDB | 3306 | Core database |
| Cache | Redis | 6379 | Session / routing cache |
| Observability | Prometheus / Grafana | 9090 / 3000 | Metrics & dashboards |

## Status, stated plainly

The stack is a **signalling and data-layer testbed**, not yet a deployable core.
There is no UE attach on the custom stack until the AMF gains NGAP/N2 and NAS.

| Area | State |
|---|---|
| osmo-stp, DRA, SCP, OAM | Configs and stubs that start; no conformance testing |
| UDM/HSS/HLR (`udm/`, `hss/`) | Substantial: 115 HTTP endpoints, S6a/Cx, MAP answering, Milenage/SUCI vectors shared with the HSS |
| UDR (`udr/`) | Nudr subscription data with ETag handling and SQN concurrency |
| MAP/SCCP (`map_sccp/`) | Lab answering only; responses are hand-built byte strings, **not** ASN.1-conformant |
| Diameter S6a/Cx (`diameter/`) | Lab answering only; no SLh, SLg or Sh |
| PCF, SMF, UPF, CAMEL, OCS | Scaffolds |
| AMF / LMF | Thin SBI services; no NGAP, no positioning engine |
| MME | SLg stub only; no UE attach |
| E-SMLC | **Not built yet** |
| Tests | pytest suites for crypto, HSS/UDM auth, SUCI, UDR, signalling headers, stack contract and the location schema; no protocol conformance suite |

Everything labelled a stub is a stub. Do not present it as a network function
that has passed an acceptance test. Service-by-service detail and the phased
plan are in [docs/PHASE1_IMPLEMENTATION_GAPS.md](docs/PHASE1_IMPLEMENTATION_GAPS.md).

## Quick start

```bash
cp .env.example .env
chmod 600 .env
./scripts/preflight.sh        # RAM, disk, SCTP, Docker and every published port
./scripts/bootstrap.sh        # build, start, wait for health
docker compose ps
```

`preflight.sh --strict` makes port conflicts fatal; run it on a shared host
before the first deploy. Every published host port is a variable in `.env`
(`db`, `oam`, `grafana` and `prometheus` clash on the shared lab VM).
`bootstrap.sh` prints the ports actually in use.

The STP renders its configuration at container start from `STP_LOCAL_PC`,
`STP_REMOTE_PCS` and `STP_ROUTES`; no point code is committed. Defaults are lab
values (1.2.3 with peers 1.2.4 and 1.2.5).

> PCF/SMF/UPF and the local DRA/SCP are **buildable scaffolds/stubs** (config, APIs, and interface placeholders), not protocol-complete or production-ready network functions. Integrate and validate real protocol stacks, simulators, and security controls before any lab interop beyond basic health checks.

Docker is not available on the current Windows development host, so the
container build is **unverified**. Python services run directly on the host for
tests.

## Directory layout

```
5g-core-engine/
├── stp/            # SIGTRAN/M3UA STP (osmo-stp configs + build)
├── dra/            # Diameter routing agent stub/config
├── scp/            # CAMEL/INAP service control plane stub
├── nrf/            # NF registry and discovery
├── udm/            # Tri-mode UDM/HSS/HLR reference service
├── udr/            # Nudr data repository with conditional writes
├── hss/            # S6a/MAP HSS face
├── amf/            # AMF SBI proxy (no NGAP)
├── mme/            # LTE MME with the LCS function
├── lmf/            # 5G LMF
├── esmlc/          # E-SMLC: LCS-AP, LPP, LPPa (new)
├── corelib/        # Milenage, Diameter, HTTP and NRF helpers shared by NFs
├── lib/            # Shared positioning library and codecs (new)
├── tools/sim/      # Simulated UE, eNB, gNB, HLR/HSS, MME, E-SMLC (new)
├── pcf/ smf/ upf/  # PCF/PCRF, SMF, UPF scaffolds
├── map_sccp/       # Lab MAP responder over SCCP
├── diameter/       # Lab Diameter S6a/Cx responder
├── database/       # MariaDB schemas, including database/location/
├── docker/         # Dockerfiles per service
├── scripts/        # Build, preflight, bootstrap, provisioning and health scripts
├── tests/          # pytest suites
├── docs/           # Architecture, inspection, decisions and phase plan
├── observability/  # Prometheus/Grafana config
└── archive/        # Superseded material kept for reference only
```

`archive/python-gmlc-stub/` is the old prototype gateway. It is not deployed,
not referenced by compose, and not a basis for the product.

## Location services

Read `docs/location/INSPECTION.md` (what exists today), `docs/location/DECISIONS.md`
(why the split is drawn where it is) and `docs/location/PLAN.md` (phases and
acceptance criteria). The rule that governs every result: a position is only
ever returned with its method, uncertainty, confidence and age. If the network
cannot measure, the result is cell-ID and says so.

## License

Internal/lab template. Third-party components retain their own licenses.
