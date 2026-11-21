"""The MME's SLs client: one LCS-AP location dialogue per target UE.

The client sends Location-Request and waits for Location-Response, but an
E-SMLC may first ask for measurements. Those requests arrive as
Connection-Oriented-Information and the Payload-Type IE says which interface
they belong to: lPP goes to the UE over NAS, lPPa goes to the eNB over S1AP.
The client hands the APDU to the matching transport and relays the answer
back unchanged, under the same payload type. It never decodes LPP or LPPa;
relaying an opaque APDU is all the MME has to do (the codecs are used by the
UE and the eNB, not here).

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
    lppa_rounds: int = 0

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
               lppa_transport: Optional[LppTransport] = None,
               timeout: Optional[float] = None) -> LocationResult:
        """Run one Location-Request dialogue to its answer.

        lpp_transport carries an LPP APDU to the UE over NAS; lppa_transport
        carries an LPPa APDU to the eNB over S1AP. Each returns the peer's
        answer, or None when the peer cannot be reached. Without the matching
        transport, a request for that payload aborts the dialogue instead of
        being ignored.
        """
        self.connect()
        budget = self.timeout if timeout is None else timeout
        started = time.monotonic()
        deadline = started + budget
        rounds = 0
        lpp_rounds = 0
        lppa_rounds = 0
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
                            f"the E-SMLC sent more than {MAX_LPP_ROUNDS} "
                            "measurement rounds")
                    payload = self._relay_apdu(
                        correlation_id, message, lpp_transport, lppa_transport)
                    if payload == lcsap.PAYLOAD_LPPA:
                        lppa_rounds += 1
                    else:
                        lpp_rounds += 1
                    deadline = time.monotonic() + budget
                    continue
                if message.procedure == lcsap.PROC_LOCATION_SERVICE:
                    return self._result(message, correlation_id, lpp_rounds,
                                        elapsed=time.monotonic() - started,
                                        lppa_rounds=lppa_rounds)
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

    def _relay_apdu(self, correlation_id: bytes, message: lcsap.LcsApMessage,
                    lpp_transport: Optional[LppTransport],
                    lppa_transport: Optional[LppTransport]) -> str:
        """Relay one APDU and return the payload type it was carried under.
        The transport argument None means this MME has no path to that peer,
        which ends the dialogue rather than dropping the E-SMLC's request."""
        apdu = lcsap.lpp_apdu(message)
        if apdu is None:
            self._abort(correlation_id)
            raise LcsApClientError(
                "Connection-Oriented-Information carried no APDU")
        payload = lcsap.payload_type(message)
        if payload is None:
            self._abort(correlation_id)
            raise LcsApClientError(
                "Connection-Oriented-Information carried no Payload-Type")
        if payload == lcsap.PAYLOAD_LPPA:
            transport, label = lppa_transport, "LPPa and this MME has no S1 association"
        elif payload == lcsap.PAYLOAD_LPP:
            transport, label = lpp_transport, "LPP and this MME has no NAS transport"
        else:
            self._abort(correlation_id)
            raise LcsApClientError(
                f"the E-SMLC sent payload type {payload!r}, which this MME "
                "cannot route")
        if transport is None:
            self._abort(correlation_id)
            raise LcsApClientError(
                f"the E-SMLC asked for {label}")
        try:
            answer = transport(apdu)
        except (RuntimeError, OSError) as exc:
            # A relay that cannot reach its peer (e.g. the eNB closed S1) ends
            # the dialogue; leaving the E-SMLC waiting would just burn its timer.
            self._abort(correlation_id)
            raise LcsApClientError(f"relaying {payload} failed: {exc}") from exc
        if answer is not None:
            self._connection.send(lcsap.connection_oriented_information(
                correlation_id, answer, payload_type=payload))
        return payload

    def _result(self, message: lcsap.LcsApMessage, correlation_id: bytes,
                rounds: int, elapsed: float, lppa_rounds: int = 0) -> LocationResult:
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
            lppa_rounds=lppa_rounds,
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
