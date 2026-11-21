"""S1AP (TS 36.413) message layer for the S1 interface.

The encoding is generated from the spec annex; see build_s1ap.py and
s1ap_codec.py. This module builds and reads only the messages a location
session crosses, so callers never touch pycrate open-type tuples:

    S1SetupRequest / Response / Failure           procedure 17
    InitialUEMessage                              procedure 12
    Uplink / Downlink NASTransport                procedures 13 and 11
    Paging                                        procedure 10
    UEContextReleaseCommand / Complete            procedure 23
    Uplink / Downlink UE-associated LPPa transport     45 and 44
    Uplink / Downlink non-UE-associated LPPa transport 47 and 46
    ErrorIndication                               procedure 15

The rest of S1AP (handover, E-RABs, load indication, ...) is present in the
generated codec but has no builder here: the MME and the lab eNB speak only
the subset above. Adding a message means adding its builder next to these.

This module is not an S1 stack. It does not keep UE contexts, assign S1AP
identities, retransmit, or answer a message on its own; those belong to the
component that owns the association.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from lib.codecs import s1ap_codec as _codec

# pycrate's PDU object keeps the value it last decoded or encoded, so sharing
# one across threads corrupts both sides. Every use is serialised here; the
# codec is fast and the lock only wraps the encode/decode call itself.
_CODEC_LOCK = threading.RLock()

PROC_PAGING = 10
PROC_DOWNLINK_NAS_TRANSPORT = 11
PROC_INITIAL_UE_MESSAGE = 12
PROC_UPLINK_NAS_TRANSPORT = 13
PROC_ERROR_INDICATION = 15
PROC_S1_SETUP = 17
PROC_UE_CONTEXT_RELEASE = 23
PROC_DOWNLINK_UE_ASSOCIATED_LPPA = 44
PROC_UPLINK_UE_ASSOCIATED_LPPA = 45
PROC_DOWNLINK_NON_UE_ASSOCIATED_LPPA = 46
PROC_UPLINK_NON_UE_ASSOCIATED_LPPA = 47

IE_MME_UE_S1AP_ID = 0
IE_CAUSE = 2
IE_ENB_UE_S1AP_ID = 8
IE_NAS_PDU = 26
IE_UEPAGING_ID = 43
IE_PAGING_DRX = 44
IE_TAI_LIST = 46
IE_TAI_ITEM = 47
IE_CRITICALITY_DIAGNOSTICS = 58
IE_TAI = 67
IE_GLOBAL_ENB_ID = 59
IE_ENB_NAME = 60
IE_MME_NAME = 61
IE_SUPPORTED_TAS = 64
IE_UE_IDENTITY_INDEX = 80
IE_RELATIVE_MME_CAPACITY = 87
IE_S_TMSI = 96
IE_UE_S1AP_IDS = 99
IE_EUTRAN_CGI = 100
IE_SERVED_GUMMEIS = 105
IE_CN_DOMAIN = 109
IE_RRC_ESTABLISHMENT_CAUSE = 134
IE_DEFAULT_PAGING_DRX = 137
IE_LPPA_PDU = 147
IE_ROUTING_ID = 148

INITIATING = "initiatingMessage"
SUCCESSFUL = "successfulOutcome"
UNSUCCESSFUL = "unsuccessfulOutcome"

CRITICALITY_REJECT = "reject"
CRITICALITY_IGNORE = "ignore"

MAX_ENB_UE_S1AP_ID = (1 << 24) - 1
MAX_MME_UE_S1AP_ID = (1 << 32) - 1
MAX_MACRO_ENB_ID = (1 << 20) - 1
MAX_CELL_ID_28 = (1 << 28) - 1

PAGING_DRX = ("v32", "v64", "v128", "v256")
CN_DOMAIN_PS = "ps"
CN_DOMAIN_CS = "cs"
RRC_CAUSES = ("emergency", "highPriorityAccess", "mt-Access", "mo-Signalling",
              "mo-Data", "delayTolerantAccess-v1020", "mo-VoiceCall-v1280")

# MCC 001, MNC 01 (0xF filler) in the TS 29.274 8.21.5 order used by every
# S1AP PLMNidentity, including the one inside an E-UTRAN CGI. Not TBCD order.
LAB_PLMN = b"\x00\xf1\x10"


class S1apError(ValueError):
    """The bytes are not an S1AP message this implementation can read."""


@dataclass(frozen=True)
class Ecgi:
    """The cell identity a location session is anchored to, TS 36.413 9.2."""

    plmn: bytes
    cell_id: int

    def bit_string(self) -> Tuple[int, int]:
        return (self.cell_id, 28)


@dataclass(frozen=True)
class Tai:
    plmn: bytes
    tac: bytes


@dataclass
class S1apMessage:
    kind: str                       # initiatingMessage / successfulOutcome / ...
    procedure: int
    criticality: str
    name: str                       # the PDU type name, e.g. InitialUEMessage
    ies: List[Tuple[str, Any]] = field(default_factory=list)

    def ie(self, type_name: str) -> Optional[Any]:
        for name, value in self.ies:
            if name == type_name:
                return value
        return None


def _pdu(kind: str, procedure: int, name: str, ies: List[Dict[str, Any]],
         criticality: str = CRITICALITY_REJECT) -> bytes:
    obj = _codec.S1AP_PDU_Descriptions.S1AP_PDU
    try:
        with _CODEC_LOCK:
            obj.set_val((kind, {
                "procedureCode": procedure,
                "criticality": criticality,
                "value": (name, {"protocolIEs": ies}),
            }))
            return obj.to_aper()
    except Exception as exc:  # pycrate raises its own error types
        raise S1apError(f"{name} could not be encoded: {exc}") from exc


def _ie(ie_id: int, criticality: str, type_name: str, value: Any) -> Dict[str, Any]:
    return {"id": ie_id, "criticality": criticality, "value": (type_name, value)}


def _check_plmn(value: bytes) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 3:
        raise S1apError("a PLMN identity is three octets")
    return bytes(value)


def _check_tac(value: bytes) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 2:
        raise S1apError("a tracking area code is two octets")
    return bytes(value)


def _check_id(value: int, maximum: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise S1apError(f"{label} is an integer")
    if not 0 <= value <= maximum:
        raise S1apError(f"{label} {value} is outside 0..{maximum}")
    return value


def _check_octets(value: bytes, label: str, low: int, high: int) -> bytes:
    if not isinstance(value, (bytes, bytearray)):
        raise S1apError(f"{label} is an octet string")
    if not low <= len(value) <= high:
        raise S1apError(f"{label} is {low}..{high} octets, not {len(value)}")
    return bytes(value)


def _check_name(value: str, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 150:
        raise S1apError(f"{label} is a string of 1..150 characters")
    if not all(32 <= ord(ch) <= 126 for ch in value):
        raise S1apError(f"{label} is a printable string")
    return value


def _check_choice(value: str, allowed: Tuple[str, ...], label: str) -> str:
    if value not in allowed:
        raise S1apError(f"{label} {value!r} is not one of {allowed}")
    return value


def _check_cell_id(cell_id: Tuple[int, int]) -> Tuple[int, int]:
    if not (isinstance(cell_id, tuple) and len(cell_id) == 2
            and cell_id[1] == 28):
        raise S1apError("a cell identity is a (value, 28) bit string")
    _check_id(cell_id[0], MAX_CELL_ID_28, "cell identity")
    return cell_id


def _check_s_tmsi(value: Tuple[bytes, bytes]) -> Dict[str, bytes]:
    if not (isinstance(value, tuple) and len(value) == 2):
        raise S1apError("an S-TMSI is (mMEC, m-TMSI)")
    mmec, mtmsi = value
    if not isinstance(mmec, (bytes, bytearray)) or len(mmec) != 1:
        raise S1apError("an S-TMSI MME code is one octet")
    if not isinstance(mtmsi, (bytes, bytearray)) or len(mtmsi) != 4:
        raise S1apError("an S-TMSI M-TMSI is four octets")
    return {"mMEC": bytes(mmec), "m-TMSI": bytes(mtmsi)}


def paging_index(m_tmsi: bytes) -> int:
    """TS 36.413 9.1.6: the UE Identity Index is the ten least significant
    bits of the S-TMSI, which are the low bits of the M-TMSI."""
    m_tmsi = _check_octets(m_tmsi, "an M-TMSI", 4, 4)
    return int.from_bytes(m_tmsi, "big") & 0x3FF


def s1_setup_request(plmn: bytes = LAB_PLMN, enb_id: int = 0,
                     tac: bytes = b"\x00\xa1", name: Optional[str] = None,
                     paging_drx: str = "v128") -> bytes:
    """enb_id is the 20-bit macro eNB identity of the global eNB ID."""
    plmn = _check_plmn(plmn)
    _check_id(enb_id, MAX_MACRO_ENB_ID, "an eNB identity")
    tac = _check_tac(tac)
    _check_choice(paging_drx, PAGING_DRX, "a paging DRX")
    ies = [
        _ie(IE_GLOBAL_ENB_ID, CRITICALITY_REJECT, "Global-ENB-ID", {
            "pLMNidentity": plmn,
            "eNB-ID": ("macroENB-ID", (enb_id, 20)),
        }),
        _ie(IE_SUPPORTED_TAS, CRITICALITY_REJECT, "SupportedTAs", [
            {"tAC": tac, "broadcastPLMNs": [plmn]},
        ]),
        _ie(IE_DEFAULT_PAGING_DRX, CRITICALITY_IGNORE, "PagingDRX", paging_drx),
    ]
    if name is not None:
        ies.insert(1, _ie(IE_ENB_NAME, CRITICALITY_IGNORE, "ENBname",
                          _check_name(name, "an eNB name")))
    return _pdu(INITIATING, PROC_S1_SETUP, "S1SetupRequest", ies)


def s1_setup_response(plmn: bytes = LAB_PLMN, mme_code: int = 1,
                      name: Optional[str] = None) -> bytes:
    """mme_code is the one-octet MME code (MMEC) the MME answers paging with."""
    plmn = _check_plmn(plmn)
    _check_id(mme_code, 0xFF, "an MME code")
    ies = [
        _ie(IE_SERVED_GUMMEIS, CRITICALITY_REJECT, "ServedGUMMEIs", [{
            "servedPLMNs": [plmn],
            "servedGroupIDs": [b"\x00\x00"],
            "servedMMECs": [bytes([mme_code])],
        }]),
        _ie(IE_RELATIVE_MME_CAPACITY, CRITICALITY_IGNORE,
            "RelativeMMECapacity", 255),
    ]
    if name is not None:
        ies.insert(0, _ie(IE_MME_NAME, CRITICALITY_IGNORE, "MMEname",
                          _check_name(name, "an MME name")))
    return _pdu(SUCCESSFUL, PROC_S1_SETUP, "S1SetupResponse", ies)


def s1_setup_failure(cause: Tuple[str, str]) -> bytes:
    group, value = cause
    return _pdu(UNSUCCESSFUL, PROC_S1_SETUP, "S1SetupFailure", [
        _ie(IE_CAUSE, CRITICALITY_IGNORE, "Cause", (group, value)),
    ])


def initial_ue_message(enb_ue_id: int, nas_pdu: bytes,
                       cell_id: Tuple[int, int],
                       plmn: bytes = LAB_PLMN, tac: bytes = b"\x00\xa1",
                       rrc_cause: str = "mo-Signalling",
                       s_tmsi: Optional[Tuple[bytes, bytes]] = None) -> bytes:
    _check_id(enb_ue_id, MAX_ENB_UE_S1AP_ID, "an eNB UE S1AP identity")
    nas_pdu = _check_octets(nas_pdu, "a NAS PDU", 1, 0xFFFF)
    plmn = _check_plmn(plmn)
    tac = _check_tac(tac)
    _check_choice(rrc_cause, RRC_CAUSES, "an RRC establishment cause")
    ies = [
        _ie(IE_ENB_UE_S1AP_ID, CRITICALITY_REJECT, "ENB-UE-S1AP-ID", enb_ue_id),
        _ie(IE_NAS_PDU, CRITICALITY_REJECT, "NAS-PDU", nas_pdu),
        _ie(IE_TAI, CRITICALITY_REJECT, "TAI", {
            "pLMNidentity": plmn, "tAC": tac,
        }),
        _ie(IE_EUTRAN_CGI, CRITICALITY_IGNORE, "EUTRAN-CGI", {
            "pLMNidentity": plmn, "cell-ID": _check_cell_id(cell_id),
        }),
        _ie(IE_RRC_ESTABLISHMENT_CAUSE, CRITICALITY_IGNORE,
            "RRC-Establishment-Cause", rrc_cause),
    ]
    if s_tmsi is not None:
        ies.append(_ie(IE_S_TMSI, CRITICALITY_REJECT, "S-TMSI",
                       _check_s_tmsi(s_tmsi)))
    return _pdu(INITIATING, PROC_INITIAL_UE_MESSAGE, "InitialUEMessage", ies)


def _nas_transport(procedure: int, name: str, mme_ue_id: int, enb_ue_id: int,
                   nas_pdu: bytes) -> bytes:
    _check_id(mme_ue_id, MAX_MME_UE_S1AP_ID, "an MME UE S1AP identity")
    _check_id(enb_ue_id, MAX_ENB_UE_S1AP_ID, "an eNB UE S1AP identity")
    nas_pdu = _check_octets(nas_pdu, "a NAS PDU", 1, 0xFFFF)
    ies = [
        _ie(IE_MME_UE_S1AP_ID, CRITICALITY_REJECT, "MME-UE-S1AP-ID", mme_ue_id),
        _ie(IE_ENB_UE_S1AP_ID, CRITICALITY_REJECT, "ENB-UE-S1AP-ID", enb_ue_id),
        _ie(IE_NAS_PDU, CRITICALITY_REJECT, "NAS-PDU", nas_pdu),
    ]
    return _pdu(INITIATING, procedure, name, ies)


def downlink_nas_transport(mme_ue_id: int, enb_ue_id: int, nas_pdu: bytes) -> bytes:
    return _nas_transport(PROC_DOWNLINK_NAS_TRANSPORT, "DownlinkNASTransport",
                          mme_ue_id, enb_ue_id, nas_pdu)


def uplink_nas_transport(mme_ue_id: int, enb_ue_id: int, nas_pdu: bytes) -> bytes:
    return _nas_transport(PROC_UPLINK_NAS_TRANSPORT, "UplinkNASTransport",
                          mme_ue_id, enb_ue_id, nas_pdu)


def paging(ue_index: int, *, s_tmsi: Optional[Tuple[bytes, bytes]] = None,
           imsi: Optional[bytes] = None, plmn: bytes = LAB_PLMN,
           tac: bytes = b"\x00\xa1", cndomain: str = CN_DOMAIN_PS,
           drx: str = "v128") -> bytes:
    """One tracking area, one identity. Exactly one of s_tmsi and imsi: the
    target device is paged by S-TMSI when it has one, by IMSI when not."""
    _check_id(ue_index, 0x3FF, "a UE identity index")
    if (s_tmsi is None) == (imsi is None):
        raise S1apError("paging takes exactly one of an S-TMSI or an IMSI")
    _check_plmn(plmn)
    _check_tac(tac)
    _check_choice(cndomain, (CN_DOMAIN_PS, CN_DOMAIN_CS), "a CN domain")
    _check_choice(drx, PAGING_DRX, "a paging DRX")
    if s_tmsi is not None:
        identity = ("s-TMSI", _check_s_tmsi(s_tmsi))
    else:
        identity = ("iMSI", _check_octets(imsi, "an IMSI", 3, 8))
    return _pdu(INITIATING, PROC_PAGING, "Paging", [
        _ie(IE_UE_IDENTITY_INDEX, CRITICALITY_IGNORE, "UEIdentityIndexValue",
            (ue_index, 10)),
        _ie(IE_UEPAGING_ID, CRITICALITY_IGNORE, "UEPagingID", identity),
        _ie(IE_PAGING_DRX, CRITICALITY_IGNORE, "PagingDRX", drx),
        _ie(IE_CN_DOMAIN, CRITICALITY_IGNORE, "CNDomain", cndomain),
        _ie(IE_TAI_LIST, CRITICALITY_IGNORE, "TAIList", [
            _ie(IE_TAI_ITEM, CRITICALITY_IGNORE, "TAIItem", {
                "tAI": {"pLMNidentity": plmn, "tAC": tac},
            }),
        ]),
    ])


def ue_context_release_command(
        mme_ue_id: int, enb_ue_id: int,
        cause: Tuple[str, str] = ("nas", "normal-release")) -> bytes:
    _check_id(mme_ue_id, MAX_MME_UE_S1AP_ID, "an MME UE S1AP identity")
    _check_id(enb_ue_id, MAX_ENB_UE_S1AP_ID, "an eNB UE S1AP identity")
    group, value = cause
    return _pdu(INITIATING, PROC_UE_CONTEXT_RELEASE, "UEContextReleaseCommand", [
        _ie(IE_UE_S1AP_IDS, CRITICALITY_REJECT, "UE-S1AP-IDs",
            ("uE-S1AP-ID-pair", {
                "mME-UE-S1AP-ID": mme_ue_id,
                "eNB-UE-S1AP-ID": enb_ue_id,
            })),
        _ie(IE_CAUSE, CRITICALITY_IGNORE, "Cause", (group, value)),
    ])


def ue_context_release_complete(mme_ue_id: int, enb_ue_id: int) -> bytes:
    _check_id(mme_ue_id, MAX_MME_UE_S1AP_ID, "an MME UE S1AP identity")
    _check_id(enb_ue_id, MAX_ENB_UE_S1AP_ID, "an eNB UE S1AP identity")
    return _pdu(SUCCESSFUL, PROC_UE_CONTEXT_RELEASE, "UEContextReleaseComplete", [
        _ie(IE_MME_UE_S1AP_ID, CRITICALITY_IGNORE, "MME-UE-S1AP-ID", mme_ue_id),
        _ie(IE_ENB_UE_S1AP_ID, CRITICALITY_IGNORE, "ENB-UE-S1AP-ID", enb_ue_id),
    ])


def _lppa_transport(procedure: int, name: str, lppa_pdu: bytes,
                    routing_id: int, mme_ue_id: Optional[int],
                    enb_ue_id: Optional[int]) -> bytes:
    lppa_pdu = _check_octets(lppa_pdu, "an LPPa PDU", 1, 0xFFFF)
    _check_id(routing_id, 0xFF, "a routing identity")
    ies = []
    if mme_ue_id is not None or enb_ue_id is not None:
        if mme_ue_id is None or enb_ue_id is None:
            raise S1apError("a UE-associated LPPa transport needs both S1AP "
                            "identities")
        _check_id(mme_ue_id, MAX_MME_UE_S1AP_ID, "an MME UE S1AP identity")
        _check_id(enb_ue_id, MAX_ENB_UE_S1AP_ID, "an eNB UE S1AP identity")
        ies += [
            _ie(IE_MME_UE_S1AP_ID, CRITICALITY_REJECT, "MME-UE-S1AP-ID", mme_ue_id),
            _ie(IE_ENB_UE_S1AP_ID, CRITICALITY_REJECT, "ENB-UE-S1AP-ID", enb_ue_id),
        ]
    ies += [
        _ie(IE_ROUTING_ID, CRITICALITY_REJECT, "Routing-ID", routing_id),
        _ie(IE_LPPA_PDU, CRITICALITY_REJECT, "LPPa-PDU", lppa_pdu),
    ]
    return _pdu(INITIATING, procedure, name, ies)


def downlink_ue_associated_lppa(mme_ue_id: int, enb_ue_id: int,
                                lppa_pdu: bytes, routing_id: int = 0) -> bytes:
    return _lppa_transport(PROC_DOWNLINK_UE_ASSOCIATED_LPPA,
                           "DownlinkUEAssociatedLPPaTransport", lppa_pdu,
                           routing_id, mme_ue_id, enb_ue_id)


def uplink_ue_associated_lppa(mme_ue_id: int, enb_ue_id: int,
                              lppa_pdu: bytes, routing_id: int = 0) -> bytes:
    return _lppa_transport(PROC_UPLINK_UE_ASSOCIATED_LPPA,
                           "UplinkUEAssociatedLPPaTransport", lppa_pdu,
                           routing_id, mme_ue_id, enb_ue_id)


def downlink_non_ue_associated_lppa(routing_id: int, lppa_pdu: bytes) -> bytes:
    return _lppa_transport(PROC_DOWNLINK_NON_UE_ASSOCIATED_LPPA,
                           "DownlinkNonUEAssociatedLPPaTransport", lppa_pdu,
                           routing_id, None, None)


def uplink_non_ue_associated_lppa(routing_id: int, lppa_pdu: bytes) -> bytes:
    return _lppa_transport(PROC_UPLINK_NON_UE_ASSOCIATED_LPPA,
                           "UplinkNonUEAssociatedLPPaTransport", lppa_pdu,
                           routing_id, None, None)


def error_indication(cause: Tuple[str, str] = ("misc", "unspecified")) -> bytes:
    group, value = cause
    return _pdu(INITIATING, PROC_ERROR_INDICATION, "ErrorIndication", [
        _ie(IE_CAUSE, CRITICALITY_IGNORE, "Cause", (group, value)),
    ])


def parse(data: bytes) -> S1apMessage:
    obj = _codec.S1AP_PDU_Descriptions.S1AP_PDU
    try:
        with _CODEC_LOCK:
            obj.from_aper(bytes(data))
            kind, body = obj.get_val()
    except Exception as exc:
        raise S1apError(f"not an S1AP PDU: {exc}") from exc
    value = body["value"]
    if not (isinstance(value, tuple) and len(value) == 2
            and isinstance(value[1], dict)):
        # An elementary procedure outside the generated object set decodes
        # with its open type left as raw octets. Refuse it by number rather
        # than invent a message name for it.
        raise S1apError(
            f"procedure {body['procedureCode']} is not a message this "
            "codec knows")
    name, message = value
    ies = []
    for ie in message.get("protocolIEs", []):
        type_name, ie_value = ie["value"]
        ies.append((type_name, ie_value))
    return S1apMessage(kind=kind, procedure=body["procedureCode"],
                       criticality=body["criticality"], name=name, ies=ies)


def ecgi(message: S1apMessage) -> Optional[Ecgi]:
    """The E-UTRAN CGI of an InitialUEMessage, or None when it carries none.
    A cell identity that is not 28 bits is an error: the MME does not trim
    it to something a cell database might recognise."""
    ie = message.ie("EUTRAN-CGI")
    if ie is None:
        return None
    plmn = bytes(ie["pLMNidentity"])
    value, bits = ie["cell-ID"]
    if bits != 28:
        raise S1apError(f"an E-UTRAN CGI cell identity is 28 bits, not {bits}")
    return Ecgi(plmn=plmn, cell_id=value)


def tai(message: S1apMessage) -> Optional[Tai]:
    ie = message.ie("TAI")
    if ie is None:
        return None
    return Tai(plmn=bytes(ie["pLMNidentity"]), tac=bytes(ie["tAC"]))


def tai_list(message: S1apMessage) -> List[Tai]:
    """TAIList is a container of single TAI items, each an open type."""
    ies = message.ie("TAIList")
    if ies is None:
        return []
    out = []
    for item in ies:
        type_name, value = item["value"]
        if type_name != "TAIItem":
            raise S1apError(f"a TAI list entry is {type_name}, not a TAI item")
        out.append(Tai(plmn=bytes(value["tAI"]["pLMNidentity"]),
                       tac=bytes(value["tAI"]["tAC"])))
    return out


def nas_pdu(message: S1apMessage) -> Optional[bytes]:
    return message.ie("NAS-PDU")


def lppa_pdu(message: S1apMessage) -> Optional[bytes]:
    return message.ie("LPPa-PDU")


def routing_id(message: S1apMessage) -> Optional[int]:
    return message.ie("Routing-ID")


def ue_ids(message: S1apMessage) -> Tuple[Optional[int], Optional[int]]:
    """(MME-UE-S1AP-ID, eNB-UE-S1AP-ID) from whichever form the message uses."""
    mme_ue_id = message.ie("MME-UE-S1AP-ID")
    enb_ue_id = message.ie("ENB-UE-S1AP-ID")
    pair = message.ie("UE-S1AP-IDs")
    if isinstance(pair, tuple) and len(pair) == 2:
        kind, value = pair
        if kind == "uE-S1AP-ID-pair":
            mme_ue_id = value.get("mME-UE-S1AP-ID", mme_ue_id)
            enb_ue_id = value.get("eNB-UE-S1AP-ID", enb_ue_id)
        elif kind == "mME-UE-S1AP-ID":
            mme_ue_id = value
    return mme_ue_id, enb_ue_id


def s_tmsi(message: S1apMessage) -> Optional[Tuple[bytes, bytes]]:
    ie = message.ie("S-TMSI")
    if ie is None:
        paging_id = message.ie("UEPagingID")
        if isinstance(paging_id, tuple) and paging_id[0] == "s-TMSI":
            ie = paging_id[1]
    if ie is None:
        return None
    return bytes(ie["mMEC"]), bytes(ie["m-TMSI"])


def paged_imsi(message: S1apMessage) -> Optional[bytes]:
    paging_id = message.ie("UEPagingID")
    if isinstance(paging_id, tuple) and paging_id[0] == "iMSI":
        return bytes(paging_id[1])
    return None


def ue_identity_index(message: S1apMessage) -> Optional[int]:
    ie = message.ie("UEIdentityIndexValue")
    if ie is None:
        return None
    return ie[0]


def cause(message: S1apMessage) -> Optional[Tuple[str, str]]:
    return message.ie("Cause")


def enb_name(message: S1apMessage) -> Optional[str]:
    return message.ie("ENBname")


def mme_name(message: S1apMessage) -> Optional[str]:
    return message.ie("MMEname")


def supported_tas(message: S1apMessage) -> List[Tai]:
    ies = message.ie("SupportedTAs")
    if ies is None:
        return []
    out = []
    for item in ies:
        for plmn in item["broadcastPLMNs"]:
            out.append(Tai(plmn=bytes(plmn), tac=bytes(item["tAC"])))
    return out


def served_plmns(message: S1apMessage) -> List[bytes]:
    items = message.ie("ServedGUMMEIs")
    if items is None:
        return []
    plmns: List[bytes] = []
    for item in items:
        plmns += [bytes(plmn) for plmn in item["servedPLMNs"]]
    return plmns
