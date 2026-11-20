# Location work - phase plan

The plan is staged by what the network can actually measure, not by protocol
count. Every phase must compile, pass its tests, and be committed on its own.

## Checkpoint

Phases 0-2, then a review. Phase 3 and later are outlined but not scheduled.

| Phase | Scope | Exit criteria |
|---|---|---|
| **0** | Inspection, decisions, layout, capability profile, tenant-aware schema, test harness | `pytest` runs; schema test passes; docs accepted |
| **1** | Cell-ID end to end: GMLC REST + governance, cell database, MAP ATI/PSI, SLh RIR, SLg PLR with cell info, dashboard | A REST request returns a cell-ID position with method, uncertainty and age for all four RATs; 200 req/s on the cell-ID path with rate limiting |
| **2** | 4G E-SMLC path: MME LCS function, SLs/LCS-AP, LPP A-GNSS to a simulated UE, LPPa to a simulated eNB, fallback at every failure | End-to-end MT-LR from REST to a simulated UE through a simulated MME; 10,000-request soak with no session leak and no fake accuracy |
| 3 | LMF and the 5G path: `Nlmf_Location`, AMF LCS function, LPP over NAS, NRPPa E-CID | End-to-end MT-LR on 5G SA against simulated gNB/UE |
| 4 | Deferred, periodic and area-event reporting (LRR/LRA, `Ngmlc_Location_EventNotify`), dashboard timeline | Event reporting with interval x amount limits enforced |
| 5 | OTDOA and NR positioning, only if RAN evidence exists (PRS on eNBs, NRPPa on gNBs) | A measured, verified improvement over E-CID on the real RAN |
| 6 | Hardening: load, soak, retention, regulatory evidence pack | Signed-off acceptance report |

## Phase 0 - what is delivered now

1. `docs/location/INSPECTION.md` - the honest state of the core.
2. `docs/location/DECISIONS.md` - D1-D16, in force.
3. `docs/location/capability-profile.schema.json` and
   `capability-profile.tenant-1.json` - what tenant 1 can claim.
4. `database/location/001_location_schema.sql` - cells, sessions, UE
   capability cache, results; `tenant_id` everywhere.
5. `tests/` - pytest configuration and a schema-conformance test that needs no
   database.
6. The old gateway stub archived out of the active tree.

Not in Phase 0: any new service process. The existing services are untouched.

## Phase 1 breakdown

| Work package | Contents |
|---|---|
| 1a | GMLC skeleton in `gmlc` repo: Spring Boot, Flyway, health, capabilities endpoint, container build |
| 1b | Le REST (`/v1/locations`, `/v1/cells`, `/v1/cdrs`, `/v1/consents`, `/v1/health`, `/v1/capabilities`), API-key auth, quotas, idempotency, audit |
| 1c | Consent store and privacy enforcement, emergency override path |
| 1d | Cell database: CGI/ECGI/NCGI helpers, CSV import with dry-run report, wedge/circle conversion, data-quality score |
| 1e | CDR writer and the result envelope |
| 1f | MAP client: ATI, PSI, SRILCS/PSL, SLR; conformant Python HLR/MSC peers for the lab |
| 1g | Diameter client: SLh RIR/RIA, SLg PLR/PLA with cell info; lab HSS/MME peers |
| 1h | Request state machine and RAT router; unknown RAT falls back to cell-ID with `accuracyFulfilled=false` |
| 1i | Dashboard: map, locate form, result panel showing the uncertainty, request log |

## Phase 2 breakdown

| Work package | Contents |
|---|---|
| 2a | LCS-AP codec from TS 29.171; SLs server; LCS-AP transaction layer over the transport abstraction |
| 2b | LPP codec from TS 37.355; capability exchange, assistance data, location information, abort |
| 2c | A-GNSS assistance provider (file/replay first) and UE-assisted solver |
| 2d | Method selector and ladder with fallbacks |
| 2e | MME: SLg server, SLs client, NAS relay, S1AP LPPa transport, paging model, cell-ID fallback |
| 2f | Simulators: UE (LPP behaviours incl. no-response/abort), eNB (LPPa), MME, HLR/HSS; truth model with walking/vehicle paths |
| 2g | End-to-end tests per failure mode: unreachable UE, no E-SMLC, LPP unsupported, malformed ASN.1, timeout, handover mid-request |
| 2h | 10,000-request soak; session table empty at the end; pcap export of generated signalling |

## Open questions the checkpoint will need answered

1. **MTN eNBs:** do they support LPPa and PRS, and would they enable them? If
   not, Phase 5 is off and Phase 2 stops at A-GNSS + E-CID.
2. **IPLOOK MME:** does it support SLs and an external E-SMLC? If the pilot MME
   is ours (D6), this becomes a question about the real operator only.
3. **2G/3G posture:** are those networks still carrying traffic worth locating?
4. **Cell data:** who supplies antenna coordinates, azimuths and radii, and in
   what format? Cell-ID accuracy is bounded by this data, not by the software.
