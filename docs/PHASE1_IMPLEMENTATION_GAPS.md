# Phase 1 Implementation Gap Summary

Status of the custom Hamiltel core in this repository, and the ordered work needed
to reach the Phase 1 goal: a 5G SA core that completes real signalling end to end,
followed by EPC / 2G / 3G interworking, then EIR, SMS and IMS.

Written 2026-11-19 against the working tree that produced `44/44` tests and
`check_stack.py: OK 33 services, no host-port collisions, contracts satisfied`.

---

## 0. How to read the status labels

| Label | Meaning |
|---|---|
| **Built** | Protocol implemented and asserted by a test. Usable. |
| **Partial** | The API or protocol exists; a required peer or procedure does not. |
| **Stub** | Process starts, answers honestly, forwards nothing. |
| **Absent** | No code. |

"Honest failure" is a deliberate design rule in this stack: where a procedure
cannot be completed, the node returns a machine-readable cause (HTTP 501 with a
`cause` field, or a Diameter result code) and never invents data. Several nodes
below are marked *Partial* rather than *Broken* for that reason.

---

## 1. Direct answers to the four questions

### 1.1 Is the GMLC ready, and is it ready for E-SMLC?

**No on both counts.**

- The GMLC process is **built** as a business and record layer: privacy decision,
  request store (Redis), request lifecycle, and structured failures. It answers
  `NO_LCS_SOURCE` for every immediate request because nothing is configured to
  supply a position.
- It has **no LCS client** to any node: `gmlc/config/gmlc.yaml` sets
  `map.enabled: false`, `diameter.enabled: false`, and every flag under
  `interfaces` to `false`. `SLg` and `SLh` exist only as HTTP shims that return
  result code `5010`. There is no Diameter SCTP listener and no MAP stack
  binding in the GMLC process.
- **E-SMLC does not exist in this repository.** No `esmlc/` directory, no `SLs`
  server, no LPP/LPPa handling. In a 5G-only deployment an E-SMLC is not needed
  (the LMF does that job); it is needed only for EPS fallback / 4G location,
  which is Phase 1B. The commercial E-SMLC that was evaluated is licensed
  software, not built here.

So the GMLC is a correct *front end* that cannot yet reach a positioning node.

### 1.2 Is the LMF working as expected?

**Partially.** What works:

- NRF registration (`nlmf-loc`), NRF discovery by the AMF.
- `POST /nlmf-loc/v1/determine-location` accepts a TS 29.572-shaped request,
  forwards it to `LMF_PROVIDER_URL`, validates the returned latitude/longitude
  range, and converts the answer into a `geographicArea` POINT.
- With no provider configured it returns `501 NO_POSITIONING_SOURCE`; with an
  unreachable provider, `504`; with a bad payload, `502`. It never simulates.

What is missing:

- No measurement source. `LMF_PROVIDER_URL` is empty by default, so every real
  request fails by design.
- No NRPPa client to the NG-RAN (NL3), so no ECID / NR-Multi-RTT / A-GNSS
  measurements can be requested.
- No LPP positioning session toward the UE (LPP is carried over N1/NAS, which
  requires the AMF's NAS layer that does not exist yet).
- No location calculation, no assistance-data delivery, no deferred/periodic
  positioning (`cancel-location` and context transfer return 501).

### 1.3 Are STP and DRA done?

**STP: built, but with a vendor's route table baked in.**
`docker/stp/Dockerfile` compiles `osmo-stp` from source and runs it with M3UA
over SCTP on 2905. It is a real STP. However
`stp/config/osmo-stp.cfg` contains point codes and 258-style route entries copied
from a production dump (`3.15.0`, `0.185.1`, `3.14.2`, ...). Those must be
replaced with Hamiltel's own point codes before any peer is connected.

**DRA: not done.** `dra/src/dra_engine.py` loads peers, peer-sets, routes and
translation rules, mirrors them into Redis, and then waits on a stop event. It
opens **no Diameter socket**: no `asyncio.start_server`, no SCTP, no relay. Port
3868 is published in Compose, but nothing is listening. Today the DRA is a route
model, not a routing agent. It also cannot answer a CER.

### 1.4 Is the UDM complete?

**Substantially, for the data and authentication side; not complete for 5G
signalling.**

| Area | State | Notes |
|---|---|---|
| Milenage (f1, f1*, f2-f5, f5*) | Built | AES-128, OPc derivation, per-vector SQN increment, fail-closed when pycryptodome is absent |
| 5G AKA key hierarchy | Built | Kausf/Kseaf/Kamf derivation per TS 33.501 Annex A |
| SUCI de-concealment | Built | Profiles A (X25519) and B (P-256), ANSI X9.63 KDF, AES-CTR, MAC verify, BCD MSIN |
| `Nudm_SDM` | Built | ~20 data types, DB-backed |
| `Nudm_UECM` | Built | AMF/3GPP, non-3GPP, SMF registrations, SMSF, IP-SM-GW |
| `Nudm_UEAU` | Built | generate-auth-data, HSS AV (EPS/IMS AKA), auth events |
| `Nudm_EE`, `_PP`, `_NIDDAU`, `_SSAU`, `_RSDS` | Built | API-level |
| Subscriber/provisioning API | Built | ~130 routes, batch upload, IMSI ranges, EPS/5G/IMS subscription, APN, CAMEL, roaming |
| EAP-AKA′ (CK′/IK′) | **Absent** | Returns `501 EAP_AKA_PRIME_NOT_IMPLEMENTED` |
| UDR split (`Nudr`) | **Absent** | UDM writes MariaDB directly; no separate UDR NF |
| SIDF / NAI SUCI | Partial | A/B only; NAI SUCI returns `SUCI_UNSUPPORTED` |
| `Nudm_MT` (SMS routing) | Partial | API present; transport to SMSF/IP-SM-GW is not built |
| AUSF role | **Absent as an NF** | UDM serves `generate-auth-data` directly; the AMF has no AUSF to call |

The gap that matters for Phase 1 is not UDM data: it is that nothing can reach
it from a UE until the AMF speaks NAS.

---

## 2. True state of every default-profile service

Default profile = 24 services. `profiles: ["free5gc"]` = 9 upstream reference
services, never started with the custom stack.

| # | Service | Ports (host) | State | One-line truth |
|---|---|---|---|---|
| 1 | `db` (MariaDB) | 3306 | Built | Schema loaded from `database/` |
| 2 | `hssdb` | 3307 | Built | HSS/EPS-UDR schema |
| 3 | `redis` | 6379 | Built | Cache + GMLC request store |
| 4 | `custom-nrf` | 8000 | Built | TS 29.510 register/patch/delete/discover/subscribe |
| 5 | `osmo-stp` | 2905 sctp/udp | Partial | Real M3UA STP; vendor route table must be replaced |
| 6 | `dra` | 3868 | **Stub** | Route model only; no socket, no relay, no CEA |
| 7 | `diameter-s6a-cx` | 3880 | Partial | S6a/Cx Diameter server for HSS; needs 4G peers to be exercised |
| 8 | `map-sccp` | 2906 | Partial | SCCP/TCAP/MAP application engine; not SIGTRAN-conformance tested |
| 9 | `camel` | 2907 | Partial | CAMEL Phases 1-4 state machine; no live gsmSSF |
| 10 | `ocs` | 3870 | Partial | Gy CCR-I/U/T client; no real CHF |
| 11 | `scp` | 3871 / 2908 | Partial | CAMEL/INAP service logic; no SBI SCP role |
| 12 | `hss` | 8090 | Built | Nhss SBI (TS 29.563) + tri-mode subscriber store |
| 13 | `custom-udm` | 8007 | Built | See §1.4 |
| 14 | `custom-pcf` | 8004, 3873, 3874 | Built | N7 policy decisions from JSON profiles; no N15/CHF |
| 15 | `custom-smf` | 8002, 8806 | Partial | N11-style HTTP + real PFCP encode + GTPv2-C server; N4 peer is a stub; GTP-C 2123 not published |
| 16 | `custom-upf` | 2152, 8805, 42050 | **Stub** | Logs `UPF STUB` at start; receives UDP and forwards nothing |
| 17 | `gmlc` | 8082 | Partial | Front end only; see §1.1 |
| 18 | `oam` | 8081 | Partial | Django O&M shell; no NF lifecycle control |
| 19 | `oam-frontend` | 3001 | Built | Static UI |
| 20 | `prometheus` | 9090 | Built | Scrape config only |
| 21 | `grafana` | 3000 | Built | Dashboards |
| 22 | `custom-amf` | 8001 | **Partial** | Namf_Location proxy to LMF; **no N2/NGAP, no NAS, no attach** |
| 23 | `custom-lmf` | 8003 | Partial | Forwarder; no measurement source |
| 24 | `custom-mme` | 3875, 8075 | Stub | Diameter SLg only; PLR answered `5012`; no S1AP/S11/S6a/SGs |

Absent 5G NFs: **AUSF, UDR, NSSF, CHF, SMSF, BSF, NWDAF, EIR, SEPP.**
Absent EPC/2G/3G NFs: **SGW, PGW, SGSN, GGSN, MSC/MGW, E-SMLC, SMSC.**
Absent Phase 2: **EIR, SMSC/SMSF, IMS (P/I/S-CSCF, MGCF, BGCF).**

---

## 3. Phase 0 — make the lab deployable (1 week)

Do this before writing new protocol code.

| ID | Task | Why |
|---|---|---|
| P0-1 | Parameterise all 44 host-port mappings in `docker-compose.yml` as `${X_HOST_PORT:-default}` and document each in `.env.example` | The target VM shares `10.44.44.121` with another application; hardcoded 3306/8081/8082/3000/9090 will collide |
| P0-2 | Pre-flight script: check free RAM/disk, `ss -lntup` for every registered host port, `modprobe sctp`, Docker version | Turns a 20-minute mystery into a one-line error |
| P0-3 | Replace STP point codes and routes with Hamiltel values; blank IMSI filters (already blank) | Vendor PC `3.14.4` cannot be used off the vendor network |
| P0-4 | Decide the single-IP strategy (see §9.1) | GTP-U and Diameter cannot be multiply-bound on one IP |
| P0-5 | CI: GitHub Actions running `check_stack.py`, `unittest discover`, and `docker compose config` on every push | 44 tests exist but nothing enforces them |

**Done when:** a clean clone on the target VM reaches `docker compose ps` with 24
services healthy, and CI is green on `master`.

---

## 4. Phase 1 — complete 5G SA core and signalling

The gate is a real UE attach. Everything else in Phase 1 serves that.

### WP1.1 — AMF: NGAP / N2 (long pole)

- SCTP server on 38412 (host mapping to be added; keep 38412 free, the free5GC
  profile already moved off it).
- NGAP ASN.1 PER codec from the 3GPP NGAP module (Rel-17). Generate with
  `asn1tools`; do not hand-write PER.
- Procedures: NG Setup, NG Reset, Error Indication, Initial UE Message,
  Downlink/Uplink NAS Transport, Initial Context Setup, UE Context Release,
  Paging, Handover Preparation (later).
- UE context store (Redis) keyed by AMF-UE-NGAP-ID / RAN-UE-NGAP-ID.

Acceptance: NG Setup completes against `UERANSIM` or `srsRAN`; a UE can send an
Initial UE Message carrying a Registration Request and receive a NAS reply.

### WP1.2 — AMF: NAS 5GMM / 5GSM and NAS security

- 5GMM: Registration Request/Accept/Reject, Authentication Request/Response,
  Security Mode Command/Complete, Identity, Service Request, Deregistration,
  Configuration Update.
- 5GSM transport: relay SM messages to SMF over N11.
- NAS security: NIA2 (AES-CMAC) integrity, NEA2 (AES-CTR) ciphering, COUNT
  handling, re-play protection.
- Key hierarchy: AUSF → Kseaf → Kausf, Kamf derived in AMF, KgNB delivery.
- SUCI: accept `supi-` and `suci-` identities; concealment remains a UDM function.

Acceptance: 5G-AKA completes with a provisioned USIM; Security Mode Complete is
received with the correct MAC; registration completes.

### WP1.3 — AUSF (new NF)

- `Nausf_UEAuthentication` (TS 29.509): authenticate request, 5G-AKA
  confirmation, SUCI-based routing.
- Consumes UDM `Nudm_UEAU`; returns Kseaf.
- Registers in NRF as `AUSF`.

Then narrow UDM's `Nudm_UEAU` to the ARPF role it should play, and point AMF at
AUSF rather than UDM.

### WP1.4 — UDM / UDR

- Optional but recommended: extract UDR (`Nudr`, TS 29.504) so subscriber data
  has the 3GPP boundary and can be shared with PCF/CHF.
- Complete SIDF (SUCI scheme 0/NAI) or document NAI as out of scope.
- `Nudm_MT` transport once SMSF exists (Phase 2).

### WP1.5 — UPF: replace the stub with a real datapath

This is the second-long pole and a buy/build decision.

- Minimum viable: GTP-U decapsulation/encapsulation on N3/N9/N6, PDR/FAR/QER
  installation from PFCP, UE IP pool, ICMP-first forwarding.
- Recommended: integrate a proven open-source datapath rather than write one
  (free5gc UPF, UPF-EPC/`upg-vpp`, or similar) behind the existing management
  API, and keep the custom PFCP control plane.
- Keep `DATA_PATH_MODE`, `DPDK_ENABLED` switches.

Acceptance: a UE receives an IP and pings an N6 host through the UPF; counters
increment; session deletion removes state.

### WP1.6 — SMF: N4 and N11 completion

- PFCP association setup/heartbeat with the UPF, node-id reporting.
- Session Establishment/Modification/Deletion with correct SEID handling and
  cause mapping (the encoders already exist in `PFCPClient`).
- Publish GTP-C 2123 only if PGW-C function is used; otherwise leave closed.
- N2 SM information returned to the AMF (tunnel info after WP1.1).
- IP pool release on session release; duplicate-session handling.

### WP1.7 — PCF

- Complete N7 `SmPolicyControl` (create/update/delete) against real SMF calls.
- Add N15 (binding support) only if multiple PCFs are deployed.
- Wire CHF for online/offline charging (WP1.11) or document charging as offline
  CDR only.

### WP1.8 — NRF and SBI security

- TLS on every SBI endpoint, service-to-service OAuth2 token request
  (TS 33.501 §13.4.1: NF consumer, NRF as authorization server).
- Discovery filters used by AMF/SMF/PCF: target-nf-type, service-names, plmn,
  snssais, dnn.

### WP1.9 — LMF: real positioning

- NRPPa client (LMF → AMF → NG-RAN) for ECID and NR-Multi-RTT.
- LPP positioning session (LMF → AMF → UE) with assistance data.
- A lab measurement adapter: first target is a gNB simulator that can report
  timing measurements; the provider interface already exists
  (`LMF_PROVIDER_URL`) and can front it.
- Deferred/periodic location and cancel.

Acceptance: GMLC request returns a real coordinate whose accuracy is consistent
with the measurement set; repeatability within the configured QoS.

### WP1.10 — GMLC: NL1 client and Le API

- `Namf_Location` client (NL1) with correct TS 29.518 request/response.
- OMA MLP or JSON/Le API for LCS clients (the current `/lcs/*` is a placeholder
  shape, not MLP).
- Privacy from UDM LCS subscription data (`lcs-privacy-data` already served).
- Remove the SLg/SLh HTTP shims once real 5G signalling exists.

### WP1.11 — CHF (optional in Phase 1)

- `Nchf_ConvergedCharging` (TS 32.290) or at minimum offline CDR generation
  from SMF. Needed if billing must be demonstrated.

### WP1.12 — NSSF (optional in Phase 1)

- `Nnssf_NSSelection` (TS 29.531). Required only if slicing is sold.

---

## 5. Phase 1 gate — what "ready for private 5G" means

| Gate | Test | Owner node |
|---|---|---|
| G1 | UE attaches over NG-RAN simulator: NG Setup, Registration, 5G-AKA, Security Mode | AMF, AUSF, UDM |
| G2 | PDU session established; UE gets an IP; ping/DNS through N3/N6 | SMF, UPF |
| G3 | Deregistration, service request, idle→connected transition | AMF |
| G4 | Policy: QoS flow established from PCF rule; usage report received | PCF, SMF |
| G5 | GMLC returns a real position through AMF→LMF with a lab measurement source | GMLC, AMF, LMF |
| G6 | NRF discovery used for every SBI call; TLS + OAuth2 enabled | All |
| G7 | 72-hour soak with metrics and log rotation; no leaks | All |
| G8 | Clean VM → running stack in under 20 minutes, documented | Compose |

Until G1 and G2 pass, "private 5G ready" is not a defensible claim, and the
current stack should be described as a **signalling and data-layer testbed**,
not a deployable core.

---

## 6. Phase 1B — EPC and 2G/3G interworking

Sequence matters: MME and SGW first (4G), then SGSN/GGSN (2G/3G), then handover.

| ID | Work | Spec | Note |
|---|---|---|---|
| P1B-1 | MME: S1AP over SCTP 36412 | TS 36.413 | ASN.1, same toolchain as NGAP |
| P1B-2 | MME: S11 GTPv2-C to SGW | TS 29.274 | Create/Modify/Delete Session |
| P1B-3 | MME: S6a to HSS | TS 29.272 | `diameter-s6a-cx` exists; exercise it |
| P1B-4 | MME: SGs to MSC (CS fallback, SMS) | TS 29.118 | Needs MSC |
| P1B-5 | MME: SLg location | TS 29.172 | Already answers; make it complete once S1AP exists |
| P1B-6 | SGW: S1-U, S11, S5/S8, GTP-U | TS 23.401 | New service |
| P1B-7 | PGW: S5/S8, SGi, IP allocation; GGSN role over Gn | TS 23.401, 29.060 | New service; can share SMF control plane |
| P1B-8 | SGSN: Gb / Iu-PS, Gn/Gp, GTP-U | TS 23.060, 48.016 | New service |
| P1B-9 | HSS: MAP Gr/Gr′ over the STP for 2G/3G | TS 29.002 | `map-sccp` engine is the base |
| P1B-10 | MSC/MGW: CS core + MAP LCS (SLR/SLA) | TS 23.018, 29.002 | Needed for GMLC MAP path |
| P1B-11 | E-SMLC + SLs for EPS positioning | TS 23.271, 29.171 | Buy or build decision |
| P1B-12 | 4G↔5G interworking (N26) | TS 23.501 §5.17 | Only if mobility between RAATs is sold |
| P1B-13 | GMLC: SLg client to MME, SLh to HSS, MAP Lg/Lh | TS 29.171/29.172 | Replaces the HTTP shims |

Phase 1B gate: a 4G UE attaches (srsENB/srsEPC-class lab), receives an IP,
pings, and a GMLC request returns a position through SLg→MME→E-SMLC→SLs.

---

## 7. Phase 2 — EIR, SMS, IMS

| Block | Work | Specs |
|---|---|---|
| EIR | S13 Diameter (ME Identity Check), Gf/Fh for 2G/3G | TS 29.272, 29.018 |
| SMS | SMSF (SMS over NAS, Nsmsf), SMS-IWMSC/SMS-GMSC, MAP SRI-SM, SGd Diameter, SMPP | TS 23.040, 29.540, 29.338 |
| IMS | P-CSCF, I-CSCF, S-CSCF, HSS Cx/Sh, Rx, Gm, Mw, MGCF/BGCF, ENUM/DNS | TS 24.229, 29.228, 29.214 |
| Voice | VoLTE / VoNR call setup, emergency calls, SRVCC (optional) | TS 23.228 |

---

## 8. Cross-cutting engineering work

| Area | Gap |
|---|---|
| Security | No TLS or OAuth2 anywhere; NAS security absent; `.env` holds all secrets (acceptable for lab, not for production) |
| Observability | Prometheus scrapes; no NF-specific metrics (sessions, attach failures, Diameter result codes) |
| Logging | Structured logs on some nodes, plain on others; no correlation IDs across NFs |
| Testing | 44 unit/contract tests; no protocol conformance suite; no integration tests against UERANSIM |
| Packaging | Compose only; no versioned release images, no signed images, no rollback procedure |
| HA | Single instance per NF; no redundancy, no StatefulSet equivalent |
| Backup | Manual `mysqldump`; no scheduled backup or restore drill |

---

## 9. Network and port constraints

### 9.1 The one-IP problem (read before Phase 1B)

GTP-U uses **UDP 2152** for N3, S1-U, S5/S8-U and Gn/Gp-U. Diameter uses
**TCP/SCTP 3868** for S6a, Cx, Sh, SLg, SLh, SLs, S13 and Gy. Two processes on
one IP cannot bind the same port.

Options, in order of preference:

1. **One IP per user-plane function** using Docker macvlan/ipvlan networks, so
   `upf`, `sgw-u`, `pgw-u`, `ggsn-u` each get a distinct address on the lab
   VLAN.
2. **One VM per function group** (5GC / EPC-C / EPC-U).
3. Host port remapping — works for control planes over TCP, but **not** for
   GTP-U or SCTP peers that expect the standard port on the far side.

For Phase 1 (5GC only) one IP is sufficient. Plan the addressing now.

### 9.2 Ports to reserve

Free today and recommended for the new NFs:

| NF | Host port |
|---|---|
| AUSF | 8005/tcp |
| UDR (if split) | 8006/tcp |
| NSSF | 8008/tcp |
| CHF | 8009/tcp |
| SMSF | 8010/tcp |
| EIR | 8011/tcp |
| SMSC | 8012/tcp |
| E-SMLC (HTTP) | 8083/tcp |
| AMF N2 | 38412/sctp |
| MME S1-MME | 36412/sctp |
| MME SGs | 29118/sctp |
| IMS Gm/Mw | 5060 tcp+udp |

All GTP-U and Diameter instances need dedicated IPs per §9.1.

---

## 10. Sequencing and indicative effort

Assumes two engineers fluent in Python and 3GPP, reusing open-source ASN.1 and
datapath components where sensible. ASN.1 work is the main schedule risk.

| Phase | Scope | Effort |
|---|---|---|
| P0 | Deployable lab, CI, port parameterisation | 1 week |
| P1a | AMF NGAP + NAS + AUSF + attach | 10-14 weeks |
| P1b | UPF datapath + SMF N4 + PDU session | 6-10 weeks |
| P1c | LMF/GMLC real positioning | 4-6 weeks |
| P1d | SBI security, CHF/NSSF (optional) | 3-5 weeks |
| **Phase 1 total** | | **24-36 engineer-weeks (~3-4.5 months with 2 engineers)** |
| Phase 1B | MME, SGW, PGW/GGSN, SGSN, MSC, E-SMLC | 28-40 engineer-weeks |
| Phase 2 | EIR, SMS, IMS | 24-36 engineer-weeks |

Buying rather than building the UPF datapath and the E-SMLC removes roughly
8-12 weeks from Phase 1 and 6-10 weeks from Phase 1B.

---

## 11. Decisions required from the operator

1. **UPF datapath**: build eBPF/XDP in-house, or integrate an existing open-source
   datapath under the custom PFCP control plane?
2. **E-SMLC**: licence a commercial E-SMLC (required for EPS location), or keep
   location 5G-only until Phase 1B?
3. **Addressing**: are multiple IPs available on the lab VLAN for user-plane and
   Diameter functions (see §9.1)?
4. **Lawful intercept**: required by UCC for this licence class? Not in scope
   above; if required, add an X1/X2/X3 work package.
5. **RAN interface**: which gNB (vendor or srsRAN/UERANSIM) will terminate N2/N3
   in the lab? This determines the first NGAP conformance target.
6. **Roaming**: is inbound/outbound roaming in the first two years? If yes, SEPP
   and N32 move into Phase 1.

---

## Appendix A — files and directories to create

```
ausf/           Nausf_UEAuthentication (WP1.3)
udr/            Nudr data repository, if split from UDM (WP1.4)
nssf/           Nnssf_NSSelection (WP1.12)
chf/            Nchf_ConvergedCharging (WP1.11)
amf/src/ngap/   ASN.1 codec + procedure handlers (WP1.1)
amf/src/nas/    5GMM/5GSM + security (WP1.2)
lmf/src/nrppa/  NRPPa client (WP1.9)
lmf/src/lpp/    LPP positioning (WP1.9)
gmlc/src/nl1/   Namf_Location client (WP1.10)
sgw/  pgw/  sgsn/  ggsn/  msc/  esmlc/     Phase 1B
eir/  smsc/  smsf/  ims/                    Phase 2
```

Every new service needs: `docker/<name>/Dockerfile`, compose block with
healthcheck, `.env.example` entries, an entry in the port register comment, and
contract checks in `scripts/check_stack.py`.

---

## Appendix B — what can be tested in Docker today

Before any of the above lands, these are real and worth running on the lab VM:

| Test | Command | Expected |
|---|---|---|
| NRF discovery | `curl localhost:8000/nnrf-nfm/v1/nf-instances` | AMF, LMF, UDM, PCF, SMF, HSS registered |
| UDM SDM | `curl localhost:8007/nudm-sdm/v2/641020000000001/am-data` | Subscription JSON |
| UDM auth | `POST /nudm-ueau/v1/{supi}/security-information/generate-auth-data` | 5G SE AV with Kseaf |
| SUCI | `POST /nudm-ueid/v1/deconceal` with a Profile A SUCI | `imsi-...` |
| GMLC chain | `POST localhost:8082/lcs/location-request` | `failed / NO_LCS_SOURCE` |
| AMF→LMF | `POST localhost:8001/namf-loc/v1/{supi}/provide-loc-info` | `501 NO_POSITIONING_SOURCE` |
| MME SLg | `POST localhost:8075/slg/plr` | result code `5012` |
| Diameter peer | CER to `127.0.0.1:3875` | CEA with SLg app-id |
| STP | M3UA connection to 2905 | ASP up |

This proves the service layer and the failure semantics. It does **not** prove
attach, user-plane forwarding, or positioning.
