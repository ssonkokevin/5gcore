# Phase 2 checkpoint - the 4G E-SMLC path

Date: 2026-11-21. Status: 2a, 2b and the MME half of 2e delivered; 2c, 2d,
2f, the S1AP half of 2e and the pcap export are open. This note is the
evidence for PLAN 2g/2h and the honest list of what a Phase 2 request can and
cannot do today.

Everything here runs on the Windows development host over the D5 TCP carrier,
with in-process simulators. No SCTP association, Docker, MariaDB or radio has
been exercised. Coordinates are synthetic for lab PLMN 001-01.

## What is implemented

| Piece | Where | State |
|---|---|---|
| LCS-AP codec (TS 29.171) | `lib/codecs/lcsap.py`, generated from the annex | 2a done |
| LPP codec (TS 37.355) | `lib/codecs/lpp.py`, generated from the annex | 2b done; broadcast module compiled, not used yet |
| SLs listener/client, reset and abort | `corelib/sls.py`, `mme/src/lcsap_client.py` | 2a done over TCP; SCTP unverified |
| Lab E-SMLC | `esmlc/src/esmlc_sim.py` | sends real LPP and validates the answer; answers from a fixed table; no positioning engine |
| MME SLg server | `mme/src/mme_server.py` | PLR/PLA, RIR/RIA; LRR/LRA refused with 5012 (Phase 4) |
| MME UE contexts and paging | `mme/src/ue_contexts.py` | connected, idle+answers, idle+ignores; lab seeding endpoint |
| LPP NAS relay | `mme/src/lcsap_client.py`, `nas_relay.py` | MME relays opaquely; the E-SMLC and lab UE speak TS 37.355 |
| Cell-ID fallback | `mme/src/location_service.py`, `cell_plan.py` | labelled `CELL_PLAN`, age unknown, no invented age |
| S1AP / LPPa transport | - | not built; `eNB` signalling is absent |

Every outcome carries `method`, `source`, `uncertainty_m`, `accuracy_fulfilled`
(when an accuracy was asked for) and `age_seconds` (when the source knows it).
A fallback never borrows the E-SMLC's confidence: it is `method=cell-id`,
`source=CELL_PLAN`, `age=null`, and fulfilled only when the cell radius is
inside the requested accuracy.

## 2g failure matrix

Each row is exercised by `tests/test_mme_failure_modes.py`, except where the
row says the existing `tests/test_mme_location.py` covers it.

| Failure | MME behaviour | SLg result | Test |
|---|---|---|---|
| Unknown IMSI | no context, no signalling | 5001 | `test_an_unknown_subscriber_gets_5001`, `test_plr_for_an_unknown_subscriber_is_5001` |
| UE idle, ignores the page | stays idle, no invented reachability | 4221 | `test_a_ue_that_ignores_the_page_gets_4221` |
| UE idle, answers the page | moved to connected, request proceeds | 2001 | `test_paging_makes_an_idle_ue_reachable` |
| No E-SMLC reachable | cell plan, source labelled | 2001 + `CELL_PLAN` | `test_an_unreachable_esmlc_falls_back_to_the_plan` |
| No E-SMLC and no cell-plan row | refuses instead of guessing | 4225 | `test_an_unreachable_esmlc_without_a_plan_row_gets_4225` |
| E-SMLC accepts but never answers | dialogue times out, Location-Abort sent, cell plan used | 2001 + `CELL_PLAN` | `test_a_silent_esmlc_times_out_and_the_mme_aborts_the_dialogue` |
| E-SMLC answers a different Correlation-ID | answer refused, cell plan used | 2001 + `CELL_PLAN` | `test_an_answer_for_a_different_correlation_is_refused` |
| Malformed LCS-AP (ASN.1) answer | parse failure, cell plan used | 2001 + `CELL_PLAN` | `test_a_malformed_lcs_ap_answer_falls_back_and_is_not_read_as_a_position` |
| E-SMLC refuses with a cause | cause kept in the detail, cell plan used | 2001 + `CELL_PLAN` | `test_a_refused_dialogue_keeps_the_cause_in_the_detail` |
| UE cannot answer LPP | E-SMLC refuses, cell plan used | 2001 + `CELL_PLAN` | `test_a_ue_that_cannot_answer_lpp_makes_the_esmlc_refuse`, `test_a_ue_without_a_nas_endpoint_cannot_satisfy_lpp` |
| UE answers a different LPP transaction | E-SMLC rejects, cell plan used | 2001 + `CELL_PLAN` | `test_an_answer_for_another_transaction_fails_the_dialogue` |
| UE aborts LPP | dialogue fails, cell plan used | 2001 + `CELL_PLAN` | `test_a_ue_abort_fails_the_dialogue` |
| UE reports a position-method failure | dialogue fails, cell plan used | 2001 + `CELL_PLAN` | `test_a_ue_failure_cause_fails_the_dialogue` |
| More than eight LPP rounds | client aborts the dialogue | 2001 + `CELL_PLAN` | `test_more_than_eight_lpp_rounds_aborts_the_client` |
| UE context removed mid-dialogue | in-flight request finishes on the cell it started with; the next one is 5001 | 2001, then 5001 | `test_a_context_removed_mid_dialogue_does_not_break_the_live_answer` |
| Handover mid-request | not signalled: there is no S1AP path yet, so a handover cannot be observed. The context-change test is the closest honest analogue. | - | - |

Malformed LPP is still not testable at the MME: the MME is an opaque relay,
so it neither accepts nor rejects an LPP APDU on its own. The E-SMLC judges
it now (2b): an answer that is not a ProvideLocationInformation for the same
transaction, or that carries a failure cause or an abort, fails the dialogue
and the MME falls back to the cell plan. Those three cases are in
`tests/test_mme_location.py`.

## 2b LPP codec

TS 37.355 (37355-j30) is compiled from its published docx by
`lib/codecs/build_lpp.py`. Unlike the LCS-AP annex, the LPP annex interleaves
prose with the syntax, so the build collects only the `-- ASN1START` /
`-- ASN1STOP` blocks between a module header and its terminating END block:

| Output | Size |
|---|---|
| `lib/codecs/asn1/lpp.asn` (LPP-PDU-Definitions, LPP-Broadcast-Definitions) | 305,890 bytes |
| `lib/codecs/lpp_codec.py` (pycrate 0.8.1 generator) | 2,096,511 bytes |
| `LPP-PDU-Definitions` types | 881 |

`lib/codecs/lpp.py` is the only surface the location code uses: builders for
RequestCapabilities, ProvideCapabilities, RequestAssistanceData,
ProvideAssistanceData, RequestLocationInformation, ProvideLocationInformation,
Abort and Error; `parse()`; transaction IDs (initiator plus number 0..255);
and an uncertainty-circle encoder/decoder using the same TS 23.032 K code as
LCS-AP. Anything that is not an ellipsoid point with uncertainty circle is
refused rather than flattened. Encode and decode are serialised by one lock
for the same pycrate reason as LCS-AP.

`tests/test_lpp_codec.py` has 17 cases: a round trip for every body, the
accuracy code and response-time rounding, a position in both hemispheres, an
empty answer decoding as "no position", a failure cause, a refusal to flatten
another shape, garbage, argument bounds, and an eight-thread concurrency check.

LPP-Broadcast-Definitions is compiled into the same module file because it
imports from LPP-PDU-Definitions; nothing reads posSIB content yet.

The E-SMLC now uses the codec for the dialogue: each round is a
RequestLocationInformation carrying the table's own uncertainty code, and the
UE's answer must be a ProvideLocationInformation for the same transaction,
from the target device, with no failure cause. The UE's estimate, if it sends
one, is not used: the table remains the only position source until the
assistance and solver work packages land.

## 2h soak

Command:

```
python tools/soak_lcs.py
```

Result on this host (Windows 10.0.26200, Python 3.12.3, TCP carrier,
simulator and service in one process):

```
requests           10000 at concurrency 8
elapsed            22.39s (447/s)
positioned         10000
sources            {'SLS': 10000}
fell back          0
failures           0
without metadata   0
stale SLS age      0
SLs connections    10000 opened, 0 open at the end (drained: True)
simulator          requests=10000 positioned=10000 unreadable=0 handler_errors=0
UE contexts left   1
result             PASS
```

What that proves and what it does not:

- Every request got a method, an uncertainty and a source, and every SLs
  association was closed before the run ended.
- The MME keeps no session table, so "session table empty" is checked as zero
  open associations plus the simulator's own request/position counters. There
  is no database in this path.
- The run is single-process over loopback TCP. It is not a claim about SCTP,
  a separate E-SMLC process, or a real MME's session handling.

The soak found a real defect before it passed: the pycrate LCS-AP PDU object
was shared across threads, so concurrent encodes and decodes corrupted each
other (sporadic `bitlen overflow` and unanswered requests). The codec is now
serialised with one lock (`lib/codecs/lcsap.py`), covered by
`test_the_shared_codec_object_is_not_corrupted_across_threads`.

### With the LPP dialogue (2b)

`python tools/soak_lcs.py --target lpp` uses the two-round target
(001010000000002, cell 0x00A1B2D) and a local HTTP UE that answers each
request with a real TS 37.355 ProvideLocationInformation. The simulator's UE
timer is 3 s here, because every answer crosses an HTTP round trip; at 1 s
this host occasionally expired the timer under eight-way concurrency.

```
target             lpp, 2 LPP round(s) per request
requests           10000 at concurrency 8
elapsed            339.89s (29/s)
positioned         10000
sources            {'SLS': 10000}
fell back          0
failures           0
without metadata   0
stale SLS age      0
SLs connections    10000 opened, 0 open at the end (drained: True)
simulator          requests=10000 positioned=10000 unreadable=0 handler_errors=0
LPP dialogue       rounds=20000 rejected=0
UE contexts left   1
result             PASS
```

Every request spent two LPP rounds and none was rejected, so the codec
survived 20,000 concurrent encodes and decodes with no corrupted transaction.

## No pcap yet, and why

The plan asks for a pcap export of generated signalling. This host can only
capture the D5 TCP carrier, which is a length-framed stand-in for SCTP, not
SLs. Writing those frames into a file labelled as SLs signalling would
misrepresent the transport, and a synthetic SCTP/IP header would be a fake
capture. The export is deferred until the signalling runs over real SCTP on
Linux; `tests/pcaps/` stays unused until then. The soak report above is the
honest substitute: it states exactly what ran and over which carrier.

## Interop with the GMLC

The GMLC's `SlgClient` requires a seven-octet ECGI. The MME originally wrote
the AVP length including RFC 6733 padding, so the gateway read eight octets
and rejected the PLA. Two changes fixed it:

- the MME encoder now excludes padding from the AVP length (RFC 6733 4.1),
  while its decoder still accepts peers that include it;
- the GMLC trims up to three zero padding octets for fixed-width values and
  trailing NULs for text, so an MME that counts padding still yields a cell.

## Still open in Phase 2

| Item | Why it is not done | Consequence |
|---|---|---|
| 2c A-GNSS assistance and solver | the codec exists, but no assistance generator or orbit/clock model is built | E-SMLC can only answer cell/E-CID from its table |
| 2d method ladder | no measurements to rank; the table names the method | no fallback ordering among measured methods |
| 2e S1AP/LPPa relay | no S1AP stack in this MME | no eNB measurements, no handover visibility |
| 2f UE/eNB simulators | the lab UE answers LPP over HTTP; there is no Uu/NAS stack or measurement reporting | the dialogue is real but the UE is a stub |
| pcap export | see above | byte-level evidence waits for Linux SCTP |
| SCTP itself | no `AF_SCTP` on this host | D5 SCTP path is implemented but unverified |

The Phase 2 open questions in PLAN.md (MTN eNB LPPa/PRS, IPLOOK SLs support,
2G/3G traffic, cell data ownership) are still unanswered and gate Phases 3-5,
not this checkpoint.
