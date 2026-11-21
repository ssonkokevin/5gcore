"""LCS-AP (TS 29.171) message layer for the MME and the E-SMLC.

The encoding itself is generated from the spec annex; see build_lcsap.py and
lcsap_codec.py. This module only builds and reads the handful of messages the
location function uses, so callers never touch pycrate open-type tuples:

    Location-Request                  MME -> E-SMLC, procedure 0
    Location-Response                 E-SMLC -> MME, procedures 0 and 3
    Location-Abort-Request            MME -> E-SMLC, procedure 3
    Connection-Oriented-Information   LPP APDU relay, procedure 1
    Reset-Request / Reset-Acknowledge procedure 4

A position crossing this interface is a TS 23.032 shape with its uncertainty.
The circle helpers here are the only shape the lab uses; any other shape is
reported as a decode error rather than flattened to a bare point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from lib.codecs import lcsap_codec as _codec

PROC_LOCATION_SERVICE = 0
PROC_CONNECTION_ORIENTED_INFORMATION = 1
PROC_CONNECTIONLESS_INFORMATION = 2
PROC_LOCATION_ABORT = 3
PROC_RESET = 4
PROC_CIPHERING_KEY_DATA = 5

IE_ACCURACY_FULFILLMENT = 0
IE_APDU = 1
IE_CORRELATION_ID = 2
IE_E_UTRAN_CELL_ID = 4
IE_IMSI = 7
IE_LCS_CLIENT_TYPE = 8
IE_LCS_PRIORITY = 9
IE_LCS_QOS = 10
IE_LCS_CAUSE = 11
IE_LOCATION_ESTIMATE = 12
IE_LOCATION_TYPE = 13
IE_PAYLOAD_TYPE = 15
IE_POSITIONING_DATA = 16
IE_UE_POSITIONING_CAPABILITY = 20

INITIATING = "initiatingMessage"
SUCCESSFUL = "successfulOutcome"
UNSUCCESSFUL = "unsuccessfulOutcome"

CRITICALITY_REJECT = "reject"
CRITICALITY_IGNORE = "ignore"

LOCATION_TYPE_GEOGRAPHIC = "geographic-Information"
LOCATION_TYPE_ASSISTANCE = "assistance-Information"
LOCATION_TYPE_LAST_KNOWN = "last-known-location"

CLIENT_EMERGENCY = "emergency-Services"
CLIENT_VALUE_ADDED = "value-Added-Services"
CLIENT_PLMN_OPERATOR = "pLMN-Operator-Services"
CLIENT_LAWFUL_INTERCEPT = "lawful-Intercept-Services"

ACCURACY_FULFILLED = "requested-accuracy-fulfilled"
ACCURACY_NOT_FULFILLED = "requested-accuracy-not-fulfilled"

PAYLOAD_LPP = "lPP"
PAYLOAD_LPPA = "lPPa"

LAB_PLMN = b"\x00\xf1\x10"   # MCC 001, MNC 01 (F filler), TS 24.008 TBCD


class LcsApError(ValueError):
    """The bytes are not an LCS-AP message this implementation can read."""


@dataclass(frozen=True)
class Circle:
    """A TS 23.032 shape 1 payload: ellipsoid point with uncertainty circle."""

    latitude: float
    longitude: float
    uncertainty_code: int
    uncertainty_m: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise LcsApError(f"latitude {self.latitude} is outside -90..90")
        if not -180.0 <= self.longitude <= 180.0:
            raise LcsApError(f"longitude {self.longitude} is outside -180..180")
        if not 0 <= self.uncertainty_code <= 127:
            raise LcsApError("uncertainty code must be 0..127")


@dataclass
class LcsApMessage:
    kind: str                       # initiatingMessage / successfulOutcome / ...
    procedure: int
    criticality: str
    name: str                       # the PDU type name, e.g. Location-Request
    ies: List[Tuple[str, Any]] = field(default_factory=list)

    def ie(self, type_name: str) -> Optional[Any]:
        for name, value in self.ies:
            if name == type_name:
                return value
        return None


def uncertainty_metres(code: int) -> float:
    """TS 23.032: radius = 10 * (1.1^K - 1) metres at 67% confidence."""
    if not 0 <= code <= 127:
        raise LcsApError("uncertainty code must be 0..127")
    return 10.0 * (1.1 ** code - 1.0)


def uncertainty_code(metres: float) -> int:
    if metres <= 0:
        raise LcsApError("an uncertainty radius must be positive")
    code = math.ceil(math.log(metres / 10.0 + 1.0, 1.1))
    if code > 127:
        raise LcsApError(f"{metres} m does not fit an uncertainty code")
    return code


def circle(latitude: float, longitude: float, radius_m: float) -> Circle:
    code = uncertainty_code(radius_m)
    return Circle(latitude, longitude, code, uncertainty_metres(code))


def location_request(correlation_id: bytes, cell_id: Tuple[int, int],
                     imsi: Optional[bytes] = None,
                     plmn: bytes = LAB_PLMN,
                     location_type: str = LOCATION_TYPE_GEOGRAPHIC,
                     client_type: str = CLIENT_PLMN_OPERATOR,
                     horizontal_accuracy_m: Optional[float] = None,
                     positioning_capability: Optional[bytes] = None) -> bytes:
    """cell_id is (bit value, bit length), the 28-bit E-UTRAN cell identity."""
    _check_correlation(correlation_id)
    _check_plmn(plmn)
    ies = [
        _ie(IE_CORRELATION_ID, CRITICALITY_REJECT, "Correlation-ID", correlation_id),
        _ie(IE_LOCATION_TYPE, CRITICALITY_REJECT, "Location-Type", location_type),
        _ie(IE_E_UTRAN_CELL_ID, CRITICALITY_IGNORE, "E-CGI", {
            "pLMNidentity": bytes(plmn),
            "cell-ID": cell_id,
        }),
        _ie(IE_LCS_CLIENT_TYPE, CRITICALITY_REJECT, "LCS-Client-Type", client_type),
    ]
    if imsi is not None:
        ies.append(_ie(IE_IMSI, CRITICALITY_IGNORE, "IMSI", imsi))
    if horizontal_accuracy_m is not None:
        ies.append(_ie(IE_LCS_QOS, CRITICALITY_REJECT, "LCS-QoS", {
            "horizontal-Accuracy": uncertainty_code(horizontal_accuracy_m),
        }))
    if positioning_capability is not None:
        ies.append(_ie(IE_UE_POSITIONING_CAPABILITY, CRITICALITY_REJECT,
                       "UE-Positioning-Capability", positioning_capability))
    return _pdu(INITIATING, PROC_LOCATION_SERVICE, "Location-Request", ies)


def location_response(correlation_id: bytes, area: Optional[Circle],
                      fulfilled: Optional[str] = None,
                      positioning_method: Optional[bytes] = None,
                      cause: Optional[Tuple[str, Any]] = None) -> bytes:
    """A response without an area is a failure response and must carry a
    cause, so an empty answer can never be read as a position."""
    _check_correlation(correlation_id)
    ies = [_ie(IE_CORRELATION_ID, CRITICALITY_REJECT, "Correlation-ID", correlation_id)]
    if area is not None:
        ies.append(_ie(IE_LOCATION_ESTIMATE, CRITICALITY_REJECT,
                       "Geographical-Area", _area_choice(area)))
    if positioning_method is not None:
        if len(positioning_method) != 1:
            raise LcsApError("a positioning method is one octet")
        ies.append(_ie(IE_POSITIONING_DATA, CRITICALITY_REJECT, "Positioning-Data", {
            "positioning-Data-Set": [bytes(positioning_method)],
        }))
    if fulfilled is not None:
        ies.append(_ie(IE_ACCURACY_FULFILLMENT, CRITICALITY_REJECT,
                       "Accuracy-Fulfillment-Indicator", fulfilled))
    if area is None and cause is None:
        cause = ("misc", "unspecified")
    if cause is not None:
        kind, value = cause
        ies.append(_ie(IE_LCS_CAUSE, CRITICALITY_IGNORE, "LCS-Cause", (kind, value)))
    return _pdu(SUCCESSFUL if area is not None else UNSUCCESSFUL,
                PROC_LOCATION_SERVICE, "Location-Response", ies)


def connection_oriented_information(correlation_id: bytes, apdu: bytes,
                                    payload_type: str = PAYLOAD_LPP) -> bytes:
    _check_correlation(correlation_id)
    ies = [
        _ie(IE_CORRELATION_ID, CRITICALITY_REJECT, "Correlation-ID", correlation_id),
        _ie(IE_PAYLOAD_TYPE, CRITICALITY_REJECT, "Payload-Type", payload_type),
        _ie(IE_APDU, CRITICALITY_REJECT, "APDU", apdu),
    ]
    return _pdu(INITIATING, PROC_CONNECTION_ORIENTED_INFORMATION,
                "Connection-Oriented-Information", ies)


def location_abort(correlation_id: bytes, cause: Tuple[str, Any]) -> bytes:
    _check_correlation(correlation_id)
    kind, value = cause
    ies = [
        _ie(IE_CORRELATION_ID, CRITICALITY_REJECT, "Correlation-ID", correlation_id),
        _ie(IE_LCS_CAUSE, CRITICALITY_IGNORE, "LCS-Cause", (kind, value)),
    ]
    return _pdu(INITIATING, PROC_LOCATION_ABORT, "Location-Abort-Request", ies)


def reset_request() -> bytes:
    return _pdu(INITIATING, PROC_RESET, "Reset-Request", [])


def reset_acknowledge() -> bytes:
    return _pdu(SUCCESSFUL, PROC_RESET, "Reset-Acknowledge", [])


def parse(data: bytes) -> LcsApMessage:
    obj = _codec.LCS_AP_PDU_Descriptions.LCS_AP_PDU
    try:
        obj.from_aper(bytes(data))
        kind, body = obj.get_val()
    except Exception as exc:
        raise LcsApError(f"not an LCS-AP PDU: {exc}") from exc
    name, message = body["value"]
    ies = []
    for ie in message.get("protocolIEs", []):
        type_name, value = ie["value"]
        ies.append((type_name, value))
    return LcsApMessage(kind=kind, procedure=body["procedureCode"],
                        criticality=body["criticality"], name=name, ies=ies)


def decode_area(message: LcsApMessage) -> Optional[Circle]:
    """The estimate as a circle, or None when the response carries none.
    Any other shape is an error: the MME does not invent a centre."""
    area = message.ie("Geographical-Area")
    if area is None:
        return None
    if not (isinstance(area, tuple) and len(area) == 2
            and area[0] == "point-With-Uncertainty"):
        raise LcsApError(
            "the E-SMLC returned a shape other than point-with-uncertainty; "
            "the MME does not flatten shapes"
        )
    shape = area[1]
    coords = shape["geographical-Coordinates"]
    latitude = coords["degreesLatitude"] * 90.0 / (1 << 23)
    if coords["latitudeSign"] == "south":
        latitude = -latitude
    longitude = coords["degreesLongitude"] * 360.0 / (1 << 24)
    code = shape["uncertainty-Code"]
    return Circle(latitude, longitude, code, uncertainty_metres(code))


def tbcd(digits: str) -> bytes:
    """TS 23.003 semi-octets, low nibble first, 0xF filler when odd."""
    if not digits.isdigit():
        raise LcsApError("TBCD takes decimal digits only")
    padded = digits if len(digits) % 2 == 0 else digits + "F"
    out = bytearray()
    for i in range(0, len(padded), 2):
        out.append(int(padded[i + 1], 16) << 4 | int(padded[i], 16))
    return bytes(out)


def correlation_id(message: LcsApMessage) -> Optional[bytes]:
    return message.ie("Correlation-ID")


def lpp_apdu(message: LcsApMessage) -> Optional[bytes]:
    return message.ie("APDU")


def _pdu(kind: str, procedure: int, name: str, ies: List[Dict[str, Any]],
         criticality: str = CRITICALITY_REJECT) -> bytes:
    obj = _codec.LCS_AP_PDU_Descriptions.LCS_AP_PDU
    obj.set_val((kind, {
        "procedureCode": procedure,
        "criticality": criticality,
        "value": (name, {"protocolIEs": ies}),
    }))
    try:
        return obj.to_aper()
    except Exception as exc:  # pycrate raises its own error types
        raise LcsApError(f"{name} could not be encoded: {exc}") from exc


def _ie(ie_id: int, criticality: str, type_name: str, value: Any) -> Dict[str, Any]:
    return {"id": ie_id, "criticality": criticality, "value": (type_name, value)}


def _area_choice(area: Circle) -> Dict[str, Any]:
    latitude = int(round(abs(area.latitude) * (1 << 23) / 90.0))
    longitude = int(round(area.longitude * (1 << 24) / 360.0))
    return ("point-With-Uncertainty", {
        "geographical-Coordinates": {
            "latitudeSign": "north" if area.latitude >= 0 else "south",
            "degreesLatitude": latitude,
            "degreesLongitude": longitude,
        },
        "uncertainty-Code": area.uncertainty_code,
    })


def _check_correlation(value: bytes) -> None:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 4:
        raise LcsApError("a Correlation-ID is exactly four octets")


def _check_plmn(value: bytes) -> None:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 3:
        raise LcsApError("a PLMN identity is three octets")
