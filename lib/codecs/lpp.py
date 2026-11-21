"""LPP (TS 37.355) message layer for the E-SMLC and the lab UE.

The encoding itself is generated from the spec annex; see build_lpp.py and
lpp_codec.py. This module only builds and reads the messages the location
function uses, so callers never touch pycrate open-type tuples:

    RequestCapabilities            location server -> target
    ProvideCapabilities            target -> location server
    RequestAssistanceData          location server -> target
    ProvideAssistanceData          location server -> target
    RequestLocationInformation     location server -> target
    ProvideLocationInformation     target -> location server
    Abort                          either direction
    Error                          either direction

An LPP transaction is identified by an initiator and a number 0..255. A
position is an LPP ``LocationCoordinates`` shape; only the uncertainty circle
is built and read here, and any other shape is reported rather than
flattened to a bare point.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

from lib.codecs import lpp_codec as _codec
from lib.codecs.lcsap import uncertainty_code, uncertainty_metres

# pycrate's PDU object keeps the value it last decoded or encoded, so sharing
# one across threads corrupts both sides. Every use is serialised here.
_CODEC_LOCK = threading.RLock()

INITIATOR_LOCATION_SERVER = "locationServer"
INITIATOR_TARGET_DEVICE = "targetDevice"
_INITIATORS = (INITIATOR_LOCATION_SERVER, INITIATOR_TARGET_DEVICE)

REQUEST_CAPABILITIES = "requestCapabilities"
PROVIDE_CAPABILITIES = "provideCapabilities"
REQUEST_ASSISTANCE_DATA = "requestAssistanceData"
PROVIDE_ASSISTANCE_DATA = "provideAssistanceData"
REQUEST_LOCATION_INFORMATION = "requestLocationInformation"
PROVIDE_LOCATION_INFORMATION = "provideLocationInformation"
ABORT = "abort"
ERROR = "error"

BODIES = (REQUEST_CAPABILITIES, PROVIDE_CAPABILITIES, REQUEST_ASSISTANCE_DATA,
          PROVIDE_ASSISTANCE_DATA, REQUEST_LOCATION_INFORMATION,
          PROVIDE_LOCATION_INFORMATION, ABORT, ERROR)

# The -r9 IE sequence inside each body's criticalExtensions.
_R9 = {name: f"{name}-r9" for name in BODIES if name not in (ERROR,)}

LOCATION_ESTIMATE_REQUIRED = "locationEstimateRequired"
LOCATION_ESTIMATE_PREFERRED = "locationEstimatePreferred"
LOCATION_MEASUREMENTS_REQUIRED = "locationMeasurementsRequired"
LOCATION_MEASUREMENTS_PREFERRED = "locationMeasurementsPreferred"

FAILURE_UNDEFINED = "undefined"
FAILURE_METHOD_NOT_SUPPORTED = "requestedMethodNotSupported"
FAILURE_POSITION_METHOD = "positionMethodFailure"


class LppError(ValueError):
    """The bytes are not an LPP message this implementation can read."""


@dataclass(frozen=True)
class TransactionId:
    initiator: str
    number: int

    def __post_init__(self) -> None:
        if self.initiator not in _INITIATORS:
            raise LppError(f"unknown LPP initiator {self.initiator!r}")
        if not 0 <= self.number <= 255:
            raise LppError("an LPP transaction number is 0..255")


@dataclass(frozen=True)
class Circle:
    """An LPP ellipsoid point with uncertainty circle, K code and metres."""

    latitude: float
    longitude: float
    uncertainty_code: int
    uncertainty_m: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise LppError(f"latitude {self.latitude} is outside -90..90")
        if not -180.0 <= self.longitude <= 180.0:
            raise LppError(f"longitude {self.longitude} is outside -180..180")
        if not 0 <= self.uncertainty_code <= 127:
            raise LppError("uncertainty code must be 0..127")


@dataclass
class LppMessage:
    kind: str
    body: Dict[str, Any]
    transaction_id: Optional[TransactionId]
    end_transaction: bool
    sequence_number: Optional[int]
    acknowledgement: Optional[Dict[str, Any]]


def circle(latitude: float, longitude: float, radius_m: float) -> Circle:
    code = uncertainty_code(radius_m)
    return Circle(latitude, longitude, code, uncertainty_metres(code))


def request_capabilities(ies: Optional[Dict[str, Any]] = None,
                         **options: Any) -> bytes:
    return _message(REQUEST_CAPABILITIES, ies, **options)


def provide_capabilities(ies: Optional[Dict[str, Any]] = None,
                         **options: Any) -> bytes:
    return _message(PROVIDE_CAPABILITIES, ies, **options)


def request_assistance_data(ies: Optional[Dict[str, Any]] = None,
                            **options: Any) -> bytes:
    return _message(REQUEST_ASSISTANCE_DATA, ies, **options)


def provide_assistance_data(ies: Optional[Dict[str, Any]] = None,
                            **options: Any) -> bytes:
    return _message(PROVIDE_ASSISTANCE_DATA, ies, **options)


def request_location_information(
        ies: Optional[Dict[str, Any]] = None,
        *, accuracy_code: Optional[int] = None,
        response_time_seconds: Optional[float] = None,
        location_information_type: str = LOCATION_ESTIMATE_REQUIRED,
        velocity_request: bool = False,
        vertical_coordinate_request: bool = False,
        **options: Any) -> bytes:
    """A request for a position. accuracy_code is the TS 23.032 K code the
    caller wants honoured; response_time_seconds is rounded up to the
    ten-second unit LPP uses by default."""
    if ies is not None and (accuracy_code is not None
                            or response_time_seconds is not None):
        raise LppError("give either the raw IEs or the convenience fields")
    if ies is None:
        common: Dict[str, Any] = {
            "locationInformationType": location_information_type,
        }
        qos: Dict[str, Any] = {
            "verticalCoordinateRequest": bool(vertical_coordinate_request),
            "velocityRequest": bool(velocity_request),
        }
        if accuracy_code is not None:
            if not 0 <= accuracy_code <= 127:
                raise LppError("an accuracy code is 0..127")
            qos["horizontalAccuracy"] = {"accuracy": accuracy_code,
                                         "confidence": 67}
        if response_time_seconds is not None:
            units = max(1, math.ceil(response_time_seconds / 10.0))
            if units > 128:
                raise LppError("a response time is at most 1280 seconds")
            qos["responseTime"] = {"time": units}
        common["qos"] = qos
        ies = {"commonIEsRequestLocationInformation": common}
    return _message(REQUEST_LOCATION_INFORMATION, ies, **options)


def provide_location_information(ies: Optional[Dict[str, Any]] = None,
                                 *, area: Optional[Circle] = None,
                                 failure: Optional[str] = None,
                                 **options: Any) -> bytes:
    """An answer carrying a position, or a failure cause. With neither, the
    message is empty, which a receiver must not read as a position."""
    if ies is not None and (area is not None or failure is not None):
        raise LppError("give either the raw IEs or an area/failure")
    if ies is None:
        common: Dict[str, Any] = {}
        if area is not None:
            common["locationEstimate"] = _area_choice(area)
        if failure is not None:
            common["locationError"] = {"locationfailurecause": failure}
        ies = {"commonIEsProvideLocationInformation": common}
    return _message(PROVIDE_LOCATION_INFORMATION, ies, **options)


def abort(cause: str = FAILURE_UNDEFINED, **options: Any) -> bytes:
    options.setdefault("initiator", INITIATOR_LOCATION_SERVER)
    return _message(ABORT, {"commonIEsAbort": {"abortCause": cause}},
                    **options)


def error(cause: str, **options: Any) -> bytes:
    options.setdefault("initiator", INITIATOR_TARGET_DEVICE)
    return _message(ERROR, {"commonIEsError": {"errorCause": cause}},
                    **options)


def parse(data: bytes) -> LppMessage:
    obj = _codec.LPP_PDU_Definitions.LPP_Message
    try:
        with _CODEC_LOCK:
            obj.from_aper(bytes(data))
            value = obj.get_val()
    except Exception as exc:
        raise LppError(f"not an LPP message: {exc}") from exc
    try:
        body_choice, body = value["lpp-MessageBody"]
    except (KeyError, TypeError) as exc:
        raise LppError("the LPP message carries no body") from exc
    if body_choice != "c1":
        raise LppError("LPP messageClassExtension carries no body in this "
                       "delivery")
    kind, body = body
    if kind not in BODIES:
        raise LppError(f"unexpected LPP body {kind!r}")
    transaction = value.get("transactionID")
    return LppMessage(
        kind=kind,
        body=body,
        transaction_id=(TransactionId(transaction["initiator"],
                                      transaction["transactionNumber"])
                        if transaction else None),
        end_transaction=value["endTransaction"],
        sequence_number=value.get("sequenceNumber"),
        acknowledgement=value.get("acknowledgement"),
    )


def location_estimate(message: LppMessage) -> Optional[Circle]:
    """The position in a ProvideLocationInformation, or None when the message
    carries none. Any shape other than the uncertainty circle is an error:
    the E-SMLC does not invent a centre."""
    ies = _r9_ies(message, PROVIDE_LOCATION_INFORMATION)
    common = ies.get("commonIEsProvideLocationInformation") or {}
    estimate = common.get("locationEstimate")
    if estimate is None:
        return None
    if not (isinstance(estimate, tuple) and len(estimate) == 2
            and estimate[0] == "ellipsoidPointWithUncertaintyCircle"):
        raise LppError(
            "the UE returned a shape other than point-with-uncertainty; "
            "this layer does not flatten shapes"
        )
    shape = estimate[1]
    latitude = shape["degreesLatitude"] * 90.0 / (1 << 23)
    if shape["latitudeSign"] == "south":
        latitude = -latitude
    longitude = shape["degreesLongitude"] * 360.0 / (1 << 24)
    code = shape["uncertainty"]
    return Circle(latitude, longitude, code, uncertainty_metres(code))


def location_failure(message: LppMessage) -> Optional[str]:
    ies = _r9_ies(message, PROVIDE_LOCATION_INFORMATION)
    common = ies.get("commonIEsProvideLocationInformation") or {}
    failure = common.get("locationError")
    return failure.get("locationfailurecause") if failure else None


def abort_cause(message: LppMessage) -> Optional[str]:
    ies = _r9_ies(message, ABORT)
    common = ies.get("commonIEsAbort") or {}
    return common.get("abortCause")


def error_cause(message: LppMessage) -> Optional[str]:
    if message.kind != ERROR:
        raise LppError(f"an {message.kind} message carries no error cause")
    body = message.body
    if not (isinstance(body, tuple) and body[0] == "error-r9"):
        raise LppError("the error body is not error-r9")
    common = body[1].get("commonIEsError") or {}
    return common.get("errorCause")


def _message(kind: str, ies: Optional[Dict[str, Any]],
             *, initiator: str = INITIATOR_LOCATION_SERVER,
             transaction_number: int = 0,
             end_transaction: bool = True,
             sequence_number: Optional[int] = None,
             acknowledgement: Optional[Dict[str, Any]] = None) -> bytes:
    if kind not in BODIES:
        raise LppError(f"unknown LPP body {kind!r}")
    transaction = TransactionId(initiator, transaction_number)
    if kind == ERROR:
        body: Any = ("error-r9", dict(ies or {}))
    else:
        body = {"criticalExtensions": ("c1", (_R9[kind], dict(ies or {})))}
    value: Dict[str, Any] = {
        "transactionID": {"initiator": transaction.initiator,
                          "transactionNumber": transaction.number},
        "endTransaction": bool(end_transaction),
        "lpp-MessageBody": ("c1", (kind, body)),
    }
    if sequence_number is not None:
        value["sequenceNumber"] = sequence_number
    if acknowledgement is not None:
        value["acknowledgement"] = acknowledgement
    obj = _codec.LPP_PDU_Definitions.LPP_Message
    try:
        with _CODEC_LOCK:
            obj.set_val(value)
            return obj.to_aper()
    except Exception as exc:  # pycrate raises its own error types
        raise LppError(f"{kind} could not be encoded: {exc}") from exc


def _r9_ies(message: LppMessage, expected: str) -> Dict[str, Any]:
    if message.kind != expected:
        raise LppError(f"expected {expected}, got {message.kind}")
    body = message.body
    try:
        choice, (name, ies) = body["criticalExtensions"]
    except (KeyError, TypeError, ValueError):
        raise LppError(f"{expected} has no criticalExtensions")
    if choice != "c1" or name != _R9[expected]:
        raise LppError(f"{expected} carries {name}, not {_R9[expected]}")
    return ies


def _area_choice(area: Circle) -> tuple:
    latitude = int(round(abs(area.latitude) * (1 << 23) / 90.0))
    longitude = int(round(area.longitude * (1 << 24) / 360.0))
    return ("ellipsoidPointWithUncertaintyCircle", {
        "latitudeSign": "north" if area.latitude >= 0 else "south",
        "degreesLatitude": latitude,
        "degreesLongitude": longitude,
        "uncertainty": area.uncertainty_code,
    })
