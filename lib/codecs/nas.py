"""The slice of EPS NAS (TS 24.301) the MME needs to learn a subscriber.

An MME learns which subscriber an S1AP connection belongs to from the NAS
Attach Request the UE sends in InitialUEMessage. This module reads exactly
that: the protocol discriminator (TS 24.007, EPS mobility management is
0x7), the security header type (9.3.1, plain), the message type (9.8, Attach
request is 0x41) and the EPS mobile identity (9.9.3.12), which is the only
place an unprotected Attach Request carries the IMSI.

Only the mandatory prefix of the message is read. The Attach Request's
mandatory IEs are EPS attach type and NAS key set identifier (half octets
sharing octet 3), then the EPS mobile identity in the LV format - length
octet, then the identity. Everything after the identity (UE network
capability, ESM container, optional IEs) is untouched.

A GUTI or an IMEI is not an IMSI. This module returns None for those rather
than guess a subscriber; the MME must then use a context it already has.
This is not a NAS stack: no attach procedure, no authentication, no ESM.
"""

from __future__ import annotations

from typing import Optional

PROTOCOL_DISCRIMINATOR_EMM = 0x07
SECURITY_HEADER_PLAIN = 0x00
ATTACH_REQUEST = 0x41

IDENTITY_IMSI = 0b001
IDENTITY_GUTI = 0b110
IDENTITY_IMEI = 0b011

# Octet 3 of an Attach Request: EPS attach type (bits 1-4: spare 0, value
# 001) and NAS key set identifier (bits 5-8: TSC 0, KSI 111 = no key). Both
# are V half-octets, so they share this octet and no IEI byte precedes them.
ATTACH_TYPE_AND_KSI = 0x71

MAX_IMSI_DIGITS = 15


class NasError(ValueError):
    """The bytes are not a NAS message this implementation can read."""


def _pack_digits(digits: str) -> bytes:
    """Pack identity digits the way figure 9.9.3.12.2 does: the first digit
    in the high nibble of octet 3, the rest two per octet, low nibble first,
    with a 0xF end mark when the count is even."""
    out = bytearray()
    rest = digits[1:]
    for index in range(0, len(rest), 2):
        low = int(rest[index])
        high = int(rest[index + 1]) if index + 1 < len(rest) else 0xF
        out.append((high << 4) | low)
    return bytes(out)


def attach_request(imsi: str, *, attach_type: int = 0x1) -> bytes:
    """A plain Attach Request that carries `imsi` in the EPS mobile identity.

    This is what a lab UE sends to an MME. The attach type defaults to
    "EPS attach"; the key set is "no key available", as on a first attach.
    """
    if not isinstance(imsi, str) or not imsi.isascii() or not imsi.isdigit():
        raise NasError("an IMSI is ASCII decimal digits")
    if not 6 <= len(imsi) <= MAX_IMSI_DIGITS:
        raise NasError(f"an IMSI is 6..{MAX_IMSI_DIGITS} digits, not {len(imsi)}")
    if not 0 < attach_type < 8:
        raise NasError(f"EPS attach type {attach_type} is not 1..7")
    odd = len(imsi) % 2 == 1
    octet3 = (int(imsi[0]) << 4) | (0x08 if odd else 0x00) | IDENTITY_IMSI
    contents = bytes([octet3]) + _pack_digits(imsi)
    header = bytes([PROTOCOL_DISCRIMINATOR_EMM,
                    ATTACH_REQUEST,
                    (ATTACH_TYPE_AND_KSI & 0xF0) | attach_type])
    return header + bytes([len(contents)]) + contents


def imsi_from_attach_request(nas_pdu: bytes) -> Optional[str]:
    """The IMSI an Attach Request carries, or None when it carries another
    identity (GUTI, IMEI) or is not a plain Attach Request.

    A security-protected message hides the identity behind the header, so it
    returns None too; the MME cannot read it without its security context.
    """
    data = bytes(nas_pdu)
    if len(data) < 4:
        raise NasError("an Attach Request is at least four octets")
    if data[0] & 0x0F != PROTOCOL_DISCRIMINATOR_EMM:
        return None
    if data[0] >> 4 != SECURITY_HEADER_PLAIN:
        return None
    if data[1] != ATTACH_REQUEST:
        return None
    length = data[3]
    if not 3 <= length <= 12:
        raise NasError(f"an EPS mobile identity is 3..12 octets, not {length}")
    if len(data) < 4 + length:
        raise NasError("the EPS mobile identity runs past the message")
    identity = data[4:4 + length]
    type_of_identity = identity[0] & 0b111
    if type_of_identity == IDENTITY_GUTI:
        return None
    if type_of_identity != IDENTITY_IMSI:
        return None
    odd = bool(identity[0] & 0x08)
    digits = [_digit(identity[0] >> 4)]
    filler = False
    rest = identity[1:]
    for position, octet in enumerate(rest):
        digits.append(_digit(octet & 0x0F))
        high = octet >> 4
        if high == 0xF:
            if position != len(rest) - 1:
                raise NasError("the identity end mark is not in the last octet")
            filler = True
            break
        digits.append(_digit(high))
    # Odd count means the last octet is full; even count needs the 0xF filler.
    if filler == odd:
        raise NasError("the odd/even indicator does not match the identity digits")
    if (len(digits) % 2 == 1) != odd:
        raise NasError("the odd/even indicator does not match the identity digits")
    if not 6 <= len(digits) <= MAX_IMSI_DIGITS:
        raise NasError(f"an IMSI is 6..{MAX_IMSI_DIGITS} digits, not {len(digits)}")
    return "".join(digits)


def _digit(nibble: int) -> str:
    if nibble > 9:
        raise NasError(f"nibble 0x{nibble:X} is not a decimal digit")
    return str(nibble)
