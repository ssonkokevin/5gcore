"""Lab E-SMLC: an SLs listener that answers from a fixed synthetic table.

A real E-SMLC runs positioning (E-CID, OTDOA, GNSS assistance) and speaks
LPP to the UE through the MME. This simulator has no solver: it answers a
Location-Request with the position configured for that IMSI or cell, or with
an unsuccessful response when the table has no entry. It never interpolates,
hashes or otherwise invents a position.

The LPP dialogue is real TS 37.355: the simulator sends a
RequestLocationInformation for a transaction, and the UE must answer with a
ProvideLocationInformation carrying the same transaction number and no
failure cause. Any other answer, or none, fails the dialogue. The UE's
estimate, if it sends one, is not used: the table is the only position
source until the assistance and solver work packages land.

Every configured coordinate is synthetic. The file says so as well.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from corelib import sls  # noqa: E402
from lib.codecs import lcsap, lpp  # noqa: E402

logger = logging.getLogger("esmlc")

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "lab_positions.json"

_METHODS = {
    "cell-id": lcsap.METHOD_CELL_ID,
    "e-cid": lcsap.METHOD_E_CID,
    "otdoa": lcsap.METHOD_OTDOA,
    "u-tdoa": lcsap.METHOD_U_TDOA,
}

@dataclass(frozen=True)
class SimulatedTarget:
    imsi: Optional[bytes]
    imsi_text: Optional[str]
    cell: Optional[int]
    latitude: float
    longitude: float
    radius_m: float
    method: int
    lpp_rounds: int


class PositionTable:
    def __init__(self, targets: List[SimulatedTarget]):
        self.targets = list(targets)

    @classmethod
    def from_dict(cls, document: dict) -> "PositionTable":
        targets = []
        for index, item in enumerate(document.get("positions", [])):
            name = item.get("method", "cell-id")
            if name not in _METHODS:
                raise ValueError(
                    f"position {index}: method {name!r} is not one of "
                    f"{sorted(_METHODS)}")
            imsi_text = item.get("imsi")
            targets.append(SimulatedTarget(
                imsi=lcsap.tbcd(imsi_text) if imsi_text else None,
                imsi_text=imsi_text,
                cell=int(str(item["cell"]), 0) if item.get("cell") else None,
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                radius_m=float(item["radius_m"]),
                method=_METHODS[name],
                lpp_rounds=int(item.get("lpp_rounds", 0)),
            ))
        return cls(targets)

    @classmethod
    def from_file(cls, path) -> "PositionTable":
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(document)

    def lookup(self, imsi: Optional[bytes],
               cell: Optional[int]) -> Optional[SimulatedTarget]:
        """IMSI wins; a cell-only entry serves a UE whose IMSI is unknown."""
        if imsi is not None:
            for target in self.targets:
                if target.imsi == imsi:
                    return target
        if cell is not None:
            for target in self.targets:
                if target.cell == cell:
                    return target
        return None


class EsmlcSimulator:
    def __init__(self, table: PositionTable, host: str = "0.0.0.0",
                 port: int = sls.DEFAULT_SLS_PORT,
                 carrier: str = sls.CARRIER_TCP, lpp_timeout: float = 3.0,
                 name: str = "esmlc-sim"):
        self.table = table
        self.lpp_timeout = lpp_timeout
        self.server = sls.SlsServer(host, port, self.handle, name=name,
                                    carrier=carrier)
        self.counters: Dict[str, int] = {
            "requests": 0,
            "positioned": 0,
            "no_position": 0,
            "aborts": 0,
            "resets": 0,
            "lpp_rounds": 0,
            "lpp_rejected": 0,
            "unreadable": 0,
        }
        self.last: Optional[dict] = None

    @property
    def port(self) -> int:
        return self.server.port

    def start(self) -> None:
        self.server.start()

    def stop(self) -> None:
        self.server.stop()

    def status(self) -> dict:
        return {**self.server.stats(), **self.counters, "last": self.last}

    def handle(self, pdu: bytes, connection: sls.SlsConnection) -> Optional[bytes]:
        try:
            message = lcsap.parse(pdu)
        except lcsap.LcsApError as exc:
            self.counters["unreadable"] += 1
            logger.warning("unreadable LCS-AP PDU (%d octets, %s): %s",
                           len(pdu), pdu[:16].hex(), exc)
            return None
        if message.procedure == lcsap.PROC_RESET:
            if message.kind != lcsap.INITIATING:
                return None
            self.counters["resets"] += 1
            return lcsap.reset_acknowledge()
        if message.procedure == lcsap.PROC_LOCATION_ABORT:
            self.counters["aborts"] += 1
            return None
        if message.procedure == lcsap.PROC_CONNECTIONLESS_INFORMATION:
            return None  # accepted, no session state in Phase 2 (D7)
        if message.procedure == lcsap.PROC_CONNECTION_ORIENTED_INFORMATION:
            return None  # an APDU with no session to attach it to
        if (message.procedure != lcsap.PROC_LOCATION_SERVICE
                or message.kind != lcsap.INITIATING):
            return None
        correlation = lcsap.correlation_id(message)
        if correlation is None:
            return None

        self.counters["requests"] += 1
        cell = _cell_id(message)
        target = self.table.lookup(message.ie("IMSI"), cell)
        if target is None:
            self.counters["no_position"] += 1
            self.last = {"correlation": correlation.hex(), "result": "no-position",
                         "cell": cell}
            return lcsap.location_response(
                correlation, None, cause=("misc", "unspecified"))

        if not self._relay_lpp(correlation, target, connection):
            self.last = {"correlation": correlation.hex(),
                         "result": "lpp-dialogue-failed", "cell": cell}
            return lcsap.location_response(
                correlation, None,
                cause=("protocol", "message-Not-Compatible-With-Receiver-State"))

        area = lcsap.circle(target.latitude, target.longitude, target.radius_m)
        self.counters["positioned"] += 1
        self.last = {
            "correlation": correlation.hex(),
            "result": "positioned",
            "imsi": target.imsi_text,
            "cell": cell,
            "latitude": target.latitude,
            "longitude": target.longitude,
            "radius_m": area.uncertainty_m,
            "method": lcsap.positioning_method(target.method)[0],
        }
        return lcsap.location_response(
            correlation, area,
            fulfilled=_fulfilment(message, area),
            positioning_method=bytes([target.method]))

    def _relay_lpp(self, correlation: bytes, target: SimulatedTarget,
                   connection: sls.SlsConnection) -> bool:
        """Request a position over real LPP, one transaction per round. The
        requested accuracy is the one the table gives, so the dialogue asks
        for exactly what the answer will claim."""
        area = lpp.circle(target.latitude, target.longitude, target.radius_m)
        first_number = correlation[-1]
        for round_no in range(target.lpp_rounds):
            number = (first_number + round_no) & 0xFF
            request = lpp.request_location_information(
                transaction_number=number,
                accuracy_code=area.uncertainty_code,
                end_transaction=round_no == target.lpp_rounds - 1,
                sequence_number=round_no,
            )
            connection.send(lcsap.connection_oriented_information(
                correlation, request))
            self.counters["lpp_rounds"] += 1
            try:
                reply = connection.receive(self.lpp_timeout)
            except (sls.SlsError, OSError):
                # The MME may abort and close while this side is still
                # waiting; that is a failed dialogue, not a server fault.
                return False
            if not reply:
                return False
            try:
                answer = lcsap.parse(reply)
            except lcsap.LcsApError:
                return False
            if (answer.procedure != lcsap.PROC_CONNECTION_ORIENTED_INFORMATION
                    or lcsap.correlation_id(answer) != correlation
                    or lcsap.lpp_apdu(answer) is None):
                return False
            if not self._accept_lpp_answer(lcsap.lpp_apdu(answer), number):
                return False
        return True

    def _accept_lpp_answer(self, apdu: bytes, number: int) -> bool:
        try:
            answer = lpp.parse(apdu)
        except lpp.LppError:
            self.counters["lpp_rejected"] += 1
            return False
        if (answer.kind != lpp.PROVIDE_LOCATION_INFORMATION
                or answer.transaction_id is None
                or answer.transaction_id.initiator != lpp.INITIATOR_TARGET_DEVICE
                or answer.transaction_id.number != number
                or lpp.location_failure(answer) is not None):
            self.counters["lpp_rejected"] += 1
            return False
        return True


def _cell_id(message: lcsap.LcsApMessage) -> Optional[int]:
    ecgi = message.ie("E-CGI")
    if not ecgi:
        return None
    value, bits = ecgi["cell-ID"]
    if bits != 28:
        return None
    return value


def _fulfilment(message: lcsap.LcsApMessage,
                area: lcsap.Circle) -> Optional[str]:
    qos = message.ie("LCS-QoS")
    if not qos:
        return None
    requested = qos.get("horizontal-Accuracy")
    if requested is None:
        return None
    if area.uncertainty_code <= requested:
        return lcsap.ACCURACY_FULFILLED
    return lcsap.ACCURACY_NOT_FULFILLED


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    table = PositionTable.from_file(os.getenv("ESMLC_POSITIONS", str(DEFAULT_CONFIG)))
    sim = EsmlcSimulator(
        table,
        host=os.getenv("ESMLC_BIND_ADDR", "0.0.0.0"),
        port=int(os.getenv("ESMLC_PORT", str(sls.DEFAULT_SLS_PORT))),
        carrier=os.getenv("ESMLC_CARRIER", sls.CARRIER_TCP),
        lpp_timeout=float(os.getenv("ESMLC_LPP_TIMEOUT", "3.0")),
    )
    sim.start()
    logger.info("E-SMLC simulator: %d synthetic targets, carrier %s",
                len(table.targets), sim.server.carrier)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()


if __name__ == "__main__":
    main()
