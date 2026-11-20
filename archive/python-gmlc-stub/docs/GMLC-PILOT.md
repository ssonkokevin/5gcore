# PaiCore-aligned GMLC Pilot (Lab Reference)

**Source:** `D:\core dpi\PaiCore\kevin\Documentation\GMLC_Documentation.md` (transcribed from PaiCore recordings; Admin/Install/Overview, release context 6.0.0). Treat as guidance to validate against the exact pinned GMLC release, license, and operator acceptance tests.

## 1. What GMLC provides (from reviewed doc)

- **Function:** Gateway Mobile Location Centre for LBS across GSM/GPRS/EDGE, UMTS/HSPA+, LTE/EPC and (indirect) 5G; first external LCS access node in a PLMN.
- **Planes:** Control-plane location via SS7 MAP and Diameter to HLR/HSS, MSC/VLR, SGSN, MME with SMLC/SAS or E-SMLC and RAN positioning; user-plane SUPL/SLP (SET↔SLP over IP/TLS, ULP/SUPL messages) as described (some SUPL positioning noted as in development in that version).
- **Runtime/deps:** Java (JDK 11) + SCTP, JAIN SLEE (SBB/RAs), deployable on WildFly **24.0.1.Final** (per doc), MongoDB for MT-LR/EPC-MT-LR correlation and callback/token data, optional GUI/CLI management.
- **Northbound APIs:** HTTP/JSON REST (e.g. `/restcomm/gmlc/rest`, token-based) and OMA MLP v3.4 XML (`/restcomm/gmlc/mlp`) for immediate/triggered/reporting services (SLIR/SLIA, TLRR/TLRA/TLREP, SLREP/SLRA).
- **Signaling:** SIGTRAN M3UA/SCTP, SCCP/TCAP/MAP (ATI/PSI/SRI/SRISM/SRILCS/PSL/SLR); Diameter SLh RIR/RIA, SLg/ELP PLR/PLA/LRR/LRA, Sh UDR/UDA (CS/PS/EPS/5GS info, RAT/active flags).

## 2. Integration boundaries in this stack

- **STP (SS7/SIGTRAN):** route M3UA/SCCP traffic for MAP-based LCS flows; keep STP routing distinct from application logic. Use jSS7 only behind a narrow adapter if needed (see template §40); do not treat jSS7 as an operator-ready STP.
- **DRA (Diameter):** separate Diameter routing/peer management for SLh/SLg/Sh; do not bridge M3UA and Diameter except via an explicit, validated interworking application.
- **HSS/UDM/MSC/SGSN/MME:** authoritative subscriber/serving-node and location sources per interface; verify exact 3GPP release/profile and roaming/permission policies.
- **MongoDB:** correlation of `clientReferenceNumber`/`lcsReferenceNumber`/callbacks and JSON-vs-MLP delivery; secure access, backups, and data minimization required.
- **SMSC/SUPL/SMLC/E-SMLC:** SMSC remains messaging lifecycle owner; SUPL and positioning nodes are separate capabilities to validate per deployment.

## 3. Pilot deployment plan (lab)

1. **Prerequisites:** Linux host/VMs, JDK 11, SCTP kernel support, WildFly 24.0.1.Final (or pinned release), MongoDB (pinned), reachable SIGTRAN peers (STP/MAP simulators or lab HLR/MSC/SGSN) and/or Diameter peers (HSS/MME simulators) as applicable, TLS material for SUPL/HTTPS where used.
2. **Install/config:** deploy GMLC package per vendor install guide; configure SS7 stack (point codes, M3UA ASP/AS, SCCP GT/GTT) and Diameter peers/realms/hosts/apps; set `curltoken`/auth, callback defaults, and MongoDB connection in management config (e.g. `GmlcManagement_gmlcproperties.xml` equivalent for the release).
3. **Network isolation:** run in isolated lab subnet; no production credentials/subscribers; sanitize IMSI/MSISDN/cell IDs in logs/traces.
4. **Smoke tests (JSON):** ATI/PSI/SRILCS-PSL and/or RIR-PLR/UDR against simulators; verify sync/async responses, HTTP callbacks, and MongoDB correlation records.
5. **MLP tests:** SLIR/SLIA (immediate), TLRR/TLRA/TLREP (deferred/triggered, geofence/periodic/motion as supported), SLREP for unsolicited/event reports; confirm XML conformance and delivery mode.
6. **Deferred/event flows:** area events, periodic LDR, UE-available/motion where supported; validate reference-number correlation, reporting intervals/amounts, termination causes, and callback reliability/idempotency.
7. **Operations:** enable CDR/location-event records, metrics/logging, access controls, retention/masking; run negative tests (unknown subscriber, timeout, privacy/authorization, malformed requests).
8. **Exit gate:** documented traces, pass/fail per flow, license review, and no signaling/data-plane impact to unrelated core functions.

## 4. Test checklist (minimum)

| Area | Cases |
|------|-------|
| MAP | ATI (CS/PS, EPS/5GS flags), PSI (SRISM/SRI/psiFirst variants), SRILCS/PSL immediate + deferred, SLR delivery/correlation |
| Diameter | Sh UDR/UDA (domain/active/EPS/5GS/RAT), SLh RIR/RIA, SLg PLR/PLA and LRR/LRA (deferred/motion/periodic as supported) |
| APIs | JSON REST auth/tokens, MLP SLIR/TLRR/SLREP, callback success/failure/retry, MongoDB correlation |
| Security/ops | TLS/authz, data masking, CDR retention, rate/abuse limits, simulator-only subscribers in lab |

## 5. Notes

- SUPL/SLP, E-SMLC/SAS, and 5GC-native LBS integrations are deployment-specific; confirm support in the exact PaiCore release before claiming capability.
- This pilot doc does not replace standards conformance, vendor documentation, or regulatory approval.
