#!/usr/bin/env python3
"""
MAP/SCCP Stack for 2G/3G HLR Interworking
TS 29.002 (MAP), TS 23.003 (SCCP Addressing), TS 23.018 (Basic Call Handling)

Implements:
- SCCP: Connectionless signaling (CLUD/CLUA) with GT addressing
- TCAP: Transaction capabilities (QUERY/RESPONSE dialogues)
- MAP Operations:
  - SRI (Send Routing Info for SM)
  - SAI (Send Authentication Info)
  - ISD (Insert Subscriber Data)
  - PRN (Provide Roaming Number)
  - TCSI (Terminating CAMEL Subscription Information)
  - OCSI (Originating CAMEL Subscription Information)
  - USSD (Unstructured Supplementary Service Data)
  - PSL (Provide Subscriber Location)
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

from corelib.milenage import CryptoUnavailable, Milenage  # noqa: E402

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger("map-sccp")

# ============================================================================
# SCCP Constants (ITU-T Q.713)
# ============================================================================

SCCP_MSG_TYPE_UDT = 0x09  # Unit Data
SCCP_MSG_TYPE_UDTS = 0x13  # Unit Data Service
SCCP_MSG_TYPE_UDT_ERROR = 0x14

SCCP_SSN_MAP = 6  # MAP Subsystem Number
SCCP_SSN_HLR = 6
SCCP_SSN_VLR = 6
SCCP_SSN_MSC = 6
SCCP_SSN_SCP = 7

# Global Title Indicator
GTI_4 = 4  # TT + NP + ES + NAI + Translation Type + Encoding Scheme + Numbering Plan + Nature of Address

# ============================================================================
# TCAP Constants (ITU-T Q.773)
# ============================================================================

TCAP_MSG_TYPE_QUERY = 0x60
TCAP_MSG_TYPE_RESPONSE = 0x62
TCAP_MSG_TYPE_U = 0x64

# TCAP P-Types
TCAP_P_TYPE_QUERY_WITH_PERMISSION = 0x60
TCAP_P_TYPE_QUERY_WITHOUT_PERMISSION = 0x61
TCAP_P_TYPE_RESPONSE = 0x62
TCAP_P_TYPE_U = 0x64

# ============================================================================
# MAP Operation Codes (TS 29.002)
# ============================================================================

MAP_OP_SRI = 21  # Send Routing Info
MAP_OP_SAI = 22  # Send Authentication Info
MAP_OP_ISD = 23  # Insert Subscriber Data
MAP_OP_PUR = 24  # Purge MS
MAP_OP_PROVIDE_ROAMING_NUMBER = 26  # Provide Roaming Number
MAP_OP_PROVIDE_IMSI = 27  # Provide IMSI
MAP_OP_AUTHENTICATION_FAILURE_REPORT = 32
MAP_OP_REGISTER_SS = 47  # Register SS
MAP_OP_ERASE_SS = 48  # Erase SS
MAP_OP_ACTIVATE_SS = 49  # Activate SS
MAP_OP_DEACTIVATE_SS = 50  # Deactivate SS
MAP_OP_INTERROGATE_SS = 51  # Interrogate SS
MAP_OP_REGISTER_PWD = 52  # Register Password
MAP_OP_GET_PASSWORD = 53  # Get Password
MAP_OP_PROCESS_UNSTRUCTURED_SS_REQUEST = 105  # Process Unstructured SS Request
MAP_OP_UNSTRUCTURED_SS_NOTIFY = 106  # Unstructured SS Notify
MAP_OP_PROVIDE_SUBSCRIBER_INFO = 107  # Provide Subscriber Info
MAP_OP_NOTIFY_SS = 108  # Notify SS
MAP_OP_ANY_TIME_INTERROGATION = 109  # Any Time Interrogation
MAP_OP_SEND_INFO_FOR_OUTGOING_CALL = 110  # Send Info For Outgoing Call
MAP_OP_SEND_ROUTING_INFO_FOR_SM = 111  # Send Routing Info For SM
MAP_OP_SEND_INFO_FOR_MT_SM = 112  # Send Info For MT SM
MAP_OP_SEND_INFO_FOR_MO_SM = 113  # Send Info For MO SM
MAP_OP_READY_FOR_SM = 114  # Ready For SM
MAP_OP_MT_FORWARD_SM = 115  # MT Forward SM
MAP_OP_MO_FORWARD_SM = 116  # MO Forward SM
MAP_OP_DELETE_MESSAGES = 117  # Delete Messages
MAP_OP_ALERT_SERVICE_CENTRE = 118  # Alert Service Centre
MAP_OP_INVOKE_MO_SM_FOR_SS = 119  # Invoke MO SM For SS
MAP_OP_SEND_GROUP_CALL_INFO = 120  # Send Group Call Info
MAP_OP_SEND_ROUTING_INFO_FOR_GROUP_CALL = 121  # Send Routing Info For Group Call
MAP_OP_ANY_TIME_INTERROGATION_2 = 122  # Any Time Interrogation
MAP_OP_NOTIFY_SS_2 = 123  # Notify SS
MAP_OP_REGISTER_SS_2 = 124  # Register SS
MAP_OP_ERASE_SS_2 = 125  # Erase SS
MAP_OP_ACTIVATE_SS_2 = 126  # Activate SS
MAP_OP_DEACTIVATE_SS_2 = 127  # Deactivate SS
MAP_OP_INTERROGATE_SS_2 = 128  # Interrogate SS
MAP_OP_REGISTER_PWD_2 = 129  # Register Password
MAP_OP_GET_PASSWORD_2 = 130  # Get Password
MAP_OP_PROCESS_UNSTRUCTURED_SS_REQUEST_2 = 131  # Process Unstructured SS Request
MAP_OP_UNSTRUCTURED_SS_NOTIFY_2 = 132  # Unstructured SS Notify
MAP_OP_PROVIDE_SUBSCRIBER_INFO_2 = 133  # Provide Subscriber Info
MAP_OP_MO_FWD_SM_2 = 134  # MO Forward SM
MAP_OP_MT_FWD_SM_2 = 135  # MT Forward SM
MAP_OP_SEND_ROUTING_INFO_FOR_SM_2 = 136  # Send Routing Info For SM
MAP_OP_PROVIDE_IMSI_2 = 137  # Provide IMSI
MAP_OP_DELETE_MESSAGES_2 = 138  # Delete Messages
MAP_OP_READY_FOR_SM_2 = 139  # Ready For SM
MAP_OP_DELETE_SM_PP = 140  # Delete SM PP
MAP_OP_SEND_ROUTING_INFO_FOR_SM_3 = 141  # Send Routing Info For SM
MAP_OP_ATTACH_DETACH = 142  # Attach Detach
MAP_OP_ANY_TIME_SUBSCRIPTION_INTERROGATION = 143  # Any Time Subscription Interrogation
MAP_OP_ANY_TIME_SUBSCRIPTION_INTERROGATION_2 = 144
MAP_OP_PROVIDE_SUBSCRIBER_INFO_3 = 145  # Provide Subscriber Info
MAP_OP_PROCESS_UNSTRUCTURED_SS_REQUEST_3 = 146  # Process Unstructured SS Request
MAP_OP_UNSTRUCTURED_SS_NOTIFY_3 = 147  # Unstructured SS Notify
MAP_OP_MO_FWD_SM_3 = 148  # MO Forward SM
MAP_OP_MT_FWD_SM_3 = 149  # MT Forward SM
MAP_OP_SEND_ROUTING_INFO_FOR_SM_4 = 150  # Send Routing Info For SM
MAP_OP_SEND_GROUP_CALL_INFO_2 = 151  # Send Group Call Info
MAP_OP_SEND_ROUTING_INFO_FOR_GROUP_CALL_2 = 152  # Send Routing Info For Group Call
MAP_OP_SEND_ROUTING_INFO_FOR_SM_5 = 153  # Send Routing Info For SM
MAP_OP_PREPARE_HANDOVER = 154  # Prepare Handover
MAP_OP_SEND_END_POINT = 155  # Send Endpoint
MAP_OP_PREPARE_SUBSEQUENT_HANDOVER = 156  # Prepare Subsequent Handover
MAP_OP_SEND_HANDOVER_REPORT = 157  # Send Handover Report
MAP_OP_PROCESS_ACCESS_SIGNALLING = 158  # Process Access Signalling
MAP_OP_PROCESS_ACCESS_SIGNALLING_2 = 159
MAP_OP_FORWARD_ACCESS_SIGNALLING = 160  # Forward Access Signalling
MAP_OP_FORWARD_ACCESS_SIGNALLING_2 = 161
MAP_OP_SEND_PARAMETERS = 162  # Send Parameters
MAP_OP_PROCESS_UNSTRUCTURED_SS_REQUEST_4 = 163  # Process Unstructured SS Request
MAP_OP_UNSTRUCTURED_SS_NOTIFY_4 = 164  # Unstructured SS Notify
MAP_OP_PROVIDE_SUBSCRIBER_INFO_4 = 165  # Provide Subscriber Info
MAP_OP_MO_FWD_SM_4 = 166  # MO Forward SM
MAP_OP_MT_FWD_SM_4 = 167  # MT Forward SM
MAP_OP_SEND_ROUTING_INFO_FOR_SM_6 = 168  # Send Routing Info For SM
MAP_OP_PROCESS_UNSTRUCTURED_SS_REQUEST_5 = 169  # Process Unstructured SS Request
MAP_OP_UNSTRUCTURED_SS_NOTIFY_5 = 170  # Unstructured SS Notify
MAP_OP_PROVIDE_SUBSCRIBER_INFO_5 = 171  # Provide Subscriber Info
MAP_OP_MO_FWD_SM_5 = 172  # MO Forward SM
MAP_OP_MT_FWD_SM_5 = 173  # MT Forward SM
MAP_OP_SEND_ROUTING_INFO_FOR_SM_7 = 174  # Send Routing Info For SM

# MAP Error Codes
MAP_ERR_UNKNOWN_SUBSCRIBER = 2
MAP_ERR_ILLEGAL_SUBSCRIBER = 3
MAP_ERR_BEARER_SERVICE_NOT_PROVISIONED = 4
MAP_ERR_TELE_SERVICE_NOT_PROVISIONED = 5
MAP_ERR_ILLEGAL_EQUIPMENT = 6
MAP_ERR_CALL_BARRED = 7
MAP_ERR_FACILITY_NOT_SUPPORTED = 8
MAP_ERR_FACILITY_NOT_SUBSCRIBED = 9
MAP_ERR_OUT_OF_CREDIT = 10
MAP_ERR_SYSTEM_FAILURE = 11
MAP_ERR_DATA_MISSING = 12
MAP_ERR_UNEXPECTED_DATA_VALUE = 13
MAP_ERR_UNKNOWN_ALPHABET = 14
MAP_ERR_USSD_BUSY = 15
MAP_ERR_UNKNOWN_FACILITY = 16
MAP_ERR_UNKNOWN_BSS = 17
MAP_ERR_UNKNOWN_HANDOVER_TYPE = 18
MAP_ERR_UNKNOWN_FLOW = 19
MAP_ERR_ILLGAL_FLOW_SPECIFICATION = 20
MAP_ERR_RECONCILIATION_FAILURE = 21
MAP_ERR_ROAMING_NOT_ALLOWED = 22
MAP_ERR_MW_SESSION_SETUP_FAILURE = 23
MAP_ERR_ILLEGAL_MT_OPERATION = 24
MAP_ERR_UNKNOWN_INTERWORKING_PLMN_IDENTITY = 25
MAP_ERR_ILLEGAL_EQUIPMENT_2 = 26
MAP_ERR_ILLEGAL_MS = 27
MAP_ERR_ILLEGAL_SS = 28
MAP_ERR_UNKNOWN_HLR = 29
MAP_ERR_UNKNOWN_VLR = 30
MAP_ERR_UNKNOWN_MSC = 31
MAP_ERR_UNKNOWN_SGSN = 32
MAP_ERR_UNKNOWN_GGSN = 33
MAP_ERR_UNKNOWN_PCSCF = 34
MAP_ERR_UNKNOWN_SCSK = 35
MAP_ERR_PACKET_ACCESS_BARRED = 36

# ============================================================================
# SCCP Address Encoding
# ============================================================================

def encode_pc_address(point_code: int, ssn: int, gt: Optional[str] = None) -> bytes:
    """Encode SCCP Called/Calling Party Address."""
    addr_indicator = 0x00
    
    if gt:
        # Global Title Indicator: GT included
        gt_bytes = gt.encode('ascii')
        gt_len = len(gt_bytes)
        addr_indicator = 0x04 | 0x20  # GTI=4, SSN indicator, GT indicator
    elif ssn:
        addr_indicator = 0x02  # SSN indicator
    
    if point_code:
        addr_indicator |= 0x01  # PC indicator
    
    result = bytes([addr_indicator])
    
    if point_code:
        # Encode point code (3 bytes for ITU format)
        pc_bytes = struct.pack("!I", point_code)[1:4]
        result += pc_bytes
    
    if ssn:
        result += bytes([ssn])
    
    if gt:
        result += bytes([gt_len]) + gt_bytes
    
    return result


def decode_pc_address(data: bytes, offset: int = 0) -> Tuple[Dict, int]:
    """Decode SCCP Called/Calling Party Address."""
    addr_indicator = data[offset]
    offset += 1
    
    pc_indicator = bool(addr_indicator & 0x01)
    ssn_indicator = bool(addr_indicator & 0x02)
    gt_indicator = bool(addr_indicator & 0x20)
    
    result = {}
    
    if pc_indicator:
        pc_bytes = data[offset:offset+3]
        result["point_code"] = struct.unpack("!I", b"\x00" + pc_bytes)[0]
        offset += 3
    
    if ssn_indicator:
        result["ssn"] = data[offset]
        offset += 1
    
    if gt_indicator:
        gt_len = data[offset]
        offset += 1
        result["global_title"] = data[offset:offset+gt_len].decode('ascii')
        offset += gt_len
    
    return result, offset


# ============================================================================
# TCAP Encoding/Decoding
# ============================================================================

def encode_tcap_query(invoke_id: int, operation_code: int, parameter_bytes: bytes) -> bytes:
    """Encode TCAP QUERY message."""
    # TCAP Header: P-Type (1) + P-Abort (0) + ...
    # Component: Invoke ID (1) + Linked ID (0) + Op Code (1) + Parameter
    
    component = bytes([0x02])  # Invoke component tag
    component += bytes([1])  # Length = 1
    component += bytes([invoke_id])  # Invoke ID
    
    component += bytes([0x02])  # Operation code tag
    component += bytes([1])  # Length = 1
    component += bytes([operation_code])  # Operation code
    
    component += bytes([0x30])  # Sequence tag for parameter
    param_len = len(parameter_bytes)
    if param_len < 128:
        component += bytes([param_len])
    else:
        component += bytes([0x81, param_len])
    component += parameter_bytes
    
    # Wrap in TCAP query
    query = bytes([TCAP_MSG_TYPE_QUERY])
    total_len = len(component)
    if total_len < 128:
        query += bytes([total_len])
    else:
        query += bytes([0x81, total_len])
    query += component
    
    # Outer wrapper
    outer = bytes([0x60])  # Query with permission tag
    outer_len = len(query)
    if outer_len < 128:
        outer += bytes([outer_len])
    else:
        outer += bytes([0x81, outer_len])
    outer += query
    
    return outer


def _ber_len(length: int) -> bytes:
    """BER definite length (short form below 128, one-byte long form above)."""
    if length < 128:
        return bytes([length])
    if length < 256:
        return bytes([0x81, length])
    return bytes([0x82, length >> 8, length & 0xFF])


def encode_tcap_response(invoke_id: int, operation_code: int, result_bytes: bytes, error_code: Optional[int] = None) -> bytes:
    """Encode TCAP RESPONSE message."""
    if error_code is not None:
        # Error component
        content = bytes([0x02, 0x01, invoke_id, 0x02, 0x01, error_code])
        component = bytes([0x6A]) + _ber_len(len(content)) + content  # Error tag
    else:
        # Return result component
        content = bytes([0x02, 0x01, invoke_id, 0x02, 0x01, operation_code]) + result_bytes
        component = bytes([0x62]) + _ber_len(len(content)) + content  # Return result tag

    # Wrap in TCAP response
    response = bytes([TCAP_MSG_TYPE_RESPONSE]) + _ber_len(len(component)) + component

    return bytes([0x62]) + _ber_len(len(response)) + response


def decode_tcap(data: bytes) -> List[Dict]:
    """Decode TCAP message into components."""
    # Simplified decoder for MAP over TCAP
    components = []
    offset = 0
    
    # Skip outer wrapper
    if offset < len(data):
        tag = data[offset]
        offset += 1
        length = data[offset]
        offset += 1
        if length & 0x80:
            num_len_bytes = length & 0x7F
            length = int.from_bytes(data[offset:offset+num_len_bytes], 'big')
            offset += num_len_bytes
    
    # Now at TCAP message type
    if offset < len(data):
        msg_type = data[offset]
        offset += 1
        length = data[offset]
        offset += 1
        if length & 0x80:
            num_len_bytes = length & 0x7F
            length = int.from_bytes(data[offset:offset+num_len_bytes], 'big')
            offset += num_len_bytes
    
    # Parse components
    while offset < len(data):
        comp_tag = data[offset]
        offset += 1
        comp_len = data[offset]
        offset += 1
        if comp_len & 0x80:
            num_len_bytes = comp_len & 0x7F
            comp_len = int.from_bytes(data[offset:offset+num_len_bytes], 'big')
            offset += num_len_bytes
        
        comp_data = data[offset:offset+comp_len]
        offset += comp_len
        
        # Extract invoke ID
        invoke_id = None
        op_code = None
        
        # Find invoke ID (tag 0x02)
        comp_offset = 0
        while comp_offset < len(comp_data):
            if comp_data[comp_offset] == 0x02:
                invoke_id = comp_data[comp_offset+2]
                break
            comp_offset += 1
        
        # Find operation code (second 0x02)
        comp_offset = 0
        found_first = False
        while comp_offset < len(comp_data):
            if comp_data[comp_offset] == 0x02:
                if found_first:
                    op_code = comp_data[comp_offset+2]
                    break
                found_first = True
            comp_offset += 1
        
        components.append({
            "tag": comp_tag,
            "invoke_id": invoke_id,
            "operation_code": op_code,
            "data": comp_data,
        })
    
    return components


# ============================================================================
# MAP Operation Encoding
# ============================================================================

def encode_imsi(imsi: str) -> bytes:
    """Encode IMSI as BCD."""
    # Pad to an even number of digits (15-digit IMSIs get a trailing F)
    if len(imsi) % 2 == 1:
        imsi = imsi + "F"
    
    bcd = b""
    for i in range(0, len(imsi), 2):
        high = int(imsi[i])
        low = int(imsi[i+1]) if imsi[i+1] != 'F' else 0xF
        bcd += bytes([(high << 4) | low])
    
    return bcd


def encode_msisdn(msisdn: str) -> bytes:
    """Encode MSISDN as BCD with nature of address."""
    npi = 0x01  # ISDN/telephony numbering plan
    nai = 0x04  # International number
    
    digit_count = len(msisdn)
    if digit_count % 2 == 1:
        digit_count_str = msisdn + "F"
    else:
        digit_count_str = msisdn
    
    bcd = b""
    for i in range(0, len(digit_count_str), 2):
        high = int(digit_count_str[i])
        low = int(digit_count_str[i+1]) if digit_count_str[i+1] != 'F' else 0xF
        bcd += bytes([(high << 4) | low])
    
    return bytes([digit_count, (npi << 4) | nai]) + bcd


# ============================================================================
# MAP Server
# ============================================================================

class MAPConfig:
    def __init__(self):
        self.point_code = int(os.getenv("MAP_POINT_CODE", "3142"), 10)  # Decimal PC
        self.ss_map = int(os.getenv("MAP_SSN_MAP", "6"))
        self.gt_map = os.getenv("MAP_GT_MAP", "208010000000000")
        self.port = int(os.getenv("MAP_PORT", "2905"))
        self.db_config = {
            "host": os.getenv("DB_HOST", "hssdb"),
            "port": int(os.getenv("DB_PORT", "3306")),
            "user": os.getenv("DB_USER", "hss"),
            "password": os.getenv("DB_PASSWORD", "hss123"),
            "database": os.getenv("DB_NAME", "hssdb"),
        }


map_config = MAPConfig()


def get_db():
    return mysql.connector.connect(**map_config.db_config)


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


def get_roaming_profile(imsi: str, visited_plmn: str) -> Optional[Dict]:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_roaming_profile WHERE imsi=%s AND visited_plmn=%s", (imsi, visited_plmn))
        return cur.fetchone()
    finally:
        conn.close()


def get_supplementary_services(imsi: str) -> List[Dict]:
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_supplementary_service WHERE imsi=%s", (imsi,))
        return cur.fetchall()
    finally:
        conn.close()


# ============================================================================
# Authentication vector helpers (TS 29.002 §7.6, TS 33.102 §6.3)
# ============================================================================

def _milenage(sub: Dict) -> Tuple[Milenage, bytes, bytes]:
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
    """Compare-and-set the SQN shared with the S6a and Nudm faces."""
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


def encode_quintuplet(vector: Dict[str, bytes]) -> bytes:
    """AuthenticationQuintuplet (TS 29.002 §7.6.1.1).

    SEQUENCE { rand, xres, ck, ik, autn } with context-specific tags
    [0]..[4]; XRES may be 4-16 octets, here the 8-octet Milenage f2 output.
    """
    body = b"".join([
        bytes([0x80, len(vector["rand"])]) + vector["rand"],
        bytes([0x81, len(vector["res"])]) + vector["res"],
        bytes([0x82, len(vector["ck"])]) + vector["ck"],
        bytes([0x83, len(vector["ik"])]) + vector["ik"],
        bytes([0x84, len(vector["autn"])]) + vector["autn"],
    ])
    return bytes([0x30, len(body)]) + body


def encode_sai_result(vectors: List[Dict[str, bytes]]) -> bytes:
    """SendAuthenticationInfoRes: SEQUENCE { authenticationSetList }.

    authenticationSetList is a CHOICE; the UMTS branch is quintupletList [1]
    (TS 29.002 §7.6.1.1).
    """
    quintuplets = b"".join(encode_quintuplet(vector) for vector in vectors)
    set_list = bytes([0xA1, len(quintuplets)]) + quintuplets
    return bytes([0x30, len(set_list)]) + set_list


# ============================================================================
# MAP Operation Handlers
# ============================================================================

def handle_sri_sm(parameters: bytes, invoke_id: int) -> bytes:
    """Send Routing Info for SM (MAP_OP_SEND_ROUTING_INFO_FOR_SM)."""
    # Extract IMSI from parameters (simplified - real MAP uses ASN.1)
    # In production, parse the MAP SRI_for_SM argument
    imsi = None
    
    # Try to find IMSI in the parameter bytes
    # This is a simplified extraction
    sub = None
    
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        # Query all subscribers to find matching IMSI (simplified)
        cur.execute("SELECT imsi, msisdn FROM tbl_subscriber LIMIT 100")
        for row in cur.fetchall():
            encoded = encode_imsi(row["imsi"])
            if encoded in parameters:
                imsi = row["imsi"]
                sub = row
                break
    finally:
        conn.close()
    
    if not sub:
        return encode_tcap_response(invoke_id, MAP_OP_SEND_ROUTING_INFO_FOR_SM, b"", error_code=MAP_ERR_UNKNOWN_SUBSCRIBER)
    
    # Build SRI for SM response
    # Result: SMS router address, MSC address, etc.
    result_params = b"".join([
        # Routeing Info for SMS
        bytes([0x30, 0x0C]),  # Sequence, length
        bytes([0x04, 0x06]) + encode_imsi(sub["imsi"]),  # IMSI
        bytes([0x04, 0x0A]) + encode_msisdn(sub.get("msisdn", "")),  # MSISDN
        # SMS router address
        bytes([0x04, 0x07]) + b"sms-router",  # Address
    ])
    
    return encode_tcap_response(invoke_id, MAP_OP_SEND_ROUTING_INFO_FOR_SM, result_params)


def handle_sai(parameters: bytes, invoke_id: int) -> bytes:
    """Send Authentication Info (MAP_OP_SEND_AUTHENTICATION_INFO)."""
    imsi = None
    
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT imsi FROM tbl_subscriber LIMIT 100")
        for row in cur.fetchall():
            encoded = encode_imsi(row["imsi"])
            if encoded in parameters:
                imsi = row["imsi"]
                break
    finally:
        conn.close()
    
    if not imsi:
        return encode_tcap_response(invoke_id, MAP_OP_SAI, b"", error_code=MAP_ERR_UNKNOWN_SUBSCRIBER)

    for attempt in (1, 2):
        sub = get_subscriber(imsi)
        if not sub:
            return encode_tcap_response(invoke_id, MAP_OP_SAI, b"", error_code=MAP_ERR_UNKNOWN_SUBSCRIBER)
        try:
            milenage, key, amf = _milenage(sub)
            sqn = int(sub.get("sqn") or 0)
            vector = milenage.generate_eps_av(key, sqn, amf)
        except CryptoUnavailable:
            return encode_tcap_response(invoke_id, MAP_OP_SAI, b"", error_code=MAP_ERR_SYSTEM_FAILURE)
        except (TypeError, ValueError):
            return encode_tcap_response(invoke_id, MAP_OP_SAI, b"", error_code=MAP_ERR_DATA_MISSING)

        if _advance_sqn(imsi, sqn, sqn + 1):
            return encode_tcap_response(invoke_id, MAP_OP_SAI, encode_sai_result([vector]))
        logger.warning("SQN contention for %s on MAP (attempt %d)", imsi, attempt)

    return encode_tcap_response(invoke_id, MAP_OP_SAI, b"", error_code=MAP_ERR_SYSTEM_FAILURE)


def handle_isd(parameters: bytes, invoke_id: int) -> bytes:
    """Insert Subscriber Data (MAP_OP_INSERT_SUBSCRIBER_DATA)."""
    imsi = None
    
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT imsi FROM tbl_subscriber LIMIT 100")
        for row in cur.fetchall():
            encoded = encode_imsi(row["imsi"])
            if encoded in parameters:
                imsi = row["imsi"]
                break
    finally:
        conn.close()
    
    if not imsi:
        return encode_tcap_response(invoke_id, MAP_OP_ISD, b"", error_code=MAP_ERR_UNKNOWN_SUBSCRIBER)
    
    # Insert subscriber data - acknowledge
    return encode_tcap_response(invoke_id, MAP_OP_ISD, b"")


def handle_prn(parameters: bytes, invoke_id: int) -> bytes:
    """Provide Roaming Number (MAP_OP_PROVIDE_ROAMING_NUMBER)."""
    imsi = None
    
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT imsi, msisdn FROM tbl_subscriber LIMIT 100")
        for row in cur.fetchall():
            encoded = encode_imsi(row["imsi"])
            if encoded in parameters:
                imsi = row["imsi"]
                break
    finally:
        conn.close()
    
    if not imsi:
        return encode_tcap_response(invoke_id, MAP_OP_PROVIDE_ROAMING_NUMBER, b"", error_code=MAP_ERR_UNKNOWN_SUBSCRIBER)
    
    # Build roaming number response
    result_params = b"".join([
        bytes([0x30, 0x0C]),  # Sequence
        bytes([0x04, 0x06]) + encode_imsi(imsi),  # IMSI
        bytes([0x04, 0x0A]) + encode_msisdn(""),  # MSISDN (empty for now)
        bytes([0x04, 0x04]) + b"MSC-01",  # MSC address
    ])
    
    return encode_tcap_response(invoke_id, MAP_OP_PROVIDE_ROAMING_NUMBER, result_params)


def handle_ussd(parameters: bytes, invoke_id: int) -> bytes:
    """Process Unstructured SS Request (MAP_OP_PROCESS_UNSTRUCTURED_SS_REQUEST)."""
    # Extract USSD string and IMSI
    # Simplified: respond with USSD response
    result_params = b"".join([
        bytes([0x04, 0x04]) + b"*100#",  # USSD string
    ])
    
    return encode_tcap_response(invoke_id, MAP_OP_PROCESS_UNSTRUCTURED_SS_REQUEST, result_params)


def handle_activate_ss(parameters: bytes, invoke_id: int) -> bytes:
    """Activate SS (MAP_OP_ACTIVATE_SS)."""
    # Supplementary service activation
    result_params = b""
    return encode_tcap_response(invoke_id, MAP_OP_ACTIVATE_SS, result_params)


def handle_deactivate_ss(parameters: bytes, invoke_id: int) -> bytes:
    """Deactivate SS (MAP_OP_DEACTIVATE_SS)."""
    result_params = b""
    return encode_tcap_response(invoke_id, MAP_OP_DEACTIVATE_SS, result_params)


def handle_interrogate_ss(parameters: bytes, invoke_id: int) -> bytes:
    """Interrogate SS (MAP_OP_INTERROGATE_SS)."""
    result_params = b"".join([
        bytes([0x30, 0x04]),  # Sequence
        bytes([0x04, 0x02]) + b"\x01\x00",  # SS code (e.g., CF Unconditional)
    ])
    return encode_tcap_response(invoke_id, MAP_OP_INTERROGATE_SS, result_params)


def handle_register_ss(parameters: bytes, invoke_id: int) -> bytes:
    """Register SS (MAP_OP_REGISTER_SS)."""
    result_params = b""
    return encode_tcap_response(invoke_id, MAP_OP_REGISTER_SS, result_params)


def handle_erase_ss(parameters: bytes, invoke_id: int) -> bytes:
    """Erase SS (MAP_OP_ERASE_SS)."""
    result_params = b""
    return encode_tcap_response(invoke_id, MAP_OP_ERASE_SS, result_params)


def handle_any_time_interrogation(parameters: bytes, invoke_id: int) -> bytes:
    """Any Time Interrogation (MAP_OP_ANY_TIME_INTERROGATION)."""
    imsi = None
    
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT imsi, msisdn FROM tbl_subscriber LIMIT 100")
        for row in cur.fetchall():
            encoded = encode_imsi(row["imsi"])
            if encoded in parameters:
                imsi = row["imsi"]
                break
    finally:
        conn.close()
    
    if not imsi:
        return encode_tcap_response(invoke_id, MAP_OP_ANY_TIME_INTERROGATION, b"", error_code=MAP_ERR_UNKNOWN_SUBSCRIBER)
    
    sub = get_subscriber(imsi)
    roaming = get_roaming_profile(imsi, "")
    supp = get_supplementary_services(imsi)
    
    # Build response with subscriber info
    result_parts = [bytes([0x04, 0x06]) + encode_imsi(imsi)]
    
    if sub and sub.get("msisdn"):
        result_parts.append(bytes([0x04, 0x0A]) + encode_msisdn(sub["msisdn"]))
    
    if roaming:
        result_parts.append(bytes([0x04, 0x02]) + bytes([0x01, 0x00]))  # Roaming allowed
    
    # Add supplementary service info
    for s in supp:
        result_parts.append(bytes([0x04, 0x02]) + s["service_code"].encode())
    
    result_params = b"".join(result_parts)
    return encode_tcap_response(invoke_id, MAP_OP_ANY_TIME_INTERROGATION, result_params)


def handle_psl(parameters: bytes, invoke_id: int) -> bytes:
    """Provide Subscriber Location (MAP_OP_PROVIDE_SUBSCRIBER_INFO with PSL)."""
    imsi = None
    
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT imsi FROM tbl_subscriber LIMIT 100")
        for row in cur.fetchall():
            encoded = encode_imsi(row["imsi"])
            if encoded in parameters:
                imsi = row["imsi"]
                break
    finally:
        conn.close()
    
    if not imsi:
        return encode_tcap_response(invoke_id, MAP_OP_PROVIDE_SUBSCRIBER_INFO, b"", error_code=MAP_ERR_UNKNOWN_SUBSCRIBER)
    
    # Build location info response
    result_params = b"".join([
        bytes([0x04, 0x06]) + encode_imsi(imsi),  # IMSI
        bytes([0x04, 0x04]) + b"CELL-01",  # Cell ID
        bytes([0x04, 0x04]) + b"LAC-01",  # Location Area Code
    ])
    
    return encode_tcap_response(invoke_id, MAP_OP_PROVIDE_SUBSCRIBER_INFO, result_params)


def handle_tcsi(parameters: bytes, invoke_id: int) -> bytes:
    """Terminating CAMEL Subscription Information (TCSI)."""
    # CAMEL TCSI - trigger for terminating calls
    result_params = b"".join([
        bytes([0x30, 0x06]),  # Sequence
        bytes([0x04, 0x02]) + b"\x01\x00",  # Service key
        bytes([0x04, 0x01]) + b"\x03",  # CAMEL phase 3
    ])
    return encode_tcap_response(invoke_id, MAP_OP_ANY_TIME_INTERROGATION, result_params)


def handle_ocsi(parameters: bytes, invoke_id: int) -> bytes:
    """Originating CAMEL Subscription Information (OCSI)."""
    result_params = b"".join([
        bytes([0x30, 0x06]),
        bytes([0x04, 0x02]) + b"\x01\x00",
        bytes([0x04, 0x01]) + b"\x03",
    ])
    return encode_tcap_response(invoke_id, MAP_OP_ANY_TIME_INTERROGATION, result_params)


# MAP operation code -> handler
MAP_HANDLERS = {
    MAP_OP_SEND_ROUTING_INFO_FOR_SM: handle_sri_sm,
    MAP_OP_SAI: handle_sai,
    MAP_OP_ISD: handle_isd,
    MAP_OP_PROVIDE_ROAMING_NUMBER: handle_prn,
    MAP_OP_PROCESS_UNSTRUCTURED_SS_REQUEST: handle_ussd,
    MAP_OP_ACTIVATE_SS: handle_activate_ss,
    MAP_OP_DEACTIVATE_SS: handle_deactivate_ss,
    MAP_OP_INTERROGATE_SS: handle_interrogate_ss,
    MAP_OP_REGISTER_SS: handle_register_ss,
    MAP_OP_ERASE_SS: handle_erase_ss,
    MAP_OP_ANY_TIME_INTERROGATION: handle_any_time_interrogation,
    MAP_OP_PROVIDE_SUBSCRIBER_INFO: handle_psl,
}


# ============================================================================
# SCCP Server (Connectionless)
# ============================================================================

class SCCPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 2905):
        self.host = host
        self.port = port
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        logger.info(f"SCCP/MAP server listening on {self.host}:{self.port}")
        
        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        logger.info(f"SCCP peer connected: {addr}")
        
        try:
            while True:
                # Read message length (SCCP over SCTP/TCP uses length-prefixed)
                len_data = await reader.readexactly(2)
                msg_len = struct.unpack("!H", len_data)[0]
                
                msg_data = await reader.readexactly(msg_len - 2)
                
                # Parse SCCP message
                msg_type = msg_data[0] if msg_data else 0
                
                if msg_type == SCCP_MSG_TYPE_UDT:
                    await self.handle_udt(msg_data, writer)
                else:
                    logger.warning(f"Unknown SCCP message type: {msg_type:#04x}")
                    
        except asyncio.IncompleteReadError:
            logger.info(f"SCCP peer disconnected: {addr}")
        except Exception as e:
            logger.error(f"SCCP error with peer {addr}: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass

    async def handle_udt(self, msg_data: bytes, writer: asyncio.StreamWriter):
        """Handle SCCP Unit Data message."""
        # Called Party Address
        called_addr, offset = decode_pc_address(msg_data, 1)
        # Calling Party Address
        calling_addr, offset = decode_pc_address(msg_data, offset)
        
        # SCCP Data (TCAP payload)
        sccp_data = msg_data[offset:]
        
        # Check if this is MAP (SSN 6)
        called_ssn = called_addr.get("ssn", 0)
        calling_ssn = calling_addr.get("ssn", 0)
        
        if called_ssn == SCCP_SSN_MAP or calling_ssn == SCCP_SSN_MAP:
            self.process_map(sccp_data, called_addr, calling_addr, writer)

    def process_map(self, tcap_data: bytes, called: Dict, calling: Dict, writer: asyncio.StreamWriter):
        """Process MAP over TCAP over SCCP."""
        components = decode_tcap(tcap_data)
        
        for comp in components:
            op_code = comp.get("operation_code")
            invoke_id = comp.get("invoke_id")
            comp_data = comp.get("data", b"")
            
            if op_code in MAP_HANDLERS:
                handler = MAP_HANDLERS[op_code]
                try:
                    response = handler(comp_data, invoke_id)
                    self.send_map_response(response, called, calling, writer)
                except Exception as e:
                    logger.error(f"MAP handler error for op={op_code}: {e}")
                    error_resp = encode_tcap_response(invoke_id or 0, op_code or 0, b"", error_code=MAP_ERR_SYSTEM_FAILURE)
                    self.send_map_response(error_resp, called, calling, writer)
            else:
                logger.warning(f"Unhandled MAP operation: {op_code}")

    def send_map_response(self, tcap_response: bytes, called: Dict, calling: Dict, writer: asyncio.StreamWriter):
        """Send MAP response back via SCCP."""
        # Build SCCP UDT with reversed addresses
        called_bytes = encode_pc_address(
            0,  # No PC for now
            called.get("ssn", SCCP_SSN_MAP),
            called.get("global_title")
        )
        calling_bytes = encode_pc_address(
            0,
            calling.get("ssn", SCCP_SSN_MAP),
            calling.get("global_title")
        )
        
        sccp_msg = bytes([SCCP_MSG_TYPE_UDT]) + called_bytes + calling_bytes + tcap_response
        msg_len = len(sccp_msg) + 2  # Include length prefix
        
        writer.write(struct.pack("!H", msg_len) + sccp_msg)
        # Note: In real implementation, we'd need to track the connection properly


# ============================================================================
# Main
# ============================================================================

async def main():
    server = SCCPServer(host="0.0.0.0", port=map_config.port)
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())