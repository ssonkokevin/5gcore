"""One location request, from an IMSI to an answer the SLg peer can use.

The order of operations mirrors what a real MME does:

  1. find the UE context (the UE must be known to this MME);
  2. make it reachable (page it when idle);
  3. ask the E-SMLC over SLs, relaying any LPP APDU to the UE;
  4. when the E-SMLC cannot produce a position, fall back to Cell-ID
     positioning from the operator's cell plan.

The fallback is labelled as such. Every outcome carries a method, a source,
an uncertainty and, when one was asked for, an accuracy verdict; there is no
code path that returns a position without saying how it was obtained.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Dict, Optional

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
           os.path.dirname(os.path.abspath(__file__)), "/app", "/app/src"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from corelib import diameter as d  # noqa: E402
from corelib import sls  # noqa: E402
from lib.codecs import lcsap  # noqa: E402

from cell_plan import CellPlan  # noqa: E402
from lcsap_client import LcsApClient, LcsApClientError  # noqa: E402
from nas_relay import HttpNasLink  # noqa: E402
from ue_contexts import UeContext, UeContextStore  # noqa: E402

logger = logging.getLogger("mme.location")

SOURCE_SLS = "SLS"
SOURCE_CELL_PLAN = "CELL_PLAN"


@dataclass(frozen=True)
class LocationOutcome:
    positioned: bool
    result_code: int
    detail: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_m: Optional[float] = None
    method: Optional[str] = None
    source: Optional[str] = None
    fulfilled: Optional[bool] = None
    age_seconds: Optional[int] = None
    cell: Optional[int] = None
    plmn: Optional[bytes] = None
    lpp_rounds: int = 0
    reached_by: str = ""

    def as_dict(self) -> dict:
        return {
            "positioned": self.positioned,
            "result_code": self.result_code,
            "detail": self.detail,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "uncertainty_m": self.radius_m,
            "method": self.method,
            "source": self.source,
            "accuracy_fulfilled": self.fulfilled,
            "age_seconds": self.age_seconds,
            "cell": None if self.cell is None else f"0x{self.cell:07X}",
            "plmn": None if self.plmn is None else self.plmn.hex(),
            "lpp_rounds": self.lpp_rounds,
            "reached_by": self.reached_by,
        }


class LocationService:
    def __init__(self, contexts: UeContextStore, plan: CellPlan, *,
                 esmlc_host: str, esmlc_port: int = sls.DEFAULT_SLS_PORT,
                 timeout: float = 5.0, carrier: str = sls.CARRIER_TCP,
                 client_factory: Callable[..., LcsApClient] = LcsApClient):
        self.contexts = contexts
        self.plan = plan
        self.esmlc_host = esmlc_host
        self.esmlc_port = esmlc_port
        self.timeout = timeout
        self.carrier = carrier
        self._client_factory = client_factory
        self._lock = threading.Lock()
        self._correlation = 0
        self.counters: Dict[str, int] = {
            "requests": 0,
            "via_sls": 0,
            "via_cell_plan": 0,
            "unknown_subscriber": 0,
            "unreachable": 0,
            "no_position": 0,
        }
        self.last: Optional[dict] = None

    def stats(self) -> dict:
        with self._lock:
            return {**self.counters, "last": self.last}

    def locate(self, imsi: str, accuracy_m: Optional[float] = None,
               client_type: str = lcsap.CLIENT_PLMN_OPERATOR) -> LocationOutcome:
        with self._lock:
            self.counters["requests"] += 1

        context = self.contexts.get(imsi)
        if context is None:
            self._count("unknown_subscriber")
            return LocationOutcome(
                positioned=False, result_code=d.RESULT_USER_UNKNOWN,
                detail=f"this MME has no context for IMSI {imsi}")

        reachable, reached_by = self.contexts.ensure_reachable(imsi)
        if not reachable:
            self._count("unreachable")
            return LocationOutcome(
                positioned=False, result_code=d.RESULT_UNREACHABLE_USER,
                detail=f"the UE is idle and did not answer the page ({reached_by})",
                cell=context.cell, plmn=context.plmn, reached_by=reached_by)

        correlation = self._next_correlation()
        transport = (HttpNasLink(context.nas_url, context.imsi)
                     if context.nas_url else None)
        failure = ""
        try:
            with self._client_factory(
                    self.esmlc_host, self.esmlc_port, timeout=self.timeout,
                    carrier=self.carrier) as client:
                result = client.locate(
                    correlation, (context.cell, 28),
                    imsi=lcsap.tbcd(imsi), plmn=context.plmn,
                    client_type=client_type,
                    horizontal_accuracy_m=accuracy_m,
                    lpp_transport=transport)
        except (LcsApClientError, OSError) as exc:
            failure = str(exc)
            result = None

        if result is not None and result.positioned and result.circle is not None:
            method = (lcsap.positioning_method(result.method)[0]
                      if result.method is not None else None)
            fulfilled = (None if result.fulfilled is None
                         else result.fulfilled == lcsap.ACCURACY_FULFILLED)
            self._count("via_sls")
            outcome = LocationOutcome(
                positioned=True, result_code=d.RESULT_SUCCESS,
                detail=f"positioned by the E-SMLC ({method or 'method not stated'})",
                latitude=result.circle.latitude,
                longitude=result.circle.longitude,
                radius_m=result.circle.uncertainty_m,
                method=method, source=SOURCE_SLS, fulfilled=fulfilled,
                age_seconds=0, cell=context.cell, plmn=context.plmn,
                lpp_rounds=result.lpp_rounds, reached_by=reached_by)
            self._remember(outcome)
            return outcome

        if result is not None and not result.positioned:
            cause = result.cause
            failure = (f"the E-SMLC refused: {cause[0]}/{cause[1]}"
                       if cause else "the E-SMLC sent no position")

        outcome = self._cell_plan_fallback(context, accuracy_m, reached_by, failure)
        self._remember(outcome)
        return outcome

    def _cell_plan_fallback(self, context: UeContext, accuracy_m: Optional[float],
                            reached_by: str, failure: str) -> LocationOutcome:
        cell = self.plan.lookup(context.plmn, context.cell)
        if cell is None:
            self._count("no_position")
            return LocationOutcome(
                positioned=False, result_code=d.RESULT_POSITIONING_FAILED,
                detail=(f"no E-SMLC position ({failure or 'no answer'}) and serving "
                        f"cell 0x{context.cell:07X} is not in the cell plan"),
                cell=context.cell, plmn=context.plmn, reached_by=reached_by)
        self._count("via_cell_plan")
        fulfilled = (None if accuracy_m is None
                     else float(cell.radius_m) <= float(accuracy_m))
        return LocationOutcome(
            positioned=True, result_code=d.RESULT_SUCCESS,
            detail=(f"Cell-ID fallback from the cell plan: "
                    f"{failure or 'the E-SMLC produced no position'}"),
            latitude=cell.latitude, longitude=cell.longitude,
            radius_m=float(cell.radius_m), method="cell-id",
            source=SOURCE_CELL_PLAN, fulfilled=fulfilled, age_seconds=None,
            cell=context.cell, plmn=context.plmn, reached_by=reached_by)

    def _next_correlation(self) -> bytes:
        with self._lock:
            self._correlation = (self._correlation + 1) & 0xFFFFFFFF
            return self._correlation.to_bytes(4, "big")

    def _count(self, key: str) -> None:
        with self._lock:
            self.counters[key] += 1

    def _remember(self, outcome: LocationOutcome) -> None:
        with self._lock:
            self.last = outcome.as_dict()
        logger.info("location %s", outcome.as_dict())
