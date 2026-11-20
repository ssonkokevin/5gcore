"""Minimal but correct Diameter base (RFC 6733) codec and TCP server.

Only what the custom nodes need: header framing, AVP encode/decode with
vendor and padding rules, grouped AVPs, and an asyncio server that reads one
message at a time from a stream. SCTP transport belongs to the STP layer.

The codec here is deliberately independent of diameter/src/diameter_server.py,
which predates it and mislabels the AVP V/M bits.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("diameter")

HEADER_LEN = 20
VERSION = 1

# Message flags
FLAG_REQUEST = 0x80
FLAG_PROXYABLE = 0x40
FLAG_ERROR = 0x20
FLAG_RETRANSMITTED = 0x10

# AVP flags
AVP_FLAG_VENDOR = 0x80
AVP_FLAG_MANDATORY = 0x40

# Application identifiers
APP_DIAMETER_COMMON = 0
APP_CX = 16777216     # TS 29.228/29.229 Cx/Dx
APP_SH = 16777217     # TS 29.328/29.329 Sh/Dh
APP_S6A = 16777251    # TS 29.272 S6a/S6d
APP_GX = 16777238
APP_SLG = 16777255
APP_SLH = 16777291
APP_GY = 4

# Command codes
CMD_CAPABILITIES_EXCHANGE = 257
CMD_DEVICE_WATCHDOG = 280
CMD_DISCONNECT_PEER = 282
CMD_PLR = 8388620   # SLg Provide-Location-Request / Answer
CMD_RIR = 8388622   # SLh Routing-Info-Request / Answer

# Base AVPs
AVP_USER_NAME = 1
AVP_RESULT_CODE = 268
AVP_SESSION_ID = 263
AVP_ORIGIN_HOST = 264
AVP_ORIGIN_REALM = 296
AVP_DESTINATION_HOST = 293
AVP_DESTINATION_REALM = 283
AVP_AUTH_SESSION_STATE = 277
AVP_ERROR_MESSAGE = 281
AVP_VENDOR_SPECIFIC_APPLICATION_ID = 260
AVP_VENDOR_ID = 266
AVP_SUPPORTED_VENDOR_ID = 265
AVP_ACCT_APPLICATION_ID = 259
AVP_ORIGIN_STATE_ID = 278
AVP_PRODUCT_NAME = 269
AVP_FIRMWARE_REVISION = 267
AVP_MSISDN = 701

# Result codes
RESULT_SUCCESS = 2001
RESULT_LIMITED_SUCCESS = 2002
RESULT_UNABLE_TO_COMPLY = 5012
RESULT_AUTHORIZATION_REJECTED = 5003
RESULT_UNKNOWN_APPLICATION = 5001
RESULT_INVALID_AVP_VALUE = 5004
RESULT_MISSING_AVP = 5005
RESULT_NO_COMMON_APPLICATION = 5010
RESULT_COMMAND_UNSUPPORTED = 3001
RESULT_REALM_NOT_SERVED = 3003
RESULT_APPLICATION_UNSUPPORTED = 3007


class DiameterError(Exception):
    pass


@dataclass
class AVP:
    code: int
    value: bytes = b""
    vendor_id: int = 0
    mandatory: bool = True
    _raw_payload_len: int = field(default=0, repr=False)

    def encode(self) -> bytes:
        flags = 0
        if self.vendor_id:
            flags |= AVP_FLAG_VENDOR
        if self.mandatory:
            flags |= AVP_FLAG_MANDATORY
        pad = b"\x00" * (-len(self.value) % 4)
        length = 8 + (4 if self.vendor_id else 0) + len(self.value) + len(pad)
        out = struct.pack("!II", (self.code << 8) | flags, length)
        if self.vendor_id:
            out += struct.pack("!I", self.vendor_id)
        return out + self.value + pad

    # --- value helpers -----------------------------------------------------
    def as_uint32(self) -> int:
        raw = self.value[:4]
        if len(raw) != 4:
            raise DiameterError(f"AVP {self.code}: expected Unsigned32")
        return struct.unpack("!I", raw)[0]

    def as_int32(self) -> int:
        raw = self.value[:4]
        if len(raw) != 4:
            raise DiameterError(f"AVP {self.code}: expected Integer32")
        return struct.unpack("!i", raw)[0]

    def as_string(self) -> str:
        return self.value.rstrip(b"\x00").decode("utf-8", "replace")

    def as_octets(self) -> bytes:
        return self.value

    def as_grouped(self) -> List["AVP"]:
        return decode_avps(self.value)


def AVP_UTF8(code: int, text: str, vendor_id: int = 0, mandatory: bool = True) -> AVP:
    return AVP(code, text.encode("utf-8"), vendor_id, mandatory)


def AVP_U32(code: int, value: int, vendor_id: int = 0, mandatory: bool = True) -> AVP:
    return AVP(code, struct.pack("!I", value), vendor_id, mandatory)


def AVP_GROUPED(code: int, avps: List[AVP], vendor_id: int = 0, mandatory: bool = True) -> AVP:
    return AVP(code, b"".join(a.encode() for a in avps), vendor_id, mandatory)


def decode_avps(payload: bytes) -> List[AVP]:
    avps: List[AVP] = []
    offset = 0
    while offset + 8 <= len(payload):
        code_flags, length = struct.unpack("!II", payload[offset:offset + 8])
        code = code_flags >> 8
        flags = code_flags & 0xFF
        if length < 8 or offset + length > len(payload):
            break
        cursor = offset + 8
        vendor_id = 0
        if flags & AVP_FLAG_VENDOR:
            if cursor + 4 > offset + length:
                break
            vendor_id = struct.unpack("!I", payload[cursor:cursor + 4])[0]
            cursor += 4
        data = payload[cursor:offset + length]
        avps.append(
            AVP(
                code=code,
                value=data,
                vendor_id=vendor_id,
                mandatory=bool(flags & AVP_FLAG_MANDATORY),
                _raw_payload_len=len(data),
            )
        )
        offset += length
    return avps


@dataclass
class Message:
    command_code: int
    app_id: int
    avps: List[AVP] = field(default_factory=list)
    flags: int = FLAG_REQUEST | FLAG_PROXYABLE
    hop_by_hop: int = 0
    end_to_end: int = 0

    def encode(self) -> bytes:
        body = b"".join(a.encode() for a in self.avps)
        length = HEADER_LEN + len(body)
        header = (
            struct.pack("!B", VERSION)
            + length.to_bytes(3, "big")
            + struct.pack("!B", self.flags)
            + (self.command_code & 0xFFFFFF).to_bytes(3, "big")
            + struct.pack("!III", self.app_id, self.hop_by_hop, self.end_to_end)
        )
        return header + body

    @property
    def is_request(self) -> bool:
        return bool(self.flags & FLAG_REQUEST)

    def avp(self, code: int) -> Optional[AVP]:
        for a in self.avps:
            if a.code == code:
                return a
        return None

    def all_avps(self, code: int) -> List[AVP]:
        return [a for a in self.avps if a.code == code]

    def summary(self) -> Dict[str, object]:
        out: Dict[str, object] = {}
        for code in (AVP_SESSION_ID, AVP_USER_NAME, AVP_MSISDN,
                     AVP_ORIGIN_HOST, AVP_DESTINATION_REALM, AVP_RESULT_CODE):
            avp = self.avp(code)
            if avp is None:
                continue
            out[{AVP_SESSION_ID: "session_id", AVP_USER_NAME: "user_name",
                 AVP_MSISDN: "msisdn", AVP_ORIGIN_HOST: "origin_host",
                 AVP_DESTINATION_REALM: "destination_realm",
                 AVP_RESULT_CODE: "result_code"}[code]] = (
                avp.as_uint32() if code == AVP_RESULT_CODE else avp.as_string()
            )
        out["avp_codes"] = [a.code for a in self.avps]
        return out


def decode_message(data: bytes) -> Message:
    if len(data) < HEADER_LEN:
        raise DiameterError("message shorter than the 20-octet header")
    version = data[0]
    if version != VERSION:
        raise DiameterError(f"unsupported Diameter version {version}")
    length = int.from_bytes(data[1:4], "big")
    if length < HEADER_LEN or length != len(data):
        raise DiameterError(f"length field {length} does not match {len(data)} octets")
    flags = data[4]
    command_code = int.from_bytes(data[5:8], "big")
    app_id, hop_by_hop, end_to_end = struct.unpack("!III", data[8:20])
    return Message(
        command_code=command_code,
        app_id=app_id,
        avps=decode_avps(data[HEADER_LEN:length]),
        flags=flags,
        hop_by_hop=hop_by_hop,
        end_to_end=end_to_end,
    )


def answer(request: Message, result_code: int, origin_host: str, origin_realm: str,
           error_message: Optional[str] = None, extra: Optional[List[AVP]] = None,
           destination_host: Optional[str] = None,
           destination_realm: Optional[str] = None) -> Message:
    """Build an answer. Origin-* name this node; Destination-Realm defaults to
    the realm the request came from."""
    avps: List[AVP] = []
    session = request.avp(AVP_SESSION_ID)
    if session is not None:
        avps.append(session)
    avps.append(AVP_UTF8(AVP_ORIGIN_HOST, origin_host))
    avps.append(AVP_UTF8(AVP_ORIGIN_REALM, origin_realm))
    requester_realm = destination_realm
    if requester_realm is None:
        origin_realm_avp = request.avp(AVP_ORIGIN_REALM)
        requester_realm = origin_realm_avp.as_string() if origin_realm_avp else None
    if requester_realm:
        avps.append(AVP_UTF8(AVP_DESTINATION_REALM, requester_realm))
    if destination_host is None:
        origin_host_avp = request.avp(AVP_ORIGIN_HOST)
        destination_host = origin_host_avp.as_string() if origin_host_avp else None
    if destination_host:
        avps.append(AVP_UTF8(AVP_DESTINATION_HOST, destination_host))
    state = request.avp(AVP_AUTH_SESSION_STATE)
    if state is not None:
        avps.append(state)
    avps.append(AVP_U32(AVP_RESULT_CODE, result_code, mandatory=True))
    if result_code >= 3000 and error_message:
        avps.append(AVP_UTF8(AVP_ERROR_MESSAGE, error_message, mandatory=False))
    if extra:
        avps.extend(extra)
    return Message(
        command_code=request.command_code,
        app_id=request.app_id,
        avps=avps,
        flags=request.flags & ~FLAG_REQUEST,
        hop_by_hop=request.hop_by_hop,
        end_to_end=request.end_to_end,
    )


async def read_message(reader: asyncio.StreamReader) -> Optional[bytes]:
    try:
        header = await reader.readexactly(HEADER_LEN)
    except asyncio.IncompleteReadError:
        return None
    length = int.from_bytes(header[1:4], "big")
    if length < HEADER_LEN or length > 65535:
        raise DiameterError(f"invalid message length {length}")
    body = b""
    remaining = length - HEADER_LEN
    while remaining:
        chunk = await reader.read(remaining)
        if not chunk:
            return None
        body += chunk
        remaining -= len(chunk)
    return header + body


class DiameterServer:
    """One request/answer per message; unknown peers are still answered so the
    peer gets a real error instead of a hang."""

    def __init__(self, host: str, port: int, handler: Callable[[Message], Optional[Message]],
                 name: str = "diameter"):
        self.host = host
        self.port = port
        self.handler = handler
        self.name = name
        self._server: Optional[asyncio.AbstractServer] = None
        self.connected_peers = 0
        self.messages_in = 0
        self.messages_out = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, self.host, self.port)
        logger.info("%s listening on %s:%s (TCP)", self.name, self.host, self.port)

    async def _serve(self, reader: asyncio.StreamReader,
                     writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        self.connected_peers += 1
        try:
            while True:
                raw = await read_message(reader)
                if raw is None:
                    break
                self.messages_in += 1
                try:
                    request = decode_message(raw)
                except DiameterError as exc:
                    logger.warning("%s: dropping malformed message from %s: %s",
                                   self.name, peer, exc)
                    break
                response = self.handler(request)
                if response is None:
                    continue
                writer.write(response.encode())
                await writer.drain()
                self.messages_out += 1
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self.connected_peers -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                pass

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def stats(self) -> Dict[str, int]:
        return {
            "connected_peers": self.connected_peers,
            "messages_in": self.messages_in,
            "messages_out": self.messages_out,
        }
