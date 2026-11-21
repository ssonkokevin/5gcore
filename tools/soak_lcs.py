"""The Phase 2 soak: N location dialogues over SLs with no session left open.

    python tools/soak_lcs.py                       # 10,000 requests, 8 at a time
    python tools/soak_lcs.py --target lpp          # with a two-round LPP dialogue
    python tools/soak_lcs.py --target lpp --capability-exchange

The lab E-SMLC simulator and the MME location service run in this process over
the D5 TCP carrier. Every position is synthetic (lab PLMN 001-01), because no
E-SMLC, cell site or UE is reachable from this host.

The contract is PLAN 2h: every request answers with a method, an uncertainty
and a source, no request is left waiting, and no SLs association is still open
when the run ends. The MME keeps no session table of its own; an association
is the only per-request state, so zero open associations is the check.

--target lpp uses the two-round target and the lab UE from
esmlc/src/lpp_ue.py, which answers real TS 37.355 messages over HTTP;
--target cell uses a cell-only target with no LPP. --capability-exchange
opens every dialogue with a RequestCapabilities transaction, as a real
location server would.

Exit status is 0 only when all of that holds; the report is printed either way.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "mme" / "src", ROOT / "esmlc" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.codecs import lcsap  # noqa: E402

import cell_plan  # noqa: E402
import esmlc_sim  # noqa: E402
import ue_contexts  # noqa: E402
from location_service import LocationService  # noqa: E402
from lpp_ue import LabUe, UeEndpoint  # noqa: E402

SOAK_IMSI = "001010000000003"
SOAK_CELL = 0x00A1B2E
LPP_IMSI = "001010000000002"
LPP_CELL = 0x00A1B2D
LPP_ROUNDS = 2


def wait_for_idle(sim, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if sim.server.stats()["active_connections"] == 0:
            return True
        time.sleep(0.02)
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=10000)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--accuracy-m", type=float, default=600.0,
                        help="requested horizontal accuracy; 0 sends none")
    parser.add_argument("--drain-seconds", type=float, default=10.0)
    parser.add_argument("--target", choices=("cell", "lpp"), default="cell",
                        help="cell: no LPP; lpp: the two-round LPP target")
    parser.add_argument("--capability-exchange", action="store_true",
                        help="open each dialogue with RequestCapabilities")
    args = parser.parse_args(argv)
    if args.requests <= 0 or args.concurrency <= 0:
        parser.error("--requests and --concurrency must be positive")
    if args.capability_exchange and args.target != "lpp":
        parser.error("--capability-exchange needs --target lpp")

    plan = cell_plan.CellPlan.from_file(cell_plan.DEFAULT_CONFIG)
    table = esmlc_sim.PositionTable.from_file(esmlc_sim.DEFAULT_CONFIG)
    sim = esmlc_sim.EsmlcSimulator(table, host="127.0.0.1", port=0,
                                   lpp_timeout=3.0,
                                   capability_exchange=args.capability_exchange)
    sim.start()
    ue = None
    if args.target == "lpp":
        ue = UeEndpoint(LabUe()).start()
        imsi, cell, rounds = LPP_IMSI, LPP_CELL, LPP_ROUNDS
        store = ue_contexts.UeContextStore([
            ue_contexts.UeContext(imsi, lcsap.LAB_PLMN, cell, nas_url=ue.url),
        ])
    else:
        imsi, cell, rounds = SOAK_IMSI, SOAK_CELL, 0
        store = ue_contexts.UeContextStore([
            ue_contexts.UeContext(imsi, lcsap.LAB_PLMN, cell),
        ])
    service = LocationService(store, plan, esmlc_host="127.0.0.1",
                              esmlc_port=sim.port, timeout=5.0)
    accuracy = args.accuracy_m if args.accuracy_m > 0 else None

    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            outcomes = list(pool.map(
                lambda _: service.locate(imsi, accuracy),
                range(args.requests)))
        elapsed = time.monotonic() - started
        drained = wait_for_idle(sim, args.drain_seconds)
        stats = sim.status()
    finally:
        if ue is not None:
            ue.stop()
        sim.stop()

    capabilities = args.requests if args.capability_exchange else 0
    sources = Counter(o.source for o in outcomes)
    failures = [o for o in outcomes if not o.positioned]
    unlabelled = [o for o in outcomes
                  if o.positioned and (not o.method or o.radius_m is None
                                       or not o.source)]
    fell_back = [o for o in outcomes if o.source == "CELL_PLAN"]
    mismatched = [o for o in outcomes
                  if o.source == "SLS" and o.age_seconds != 0]

    ok = (not failures and not unlabelled and not mismatched and drained
          and stats["active_connections"] == 0
          and stats["connections"] == args.requests
          and stats["requests"] == args.requests
          and stats["positioned"] == args.requests
          and stats["lpp_capabilities"] == capabilities
          and stats["lpp_rounds"] == args.requests * rounds
          and stats["lpp_rejected"] == 0)

    print(f"target             {args.target}, {rounds} LPP round(s) per request, "
          f"capabilities {'on' if args.capability_exchange else 'off'}")
    print(f"requests           {args.requests} at concurrency {args.concurrency}")
    print(f"elapsed            {elapsed:.2f}s ({args.requests / elapsed:.0f}/s)")
    print(f"positioned         {len(outcomes) - len(failures)}")
    print(f"sources            {dict(sources)}")
    print(f"fell back          {len(fell_back)}")
    print(f"failures           {len(failures)}")
    print(f"without metadata   {len(unlabelled)}")
    print(f"stale SLS age      {len(mismatched)}")
    print(f"SLs connections    {stats['connections']} opened, "
          f"{stats['active_connections']} open at the end "
          f"(drained: {drained})")
    print(f"simulator          requests={stats['requests']} "
          f"positioned={stats['positioned']} unreadable={stats['unreadable']} "
          f"handler_errors={stats['handler_errors']}")
    print(f"LPP dialogue       capabilities={stats['lpp_capabilities']} "
          f"rounds={stats['lpp_rounds']} rejected={stats['lpp_rejected']}")
    print(f"UE contexts left   {len(store)}")
    print("result             " + ("PASS" if ok else "FAIL"))
    for outcome in failures[:5]:
        print(f"  failure: {outcome.result_code} {outcome.detail}")
    for outcome in fell_back[:5]:
        print(f"  fallback: {outcome.detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
