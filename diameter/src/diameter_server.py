#!/usr/bin/env python3
"""
Diameter S6a/Cx Server for HSS/HLR Interworking
TS 29.272 (S6a), TS 29.228/29.229 (Cx), TS 29.273 (SWx/S6b)

Implements:
- Diameter Base Protocol (CER/CEA, DWR/DWA, DPA)
- S6a: SendRoutingInfo, SendAuthInfo, InsertSubscriberData, DeleteSubscriberData,
       PurgeUE, Reset, Notify
- Cx: UserAuthorization, ServerAssignment, LocationInfo, MultimediaAuth,
      PushProfile, RegistrationTermination
- SWx: UserDataRequest, UserDataAnswer (Sh interface)

Queries hssdb for subscriber data and UDM for auth vectors.
"""

import asyncio
import logging
import os
import secrets
import struct
import sys
import json
import mysql.connector
from typing import Optional, Dict, List, Tuple
from enum import IntEnum

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_SRC_DIR)
for _path in (_APP_DIR, _SRC_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from corelib.milenage import (  # noqa: E402
    CryptoUnavailable,
    Milenage,
    plmn_id,
)

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger("diameter-s6a-cx")

# ============================================================================
# Diameter Constants (RFC 6733, TS 29.272, TS 29.228)
# ============================================================================

# Command Codes
CMD_CER = 257
CMD_CEA = 257
CMD_DWR = 280
CMD_DWA = 280
CMD_DPA = 282  # Reuse for DPA/DWA
CMD_SRI = 16777246  # Send Routing Info
CMD_SAI = 318  # Send Auth Info
CMD_ISD = 319  # Insert Subscriber Data
CMD_DSD = 320  # Delete Subscriber Data
CMD_PUR = 321  # Purge UE
CMD_RST = 282  # Reset
CMD_NOT = 323  # Notify
CMD_UA = 300  # User Authorization (Cx)
CMD_SA = 301  # Server Assignment (Cx)
CMD_LI = 302  # Location Info (Cx)
CMD_MA = 303  # Multimedia Auth (Cx)
CMD_PP = 304  # Push Profile (Cx)
CMD_RT = 305  # Registration Termination (Cx)

# Application IDs
APP_3GPP_S6a = 16777251  # S6a
APP_3GPP_Cx = 16777216   # Cx
APP_3GPP_Sh = 16777251   # Sh (same as S6a app ID)

# AVP Codes (subset)
AVP_ORIGIN_HOST = 264
AVP_ORIGIN_REALM = 296
AVP_DESTINATION_HOST = 293
AVP_DESTINATION_REALM = 283
AVP_AUTH_APPLICATION_ID = 258
AVP_RESULT_CODE = 268
AVP_ORIGIN_STATE_ID = 278
AVP_EXPERIMENTAL_RESULT = 297
AVP_ERROR_MESSAGE = 286
AVP_USER_NAME = 1
AVP_USER_DATA = 300
AVP_IMSI = 320
AVP_MSISDN = 701
AVP_SRVCC_INFO = 1242
AVP_SRVCC_SUPPORTED = 1243
AVP_REGISTERED_IP = 1229
AVP_AF_APP_ID = 1214
AVP_SDP_MEDIA_COMPONENT = 1237
AVP_SDP_SESSION_DESCRIPTION = 1238
AVP_SDP_IP_CAN_BODY = 1236
AVP_MEDIA_TYPE = 1232
AVP_RAT_TYPE = 1032
AVP_UE_SRVCC_CAPABILITY = 1254
AVP_IMEISV = 860
AVP_RESTORATION_PRIORITY = 1267
AVP_PULL_MODE = 1265
AVP_TADS = 1634  # Terminating Access Domain Selection
AVP_USER_STATE = 1635
AVP_LOCATION_TYPE = 1636
AVP_CURRENT_LOCATION = 1637
AVP_LOCATION_INFO = 1638
AVP_5GSRVCC_INFO = 1647
AVP_LOCATION_RETRIEVAL_STATUS = 1639
AVP_ECGI = 1640
AVP_TAI = 1641
AVP_LOCATION_STAMP = 1642
AVP_SUBSCRIBED_PERIODIC_RAU_TAU_TIMER = 1459
# Authentication AVPs (TS 29.272 §7.3, TS 29.230 §5)
AVP_EUTRAN_AUTH_INFO = 1414   # E-UTRAN-Vector
AVP_VISITED_PLMN_ID = 1407
AVP_AUTHENTICATION_INFO = 1413
AVP_RESYNC_INFO = 1411
AVP_REQUESTED_EUTRAN_AUTH_INFO = 1408
AVP_NUMBER_OF_REQUESTED_VECTORS = 1410
AVP_IMMEDIATE_RESPONSE_PREFERRED = 1412
AVP_ITEM_NUMBER = 1419
AVP_RAND = 1447
AVP_XRES = 1448
AVP_AUTN = 1449
AVP_KASME = 1450
AVP_UTRAN_AUTH_INFO = 1415
AVP_GERAN_AUTH_INFO = 1416
AVP_IMS_AUTH_DATA = 1437
AVP_AUTHENTICATION_SCHEME = 1443
AVP_PRIVATE_IDENTITY = 1442
AVP_PUBLIC_IDENTITY = 1441
AVP_HTTP_DIGEST = 1440
AVP_AKA_PROTOCOL = 1444
AVP_AUTHENTICATION_INFO_V2 = 1445
AVP_E_UTRAN_AUTH_INFO_V2 = 1446
AVP_U_UTRAN_AUTH_INFO_V2 = 1447
AVP_G_UTRAN_AUTH_INFO_V2 = 1448
AVP_SELECTED_AUTH_SCHEME = 1451
AVP_USER_ID = 1454
AVP_DNS_SERVER_IPv6_ADDRESS = 1455
AVP_NEXT_HOP_PARAMETER = 463
AVP_ROUTE_RECORD = 182
AVP_PROXY_INFO = 334
AVP_PROXY_HOST = 330
AVP_PROXY_STATE = 333
AVP_SERVICE_SELECTION = 16777246  # Reuse
AVP_NETWORK_ACCESS_MODE = 456
AVP_ACCESS_RESTRICTION_DATA = 457
AVP_SUBSCRIPTION_DATA = 458
AVP_AMBR = 459
AVP_TRAFFIC_EXCEPTIONS = 461
AVP_ODB_PACKET = 1142
AVP_ODB_CS = 1143
AVP_ODB_PLMN = 1144
AVP_CSG_SUBSCRIPTION_DATA = 1439
AVP_CSG_ID = 1449
AVP_CSG_OPERATOR = 1450
AVP_NGEIR = 1428
AVP_SMS_REGISTER = 1429
AVP_SERVICE_NODE = 844
AVP_CHARGING_CHARACTERISTICS = 1397
AVP_CHARGING_COLLECTOR_ADDRESS = 1398
AVP_CHARGING_DATA_SERVER_ADDRESS = 1399
AVP_CHARGING_RULE_NAME = 1418
AVP_PCC_RULE_PROVISIONING = 1419
AVP_PCC_RULE_OPERATION = 1420
AVP_PCC_RULE_STATUS = 1421
AVP_EVENT_TRIGGER = 1422
AVP_UE_TIME_ZONE = 1423
AVP_UE_LOCAL_TIME = 1424
AVP_USER_IDENTIFIER = 1436
AVP_GMLC_ADDRESS = 1435
AVP_LCS_PRIVACY = 1438
AVP_LCS_CODEWORD = 1440
AVP_LCS_FORMAT_INDICATOR = 1441
AVP_LOCATION_TYPE_REQ = 1442
AVP_LCS_CLIENT_EXTERNAL_ID = 1443
AVP_LCS_CLIENT_NAME = 1444
AVP_LCS_CLIENT_TYPE = 1445
AVP_LCS_KEY_SET_IDENTIFIER = 1446
AVP_LCS_PRIVACY_CLASS = 1447
AVP_LCS_QOS = 1448
AVP_SUPPORTED_FEATURES = 628
AVP_VENDOR_ID = 266
AVP_VENDOR_SPECIFIC_APPLICATION_ID = 260

# Result Codes
RESULT_SUCCESS = 2001
RESULT_DIAMETER_SUCCESS = 2001
RESULT_DIAMETER_LIMITED_SUCCESS = 2002
RESULT_DIAMETER_UNABLE_TO_COMPLY = 5012
RESULT_DIAMETER_AUTHENTICATION_REJECTED = 5001
RESULT_DIAMETER_AVP_NOT_ALLOWED = 5007
RESULT_DIAMETER_UNKNOWN_PEER = 5006
RESULT_DIAMETER_UNAUTHORIZED_REQUESTING_ENTITY = 5009
RESULT_DIAMETER_UNKNOWN_USER = 5003
RESULT_DIAMETER_RAT_NOT_ALLOWED = 5035
RESULT_DIAMETER_EQUIPMENT_UNKNOWN = 5036
RESULT_DIAMETER_UNKNOWN_EPS_SUBSCRIPTION = 5130
RESULT_DIAMETER_ROAMING_NOT_ALLOWED = 5032

# ============================================================================
# Diameter AVP Encoding/Decoding
# ============================================================================

def encode_avp(code: int, flags: int, vendor_id: int, data: bytes) -> bytes:
    """Encode a Diameter AVP (RFC 6733 §4.1).

    The V bit (0x80) adds the four-octet Vendor-Id field, so the declared
    length must include it.
    """
    has_vendor = bool(flags & 0x80)
    avp_len = (12 if has_vendor else 8) + len(data)
    header = struct.pack("!I", (code << 8) | flags)
    header += struct.pack("!I", avp_len)
    if has_vendor:
        header += struct.pack("!I", vendor_id)
    return header + data


def encode_uint32_avp(code: int, value: int, vendor_id: int = 0, mandatory: bool = True) -> bytes:
    """Encode an unsigned 32-bit AVP."""
    flags = (0x80 if vendor_id else 0x00) | (0x40 if mandatory else 0x00)
    data = struct.pack("!I", value)
    return encode_avp(code, flags, vendor_id, data)


def encode_utf8_avp(code: int, value: str, vendor_id: int = 0, mandatory: bool = True) -> bytes:
    """Encode a UTF8String AVP."""
    flags = (0x80 if vendor_id else 0x00) | (0x40 if mandatory else 0x00)
    data = value.encode('utf-8')
    return encode_avp(code, flags, vendor_id, data)


def encode_grouped_avp(code: int, sub_avps: bytes, vendor_id: int = 0, mandatory: bool = True) -> bytes:
    """Encode a Grouped AVP."""
    flags = (0x80 if vendor_id else 0x00) | (0x40 if mandatory else 0x00)
    return encode_avp(code, flags, vendor_id, sub_avps)


def decode_avp(data: bytes, offset: int = 0) -> Tuple[int, int, int, int, bytes]:
    """Decode a Diameter AVP. Returns (code, flags, length, vendor_id, data, next_offset)."""
    avp_code = struct.unpack("!I", data[offset:offset+4])[0]
    code = avp_code >> 8
    flags = avp_code & 0xFF
    avp_len = struct.unpack("!I", data[offset+4:offset+8])[0]
    vendor_id = struct.unpack("!I", data[offset+8:offset+12])[0] if (flags & 0x80) else 0
    
    # V bit: bit 7 of flags byte 0 = 0x80
    has_vendor = bool(flags & 0x80)
    base_len = 12 if has_vendor else 8
    
    avp_data = data[offset+base_len:offset+avp_len]
    next_offset = offset + avp_len
    return code, flags, avp_len, vendor_id, avp_data, next_offset


def decode_all_avps(data: bytes, offset: int = 0) -> List[Dict]:
    """Decode all AVPs in a message body (the 20-octet header is already gone)."""
    avps = []
    while offset + 8 <= len(data):
        code, flags, avp_len, vendor_id, avp_data, offset = decode_avp(data, offset)
        avps.append({
            "code": code,
            "flags": flags,
            "vendor_id": vendor_id,
            "data": avp_data,
            "raw_len": avp_len
        })
    return avps


def decode_avps(data: bytes) -> List[Dict]:
    """Decode a run of AVPs that starts at offset 0 (a Grouped AVP payload)."""
    avps: List[Dict] = []
    offset = 0
    while offset + 8 <= len(data):
        code, flags, avp_len, vendor_id, avp_data, offset = decode_avp(data, offset)
        if avp_len < 8:
            break
        avps.append({
            "code": code,
            "flags": flags,
            "vendor_id": vendor_id,
            "data": avp_data,
            "raw_len": avp_len,
        })
    return avps


def avp_get_uint32(avp_data: bytes) -> int:
    """Extract uint32 from AVP data."""
    return struct.unpack("!I", avp_data)[0]


def avp_get_utf8(avp_data: bytes) -> str:
    """Extract UTF8String from AVP data."""
    return avp_data.decode('utf-8')


# ============================================================================
# Diameter Message Building
# ============================================================================

def build_diameter_header(command_code: int, flags: int, app_id: int,
                          hop_by_hop: int, end_to_end: int, message_length: int) -> bytes:
    """Build the 20-octet Diameter header (RFC 6733 §3)."""
    return (
        struct.pack("!I", (0x01 << 24) | message_length)       # Version 1 | Length
        + struct.pack("!I", (flags << 24) | command_code)      # Flags | Command
        + struct.pack("!I", app_id)
        + struct.pack("!I", hop_by_hop)
        + struct.pack("!I", end_to_end)
    )


def build_diameter_message(command_code: int, flags: int, app_id: int, avps: List[bytes]) -> bytes:
    """Build a complete Diameter message."""
    hop_by_hop = secrets.randbits(32)
    end_to_end = secrets.randbits(32)
    body = b"".join(avps)
    hdr = build_diameter_header(command_code, flags, app_id, hop_by_hop, end_to_end, 20 + len(body))
    return hdr + body


# ============================================================================
# Diameter Server Configuration
# ============================================================================

class DiameterConfig:
    def __init__(self):
        self.origin_host = os.getenv("DIAMETER_ORIGIN_HOST", "hss.core.local")
        self.origin_realm = os.getenv("DIAMETER_ORIGIN_REALM", "core.local")
        self.vendor_id = int(os.getenv("DIAMETER_VENDOR_ID", "10415"))
        self.product_name = os.getenv("DIAMETER_PRODUCT_NAME", "5G-Core-HSS")
        self.firmware_revision = int(os.getenv("DIAMETER_FIRMWARE_REVISION", "1"))
        self.port = int(os.getenv("DIAMETER_PORT", "3868"))
        self.db_config = {
            "host": os.getenv("DB_HOST", "hssdb"),
            "port": int(os.getenv("DB_PORT", "3306")),
            "user": os.getenv("DB_USER", "hss"),
            "password": os.getenv("DB_PASSWORD", "hss123"),
            "database": os.getenv("DB_NAME", "hssdb"),
        }


config = DiameterConfig()


# ============================================================================
# Database Helpers
# ============================================================================

def get_db():
    return mysql.connector.connect(**config.db_config)


def get_subscriber(imsi: str) -> Optional[Dict]:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        return cur.fetchone()
    finally:
        conn.close()


def get_eps_subscription(imsi: str) -> Optional[Dict]:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_eps_subscription WHERE imsi=%s", (imsi,))
        return cur.fetchone()
    finally:
        conn.close()


def get_5g_subscription(imsi: str) -> Optional[Dict]:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        return cur.fetchone()
    finally:
        conn.close()


def get_ims_subscription(imsi: str) -> Optional[Dict]:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_ims_subscription WHERE imsi=%s", (imsi,))
        return cur.fetchone()
    finally:
        conn.close()


# ============================================================================
# Authentication vector helpers (TS 29.272 §6.3.2, TS 33.401 Annex A.2)
# ============================================================================

def _serving_network_id(avps: List[Dict]) -> bytes:
    """Three-octet SN id for the KASME KDF.

    The MME's Visited-PLMN-Id is authoritative; otherwise the configured home
    PLMN is used (lab default 001/01, never a production 641xx network).
    """
    for avp in avps:
        if avp["code"] == AVP_VISITED_PLMN_ID and len(avp["data"]) == 3:
            return avp["data"]
    digits = os.getenv("DIAMETER_SERVING_PLMN", "00101")
    if len(digits) not in (5, 6) or not digits.isdigit():
        raise ValueError("DIAMETER_SERVING_PLMN must be MCC+MNC digits, e.g. 00101")
    return plmn_id(digits[:3], digits[3:])


def _milenage(sub: Dict) -> Tuple[Milenage, bytes, bytes]:
    """Build the Milenage state from one tbl_subscriber row."""
    key_hex = sub.get("ki") or sub.get("k")
    if not key_hex:
        raise ValueError("no Ki/K")
    key = bytes.fromhex(key_hex)
    if len(key) != 16:
        raise ValueError("Ki must be 128 bits")
    if sub.get("opc"):
        milenage = Milenage(bytes.fromhex(sub["opc"]))
    elif sub.get("op"):
        milenage = Milenage.from_op(bytes.fromhex(sub["op"]), key)
    else:
        raise ValueError("no OPc/OP")
    amf_hex = (sub.get("amf") or "8000").ljust(4, "0")
    return milenage, key, bytes.fromhex(amf_hex)


def _advance_sqn(imsi: str, expected: int, new_sqn: int) -> bool:
    """Compare-and-set the SQN so two signalling faces cannot reuse a value."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tbl_subscriber SET sqn=%s WHERE imsi=%s AND sqn=%s",
            (new_sqn, imsi, expected),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def _sai_request(avps: List[Dict]) -> Tuple[Optional[str], int, Optional[bytes]]:
    """Read IMSI, vector count and resynchronisation info from an AIR."""
    imsi = None
    count = 1
    resync = None
    for avp in avps:
        if avp["code"] in (AVP_USER_NAME, AVP_IMSI):
            try:
                imsi = avp_get_utf8(avp["data"])
            except UnicodeDecodeError:
                imsi = None
        elif avp["code"] == AVP_REQUESTED_EUTRAN_AUTH_INFO:
            for child in decode_avps(avp["data"]):
                if child["code"] == AVP_NUMBER_OF_REQUESTED_VECTORS and len(child["data"]) == 4:
                    count = avp_get_uint32(child["data"])
                elif child["code"] == AVP_RESYNC_INFO and child["data"]:
                    resync = child["data"]
    return imsi, max(1, min(count, 5)), resync


def _sai_answer(vectors: List[Dict]) -> bytes:
    """Authentication-Info grouped AVP carrying one E-UTRAN-Vector per AV."""
    vector_avps = []
    for item, vector in enumerate(vectors):
        vector_avps.append(encode_grouped_avp(AVP_EUTRAN_AUTH_INFO, b"".join([
            encode_uint32_avp(AVP_ITEM_NUMBER, item, config.vendor_id),
            encode_avp(AVP_RAND, 0xC0, config.vendor_id, vector["rand"]),
            encode_avp(AVP_XRES, 0xC0, config.vendor_id, vector["xres"]),
            encode_avp(AVP_AUTN, 0xC0, config.vendor_id, vector["autn"]),
            encode_avp(AVP_KASME, 0xC0, config.vendor_id, vector["k_asme"]),
        ]), config.vendor_id))

    return build_diameter_message(CMD_SAI, 0x80, APP_3GPP_S6a, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_S6a),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
        encode_grouped_avp(AVP_AUTHENTICATION_INFO, b"".join(vector_avps), config.vendor_id),
    ])


# ============================================================================
# S6a Command Handlers
# ============================================================================

def handle_sri(avps: List[Dict]) -> bytes:
    """Send Routing Info for SM (SRI) - TS 29.272 §6.3.1."""
    # Extract IMSI from AVPs
    imsi = None
    for avp in avps:
        if avp["code"] == AVP_IMSI:
            imsi = avp_get_utf8(avp["data"])
            break
    
    if not imsi:
        return build_error_response(CMD_SRI, APP_3GPP_S6a, RESULT_DIAMETER_UNKNOWN_USER, "Missing IMSI")
    
    sub = get_subscriber(imsi)
    if not sub:
        return build_error_response(CMD_SRI, APP_3GPP_S6a, RESULT_DIAMETER_UNKNOWN_USER, "Unknown subscriber")
    
    # Build SRI Answer
    result_avps = [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_S6a),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ]
    
    # Add SMS routing info if available (from UECM registration via UDM)
    # This would query Redis for SMSF/IP-SM-GW registration
    result_avps.append(encode_utf8_avp(AVP_MSISDN, sub.get("msisdn", "")))
    
    return build_diameter_message(CMD_SRI, 0x80, APP_3GPP_S6a, result_avps)


def handle_sai(avps: List[Dict]) -> bytes:
    """Send Authentication Info (SAI) - TS 29.272 §6.3.2.

    Vectors are real EPS-AKA vectors from the shared Milenage implementation:
    KASME = KDF(CK||IK, FC=0x10, SN id, SQN xor AK) per TS 33.401 Annex A.2.
    The SQN advance is a compare-and-set so the S6a, MAP and Nudm faces cannot
    issue the same SQN twice.
    """
    imsi, count, resync = _sai_request(avps)

    if not imsi:
        return build_error_response(CMD_SAI, APP_3GPP_S6a, RESULT_DIAMETER_UNKNOWN_USER, "Missing IMSI")

    if resync is not None:
        # MAC-S can only be checked with the RAND of the vector this HSS issued
        # last (TS 33.102 §6.3.3). This build does not retain that RAND, so it
        # refuses instead of acknowledging a resync it cannot verify.
        return build_error_response(
            CMD_SAI, APP_3GPP_S6a, RESULT_DIAMETER_UNABLE_TO_COMPLY,
            "AUTS resynchronisation requires the previously issued RAND, which this build does not store",
        )

    try:
        sn_id = _serving_network_id(avps)
    except ValueError as exc:
        return build_error_response(CMD_SAI, APP_3GPP_S6a, RESULT_DIAMETER_UNABLE_TO_COMPLY, str(exc))

    for attempt in (1, 2):
        sub = get_subscriber(imsi)
        if not sub:
            return build_error_response(CMD_SAI, APP_3GPP_S6a, RESULT_DIAMETER_UNKNOWN_USER, "Unknown subscriber")
        try:
            milenage, key, amf = _milenage(sub)
            sqn = int(sub.get("sqn") or 0)
            vectors = [
                milenage.generate_eps_av(key, sqn + index, amf, sn_id)
                for index in range(count)
            ]
        except CryptoUnavailable as exc:
            return build_error_response(CMD_SAI, APP_3GPP_S6a, RESULT_DIAMETER_UNABLE_TO_COMPLY, str(exc))
        except (TypeError, ValueError) as exc:
            return build_error_response(
                CMD_SAI, APP_3GPP_S6a, RESULT_DIAMETER_AUTHENTICATION_REJECTED,
                f"Unusable authentication credentials: {exc}",
            )

        if _advance_sqn(imsi, sqn, sqn + count):
            return _sai_answer(vectors)
        logger.warning("SQN contention for %s on S6a (attempt %d)", imsi, attempt)

    return build_error_response(
        CMD_SAI, APP_3GPP_S6a, RESULT_DIAMETER_UNABLE_TO_COMPLY, "SQN contention, retry",
    )


def handle_isd(avps: List[Dict]) -> bytes:
    """Insert Subscriber Data (ISD) - TS 29.272 §6.3.3."""
    imsi = None
    for avp in avps:
        if avp["code"] == AVP_IMSI:
            imsi = avp_get_utf8(avp["data"])
            break
    
    if not imsi:
        return build_error_response(CMD_ISD, APP_3GPP_S6a, RESULT_DIAMETER_UNKNOWN_USER, "Missing IMSI")
    
    return build_diameter_message(CMD_ISD, 0x80, APP_3GPP_S6a, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_S6a),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_dsd(avps: List[Dict]) -> bytes:
    """Delete Subscriber Data (DSD) - TS 29.272 §6.3.4."""
    imsi = None
    for avp in avps:
        if avp["code"] == AVP_IMSI:
            imsi = avp_get_utf8(avp["data"])
            break
    
    if not imsi:
        return build_error_response(CMD_DSD, APP_3GPP_S6a, RESULT_DIAMETER_UNKNOWN_USER, "Missing IMSI")
    
    return build_diameter_message(CMD_DSD, 0x80, APP_3GPP_S6a, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_S6a),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_pur(avps: List[Dict]) -> bytes:
    """Purge UE (PUR) - TS 29.272 §6.3.5."""
    imsi = None
    for avp in avps:
        if avp["code"] == AVP_IMSI:
            imsi = avp_get_utf8(avp["data"])
            break
    
    if not imsi:
        return build_error_response(CMD_PUR, APP_3GPP_S6a, RESULT_DIAMETER_UNKNOWN_USER, "Missing IMSI")
    
    return build_diameter_message(CMD_PUR, 0x80, APP_3GPP_S6a, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_S6a),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_rst(avps: List[Dict]) -> bytes:
    """Reset (RST) - TS 29.272 §6.3.6."""
    return build_diameter_message(CMD_RST, 0x80, APP_3GPP_S6a, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_S6a),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_not(avps: List[Dict]) -> bytes:
    """Notify (NOT) - TS 29.272 §6.3.7."""
    imsi = None
    for avp in avps:
        if avp["code"] == AVP_IMSI:
            imsi = avp_get_utf8(avp["data"])
            break
    
    if not imsi:
        return build_error_response(CMD_NOT, APP_3GPP_S6a, RESULT_DIAMETER_UNKNOWN_USER, "Missing IMSI")
    
    return build_diameter_message(CMD_NOT, 0x80, APP_3GPP_S6a, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_S6a),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


# ============================================================================
# Cx Command Handlers
# ============================================================================

def handle_ua(avps: List[Dict]) -> bytes:
    """User Authorization (UA) - TS 29.228 §6.2."""
    imsi = None
    for avp in avps:
        if avp["code"] == AVP_IMSI:
            imsi = avp_get_utf8(avp["data"])
            break
    
    if not imsi:
        return build_error_response(CMD_UA, APP_3GPP_Cx, RESULT_DIAMETER_UNKNOWN_USER, "Missing IMSI")
    
    sub = get_subscriber(imsi)
    ims = get_ims_subscription(imsi)
    
    result_avps = [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS if sub else RESULT_DIAMETER_UNKNOWN_USER),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_Cx),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ]
    
    if sub and ims:
        result_avps.extend([
            encode_utf8_avp(AVP_PRIVATE_IDENTITY, ims.get("impi", "")),
            encode_utf8_avp(AVP_PUBLIC_IDENTITY, ims.get("impu_list", [""])[0] if isinstance(ims.get("impu_list"), list) else ""),
        ])
    
    return build_diameter_message(CMD_UA, 0x80, APP_3GPP_Cx, result_avps)


def handle_sa(avps: List[Dict]) -> bytes:
    """Server Assignment (SA) - TS 29.228 §6.3."""
    return build_diameter_message(CMD_SA, 0x80, APP_3GPP_Cx, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_Cx),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_li(avps: List[Dict]) -> bytes:
    """Location Info (LI) - TS 29.228 §6.4."""
    imsi = None
    for avp in avps:
        if avp["code"] == AVP_IMSI:
            imsi = avp_get_utf8(avp["data"])
            break
    
    if not imsi:
        return build_error_response(CMD_LI, APP_3GPP_Cx, RESULT_DIAMETER_UNKNOWN_USER, "Missing IMSI")
    
    return build_diameter_message(CMD_LI, 0x80, APP_3GPP_Cx, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_Cx),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_ma(avps: List[Dict]) -> bytes:
    """Multimedia Auth (MA) - TS 29.228 §6.5."""
    return build_diameter_message(CMD_MA, 0x80, APP_3GPP_Cx, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_Cx),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_pp(avps: List[Dict]) -> bytes:
    """Push Profile (PP) - TS 29.228 §6.6."""
    return build_diameter_message(CMD_PP, 0x80, APP_3GPP_Cx, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_Cx),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_rt(avps: List[Dict]) -> bytes:
    """Registration Termination (RT) - TS 29.228 §6.7."""
    return build_diameter_message(CMD_RT, 0x80, APP_3GPP_Cx, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_Cx),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


# ============================================================================
# Diameter Base Protocol
# ============================================================================

def handle_cer(avps: List[Dict]) -> bytes:
    """Capabilities Exchange Request (CER) - RFC 6733."""
    return build_diameter_message(CMD_CEA, 0x80, 0, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_S6a),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, APP_3GPP_Cx),
        encode_uint32_avp(AVP_VENDOR_ID, config.vendor_id),
        encode_utf8_avp(AVP_PRODUCT_NAME, config.product_name),
        encode_uint32_avp(AVP_ORIGIN_STATE_ID, secrets.randbits(32)),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


def handle_dwr(avps: List[Dict]) -> bytes:
    """Device Watchdog Request (DWR) - RFC 6733."""
    origin_state_id = secrets.randbits(32)
    for avp in avps:
        if avp["code"] == AVP_ORIGIN_STATE_ID:
            origin_state_id = avp_get_uint32(avp["data"])
            break
    
    return build_diameter_message(CMD_DWA, 0x80, 0, [
        encode_uint32_avp(AVP_RESULT_CODE, RESULT_SUCCESS),
        encode_uint32_avp(AVP_ORIGIN_STATE_ID, origin_state_id),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
    ])


# ============================================================================
# Error Response
# ============================================================================

def build_error_response(command_code: int, app_id: int, result_code: int, error_message: str) -> bytes:
    """Build a Diameter error response."""
    return build_diameter_message(command_code, 0x80, app_id, [
        encode_uint32_avp(AVP_RESULT_CODE, result_code),
        encode_uint32_avp(AVP_AUTH_APPLICATION_ID, app_id),
        encode_utf8_avp(AVP_ORIGIN_HOST, config.origin_host),
        encode_utf8_avp(AVP_ORIGIN_REALM, config.origin_realm),
        encode_utf8_avp(AVP_ERROR_MESSAGE, error_message),
    ])


# ============================================================================
# Command Handler Dispatcher
# ============================================================================

S6A_HANDLERS = {
    CMD_SRI: handle_sri,
    CMD_SAI: handle_sai,
    CMD_ISD: handle_isd,
    CMD_DSD: handle_dsd,
    CMD_PUR: handle_pur,
    CMD_RST: handle_rst,
    CMD_NOT: handle_not,
}

CX_HANDLERS = {
    CMD_UA: handle_ua,
    CMD_SA: handle_sa,
    CMD_LI: handle_li,
    CMD_MA: handle_ma,
    CMD_PP: handle_pp,
    CMD_RT: handle_rt,
}


def dispatch_command(command_code: int, app_id: int, avps: List[Dict]) -> bytes:
    """Dispatch a Diameter command to the appropriate handler."""
    if app_id == APP_3GPP_S6a:
        handler = S6A_HANDLERS.get(command_code)
        if handler:
            return handler(avps)
    elif app_id == APP_3GPP_Cx:
        handler = CX_HANDLERS.get(command_code)
        if handler:
            return handler(avps)
    
    return build_error_response(command_code, app_id, RESULT_DIAMETER_UNABLE_TO_COMPLY, "Unsupported command")


# ============================================================================
# Diameter Server (asyncio)
# ============================================================================

class DiameterServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 3868):
        self.host = host
        self.port = port
        self.server = None
        self.peers = {}  # hop_by_hop -> writer

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        logger.info(f"Diameter S6a/Cx server listening on {self.host}:{self.port}")
        
        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        logger.info(f"Diameter peer connected: {addr}")
        
        try:
            while True:
                # Read Diameter header (20 bytes)
                header_data = await reader.readexactly(20)
                
                # Parse header (RFC 6733 §3): Version|Length, Flags|Command
                version_length = struct.unpack("!I", header_data[0:4])[0]
                msg_len = version_length & 0xFFFFFF
                flags_command = struct.unpack("!I", header_data[4:8])[0]
                flags = (flags_command >> 24) & 0xFF
                command_code = flags_command & 0xFFFFFF
                app_id = struct.unpack("!I", header_data[8:12])[0]
                hop_by_hop = struct.unpack("!I", header_data[12:16])[0]
                end_to_end = struct.unpack("!I", header_data[16:20])[0]

                if msg_len < 20:
                    logger.warning(f"Peer {addr} sent an invalid Diameter length {msg_len}; closing")
                    break

                # Read remaining body
                body_len = msg_len - 20
                if body_len > 0:
                    body_data = await reader.readexactly(body_len)
                else:
                    body_data = b""
                
                # Decode AVPs
                avps = decode_all_avps(body_data)
                
                logger.debug(f"Received Diameter cmd={command_code} app={app_id} h2h={hop_by_hop} e2e={end_to_end}")
                
                # Handle base protocol commands
                if command_code == CMD_CER:
                    response = handle_cer(avps)
                elif command_code == CMD_DWR:
                    response = handle_dwr(avps)
                elif command_code in [CMD_DPA]:  # DPA is answer to DWR/RST
                    response = b""  # No response needed
                else:
                    response = dispatch_command(command_code, app_id, avps)
                
                if response:
                    # Answers must echo the request's Hop-by-Hop and End-to-End
                    # identifiers or the peer cannot correlate them (RFC 6733 §3).
                    response = (
                        response[:12]
                        + struct.pack("!II", hop_by_hop, end_to_end)
                        + response[20:]
                    )
                    writer.write(response)
                    await writer.drain()
                    logger.debug(f"Sent Diameter response cmd={command_code}")
                    
        except asyncio.IncompleteReadError:
            logger.info(f"Diameter peer disconnected: {addr}")
        except Exception as e:
            logger.error(f"Diameter error with peer {addr}: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass


# ============================================================================
# Main
# ============================================================================

async def main():
    server = DiameterServer(host="0.0.0.0", port=config.port)
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())