#!/usr/bin/env python3
"""
OCS/Gy Client - Online Charging System (RFC 4006, TS 32.299)

Implements Diameter Credit-Control Application (Gy interface):
- CCR-I (Credit-Control Request Initial)
- CCR-U (Credit-Control Request Update)
- CCR-T (Credit-Control Request Terminate)
- CCA (Credit-Control Answer)

Used by PCF/CHF for real-time credit control during PDU sessions.
"""

import asyncio
import logging
import os
import secrets
import struct
import json
import time
from typing import Optional, Dict, List, Tuple

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger("ocs-gy")

# ============================================================================
# Diameter Credit-Control Constants (RFC 4006)
# ============================================================================

# Command Codes
CCR_CC = 272  # Credit-Control Request/Answer
CCA_CC = 272

# Application ID
APP_3GPP_Gy = 16777238  # 3GPP Gy

# CC-Request-Type
CCR_TYPE_INITIAL = 1
CCR_TYPE_UPDATE = 2
CCR_TYPE_TERMINATE = 3
CCR_TYPE_EVENT = 4

# CC-Request-Number
CC_REQUEST_NUMBER_INITIAL = 0

# AVP Codes (Credit-Control)
AVP_CC_REQUEST_TYPE = 416
AVP_CC_REQUEST_NUMBER = 415
AVP_CC_SESSION_FAILOVER = 417
AVP_CC_MULTIPLE_SERVICE_INDICATOR = 456
AVP_CC_RESULT_CODE = 268  # Result-Code (base)
AVP_CC_ORIGIN_HOST = 264
AVP_CC_ORIGIN_REALM = 296
AVP_CC_DESTINATION_HOST = 293
AVP_CC_DESTINATION_REALM = 283
AVP_CC_AUTH_APPLICATION_ID = 258
AVP_CC_USER_NAME = 1
AVP_CC_SUBSCRIPTION_ID = 443
AVP_CC_SUBSCRIPTION_ID_TYPE = 450
AVP_CC_SERVICE_IDENTIFIER = 439
AVP_CC_SERVICE_CONTEXT_ID = 461
AVP_CC_REQUESTED_ACTION = 436
AVP_CC_REQUESTED_SERVICE_UNIT = 437
AVP_CC_USED_SERVICE_UNIT = 438
AVP_CC_TARIFF_CHANGE = 452
AVP_CC_VALIDITY_TIME = 448
AVP_CC_RE_VALIDATION_TIME = 449
AVP_CC_SERVICE_IDENTIFIER_2 = 439
AVP_CC_RATING_GROUP = 432
AVP_CC_CHARGING_RULE_NAME = 1432
AVP_CC_GSU_TARIFF_CHANGE = 452
AVP_CC_GSU_TIMESTAMP = 453
AVP_CC_GSU_CCN_TOTAL = 454
AVP_CC_GSU_CCN_INPUT_OCTETS = 451
AVP_CC_GSU_CCN_OUTPUT_OCTETS = 452
AVP_CC_GSU_SERVICE_SPECIFIC_UNITS = 447
AVP_CC_COST_INFORMATION = 445
AVP_CC_COST_UNIT = 446
AVP_CC_COST_VALUE = 448
AVP_CC_CURRENCY_CODE = 445
AVP_CC_TRUNK_GROUP_ID = 449
AVP_CC_TRUNK_GROUP_ID_2 = 450
AVP_CC_USER_SESSION_ID = 431
AVP_CC_CALLING_SESSION_ID = 430
AVP_CC_CALLED_SESSION_ID = 431
AVP_CC_FAILURE_HANDLING = 437
AVP_CC_POLICY_COUNTER = 449
AVP_CC_POLICY_COUNTER_2 = 450
AVP_CC_ACCOUNTING_INPUT_OCTETS = 1402  # Acct-Input-Octets
AVP_CC_ACCOUNTING_OUTPUT_OCTETS = 1403  # Acct-Output-Octets
AVP_CC_ACCOUNTING_INPUT_PACKETS = 1404  # Acct-Input-Packets
AVP_CC_ACCOUNTING_OUTPUT_PACKETS = 1405  # Acct-Output-Packets
AVP_CC_ACCOUNTING_SESSION_ID = 44  # Acct-Session-Id
AVP_CC_ACCOUNTING_RECORD_TYPE = 48  # Acct-Record-Type
AVP_CC_ACCOUNTING_RECORD_NUMBER = 43  # Acct-Record-Number
AVP_CC_ACCOUNTING_INTERIM_INTERVAL = 85  # Acct-Interim-Interval

# AVP Codes for Multiple-Services-Credit-Control (MSCC)
AVP_CC_MSCC = 456  # Multiple-Services-Credit-Control
AVP_CC_MSCC_REQUESTED_SERVICE_UNIT = 437
AVP_CC_MSCC_USED_SERVICE_UNIT = 438
AVP_CC_MSCC_TARIFF_CHANGE = 452
AVP_CC_MSCC_SERVICE_IDENTIFIER = 439
AVP_CC_MSCC_RATING_GROUP = 432
AVP_CC_MSCC_VALIDITY_TIME = 448
AVP_CC_MSCC_RE_VALIDATION_TIME = 449
AVP_CC_MSCC_GRANTED_SERVICE_UNIT = 430  # Granted-Service-Unit
AVP_CC_MSCC_GSU_TOTAL_CCM = 430
AVP_CC_MSCC_GSU_CCN_INPUT_OCTETS = 451
AVP_CC_MSCC_GSU_CCN_OUTPUT_OCTETS = 452
AVP_CC_MSCC_GSU_SERVICE_SPECIFIC_UNITS = 447
AVP_CC_MSCC_GSU_TARIFF_CHANGE = 452
AVP_CC_MSCC_COST_INFORMATION = 445

# Result Codes
CCA_RESULT_CODE_SUCCESS = 2001
CCA_RESULT_CODE_SUCCESS_LIMITED_SUCCESS = 2002
CCA_RESULT_CODE_DIAMETER_UNABLE_TO_COMPLY = 5012
CCA_RESULT_CODE_DIAMETER_AUTHENTICATION_REJECTED = 5001
CCA_RESULT_CODE_DIAMETER_CREDIT_CONTROL_NOT_APPLICABLE = 4011
CCA_RESULT_CODE_DIAMETER_CREDIT_LIMIT_REACHED = 4012
CCA_RESULT_CODE_DIAMETER_USER_UNKNOWN = 5003
CCA_RESULT_CODE_DIAMETER_RATING_FAILED = 4010
CCA_RESULT_CODE_DIAMETER_MISSING_SESSION_ID = 4013
CCA_RESULT_CODE_DIAMETER_UNKNOWN_SESSION_ID = 5004

# Failure Handling
FAILURE_HANDLING_TERMINATE = 1
FAILURE_HANDLING_CONTINUE = 2
FAILURE_HANDLING_RETRY_AND_TERMINATE = 3
FAILURE_HANDLING_RETRY_AND_CONTINUE = 4

# Credit-Control-Failure-Handling (CCFF)
CCFF_TERMINATE = 0x01
CCFF_CONTINUE = 0x02

# ============================================================================
# OCS Configuration
# ============================================================================

class OCSConfig:
    def __init__(self):
        self.origin_host = os.getenv("OCS_ORIGIN_HOST", "ocs.core.local")
        self.origin_realm = os.getenv("OCS_ORIGIN_REALM", "core.local")
        self.vendor_id = int(os.getenv("OCS_VENDOR_ID", "10415"))
        self.product_name = os.getenv("OCS_PRODUCT_NAME", "5G-Core-OCS")
        self.host = os.getenv("OCS_HOST", "0.0.0.0")
        self.port = int(os.getenv("OCS_PORT", "3869"))
        self.failure_handling = int(os.getenv("OCS_FAILURE_HANDLING", "2"))  # CONTINUE
        self.session_timeout = int(os.getenv("OCS_SESSION_TIMEOUT", "300"))  # 5 minutes


ocs_config = OCSConfig()


# ============================================================================
# AVP Encoding/Decoding (Same as Diameter server)
# ============================================================================

def encode_avp(code: int, flags: int, vendor_id: int, data: bytes) -> bytes:
    """Encode a Diameter AVP."""
    avp_len = 8 + len(data)
    header = struct.pack("!I", (code << 8) | flags)
    header += struct.pack("!I", avp_len)
    header += struct.pack("!I", vendor_id)
    return header + data


def encode_uint32_avp(code: int, value: int, vendor_id: int = 0, mandatory: bool = True) -> bytes:
    """Encode an unsigned 32-bit AVP."""
    flags = 0x80 if mandatory else 0x00
    data = struct.pack("!I", value)
    return encode_avp(code, flags, vendor_id, data)


def encode_utf8_avp(code: int, value: str, vendor_id: int = 0, mandatory: bool = True) -> bytes:
    """Encode a UTF8String AVP."""
    flags = 0x80 if mandatory else 0x00
    data = value.encode('utf-8')
    return encode_avp(code, flags, vendor_id, data)


def encode_grouped_avp(code: int, sub_avps: bytes, vendor_id: int = 0, mandatory: bool = True) -> bytes:
    """Encode a Grouped AVP."""
    flags = 0x80 if mandatory else 0x00
    return encode_avp(code, flags, vendor_id, sub_avps)


def decode_avp(data: bytes, offset: int = 0) -> Tuple[int, int, int, int, bytes]:
    """Decode a Diameter AVP."""
    avp_code = struct.unpack("!I", data[offset:offset+4])[0]
    code = (avp_code >> 8) & 0xFFFFFF
    flags = (avp_code >> 24) & 0xFF
    avp_len = struct.unpack("!I", data[offset+4:offset+8])[0]
    vendor_id = struct.unpack("!I", data[offset+8:offset+12])[0] if (flags & 0x80) else 0
    has_vendor = bool(flags & 0x80)
    base_len = 12 if has_vendor else 8
    avp_data = data[offset+base_len:offset+avp_len]
    next_offset = offset + avp_len
    return code, flags, avp_len, vendor_id, avp_data, next_offset


def decode_all_avps(data: bytes) -> List[Dict]:
    """Decode all AVPs in a Diameter message."""
    avps = []
    offset = 20  # Skip Diameter header
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


def avp_get_uint32(avp_data: bytes) -> int:
    return struct.unpack("!I", avp_data)[0]


def avp_get_utf8(avp_data: bytes) -> str:
    return avp_data.decode('utf-8')


# ============================================================================
# Diameter Message Building
# ============================================================================

def build_diameter_header(command_code: int, flags: int, app_id: int, hop_by_hop: int, end_to_end: int) -> bytes:
    hdr = struct.pack("!I", (command_code << 8) | flags)
    hdr += struct.pack("!I", app_id)
    hdr += struct.pack("!I", hop_by_hop)
    hdr += struct.pack("!I", end_to_end)
    return hdr


def build_diameter_message(command_code: int, flags: int, app_id: int, avps: List[bytes]) -> bytes:
    hop_by_hop = secrets.randbits(32)
    end_to_end = secrets.randbits(32)
    body = b"".join(avps)
    hdr = build_diameter_header(command_code, flags, app_id, hop_by_hop, end_to_end)
    return hdr + body


# ============================================================================
# OCS Credit-Control Client
# ============================================================================

class CreditControlSession:
    """Represents a credit-control session for a subscriber."""
    
    def __init__(self, session_id: str, imsi: str, service_context_id: str):
        self.session_id = session_id
        self.imsi = imsi
        self.service_context_id = service_context_id
        self.cc_request_number = 0
        self.granted_units = 0
        self.used_units = 0
        self.validity_time = 0
        self.re_validation_time = 0
        self.final_unit_indication = False
        self.active = True
        self.created_at = time.time()
    
    def next_cc_request_number(self) -> int:
        self.cc_request_number += 1
        return self.cc_request_number


class OCSClient:
    """OCS/Gy Credit-Control Client."""
    
    def __init__(self, ocs_host: str = "ocs.core.local", ocs_port: int = 3869):
        self.ocs_host = ocs_host
        self.ocs_port = ocs_port
        self.sessions: Dict[str, CreditControlSession] = {}
        self.writer: Optional[asyncio.StreamWriter] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.connected = False
    
    async def connect(self):
        """Connect to OCS server."""
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.ocs_host, self.ocs_port
            )
            self.connected = True
            logger.info(f"OCS client connected to {self.ocs_host}:{self.ocs_port}")
            
            # Send CER
            await self.send_capabilities_exchange()
        except Exception as e:
            logger.error(f"OCS connection failed: {e}")
            self.connected = False
    
    async def disconnect(self):
        """Disconnect from OCS server."""
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except:
                pass
        self.connected = False
    
    async def send_capabilities_exchange(self):
        """Send CER (Capabilities Exchange Request)."""
        avps = [
            encode_uint32_avp(AVP_CC_RESULT_CODE, CCA_RESULT_CODE_SUCCESS),
            encode_uint32_avp(AVP_CC_AUTH_APPLICATION_ID, APP_3GPP_Gy),
            encode_uint32_avp(AVP_CC_VENDOR_ID := 266, ocs_config.vendor_id),
            encode_utf8_avp(AVP_CC_PRODUCT_NAME := 269, ocs_config.product_name),
            encode_uint32_avp(AVP_CC_ORIGIN_STATE_ID := 278, secrets.randbits(32)),
            encode_utf8_avp(AVP_CC_ORIGIN_HOST, ocs_config.origin_host),
            encode_utf8_avp(AVP_CC_ORIGIN_REALM, ocs_config.origin_realm),
        ]
        
        msg = build_diameter_message(CCR_CC, 0x80, APP_3GPP_Gy, avps)
        if self.writer:
            self.writer.write(msg)
            await self.writer.drain()
    
    def create_session(self, imsi: str, service_context_id: str) -> str:
        """Create a new credit-control session."""
        session_id = f"ocs-{secrets.token_hex(16)}"
        session = CreditControlSession(session_id, imsi, service_context_id)
        self.sessions[session_id] = session
        return session_id
    
    async def send_ccr(self, session_id: str, cc_request_type: int,
                       requested_units: Optional[Dict] = None,
                       service_identifier: Optional[str] = None,
                       rating_group: Optional[int] = None) -> Optional[Dict]:
        """Send Credit-Control Request (CCR-I/U/T)."""
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return None
        
        if not self.connected:
            await self.connect()
        
        cc_request_number = session.next_cc_request_number()
        
        avps = [
            encode_uint32_avp(AVP_CC_RESULT_CODE, CCA_RESULT_CODE_SUCCESS),  # Placeholder
            encode_uint32_avp(AVP_CC_AUTH_APPLICATION_ID, APP_3GPP_Gy),
            encode_utf8_avp(AVP_CC_ORIGIN_HOST, ocs_config.origin_host),
            encode_utf8_avp(AVP_CC_ORIGIN_REALM, ocs_config.origin_realm),
            encode_uint32_avp(AVP_CC_CC_REQUEST_TYPE, cc_request_type),
            encode_uint32_avp(AVP_CC_CC_REQUEST_NUMBER, cc_request_number),
            encode_utf8_avp(AVP_CC_SUBSCRIPTION_ID_TYPE, "1"),  # END_USER_E164
            encode_grouped_avp(AVP_CC_SUBSCRIPTION_ID, b"".join([
                encode_uint32_avp(450, 1),  # Subscription-ID-Type
                encode_utf8_avp(444, session.imsi),  # Subscription-ID-Value
            ])),
            encode_utf8_avp(AVP_CC_USER_NAME, session.imsi),
            encode_utf8_avp(AVP_CC_SERVICE_CONTEXT_ID, session.service_context_id),
        ]
        
        if service_identifier:
            avps.append(encode_utf8_avp(AVP_CC_SERVICE_IDENTIFIER, service_identifier))
        
        if rating_group is not None:
            avps.append(encode_uint32_avp(AVP_CC_RATING_GROUP, rating_group))
        
        if requested_units:
            # Multiple-Services-Credit-Control grouped AVP
            mscc_avps = []
            if requested_units.get("cc_input_octets") is not None:
                mscc_avps.append(encode_uint32_avp(AVP_CC_MSCC_GSU_CCN_INPUT_OCTETS, requested_units["cc_input_octets"]))
            if requested_units.get("cc_output_octets") is not None:
                mscc_avps.append(encode_uint32_avp(AVP_CC_MSCC_GSU_CCN_OUTPUT_OCTETS, requested_units["cc_output_octets"]))
            if requested_units.get("cc_time") is not None:
                mscc_avps.append(encode_uint32_avp(AVP_CC_MSCC_GSU_TOTAL_CCM, requested_units["cc_time"]))
            
            if mscc_avps:
                avps.append(encode_grouped_avp(AVP_CC_MSCC, b"".join(mscc_avps)))
        
        msg = build_diameter_message(CCR_CC, 0x80, APP_3GPP_Gy, avps)
        
        if self.writer:
            self.writer.write(msg)
            await self.writer.drain()
            
            # Read response (with timeout)
            try:
                header_data = await asyncio.wait_for(self.reader.readexactly(20), timeout=5.0)
                cmd_flags_len = struct.unpack("!I", header_data[0:4])[0]
                command_code = (cmd_flags_len >> 8) & 0xFFFFFF
                msg_len = struct.unpack("!I", header_data[4:8])[0]
                
                body_len = msg_len - 20
                if body_len > 0:
                    body_data = await asyncio.wait_for(self.reader.readexactly(body_len), timeout=5.0)
                else:
                    body_data = b""
                
                avps_response = decode_all_avps(body_data)
                
                result_code = None
                granted_units = None
                validity_time = None
                final_unit = False
                
                for avp in avps_response:
                    if avp["code"] == AVP_CC_RESULT_CODE:
                        result_code = avp_get_uint32(avp["data"])
                    elif avp["code"] == AVP_CC_MSCC_GSU_TOTAL_CCM:
                        granted_units = avp_get_uint32(avp["data"])
                    elif avp["code"] == AVP_CC_MSCC_VALIDITY_TIME:
                        validity_time = avp_get_uint32(avp["data"])
                
                session.granted_units = granted_units or 0
                session.validity_time = validity_time or 0
                
                return {
                    "result_code": result_code,
                    "granted_units": granted_units,
                    "validity_time": validity_time,
                    "final_unit_indication": final_unit,
                }
            except asyncio.TimeoutError:
                logger.error("OCS response timeout")
                return None
        
        return None
    
    async def credit_control_initial(self, session_id: str,
                                     requested_units: Optional[Dict] = None,
                                     service_identifier: Optional[str] = None,
                                     rating_group: Optional[int] = None) -> Optional[Dict]:
        """Send CCR-I (Initial)."""
        return await self.send_ccr(session_id, CCR_TYPE_INITIAL, requested_units, service_identifier, rating_group)
    
    async def credit_control_update(self, session_id: str,
                                    requested_units: Optional[Dict] = None,
                                    service_identifier: Optional[str] = None,
                                    rating_group: Optional[int] = None) -> Optional[Dict]:
        """Send CCR-U (Update)."""
        return await self.send_ccr(session_id, CCR_TYPE_UPDATE, requested_units, service_identifier, rating_group)
    
    async def credit_control_terminate(self, session_id: str) -> Optional[Dict]:
        """Send CCR-T (Terminate)."""
        return await self.send_ccr(session_id, CCR_TYPE_TERMINATE)
    
    def close_session(self, session_id: str):
        """Close a credit-control session."""
        if session_id in self.sessions:
            del self.sessions[session_id]


# Global OCS client instance
ocs_client = OCSClient()


# ============================================================================
# Convenience Functions
# ============================================================================

async def ocs_credit_control_init(imsi: str, service_context_id: str,
                                  requested_units: Optional[Dict] = None,
                                  service_identifier: Optional[str] = None,
                                  rating_group: Optional[int] = None) -> Optional[Dict]:
    """Initialize credit control session and send CCR-I."""
    session_id = ocs_client.create_session(imsi, service_context_id)
    result = await ocs_client.credit_control_initial(session_id, requested_units, service_identifier, rating_group)
    return result


async def ocs_credit_control_update(session_id: str,
                                     requested_units: Optional[Dict] = None,
                                     service_identifier: Optional[str] = None,
                                     rating_group: Optional[int] = None) -> Optional[Dict]:
    """Send CCR-U (Update)."""
    return await ocs_client.credit_control_update(session_id, requested_units, service_identifier, rating_group)


async def ocs_credit_control_terminate(session_id: str) -> Optional[Dict]:
    """Send CCR-T (Terminate)."""
    return await ocs_client.credit_control_terminate(session_id)


async def ocs_connect():
    """Connect to OCS server."""
    await ocs_client.connect()


async def ocs_disconnect():
    """Disconnect from OCS server."""
    await ocs_client.disconnect()