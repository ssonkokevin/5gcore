"""The MME's SLs client: one LCS-AP location dialogue per target UE.

The client sends Location-Request and waits for Location-Response, but an
E-SMLC may first ask the UE for LPP information. Those requests arrive as
Connection-Oriented-Information; the client hands the APDU to the caller's
NAS transport callback and relays the UE's answer back unchanged. It never
decodes LPP: the TS 37.355 codec is a later work package, and relaying an
opaque APDU is all the MME has to do.

A transaction is synchronous and owned by one SLs association. A caller with
concurrent sessions opens one client (one connection) per session.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from corelib import sls  # noqa: E402
from lib.codecs import lcsap  # noqa: E402

MAX_LPP_ROUNDS = 8

LppTransport = Callable[[bytes], Optional[bytes]]


class LcsApClientError(RuntimeError):
    """The dialogue could not be completed; the message says why."""


@dataclass(frozen=True)
class LocationResult:
    correlation_id: bytes
    circle: Optional[lcsap.Circle]
    cause: Optional[Tuple[str, Any]]
    fulfilled: Optional[str]
    method: Optional[int]
    lpp_rounds: int
    elapsed: float

    @property
    def positioned(self) -> bool:
        return self.circle is not None


class LcsApClient:
    def __init__(self, host: str, port: int = sls.DEFAULT_SLS_PORT,
                 timeout: float = 5.0, carrier: str = sls.CARRIER_TCP,
                 connection: Optional[sls.SlsConnection] = None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.carrier = carrier
        self._connection = connection

    @property
    def connected(self) -> bool:
        return self._connection is not None

    def connect(self) -> "LcsApClient":
        if self._connection is None:
            try:
                self._connection = sls.SlsConnection.connect(
                    self.host, self.port, self.timeout, self.carrier)
            except OSError as exc:
                raise LcsApClientError(
                    f"cannot reach the E-SMLC at {self.host}:{self.port}: {exc}"
                ) from exc
        return self

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "LcsApClient":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    def locate(self, correlation_id: bytes, cell_id: Tuple[int, int], *,
               imsi: Optional[bytes] = None,
               plmn: bytes = lcsap.LAB_PLMN,
               location_type: str = lcsap.LOCATION_TYPE_GEOGRAPHIC,
               client_type: str = lcsap.CLIENT_PLMN_OPERATOR,
               horizontal_accuracy_m: Optional[float] = None,
               positioning_capability: Optional[bytes] = None,
               lpp_transport: Optional[LppTransport] = None,
               timeout: Optional[float] = None) -> LocationResult:
        """Run one Location-Request dialogue to its answer.

        lpp_transport carries an LPP APDU to the UE and returns the UE's
        answer, or None when the UE cannot be reached. Without a transport,
        an E-SMLC LPP request aborts the dialogue instead of being ignored.
        """
        self.connect()
        budget = self.timeout if timeout is None else timeout
        started = time.monotonic()
        deadline = started + budget
        rounds = 0
        request = lcsap.location_request(
            correlation_id, cell_id, imsi=imsi, plmn=plmn,
            location_type=location_type, client_type=client_type,
            horizontal_accuracy_m=horizontal_accuracy_m,
            positioning_capability=positioning_capability,
        )
        try:
            self._connection.send(request)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._abort(correlation_id)
                    raise LcsApClientError(
                        f"no Location-Response from {self.host}:{self.port} "
                        f"within {budget:g}s")
                try:
                    raw = self._connection.receive(remaining)
                except sls.SlsError as exc:
                    self._abort(correlation_id)
                    raise LcsApClientError(
                        f"no usable Location-Response from {self.host}:{self.port} "
                        f"within {budget:g}s: {exc}") from exc
                if not raw:
                    raise LcsApClientError(
                        f"{self.host}:{self.port} closed the SLs association")
                message = self._parse(raw)
                if lcsap.correlation_id(message) != correlation_id:
                    raise LcsApClientError(
                        "the E-SMLC answered a different Correlation-ID")
                if (message.procedure == lcsap.PROC_RESET
                        and message.kind == lcsap.INITIATING):
                    self._connection.send(lcsap.reset_acknowledge())
                    deadline = time.monotonic() + budget
                    continue
                if message.procedure == lcsap.PROC_CONNECTIONLESS_INFORMATION:
                    continue
                if message.procedure == lcsap.PROC_CONNECTION_ORIENTED_INFORMATION:
                    rounds += 1
                    if rounds > MAX_LPP_ROUNDS:
                        self._abort(correlation_id)
                        raise LcsApClientError(
                            f"the E-SMLC sent more than {MAX_LPP_ROUNDS} LPP rounds")
                    self._relay_lpp(correlation_id, message, lpp_transport)
                    deadline = time.monotonic() + budget
                    continue
                if message.procedure == lcsap.PROC_LOCATION_SERVICE:
                    return self._result(message, correlation_id, rounds,
                                        time.monotonic() - started)
                raise LcsApClientError(
                    f"unexpected LCS-AP procedure {message.procedure}")
        except sls.SlsError as exc:
            raise LcsApClientError(str(exc)) from exc

    def reset(self, timeout: Optional[float] = None) -> None:
        self.connect()
        budget = self.timeout if timeout is None else timeout
        try:
            self._connection.send(lcsap.reset_request())
            raw = self._connection.receive(budget)
        except sls.SlsError as exc:
            raise LcsApClientError(str(exc)) from exc
        if not raw:
            raise LcsApClientError("the E-SMLC closed before Reset-Acknowledge")
        message = self._parse(raw)
        if (message.procedure != lcsap.PROC_RESET
                or message.kind != lcsap.SUCCESSFUL):
            raise LcsApClientError(
                "the E-SMLC did not acknowledge the Reset-Request")

    def _relay_lpp(self, correlation_id: bytes, message: lcsap.LcsApMessage,
                   transport: Optional[LppTransport]) -> None:
        apdu = lcsap.lpp_apdu(message)
        if apdu is None:
            self._abort(correlation_id)
            raise LcsApClientError(
                "Connection-Oriented-Information carried no APDU")
        if transport is None:
            self._abort(correlation_id)
            raise LcsApClientError(
                "the E-SMLC asked for LPP but this MME has no NAS transport")
        answer = transport(apdu)
        if answer is not None:
            self._connection.send(
                lcsap.connection_oriented_information(correlation_id, answer))

    def _result(self, message: lcsap.LcsApMessage, correlation_id: bytes,
                rounds: int, elapsed: float) -> LocationResult:
        try:
            circle = lcsap.decode_area(message)
        except lcsap.LcsApError as exc:
            raise LcsApClientError(str(exc)) from exc
        if message.kind == lcsap.SUCCESSFUL and circle is None:
            raise LcsApClientError(
                "the E-SMLC sent a successful Location-Response with no position")
        return LocationResult(
            correlation_id=correlation_id,
            circle=circle,
            cause=message.ie("LCS-Cause"),
            fulfilled=message.ie("Accuracy-Fulfillment-Indicator"),
            method=lcsap.positioning_data(message),
            lpp_rounds=rounds,
            elapsed=elapsed,
        )

    def _abort(self, correlation_id: bytes) -> None:
        """Best effort: a peer that has stopped answering may not read it."""
        try:
            self._connection.send(
                lcsap.location_abort(correlation_id, ("misc", "unspecified")))
        except (sls.SlsError, OSError, AttributeError):
            pass

    @staticmethod
    def _parse(raw: bytes) -> lcsap.LcsApMessage:
        try:
            return lcsap.parse(raw)
        except lcsap.LcsApError as exc:
            raise LcsApClientError(str(exc)) from exc
