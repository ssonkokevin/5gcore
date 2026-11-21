"""LPPa (TS 36.455) message layer for E-CID measurements over S1.

The encoding is generated from the spec annex; see build_lppa.py and
lppa_codec.py. This module builds and reads only the procedures a location
session uses to ask the eNB for E-CID measurements and to carry the answer:

    E-CIDMeasurementInitiationRequest / Response / Failure   procedure 2
    E-CIDMeasurementFailureIndication                        procedure 3
    E-CIDMeasurementReport                                   procedure 4
    E-CIDMeasurementTerminationCommand                       procedure 5
    ErrorIndication                                          procedure 0

Every LPPa PDU carries a transaction identifier (LPPATransactionID, 0..32767)
in its envelope beside the procedure code. That is unlike S1AP, where the
envelope is only procedure code, criticality and value.

Two IEs share the name Measurement-ID: the E-SMLC's (IE id 2) and the eNB's
(IE id 6). Accessors here read them by id so a message that carries both is
never ambiguous. The other procedures in the generated codec (OTDOA,
inter-RAT, WLAN, ...) have no builder: the lab eNB answers E-CID only.

This module is not an LPPa stack. It does not track transactions, retransmit,
or answer a message on its own; those belong to the component that owns the
S1 association.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from lib.codecs import lppa_codec as _codec

# pycrate's PDU object keeps the value it last decoded or encoded, so sharing
# one across threads corrupts both sides. Every use is serialised here.
_CODEC_LOCK = threading.RLock()

PROC_ERROR_INDICATION = 0
PROC_E_CID_INITIATION = 2
PROC_E_CID_FAILURE_INDICATION = 3
PROC_E_CID_REPORT = 4
PROC_E_CID_TERMINATION = 5

IE_CAUSE = 0
IE_CRITICALITY_DIAGNOSTICS = 1
IE_E_SMLC_UE_MEASUREMENT_ID = 2
IE_REPORT_CHARACTERISTICS = 3
IE_MEASUREMENT_PERIODICITY = 4
IE_MEASUREMENT_QUANTITIES = 5
IE_ENB_UE_MEASUREMENT_ID = 6
IE_E_CID_MEASUREMENT_RESULT = 7
IE_MEASUREMENT_QUANTITIES_ITEM = 11
IE_CELL_PORTION_ID = 14

INITIATING = "initiatingMessage"
SUCCESSFUL = "successfulOutcome"
UNSUCCESSFUL = "unsuccessfulOutcome"

CRITICALITY_REJECT = "reject"
CRITICALITY_IGNORE = "ignore"

MAX_TRANSACTION_ID = 32767
MIN_MEASUREMENT_ID = 1
MAX_MEASUREMENT_ID = 15
MAX_CELL_ID_28 = (1 << 28) - 1

REPORT_CHARACTERISTICS = ("onDemand", "periodic")
MEASUREMENT_PERIODICITY = ("ms120", "ms240", "ms480", "ms640", "ms1024",
                           "ms2048", "ms5120", "ms10240", "min1", "min6",
                           "min12", "min30", "min60")
MEASUREMENT_QUANTITIES = ("cell-ID", "angleOfArrival", "timingAdvanceType1",
                          "timingAdvanceType2", "rSRP", "rSRQ")
MEASURED_RESULTS = ("valueAngleOfArrival", "valueTimingAdvanceType1",
                    "valueTimingAdvanceType2", "resultRSRP", "resultRSRQ")
CAUSE_GROUPS = ("radioNetwork", "protocol", "misc")

# MCC 001, MNC 01 in the TS 29.274 8.21.5 order, as in S1AP and LCS-AP.
LAB_PLMN = b"\x00\xf1\x10"


class LppaError(ValueError):
    """The bytes are not an LPPa message this implementation can read."""


@dataclass(frozen=True)
class Ecgi:
    """The E-UTRAN CGI an eNB reports its measurements for, TS 36.455."""

    plmn: bytes
    cell_id: int

    def bit_string(self) -> Tuple[int, int]:
        return (self.cell_id, 28)


@dataclass(frozen=True)
class CellPosition:
    """E-UTRANAccessPointPosition exactly as coded, no unit conversion."""

    latitude_sign: str
    latitude: int
    longitude: int
    altitude_direction: str
    altitude: int
    uncertainty_semi_major: int
    uncertainty_semi_minor: int
    orientation_of_major_axis: int
    uncertainty_altitude: int
    confidence: int


@dataclass(frozen=True)
class MeasurementResult:
    cell: Ecgi
    tac: bytes
    position: Optional[CellPosition] = None
    measured: Tuple[Tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class Ie:
    id: int
    criticality: str
    type_name: str
    value: Any


@dataclass
class LppaMessage:
    kind: str
    procedure: int
    transaction_id: int
    criticality: str
    name: str                     # the PDU type name, e.g. E-CIDMeasurementReport
    ies: List[Ie] = field(default_factory=list)

    def ie(self, type_name: str) -> Optional[Any]:
        for ie in self.ies:
            if ie.type_name == type_name:
                return ie.value
        return None

    def ie_by_id(self, ie_id: int) -> Optional[Any]:
        for ie in self.ies:
            if ie.id == ie_id:
                return ie.value
        return None


def _pdu(kind: str, procedure: int, transaction_id: int, name: str,
         ies: List[Dict[str, Any]],
         criticality: str = CRITICALITY_REJECT) -> bytes:
    _check_transaction(transaction_id)
    obj = _codec.LPPA_PDU_Descriptions.LPPA_PDU
    try:
        with _CODEC_LOCK:
            obj.set_val((kind, {
                "procedureCode": procedure,
                "criticality": criticality,
                "lppatransactionID": transaction_id,
                "value": (name, {"protocolIEs": ies}),
            }))
            return obj.to_aper()
    except Exception as exc:  # pycrate raises its own error types
        raise LppaError(f"{name} could not be encoded: {exc}") from exc


def _ie(ie_id: int, criticality: str, type_name: str, value: Any) -> Dict[str, Any]:
    return {"id": ie_id, "criticality": criticality, "value": (type_name, value)}


def _check_plmn(value: bytes) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 3:
        raise LppaError("a PLMN identity is three octets")
    return bytes(value)


def _check_tac(value: bytes) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 2:
        raise LppaError("a tracking area code is two octets")
    return bytes(value)


def _check_range(value: int, low: int, high: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise LppaError(f"{label} is an integer")
    if not low <= value <= high:
        raise LppaError(f"{label} {value} is outside {low}..{high}")
    return value


def _check_transaction(value: int) -> int:
    return _check_range(value, 0, MAX_TRANSACTION_ID, "a transaction identifier")


def _check_measurement_id(value: int, label: str) -> int:
    return _check_range(value, MIN_MEASUREMENT_ID, MAX_MEASUREMENT_ID, label)


def _check_choice(value: str, allowed: Tuple[str, ...], label: str) -> str:
    if value not in allowed:
        raise LppaError(f"{label} {value!r} is not one of {allowed}")
    return value


def _check_cell(cell: Ecgi) -> Ecgi:
    if not isinstance(cell, Ecgi):
        raise LppaError("a measurement result names an ECGI")
    _check_plmn(cell.plmn)
    _check_range(cell.cell_id, 0, MAX_CELL_ID_28, "a cell identity")
    return cell


def _result_ies(result: MeasurementResult) -> Dict[str, Any]:
    _check_cell(result.cell)
    tac = _check_tac(result.tac)
    encoded: Dict[str, Any] = {
        "servingCell-ID": {
            "pLMN-Identity": result.cell.plmn,
            "eUTRANcellIdentifier": result.cell.bit_string(),
        },
        "servingCellTAC": tac,
    }
    if result.position is not None:
        p = result.position
        encoded["e-UTRANAccessPointPosition"] = {
            "latitudeSign": p.latitude_sign,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "directionOfAltitude": p.altitude_direction,
            "altitude": p.altitude,
            "uncertaintySemi-major": p.uncertainty_semi_major,
            "uncertaintySemi-minor": p.uncertainty_semi_minor,
            "orientationOfMajorAxis": p.orientation_of_major_axis,
            "uncertaintyAltitude": p.uncertainty_altitude,
            "confidence": p.confidence,
        }
    if result.measured:
        measured = []
        for kind, value in result.measured:
            _check_choice(kind, MEASURED_RESULTS, "a measured result")
            measured.append((kind, value))
        encoded["measuredResults"] = measured
    return encoded


def _cause_ie(cause: Tuple[str, str], criticality: str = CRITICALITY_IGNORE
              ) -> Dict[str, Any]:
    group, value = cause
    _check_choice(group, CAUSE_GROUPS, "a cause group")
    return _ie(IE_CAUSE, criticality, "Cause", (group, value))


def measurement_initiation_request(
        transaction_id: int, esmlc_measurement_id: int,
        report_characteristics: str = "onDemand",
        quantities: Tuple[str, ...] = ("cell-ID",),
        periodicity: Optional[str] = None) -> bytes:
    """Ask the eNB for the named E-CID measurements. TS 36.455 makes the
    periodicity conditional on a periodic report and forbids it otherwise."""
    _check_measurement_id(esmlc_measurement_id, "an E-SMLC measurement identity")
    _check_choice(report_characteristics, REPORT_CHARACTERISTICS,
                  "a report characteristic")
    if report_characteristics == "periodic":
        if periodicity is None:
            raise LppaError("a periodic report needs a measurement periodicity")
    elif periodicity is not None:
        raise LppaError("a periodicity is only allowed for a periodic report")
    if not quantities:
        raise LppaError("a measurement request names at least one quantity")
    for quantity in quantities:
        _check_choice(quantity, MEASUREMENT_QUANTITIES, "a measurement quantity")
    ies = [
        _ie(IE_E_SMLC_UE_MEASUREMENT_ID, CRITICALITY_REJECT, "Measurement-ID",
            esmlc_measurement_id),
        _ie(IE_REPORT_CHARACTERISTICS, CRITICALITY_REJECT,
            "ReportCharacteristics", report_characteristics),
    ]
    if periodicity is not None:
        _check_choice(periodicity, MEASUREMENT_PERIODICITY,
                      "a measurement periodicity")
        ies.append(_ie(IE_MEASUREMENT_PERIODICITY, CRITICALITY_REJECT,
                       "MeasurementPeriodicity", periodicity))
    ies.append(_ie(IE_MEASUREMENT_QUANTITIES, CRITICALITY_REJECT,
                   "MeasurementQuantities", [
                       _ie(IE_MEASUREMENT_QUANTITIES_ITEM, CRITICALITY_REJECT,
                           "MeasurementQuantities-Item",
                           {"measurementQuantitiesValue": quantity})
                       for quantity in quantities
                   ]))
    return _pdu(INITIATING, PROC_E_CID_INITIATION, transaction_id,
                "E-CIDMeasurementInitiationRequest", ies)


def measurement_initiation_response(
        transaction_id: int, esmlc_measurement_id: int,
        enb_measurement_id: int,
        result: Optional[MeasurementResult] = None) -> bytes:
    _check_measurement_id(esmlc_measurement_id, "an E-SMLC measurement identity")
    _check_measurement_id(enb_measurement_id, "an eNB measurement identity")
    ies = [
        _ie(IE_E_SMLC_UE_MEASUREMENT_ID, CRITICALITY_REJECT, "Measurement-ID",
            esmlc_measurement_id),
        _ie(IE_ENB_UE_MEASUREMENT_ID, CRITICALITY_REJECT, "Measurement-ID",
            enb_measurement_id),
    ]
    if result is not None:
        ies.append(_ie(IE_E_CID_MEASUREMENT_RESULT, CRITICALITY_IGNORE,
                       "E-CID-MeasurementResult", _result_ies(result)))
    return _pdu(SUCCESSFUL, PROC_E_CID_INITIATION, transaction_id,
                "E-CIDMeasurementInitiationResponse", ies)


def measurement_initiation_failure(
        transaction_id: int, esmlc_measurement_id: int,
        cause: Tuple[str, str]) -> bytes:
    _check_measurement_id(esmlc_measurement_id, "an E-SMLC measurement identity")
    return _pdu(UNSUCCESSFUL, PROC_E_CID_INITIATION, transaction_id,
                "E-CIDMeasurementInitiationFailure", [
                    _ie(IE_E_SMLC_UE_MEASUREMENT_ID, CRITICALITY_REJECT,
                        "Measurement-ID", esmlc_measurement_id),
                    _cause_ie(cause),
                ])


def measurement_failure_indication(
        transaction_id: int, esmlc_measurement_id: int,
        enb_measurement_id: int, cause: Tuple[str, str]) -> bytes:
    _check_measurement_id(esmlc_measurement_id, "an E-SMLC measurement identity")
    _check_measurement_id(enb_measurement_id, "an eNB measurement identity")
    return _pdu(INITIATING, PROC_E_CID_FAILURE_INDICATION, transaction_id,
                "E-CIDMeasurementFailureIndication", [
                    _ie(IE_E_SMLC_UE_MEASUREMENT_ID, CRITICALITY_REJECT,
                        "Measurement-ID", esmlc_measurement_id),
                    _ie(IE_ENB_UE_MEASUREMENT_ID, CRITICALITY_REJECT,
                        "Measurement-ID", enb_measurement_id),
                    _cause_ie(cause),
                ])


def measurement_report(transaction_id: int, esmlc_measurement_id: int,
                       enb_measurement_id: int,
                       result: MeasurementResult) -> bytes:
    _check_measurement_id(esmlc_measurement_id, "an E-SMLC measurement identity")
    _check_measurement_id(enb_measurement_id, "an eNB measurement identity")
    return _pdu(INITIATING, PROC_E_CID_REPORT, transaction_id,
                "E-CIDMeasurementReport", [
                    _ie(IE_E_SMLC_UE_MEASUREMENT_ID, CRITICALITY_REJECT,
                        "Measurement-ID", esmlc_measurement_id),
                    _ie(IE_ENB_UE_MEASUREMENT_ID, CRITICALITY_REJECT,
                        "Measurement-ID", enb_measurement_id),
                    _ie(IE_E_CID_MEASUREMENT_RESULT, CRITICALITY_IGNORE,
                        "E-CID-MeasurementResult", _result_ies(result)),
                ])


def measurement_termination_command(transaction_id: int,
                                    esmlc_measurement_id: int,
                                    enb_measurement_id: int) -> bytes:
    _check_measurement_id(esmlc_measurement_id, "an E-SMLC measurement identity")
    _check_measurement_id(enb_measurement_id, "an eNB measurement identity")
    return _pdu(INITIATING, PROC_E_CID_TERMINATION, transaction_id,
                "E-CIDMeasurementTerminationCommand", [
                    _ie(IE_E_SMLC_UE_MEASUREMENT_ID, CRITICALITY_REJECT,
                        "Measurement-ID", esmlc_measurement_id),
                    _ie(IE_ENB_UE_MEASUREMENT_ID, CRITICALITY_REJECT,
                        "Measurement-ID", enb_measurement_id),
                ])


def error_indication(transaction_id: int,
                     cause: Optional[Tuple[str, str]] = None) -> bytes:
    ies = [] if cause is None else [_cause_ie(cause)]
    return _pdu(INITIATING, PROC_ERROR_INDICATION, transaction_id,
                "ErrorIndication", ies)


def parse(data: bytes) -> LppaMessage:
    obj = _codec.LPPA_PDU_Descriptions.LPPA_PDU
    try:
        with _CODEC_LOCK:
            obj.from_aper(bytes(data))
            kind, body = obj.get_val()
    except Exception as exc:
        raise LppaError(f"not an LPPa PDU: {exc}") from exc
    value = body["value"]
    if not (isinstance(value, tuple) and len(value) == 2
            and isinstance(value[1], dict)):
        # An elementary procedure outside the generated object set decodes
        # with its open type left as raw octets. Refuse it by number rather
        # than invent a message name for it.
        raise LppaError(
            f"procedure {body['procedureCode']} is not a message this "
            "codec knows")
    name, message = value
    ies = []
    for ie in message.get("protocolIEs", []):
        type_name, ie_value = ie["value"]
        ies.append(Ie(id=ie["id"], criticality=ie["criticality"],
                      type_name=type_name, value=ie_value))
    return LppaMessage(kind=kind, procedure=body["procedureCode"],
                       transaction_id=body["lppatransactionID"],
                       criticality=body["criticality"], name=name, ies=ies)


def esmlc_measurement_id(message: LppaMessage) -> Optional[int]:
    return message.ie_by_id(IE_E_SMLC_UE_MEASUREMENT_ID)


def enb_measurement_id(message: LppaMessage) -> Optional[int]:
    return message.ie_by_id(IE_ENB_UE_MEASUREMENT_ID)


def measurement_quantities(message: LppaMessage) -> List[str]:
    """The quantities of an initiation request, in the order they appear."""
    items = message.ie("MeasurementQuantities")
    if items is None:
        return []
    out = []
    for item in items:
        type_name, value = item["value"]
        if type_name != "MeasurementQuantities-Item":
            raise LppaError(f"a measurement quantity is {type_name}, not an "
                            "item")
        out.append(value["measurementQuantitiesValue"])
    return out


def measurement_result(message: LppaMessage) -> Optional[MeasurementResult]:
    ie = message.ie("E-CID-MeasurementResult")
    if ie is None:
        return None
    cell = ie["servingCell-ID"]
    plmn = bytes(cell["pLMN-Identity"])
    value, bits = cell["eUTRANcellIdentifier"]
    if bits != 28:
        raise LppaError(f"an ECGI cell identity is 28 bits, not {bits}")
    _check_range(value, 0, MAX_CELL_ID_28, "a cell identity")
    position = None
    raw_position = ie.get("e-UTRANAccessPointPosition")
    if raw_position is not None:
        position = CellPosition(
            latitude_sign=raw_position["latitudeSign"],
            latitude=raw_position["latitude"],
            longitude=raw_position["longitude"],
            altitude_direction=raw_position["directionOfAltitude"],
            altitude=raw_position["altitude"],
            uncertainty_semi_major=raw_position["uncertaintySemi-major"],
            uncertainty_semi_minor=raw_position["uncertaintySemi-minor"],
            orientation_of_major_axis=raw_position["orientationOfMajorAxis"],
            uncertainty_altitude=raw_position["uncertaintyAltitude"],
            confidence=raw_position["confidence"],
        )
    measured = tuple((kind, value) for kind, value in
                     ie.get("measuredResults", []))
    return MeasurementResult(cell=Ecgi(plmn=plmn, cell_id=value),
                             tac=bytes(ie["servingCellTAC"]),
                             position=position, measured=measured)


def measured_value(message: LppaMessage, kind: str) -> Optional[Any]:
    """The first value of one measured-result kind, or None. Kinds are the
    MeasuredResultsValue choice names, e.g. valueTimingAdvanceType1."""
    result = measurement_result(message)
    if result is None:
        return None
    for measured_kind, value in result.measured:
        if measured_kind == kind:
            return value
    return None


def cause(message: LppaMessage) -> Optional[Tuple[str, str]]:
    return message.ie("Cause")
