"""Lab UE: a conforming LPP peer for the E-SMLC, reachable over HTTP.

A real UE answers LPP inside NAS on a bearer this lab does not have, so the
MME posts the E-SMLC's APDU to a URL the UE context names (see
``mme/src/nas_relay.py``). This module is the UE side of that seam: it
decodes the relayed TS 37.355 message, answers as a target device, and can
be told to misbehave so the E-SMLC's rejection paths are exercised by a
named behaviour rather than a hand-written lambda in each test.

The behaviours:

    answer             ProvideLocationInformation in the same transaction
    ignore             no answer at all; the E-SMLC's own timer decides
    abort              Abort with cause targetDeviceAbort
    failure            ProvideLocationInformation with a failure cause
    error              Error with cause incorrectDataValue
    wrong-transaction  an otherwise valid answer under another number

A request this UE does not implement (assistance data, capabilities it was
not asked for) gets no answer: silence is the honest reply when there is
nothing to say, and it lets the peer's timer bound the dialogue.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Optional, Tuple

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.codecs import lpp  # noqa: E402

BEHAVIOUR_ANSWER = "answer"
BEHAVIOUR_IGNORE = "ignore"
BEHAVIOUR_ABORT = "abort"
BEHAVIOUR_FAILURE = "failure"
BEHAVIOUR_ERROR = "error"
BEHAVIOUR_WRONG_TRANSACTION = "wrong-transaction"

BEHAVIOURS = (BEHAVIOUR_ANSWER, BEHAVIOUR_IGNORE, BEHAVIOUR_ABORT,
              BEHAVIOUR_FAILURE, BEHAVIOUR_ERROR, BEHAVIOUR_WRONG_TRANSACTION)

ABORT_CAUSE = "targetDeviceAbort"
ERROR_CAUSE = "incorrectDataValue"


class LabUe:
    """The target device half of an LPP dialogue.

    ``position`` is what the UE claims when it answers a location request;
    with none configured the answer is an empty ProvideLocationInformation,
    which is still a valid transaction answer but carries no estimate. The
    E-SMLC does not use the estimate yet, so both shapes are accepted.
    """

    def __init__(self, *, behaviour: str = BEHAVIOUR_ANSWER,
                 position: Optional[lpp.Circle] = None,
                 failure: str = lpp.FAILURE_POSITION_METHOD,
                 error_cause: str = ERROR_CAUSE,
                 transaction_shift: int = 1):
        if behaviour not in BEHAVIOURS:
            raise ValueError(f"behaviour {behaviour!r} is not one of "
                             f"{list(BEHAVIOURS)}")
        if not 0 < transaction_shift <= 255:
            raise ValueError("a transaction shift is 1..255")
        self.behaviour = behaviour
        self.position = position
        self.failure = failure
        self.error_cause = error_cause
        self.transaction_shift = transaction_shift

    def answer(self, apdu: bytes) -> Optional[bytes]:
        """Answer one relayed LPP APDU, or None when the UE stays silent."""
        if self.behaviour == BEHAVIOUR_IGNORE:
            return None
        try:
            request = lpp.parse(apdu)
        except lpp.LppError:
            return None
        if request.transaction_id is None:
            return None
        number = request.transaction_id.number
        if self.behaviour == BEHAVIOUR_WRONG_TRANSACTION:
            number = (number + self.transaction_shift) & 0xFF
        options = {"initiator": lpp.INITIATOR_TARGET_DEVICE,
                   "transaction_number": number,
                   "end_transaction": request.end_transaction}
        if self.behaviour == BEHAVIOUR_ABORT:
            return lpp.abort(ABORT_CAUSE, **options)
        if self.behaviour == BEHAVIOUR_ERROR:
            return lpp.error(self.error_cause, **options)
        if request.kind == lpp.REQUEST_CAPABILITIES:
            return lpp.provide_capabilities(**options)
        if request.kind == lpp.REQUEST_LOCATION_INFORMATION:
            if self.behaviour == BEHAVIOUR_FAILURE:
                return lpp.provide_location_information(
                    failure=self.failure, **options)
            if self.behaviour == BEHAVIOUR_ANSWER and self.position is not None:
                return lpp.provide_location_information(
                    area=self.position, **options)
            return lpp.provide_location_information(**options)
        return None


class _UeRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            document = json.loads(self.rfile.read(length) or b"{}")
            apdu = bytes.fromhex(document.get("apdu") or "")
        except (ValueError, TypeError, AttributeError):
            self.send_error(400, "the body is not {imsi, apdu}")
            return
        self.server.requests.append((document.get("imsi"), apdu))
        answer = self.server.ue.answer(apdu)
        if answer is None:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps({"apdu": answer.hex()}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class UeEndpoint:
    """The UE's HTTP face: POST {"imsi", "apdu"} -> {"apdu"} or 204."""

    def __init__(self, ue: LabUe, host: str = "127.0.0.1", port: int = 0):
        self.ue = ue
        self.server = ThreadingHTTPServer((host, port), _UeRequestHandler)
        self.server.ue = ue
        self.server.requests: List[Tuple[Optional[str], bytes]] = []
        self.thread = None

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/lpp"

    @property
    def requests(self) -> List[Tuple[Optional[str], bytes]]:
        return self.server.requests

    def start(self) -> "UeEndpoint":
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self) -> "UeEndpoint":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
