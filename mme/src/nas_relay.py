"""Carry an LPP APDU to the UE over the lab NAS endpoint.

A real MME relays LPP inside NAS messages on S1-MME, and LPPa to the eNB over
S1AP. Neither interface exists here. What this module provides is the seam at
the same boundary: the E-SMLC's APDU is posted to a URL the UE context names,
and the UE's answer is returned unchanged. The MME does not look inside the
APDU; TS 37.355 decoding is a later work package.

Failure is reported as None ("the UE could not be reached") rather than an
exception, because the caller's honest response to an unreachable UE is to
record that, not to fail the whole transaction with a stack trace.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger("mme.nas")

DEFAULT_TIMEOUT = 2.0


class HttpNasLink:
    """POST {"imsi", "apdu": hex} to the UE's endpoint; return its answer.

    204 means the UE accepted the APDU and has nothing to say yet, so the
    caller sends nothing back and the E-SMLC's own timer decides the outcome.
    """

    def __init__(self, url: str, imsi: str, timeout: float = DEFAULT_TIMEOUT):
        self.url = url
        self.imsi = imsi
        self.timeout = timeout

    def __call__(self, apdu: bytes) -> Optional[bytes]:
        body = json.dumps({"imsi": self.imsi, "apdu": bytes(apdu).hex()}).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status == 204:
                    return None
                payload = response.read()
        except (urllib.error.URLError, OSError) as exc:
            logger.warning("NAS relay to %s failed for %s: %s", self.url, self.imsi, exc)
            return None
        try:
            document = json.loads(payload or b"{}")
            answer = document.get("apdu")
            return bytes.fromhex(answer) if answer else None
        except (ValueError, TypeError, AttributeError) as exc:
            logger.warning("NAS relay to %s returned an unreadable answer for %s: %s",
                           self.url, self.imsi, exc)
            return None
