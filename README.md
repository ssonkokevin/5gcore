# 5G Core Engine

Hamiltel in-house core: SS7/Diameter planes, tri-mode UDM/HSS/HLR, PCF/SMF/UPF
scaffolds, and the location functions that belong on the core side - the MME
LCS function, the E-SMLC and the LMF.

The GMLC is **not** in this repository. It is a separate Java/Spring service at
`github.com/ssonkokevin/gmlc`, because its hard work is SS7 MAP and Diameter and
it reuses the SS7 stack already proven in the SMSC gateway. The two services
talk over standard 3GPP interfaces only.

## Status, stated plainly

| Area | State |
|---|---|
| osmo-stp, DRA, SCP, OAM | Configs and stubs that start; no conformance testing |
| UDM/HSS/HLR (`udm/`) | Substantial: 115 HTTP endpoints, S6a/Cx, MAP answering, auth vectors |
| MAP/SCCP server (`map_sccp/`) | Lab answering only; responses are hand-built byte strings, **not** ASN.1-conformant |
| Diameter S6a/Cx (`diameter/`) | Lab answering only; no SLh, SLg or Sh |
| PCF, SMF, UPF, CAMEL, OCS | Scaffolds |
| MME, E-SMLC, LMF | **Not built yet** - this is the current work |
| Tests | None in this repository yet; the location work adds them first |

Everything labelled a stub is a stub. Do not present it as a network function
that has passed an acceptance test.

## Quick start

```bash
cp .env.example .env    # change every secret before use
docker compose build
docker compose up -d
docker compose ps
```

Docker is not available on the current Windows development host, so the
container build is **unverified**. Python services run directly on the host for
tests.

## Directory layout

```
5g-core-engine/
├── stp/            # SIGTRAN/M3UA STP (osmo-stp configs + build)
├── dra/            # Diameter routing agent stub
├── scp/            # CAMEL/INAP service control plane stub
├── udm/            # Tri-mode UDM/HSS/HLR reference service
├── pcf/ smf/ upf/  # PCF/PCRF, SMF, UPF scaffolds
├── map_sccp/       # Lab MAP responder over SCCP
├── diameter/       # Lab Diameter S6a/Cx responder
├── mme/            # LTE MME with the LCS function (new)
├── esmlc/          # E-SMLC: LCS-AP, LPP, LPPa (new)
├── lmf/            # 5G LMF (later phase)
├── lib/            # Shared positioning library and codecs (new)
├── tools/sim/      # Simulated UE, eNB, gNB, HLR/HSS, MME, E-SMLC (new)
├── database/       # MariaDB schemas, including database/location/
├── docker/         # Dockerfiles per service
├── scripts/        # Build/bootstrap/provision/health scripts
├── tests/          # pytest suites (new)
├── docs/           # Architecture, inspection, decisions and phase plan
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
