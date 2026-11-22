# Location work - Phase 0 inspection

Date: 2026-11-21
Repository: `github.com/ssonkokevin/5gcore`, branch `main`
Local path: `C:\Users\KEVIN\core dpi\5g-core-engine`

This is what the core actually is, before any location code is written. Every
statement below was read from the tree, not from a design document. Where the
existing README overstates something, the row says so.

## 1. Toolchain

| Item | Fact |
|---|---|
| Language | Python, one directory per network function, `src/<name>_server.py` |
| Runtime base image | `python:3.11-slim` in every Dockerfile |
| Host runtime | `py` = Python 3.15.2 (pytest 9.2.0 installed for tests) |
| Web framework | FastAPI + uvicorn (GMLC stub, UDM); some services use raw asyncio |
| Data access | `mysql-connector-python` against MariaDB, raw SQL, `dict` cursors |
| Config | Environment variables plus a YAML/JSON file per service |
| Dependency management | Pinned only inside Dockerfiles. No `requirements.txt`, no lock file |
| Tests | **None.** No `tests/` directory, no CI workflow, no test runner config |
| Licence files | None in the tree |

Python 3.15 on the host versus 3.11 in the images is a real difference: avoid
syntax and library features newer than 3.11.

## 2. Modules as they stand

Line counts are from `wc -l` over the merged tree (9,121 Python lines total).

| Module | Size | What it really does | Status for location |
|---|---|---|---|
| `udm/` | 3,440 | 115 HTTP endpoints: `Nudm_SDM`, `Nudm_UEAU`, `Nudm_UECM`, `Nudm_UEID`, S6a/Cx and MAP answers against MariaDB | **Useful.** Serves `amf-3gpp-access` registration (serving AMF) and `lcs-privacy-data` / `lcs-mo-data` / `lcs-subscription-data` from `tbl_5g_subscription.lcs_privacy_5g` |
| `map_sccp/` | 938 | SCCP/TCAP/MAP answering over a socket; SRI-SM, SAI, ISD, PRN, USSD, SS, ATI, PSL | **Lab only, non-conformant** - see 3.1 |
| `diameter/` | 789 | Diameter S6a (SRI, SAI, ISD, DSD, PUR, RST, NOT) and Cx (UA, SA, LI, MA, PP, RT), CER/CEA, DWR/DWA | **S6a/Cx only.** No SLh, no SLg, no Sh |
| `oam/` | 1,900 | Django admin: models, views, serialisers for the DB | Not involved |
| `camel/` | 597 | CAMEL/INAP state machine stub | Not involved |
| `ocs/` | 492 | Gy credit-control client stub | Not involved |
| `dra/` | 228 | Diameter routing agent stub | Not involved |
| `scp/` | 156 | Service control plane stub | Not involved |
| `pcf/` `smf/` `upf/` | 65-73 each | FastAPI scaffolds answering health/status | Not involved |
| `stp/` | config | osmo-stp container, M3UA ASP/AS config | SS7 peer for the GMLC |
| `gmlc/` | 238 | FastAPI stub: `/health`, `/lcs/location-request`, `/diameter/slh`, `/diameter/slg` | **Moved to `archive/python-gmlc-stub/`** - superseded, not deployed |

Containers in `docker-compose.yml`: db, hssdb, redis, osmo-stp, open5gs-dra,
diameter, map-sccp, camel, ocs, nrf, mongo, amf, smf, upf, ausf, udm,
custom-udm, pcf, chf, scp, custom-pcf, custom-smf, custom-upf, oam, prometheus,
grafana. The `gmlc` service has been removed; the GMLC now runs from its own
repository.

The AMF is the stock image `free5gc/amf:v3.4.0` (`docker-compose.yml:303`). It
has no LCS function: no `Namf_Location` service, no LPP/NRPPa relay. Nothing in
this repository currently answers a `ProvidePositioningInfo` request.

## 3. What exists that touches location

### 3.1 `map_sccp` ATI and PSL - not usable as a peer

`handle_any_time_interrogation` (`map_sccp/src/map_sccp_server.py:713`) and
`handle_psl` (`:753`) find the IMSI by scanning the raw parameter bytes, then
return hand-assembled tag/value pairs such as `bytes([0x04, 0x06]) + imsi`
(`:737`) and `bytes([0x04, 0x06]) + encode_imsi(imsi)` (`:774`).

Two problems:

1. The result is placed directly after the invoke, so the caller sees an
   invented structure rather than `AnyTimeInterrogationRes` or
   `ProvideSubscriberLocation-Res` from TS 29.002. A conformant GMLC will
   reject it.
2. ATI and PSL return subscriber identity, a hard-coded `"CELL-01"` /
   `"LAC-01"` (`:775-776`) and invented tags. There is no location estimate,
   no age of location, no service-node address, no cell fields.

Consequence for this work: the Python MAP peer must be **rewritten against the
TS 29.002 ASN.1**, and the GMLC's MAP client must be built against the same
module. The SMS subset already proven in the SMSC gateway is a Java stack; this
one is unrelated code and shares nothing.

### 3.2 Diameter - no LCS applications

`dispatch_command` (`diameter/src/diameter_server.py:688`) knows only
`S6A_HANDLERS` and `CX_HANDLERS`. There are no LIR/LIA, RIR/RIA, PLR/PLA,
LRR/LRA or UDR/UDA handlers. `APP_3GPP_Sh` now imports `APP_SH` (16777217,
TS 29.328 5.1) from `corelib.diameter`, but Sh itself is not implemented
despite the module docstring mentioning "SWx ... (Sh interface)".

The infrastructure that *is* reusable: AVP encode/decode, the message header
builder, CER/CEA and DWR/DWA, and the socket loop.

### 3.3 UDM - the only LCS-aware data source

- `GET /nudm-sdm/v2/{ue_id}/lcs-privacy-data` (`udm/src/udm_server.py:2105`)
- `GET /nudm-sdm/v2/{imsi}/lcs-mo-data` (`:2121`)
- `GET /nudm-sdm/v2/{imsi}/lcs-bca-data` (`:2140`) - returns `{}`
- `GET /nudm-sdm/v2/{imsi}/lcs-subscription-data` (`:2149`)
- `GET /nudm-uecm/v1/{ue_id}/registrations/amf-3gpp-access` (`:1771`) - the
  serving-AMF answer the GMLC needs

These return stored JSON blobs (`tbl_5g_subscription.lcs_privacy_5g`) without
validating their shape against TS 29.503. That is enough to start, and it means
the GMLC's `Nudm_SDM` client has something to talk to on day one.

### 3.4 Nothing else

No MME, no E-SMLC, no LMF, no SMLC, no positioning library, no cell database,
no LPP/LPPa/NRPPa/LCS-AP codec, no SUPL. The only cell-like string in the tree
is the hard-coded `"CELL-01"` above.

## 4. Database

Two MariaDB bootstrap files, mounted into the `db` and `hssdb` containers:

- `database/hssdbInitial.sql` - 17 tables: subscribers, EPS/5G/IMS
  subscriptions, APN profiles, SS, roaming, USSD routing, CAMEL, auth vectors,
  network nodes, batch upload, IMSI ranges, UECM registration.
- `database/srg_db.sql` - 13 tables for DRA/STP: peers, routes, translations,
  M3UA local/global/link/link set, trace.

Facts that matter:

- **No table has a tenant column.** Hamiltel will be tenant 1, but the model
  cannot express a second operator yet.
- No cell/antenna table, no positioning session table, no location record.
- `tbl_subscriber` carries K, Ki, OP/OPc in clear columns (that is the existing
  design; location work does not touch it and must not log it).
- Seeding is by init script only; there is no migration tool, so new location
  tables go in `database/location/` as ordered, idempotent SQL files applied by
  the same mechanism.

## 5. Host and lab constraints

- **No Docker on this host.** Container definitions are authored but unverified.
- **No SCTP on Windows.** `AF_SCTP` does not exist, so every SIGTRAN test runs
  over a TCP lab carrier behind a transport interface. SCTP sockets exist only
  in the Linux containers and are labelled unverified until run there.
- No D: drive. Earlier paths in the vendor documentation (`D:\core dpi\...`) do
  not resolve on this machine.
- Specs live at `C:\Users\KEVIN\Downloads\3gpp_specs`, each as a zip containing
  a single `.docx`. **TS 23.003 (numbering, identities, cell-ID format) is
  missing** and is needed for ECGI/NCGI helpers and test vectors.
- Lab PLMN only: 001/01 or 999/70. No vendor point codes in commits.

## 6. Risk register carried into Phase 1

| Risk | Effect | Mitigation |
|---|---|---|
| No SCTP on the dev host | LCS-AP, SLg and MAP cannot be tested over their real transport here | Transport interface with a TCP carrier; SCTP mode tested in Linux only, labelled unverified until it runs |
| Existing MAP responses are non-conformant | GMLC interop would fail against `map_sccp` | Rewrite the MAP peer from ASN.1 before writing the GMLC client; round-trip tests both ways |
| UDM LCS payloads unvalidated | GMLC may consume a wrongly shaped privacy profile | Validate at the GMLC boundary and fail closed on unknown shape |
| No real eNB/gNB/UE | No end-to-end radio evidence | Simulators derive measurements from a truth model; every claim labels its evidence |
| TS 23.003 absent | Cell identity mistakes | Obtain the spec before the cell DB helper work |
| Python 3.15 host vs 3.11 images | Silent incompatibility | CI/test run on 3.11 syntax limits; avoid post-3.11 features |

## 7. What Phase 0 changes in this repository

1. `gmlc/` and `docker/gmlc/` archived under `archive/python-gmlc-stub/`; the
   compose service removed; README and `.env.example` corrected.
2. `docs/location/` written: this file, `DECISIONS.md`, `PLAN.md`, capability
   profile schema and the tenant-1 profile.
3. `database/location/001_location_schema.sql`: tenant-aware tables for cells,
   positioning sessions, per-UE capability cache and results.
4. `tests/` created with a schema-conformance test that runs without a
   database, plus the pytest configuration.

No behaviour of the existing services changes in Phase 0.
