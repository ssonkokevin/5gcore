"""A lab eNB: one S1 association that answers E-CID measurement requests.

A real eNB terminates S1AP, holds a UE context per S1 connection and answers
an E-SMLC's LPPa E-CID measurement initiation with its own measurements. This
lab peer does exactly that much and no more:

  * sets up S1 and sends one NAS Attach Request, which is how the MME learns
    the IMSI behind the S1AP identities;
  * answers an E-CID Measurement Initiation with a Measurement Initiation
    Response carrying the serving ECGI, TAC and - when the request asks for
    the cell identity - the position the operator's cell plan has for that
    cell, with the plan's radius as the uncertainty;
  * acknowledges a UE context release and records paging;
  * ignores everything else, counting it.

The position it reports comes from mme/config/lab_cells.json through the same
``CellPlan`` the MME's fallback uses. It is synthetic lab data, not a
measurement of any real signal. The eNB does not do timing advance, AoA,
RSRP or OTDOA; it has no radio.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Dict, Optional

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
           os.path.dirname(os.path.abspath(__file__)), "/app", "/app/src"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from corelib import wire  # noqa: E402
from lib.codecs import lcsap, lppa, s1ap  # noqa: E402

import cell_plan as cell_plan_module  # noqa: E402
from s1_link import S1Client, S1LinkError  # noqa: E402

logger = logging.getLogger("lab-enb")

DEFAULT_IMSI = "001010000000001"
DEFAULT_CELL = 0x00A1B2C
DEFAULT_TAC = b"\x00\xa1"
DEFAULT_ENB_ID = 0xA1B2C
DEFAULT_MEASUREMENT_ID = 1

# TS 23.032 says an uncertainty radius is a 67% confidence radius; the
# reported confidence says so rather than claiming a tighter one.
PLAN_CONFIDENCE = 67


class LabEnbError(RuntimeError):
    """The lab eNB could not set up, attach or answer."""


def coded_position(latitude: float, longitude: float, radius_m: float,
                   confidence: int = PLAN_CONFIDENCE) -> lppa.CellPosition:
    """Encode a plan coordinate as E-UTRANAccessPointPosition does: latitude
    in its own sign plus 23 bits, longitude as a signed 24-bit value, and the
    radius as the TS 23.032 uncertainty code in both axes."""
    if not -90.0 <= latitude <= 90.0:
        raise LabEnbError(f"latitude {latitude} is outside -90..90")
    if not -180.0 <= longitude <= 180.0:
        raise LabEnbError(f"longitude {longitude} is outside -180..180")
    latitude_code = int(round(abs(latitude) * (1 << 23) / 90.0))
    latitude_code = min(latitude_code, (1 << 23) - 1)
    longitude_code = int(round(longitude * (1 << 24) / 360.0))
    longitude_code = max(-(1 << 23), min(longitude_code, (1 << 23) - 1))
    uncertainty = lcsap.uncertainty_code(radius_m)
    return lppa.CellPosition(
        latitude_sign="north" if latitude >= 0 else "south",
        latitude=latitude_code,
        longitude=longitude_code,
        altitude_direction="height",
        altitude=0,
        uncertainty_semi_major=uncertainty,
        uncertainty_semi_minor=uncertainty,
        orientation_of_major_axis=0,
        uncertainty_altitude=0,
        confidence=int(confidence),
    )


class LabEnb:
    """One S1 association and the E-CID answers on it."""

    def __init__(self, host: str, port: int, imsi: str = DEFAULT_IMSI,
                 cell: int = DEFAULT_CELL, *, mcc: str = "001", mnc: str = "01",
                 tac: bytes = DEFAULT_TAC, name: str = "lab-enb",
                 enb_id: int = DEFAULT_ENB_ID,
                 position: Optional[cell_plan_module.PlannedCell] = None,
                 measurement_id: int = DEFAULT_MEASUREMENT_ID,
                 carrier: str = wire.CARRIER_TCP, timeout: float = 5.0,
                 poll: float = 0.5):
        self.imsi = imsi
        self.cell = cell
        self.plmn = lcsap.plmn_identity(mcc, mnc)
        self.tac = bytes(tac)
        self.name = name
        self.enb_id = enb_id
        self.position = position
        self.measurement_id = measurement_id
        self.poll = poll
        self.client = S1Client(host, port, timeout, carrier)
        self.enb_ue_id: Optional[int] = None
        self._associations: Dict[int, int] = {}   # mme id -> enb id
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.counters: Dict[str, int] = {
            "setups": 0,
            "attaches": 0,
            "lppa_requests": 0,
            "lppa_responses": 0,
            "lppa_without_position": 0,
            "lppa_failures": 0,
            "terminations": 0,
            "pages": 0,
            "releases": 0,
            "downlink_nas": 0,
            "error_indication": 0,
            "unreadable": 0,
            "unexpected": 0,
        }

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> "LabEnb":
        self.client.setup(name=self.name, enb_id=self.enb_id, tac=self.tac,
                          plmn=self.plmn)
        self.counters["setups"] += 1
        self.enb_ue_id = self.client.initial_ue(
            self.imsi, (self.cell, 28), plmn=self.plmn, tac=self.tac)
        self.counters["attaches"] += 1
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name=f"{self.name}-s1")
        self._thread.start()
        logger.info("%s attached IMSI %s on cell 0x%07X over %s", self.name,
                    self.imsi, self.cell, self.client.carrier)
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.client.close()

    def __enter__(self) -> "LabEnb":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def status(self) -> dict:
        return {
            "running": self.running,
            "imsi": self.imsi,
            "cell": f"0x{self.cell:07X}",
            "plmn": self.plmn.hex(),
            "tac": self.tac.hex(),
            "enb_ue_id": self.enb_ue_id,
            "mme": None if not self.client.connected
            else f"{self.client.host}:{self.client.port}",
            "mme_name": self.client.mme_name,
            "carrier": self.client.carrier,
            "ues": len(self._associations),
            "counters": dict(self.counters),
        }

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                message = self.client.receive(self.poll)
            except wire.WireError:
                continue                     # idle between messages
            except (S1LinkError, OSError):
                self.counters["unreadable"] += 1
                continue
            if message is None:
                logger.warning("%s: the MME closed the S1 association", self.name)
                break
            try:
                self._handle(message)
            except Exception:
                self.counters["unexpected"] += 1
                logger.exception("%s: failed to handle %s", self.name,
                                 message.name)

    def _handle(self, message: s1ap.S1apMessage) -> None:
        if message.procedure == s1ap.PROC_DOWNLINK_UE_ASSOCIATED_LPPA:
            self._downlink_lppa(message)
        elif message.procedure == s1ap.PROC_DOWNLINK_NON_UE_ASSOCIATED_LPPA:
            self.counters["unexpected"] += 1
        elif message.procedure == s1ap.PROC_DOWNLINK_NAS_TRANSPORT:
            self.counters["downlink_nas"] += 1
        elif message.procedure == s1ap.PROC_PAGING:
            self.counters["pages"] += 1
        elif message.procedure == s1ap.PROC_UE_CONTEXT_RELEASE:
            self._released(message)
        elif message.procedure == s1ap.PROC_ERROR_INDICATION:
            self.counters["error_indication"] += 1
        else:
            self.counters["unexpected"] += 1

    def _downlink_lppa(self, message: s1ap.S1apMessage) -> None:
        mme_ue_id, enb_ue_id = s1ap.ue_ids(message)
        if mme_ue_id is None or enb_ue_id is None:
            self.counters["unexpected"] += 1
            return
        self._associations[mme_ue_id] = enb_ue_id
        routing = s1ap.routing_id(message)
        if routing is None:
            routing = 0
        apdu = s1ap.lppa_pdu(message)
        if apdu is None:
            self.counters["unreadable"] += 1
            return
        try:
            request = lppa.parse(apdu)
        except lppa.LppaError:
            self.counters["unreadable"] += 1
            return
        if (request.procedure == lppa.PROC_E_CID_INITIATION
                and request.kind == lppa.INITIATING):
            self._measurement_initiation(request, mme_ue_id, enb_ue_id, routing)
        elif (request.procedure == lppa.PROC_E_CID_TERMINATION
                and request.kind == lppa.INITIATING):
            self.counters["terminations"] += 1
        else:
            self.counters["unexpected"] += 1

    def _measurement_initiation(self, request: lppa.LppaMessage, mme_ue_id: int,
                                enb_ue_id: int, routing: int) -> None:
        self.counters["lppa_requests"] += 1
        esmlc_id = lppa.esmlc_measurement_id(request)
        if esmlc_id is None:
            self.counters["lppa_failures"] += 1
            self.client.uplink_lppa(
                mme_ue_id, enb_ue_id,
                lppa.error_indication(request.transaction_id,
                                      ("protocol", "semantic-error")), routing)
            return
        try:
            quantities = lppa.measurement_quantities(request)
        except lppa.LppaError:
            self.counters["lppa_failures"] += 1
            self.client.uplink_lppa(
                mme_ue_id, enb_ue_id,
                lppa.measurement_initiation_failure(
                    request.transaction_id, esmlc_id,
                    ("protocol", "semantic-error")), routing)
            return
        result = self._result(wants_position="cell-ID" in quantities)
        answer = lppa.measurement_initiation_response(
            request.transaction_id, esmlc_id, self.measurement_id, result)
        self.counters["lppa_responses"] += 1
        if result.position is None:
            self.counters["lppa_without_position"] += 1
        self.client.uplink_lppa(mme_ue_id, enb_ue_id, answer, routing)

    def _result(self, *, wants_position: bool) -> lppa.MeasurementResult:
        cell = lppa.Ecgi(plmn=self.plmn, cell_id=self.cell)
        if not wants_position or self.position is None:
            return lppa.MeasurementResult(cell=cell, tac=self.tac)
        position = coded_position(self.position.latitude,
                                  self.position.longitude,
                                  float(self.position.radius_m))
        return lppa.MeasurementResult(cell=cell, tac=self.tac,
                                      position=position)

    def _released(self, message: s1ap.S1apMessage) -> None:
        mme_ue_id, enb_ue_id = s1ap.ue_ids(message)
        if mme_ue_id is None or enb_ue_id is None:
            self.counters["unexpected"] += 1
            return
        self._associations.pop(mme_ue_id, None)
        self.client.release_complete(mme_ue_id, enb_ue_id)
        self.counters["releases"] += 1


def load_position(plan_path, plmn: bytes, cell: int
                  ) -> Optional[cell_plan_module.PlannedCell]:
    try:
        plan = cell_plan_module.CellPlan.from_file(plan_path)
    except (OSError, ValueError) as exc:
        logger.warning("cell plan %s not loaded (%s); E-CID results will carry "
                       "no position", plan_path, exc)
        return None
    position = plan.lookup(plmn, cell)
    if position is None:
        logger.warning("cell 0x%07X is not in %s; E-CID results will carry no "
                       "position", cell, plan_path)
    return position


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    mcc = os.getenv("LAB_ENB_MCC", "001")
    mnc = os.getenv("LAB_ENB_MNC", "01")
    cell = int(os.getenv("LAB_ENB_CELL", hex(DEFAULT_CELL)), 0)
    plmn = lcsap.plmn_identity(mcc, mnc)
    plan_path = os.getenv("LAB_ENB_CELL_PLAN",
                          str(cell_plan_module.DEFAULT_CONFIG))
    enb = LabEnb(
        host=os.getenv("MME_S1_ADDR", "127.0.0.1"),
        port=int(os.getenv("MME_S1_PORT", "36412")),
        imsi=os.getenv("LAB_ENB_IMSI", DEFAULT_IMSI),
        cell=cell,
        mcc=mcc,
        mnc=mnc,
        tac=bytes.fromhex(os.getenv("LAB_ENB_TAC", DEFAULT_TAC.hex())),
        name=os.getenv("LAB_ENB_NAME", "lab-enb"),
        enb_id=int(os.getenv("LAB_ENB_ID", hex(DEFAULT_ENB_ID)), 0),
        position=load_position(plan_path, plmn, cell),
        carrier=os.getenv("LAB_ENB_CARRIER", wire.CARRIER_TCP),
    )
    try:
        enb.start()
    except (S1LinkError, OSError) as exc:
        logger.error("lab eNB could not start: %s", exc)
        raise SystemExit(2)
    logger.info("lab eNB running as %s", enb.name)
    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        enb.stop()


if __name__ == "__main__":
    main()
