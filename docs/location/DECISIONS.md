# Location work - architecture decisions

Date: 2026-11-21. Status: in force unless a later entry says otherwise.
Each decision records the choice, why, and what it rules out.

---

## D1. The GMLC is a separate Java/Spring service

**Decision.** The GMLC lives in `github.com/ssonkokevin/gmlc`. This repository
keeps the MME LCS function, the E-SMLC and the LMF - the parts whose work is
ASN.1, timers and radio measurements, not SS7.

**Why.** The GMLC's hard work is MAP (ATI, PSI, SRILCS, PSL, SLR) and Diameter
(SLh, SLg, Sh). A working Java/Spring SS7 stack already exists in the SMSC
gateway, so the GMLC reuses the same patterns instead of re-implementing
TCAP/MAP in Python. The split also matches the interface: GMLC to MME/AMF over
SLg/SBI is standard, so the language boundary is also a protocol boundary.

**Rules out.** A Python GMLC in this repository; a shared library across the
two languages; a private bridge protocol.

**Cost accepted.** Two build systems, two test suites, two release processes.

---

## D2. The core keeps its existing shape

**Decision.** Python 3.11-compatible code, one directory per function,
`<fn>/src/<fn>_server.py`, `<fn>/config/`, a Dockerfile in `docker/<fn>/`,
environment configuration. New modules follow the same pattern:

```
mme/         LTE MME, LCS function (SLg server, SLs client, NAS + S1AP relay)
esmlc/       E-SMLC: LCS-AP, LPP, LPPa, method selector, positioning engine
lmf/         5G LMF: Nlmf_Location, LPP, NRPPa (later phase)
lib/codecs/  ASN.1/BER code and generated codecs shared by the services
lib/positioning/  estimators, uncertainty shapes, assistance data provider
tools/sim/   simulated UE, eNB, gNB, HLR/HSS, MME, E-SMLC, truth model
tests/       pytest suites
```

**Why.** A second web framework or architecture style in the same repository
would double the operational surface for no gain. The existing services talk to
MariaDB with `mysql-connector` and raw SQL; the new ones do the same.

---

## D3. One positioning library for E-SMLC and LMF

**Decision.** `lib/positioning` holds the estimators, the method ladder and the
shape/uncertainty builders. The E-SMLC and LMF differ only in transport,
configuration and session bookkeeping.

**Why.** The geometry does not change between LTE and NR. Duplicating it
guarantees the two engines drift and disagree about the same subscriber.

**Rule.** Estimators take measurements and return a result object. They never
touch I/O, clocks or the database, so they can be tested against synthetic
truth.

---

## D4. ASN.1 comes from the specs, generated, checked in

**Decision.** LCS-AP (TS 29.171), LPP (TS 37.355), LPPa (TS 36.455), NRPPa
(TS 38.455), S1AP (TS 36.413) and NGAP (TS 38.413) modules are extracted from
the spec annexes and compiled with `asn1tools` into Python. Generated modules
are committed; a script regenerates them and the header records the input spec
version and tool version.

**Why.** Hand-built encodings are how the existing MAP stub ended up returning
invented tags (see `INSPECTION.md` 3.1). Protocol code that cannot round-trip
against its own spec is not protocol code.

**Rules out.** Hand-written PER/UPER bit twiddling, except for vendor checks
where the field is vendor-defined and documented as such.

**Where a spec omits an ASN.1 module** (TS 29.002 is textual with ASN.1
annex), the module is still taken verbatim from the annex; no paraphrasing.

---

## D4a. The ASN.1 compiler is pycrate, because asn1tools cannot read CLASS

**Decision.** The modules in D4 are compiled with `pycrate-asn1c`, not
`asn1tools`. `lib/codecs/build_lcsap.py` extracts the annex from the delivered
docx (rejoining the formatted runs), compiles it, and writes both
`asn1/lcsap.asn` and the generated `lcsap_codec.py`. A test regenerates the
module and fails when the committed copy is stale.

**Why.** Every 3GPP PDU module uses information object classes
(`LCS-AP-PDU ::= CHOICE` over `LCS-AP-ELEMENTARY-PROCEDURE.&InitiatingMessage`)
and parameterised open types. `asn1tools` refuses `CLASS`; pycrate resolves it.
Trying asn1tools first is recorded here so nobody repeats the attempt.

**Evidence that the generated codec is conformant.** A plain SEQUENCE encoded
by pycrate and by asn1tools is byte-identical under aligned PER, and LCS-AP
messages round-trip through the generated module in `tests/test_lcsap_codec.py`.

**Repairs.** The docx has two formatting artefacts; the builder lists them and
a compile failure is raised, never swallowed. No protocol type is altered.

**S1AP and LPP take the same route.** `build_s1ap.py` extracts the seven
TS 36.413 modules and `build_lpp.py` the two TS 37.355 modules from their
published docx deliveries, each with a documented repair list (both are
empty). The plain-text renderings those specifications also came in are
lossy, so they are not a source: S1AP's merges identifiers with their types
and drops type references. Regenerating from the committed `.asn` is a test
in every codec, LCS-AP included.

---

## D5. Transport abstraction: SCTP in production, TCP carrier in the lab

**Decision.** Every SIGTRAN-facing component talks through a small transport
interface with two implementations: SCTP (Linux containers) and a length-framed
TCP carrier (Windows development host). The application payload is identical;
only the framing differs.

**Why.** Windows has no `AF_SCTP`, and the dev host has no Docker, so without a
carrier nothing can be tested here. The carrier is a test tool, not a
standards claim.

**Labelling.** Any test or report that used the carrier says so. SCTP is
"implemented, unverified" until it runs on Linux against osmo-stp.

---

## D6. The MME is built as an LCS-function stack first

**Decision.** `mme/` implements the LCS function for real: SLg server (PLR,
PLA, LRR, LRA), SLs client (LCS-AP), NAS transport relay for LPP, S1AP LPPa
transport relay, paging when the UE is idle, and a cell-ID answer when no
E-SMLC can be reached.

It does **not** yet implement EMM attach, S6a authentication, S11 or bearer
management. UE contexts come from either a simulated eNB over the lab carrier
or a lab seeding endpoint. This is stated in the service README and in every
report until the attach path exists.

**Why.** A full MME is a multi-quarter stack. The location product only needs
the LCS function plus enough UE context to address a session. Building EMM
first would delay the only thing the product sells. The SLg/SLs/NAS/S1AP
interfaces are built to the spec so an EMM layer can sit under them later
without rework.

**Rules out.** Claiming "MME" in a customer-facing document until attach works.

---

## D7. E-SMLC transport and port

**Decision.** SLs is an SCTP server on port **9082**, one listener supporting
several MME peers; sessions are keyed by the MME's LCS-AP session identity
plus the UE's identity. LCS-AP is TS 29.171 ASN.1 (PER, aligned).

**Why.** 9082 is the registered SLs port. Multi-MME from the start avoids a
rewrite when the second MME appears.

**Deferred.** Location Abort and Reset are implemented; Connectionless
Information is accepted and logged but carries no session state in Phase 2.

---

## D8. Cell database ownership

**Decision.** The **GMLC owns** the authoritative cell database: coordinates,
antenna height, azimuth, beamwidth, radius or polygon, data quality, validity
dates. The E-SMLC and LMF hold only the positioning subset they need (identity,
coordinates, PCI/ARFCN, PRS/TRP configuration), loaded from the **same CSV
import format** in Phase 2 and synchronised from the GMLC REST API later.

**Why.** Two authoritative stores will disagree, and the disagreement will be
discovered by a regulator. One owner, one import format, one validation report.

**Consequence.** A cell unknown to the E-SMLC is not invented: the session
falls back to the GMLC for conversion, and if the GMLC cannot resolve it either
the result is a failure with a clear reason, not a made-up coordinate.

---

## D9. No SMLC; 2G/3G are cell-ID only

**Decision.** UMTS and GSM return cell-ID from the cell database. The adapter
point for a future SMLC/SAS exists behind a disabled-by-default capability
flag.

**Why.** The SMLC path needs BSS-side support and older specs; the operator's
2G/3G posture is a separate open question. Cell-ID is honest and shippable.

---

## D10. The result envelope is non-negotiable

Every position delivered by either engine, and every position the GMLC returns
to a client, carries:

| Field | Meaning |
|---|---|
| `method` | `CELL_ID`, `E_CID`, `A_GNSS`, `OTDOA`, `RTT`, `DL_TDOA` |
| `shape` | point, circle, ellipse, polygon, arc - per TS 23.032 |
| `uncertaintyMeters` | radius or semi-axes; never absent for a measured result |
| `confidence` | 0-100 |
| `ageSeconds` | now minus the measurement time |
| `accuracyFulfilled` | false when the best available is coarser than requested |
| `methodsAttempted[]` | the ladder actually tried, in order |

**Why.** A coordinate without its uncertainty is a lie with a decimal point.
This is also what makes the fallback defensible: a cell-ID result that says
"±1.2 km, method CELL_ID, accuracy not fulfilled" is useful; a silent 6-decimal
coordinate is not.

**Rules out.** Returning a bare lat/lon anywhere - API, CDR, dashboard, log.
Audit logs carry a result reference, never the coordinates.

---

## D11. `tenant_id` from the first migration

**Decision.** Every new table in both repositories carries `tenant_id BIGINT
NOT NULL DEFAULT 1`, indexed first in composite keys. Every request carries a
tenant resolved from the authenticated client. Hamiltel is tenant 1.

**Why.** Retrofitting tenancy into a schema with production data is a rewrite.
The cost now is one column and one index.

---

## D12. Scope of the first checkpoint

**Decision.** Phases 0-2, then a review before continuing:

- Phase 0: inspection, decisions, layout, capability profile, tenant-aware
  schema, test harness.
- Phase 1: cell-ID end to end. GMLC REST, client auth, consent, CDR, cell
  database with import and dry-run; cell-ID answers for GSM/UMTS/LTE/NR;
  dashboard map and locate.
- Phase 2: the 4G E-SMLC path. MME LCS function, SLg/SLs, LPP A-GNSS to a
  simulated UE, LPPa to a simulated eNB, cell-ID fallback at every failure
  point, 10,000-request soak without session leaks.

**Why.** Cell-ID is the only tier that can be demonstrated end to end today.
A-GNSS over LPP needs only the UE and the MME relay - not LPPa on the eNB - so
it is the first measured method. OTDOA and NR positioning wait for RAN
evidence that does not exist.

**Deferred to Phase 3+:** LMF and the 5G path, NRPPa, OTDOA, deferred/periodic
reporting, area events, SUPL/SLP, MLP northbound.

---

## D13. Testing shape

**Decision.** `pytest` from the repository root. Three tiers:

1. **Unit** - codecs round-trip against spec-derived fixtures; estimators
   against a truth model with injected noise, including degenerate geometry.
2. **Contract** - each interface against a simulator (TCP carrier for SIGTRAN).
3. **End-to-end** - one path per RAT, from a REST request through simulated
   network elements to a result that states its method.

No test requires Docker, MariaDB or SCTP to run on this host. Database tests
are marked and skip with a clear message when no MariaDB is reachable.
Estimator and codec tests must never be skipped.

**Why.** A test suite that only runs on a build server nobody has is decoration.

---

## D14. Archive, not delete

**Decision.** Superseded material moves to `archive/` with a note. The old
Python GMLC stub is at `archive/python-gmlc-stub/` and is not deployed.

**Why.** The stub documents the API shape a vendor demo used; it is useful as
context and useless as a product. Keeping it out of the active tree preserves
that without anyone mistaking it for the gateway.

---

## D15. Identity helpers are provisional until TS 23.003 is in hand

**Decision.** ECGI/NCGI/CGI parsing and formatting are implemented from the
field definitions in TS 36.413 and TS 38.413 (PLMN + 28-bit ECI; PLMN + 36-bit
NCI) with unit tests for bit packing. The helpers are marked `PROVISIONAL` in
their docstring and re-verified against TS 23.003 before Phase 2 exit.

**Why.** TS 23.003 is missing from the local spec set, and cell identity is the
one thing every cell-ID result depends on.

---

## D16. Time, coordinates, identity formats

**Decision.**

- Timestamps: UTC, ISO-8601 with milliseconds, `Z` suffix.
- Coordinates: WGS-84 decimal degrees, at least 7 decimals in storage, no
  rounding before uncertainty is computed.
- Distances: metres, ellipsoidal approximation with the local mean Earth radius;
  no projection-specific code until a real need appears.
- Subscriber identity: IMSI for the core side, MSISDN accepted at the GMLC and
  resolved before signalling; no MSISDN travels on SLg/SLs.
- MSISDN and IMSI validation is strict (length, MCC/MNC prefix from the tenant
  profile), to make enumeration attacks expensive.

**Why.** Mixed time bases and coordinate rounding are the two most common
sources of "the location is 300 m off and nobody knows why".
