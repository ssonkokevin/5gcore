"""Read SLg request AVPs and build the SLg answer AVPs around an outcome.

Every code here is from TS 29.172; the ECGI layout is the one the GMLC already
decodes (PLMN in TS 29.274 8.21.5 order, then the 28-bit ECI in four octets
whose top nibble is spare and must be zero).
"""

from __future__ import annotations

import os
import struct
import sys
from typing import List, Optional

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from corelib import diameter as d  # noqa: E402
from lib.codecs import lcsap  # noqa: E402

from location_service import LocationOutcome  # noqa: E402

LOCATION_TYPE_CURRENT_OR_LAST_KNOWN = 1
LOCATION_TYPE_CURRENT_LOCATION = 2
LOCATION_TYPE_INITIATE_REPORTING = 3

# LCS-Client-Type values, TS 29.172 7.4.4 / TS 32.299.
CLIENT_EMERGENCY = 0
CLIENT_VALUE_ADDED = 1
CLIENT_LAWFUL_INTERCEPT = 2
CLIENT_PLMN_OPERATOR = 3

_CLIENT_TYPES = {
    CLIENT_EMERGENCY: lcsap.CLIENT_EMERGENCY,
    CLIENT_VALUE_ADDED: lcsap.CLIENT_VALUE_ADDED,
    CLIENT_LAWFUL_INTERCEPT: lcsap.CLIENT_LAWFUL_INTERCEPT,
    CLIENT_PLMN_OPERATOR: lcsap.CLIENT_PLMN_OPERATOR,
}

FULFILMENT_FULFILLED = 0
FULFILMENT_NOT_FULFILLED = 1


def subscriber(request: d.Message) -> Optional[str]:
    """User-Name carries the IMSI on SLg; MSISDN is the fallback identity."""
    user = request.avp(d.AVP_USER_NAME)
    if user is not None and user.as_string():
        return user.as_string()
    msisdn = request.avp(d.AVP_MSISDN)
    if msisdn is not None and msisdn.as_string():
        return msisdn.as_string()
    return None


def location_type(request: d.Message) -> Optional[int]:
    avp = request.avp(d.AVP_SLG_LOCATION_TYPE)
    return avp.as_uint32() if avp is not None else None


def requested_accuracy(request: d.Message) -> Optional[float]:
    """Horizontal-Accuracy inside LCS-QoS is an uncertainty code in metres,
    the same code TS 23.032 uses, not a metre count."""
    qos = request.avp(d.AVP_LCS_QOS)
    if qos is None:
        return None
    for avp in d.decode_avps(qos.value):
        if avp.code == d.AVP_HORIZONTAL_ACCURACY:
            try:
                return lcsap.uncertainty_metres(avp.as_uint32())
            except (lcsap.LcsApError, d.DiameterError):
                return None
    return None


def client_type(request: d.Message) -> str:
    avp = request.avp(d.AVP_LCS_CLIENT_TYPE)
    if avp is None:
        return lcsap.CLIENT_PLMN_OPERATOR
    return _CLIENT_TYPES.get(avp.as_uint32(), lcsap.CLIENT_PLMN_OPERATOR)


def ecgi(plmn: bytes, cell: int) -> bytes:
    """E-UTRAN-CGI, TS 29.274 8.21.5: three PLMN octets then 28 bits of ECI
    starting at bit 4 of the fourth octet. The spare nibble stays zero."""
    if len(plmn) != 3:
        raise ValueError("a PLMN identity is three octets")
    if not 0 <= cell < (1 << 28):
        raise ValueError(f"cell {cell} is not a 28-bit E-UTRAN cell identity")
    return bytes(plmn) + struct.pack("!I", cell)


def location_answer_avps(outcome: LocationOutcome) -> List[d.AVP]:
    """The AVPs a successful PLA adds to the result code, and nothing for a
    failure: a caller must not be able to read a position out of an error."""
    if not outcome.positioned:
        return []
    avps: List[d.AVP] = []
    if outcome.plmn is not None and outcome.cell is not None:
        avps.append(d.AVP(d.AVP_ECGI, ecgi(outcome.plmn, outcome.cell),
                          vendor_id=d.VENDOR_3GPP))
    if outcome.fulfilled is not None:
        avps.append(d.AVP_U32(
            d.AVP_ACCURACY_FULFILMENT,
            FULFILMENT_FULFILLED if outcome.fulfilled else FULFILMENT_NOT_FULFILLED,
            vendor_id=d.VENDOR_3GPP))
    if outcome.age_seconds is not None:
        avps.append(d.AVP_U32(d.AVP_AGE_OF_LOCATION, int(outcome.age_seconds),
                              vendor_id=d.VENDOR_3GPP))
    return avps
