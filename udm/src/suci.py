"""SUCI de-concealment per 3GPP TS 33.501 Annex C.

Protection schemes handled:
  0 - null scheme (MSIN sent in clear, BCD packed)
  1 - Profile A: ECIES over X25519, AES-128-CTR, HMAC-SHA-256 truncated to 8 octets
  2 - Profile B: ECIES over secp256r1, same symmetric construction

Scheme output layout (Annex C.3):
  Profile A:  PK_UE (32) || ciphertext || MAC (8)
  Profile B:  PK_UE (33 compressed or 65 uncompressed) || ciphertext || MAC (8)

Key derivation (Annex C.4) is ANSI X9.63 KDF with SHA-256 over the 64-octet
output: enc_key = K[0:16], ICB = K[16:32], mac_key = K[32:64]. The ICB is
derived, not zero.

The home network private key never leaves this module. Profiles are loaded
from SUCI_PROFILES (JSON) or SUCI_PROFILE_A_PRIVATE_KEY / SUCI_PROFILE_B_PRIVATE_KEY.
A missing key is an operator error and must fail the request, never fall back
to sending a subscriber lookup with an un-deconcealed identity.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, x25519
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SCHEME_NULL = 0
SCHEME_PROFILE_A = 1
SCHEME_PROFILE_B = 2

ENC_KEY_LEN = 16
ICB_LEN = 16
MAC_KEY_LEN = 32
MAC_LEN = 8
KDF_OUT_LEN = ENC_KEY_LEN + ICB_LEN + MAC_KEY_LEN

_SUCI_RE = re.compile(
    r"^suci-(?P<supi_type>\d)"          # 0 = IMSI, 1 = NAI
    r"-(?P<hni>[0-9]{3}-[0-9]{2,3})"    # MCC-MNC (IMSI only)
    r"-(?P<ri>\d{1,4})"
    r"-(?P<scheme>[0-2])"
    r"-(?P<pkid>\d{1,3})"
    r"-(?P<out>[0-9A-Fa-f]+)$"
)


class SuciError(Exception):
    """Base error. `code` is a stable machine-readable cause."""

    code = "SUCI_ERROR"
    http_status = 400


class SuciMalformed(SuciError):
    code = "SUCI_MALFORMED"


class SuciUnsupported(SuciError):
    code = "SUCI_UNSUPPORTED"


class SuciAuthenticationFailed(SuciError):
    """MAC mismatch or invalid curve point: the SUCI was not produced by a
    subscriber holding the home network public key for this profile."""

    code = "SUCI_AUTHENTICATION_FAILED"


class SuciKeyNotConfigured(SuciError):
    code = "SUCI_KEY_NOT_CONFIGURED"
    http_status = 500


@dataclass(frozen=True)
class SuciProfile:
    pkid: int
    scheme: int
    private_key: bytes


@dataclass(frozen=True)
class ParsedSuci:
    supi_type: int
    mcc: str
    mnc: str
    routing_indicator: str
    scheme: int
    pkid: int
    scheme_output_hex: str

    @property
    def scheme_output(self) -> bytes:
        if self.scheme == SCHEME_NULL:
            raise SuciMalformed("null scheme output is a digit string, not octets")
        return bytes.fromhex(self.scheme_output_hex)


def parse_suci(suci: str) -> ParsedSuci:
    if not isinstance(suci, str):
        raise SuciMalformed("SUCI must be a string")
    m = _SUCI_RE.match(suci.strip())
    if not m:
        raise SuciMalformed(
            "expected suci-<supi type>-<mcc>-<mnc>-<routing ind>-<scheme>-<pkid>-<output>"
        )
    supi_type = int(m.group("supi_type"))
    if supi_type != 0:
        raise SuciUnsupported("NAI SUCI (supi type 1) is not implemented")
    mcc, mnc = m.group("hni").split("-")
    scheme = int(m.group("scheme"))
    out_hex = m.group("out")
    if scheme == SCHEME_NULL:
        if not (out_hex.rstrip("f").isdigit() and out_hex.rstrip("f")):
            raise SuciMalformed("null scheme output must be decimal digits")
    elif len(out_hex) % 2:
        raise SuciMalformed("scheme output has an odd number of hex digits")
    return ParsedSuci(
        supi_type=supi_type,
        mcc=mcc,
        mnc=mnc,
        routing_indicator=m.group("ri"),
        scheme=scheme,
        pkid=int(m.group("pkid")),
        scheme_output_hex=out_hex,
    )


def ansi_x963_kdf(shared_secret: bytes, shared_info: bytes, length: int = KDF_OUT_LEN) -> bytes:
    out = bytearray()
    counter = 1
    while len(out) < length:
        digest = hashlib.sha256(shared_secret + counter.to_bytes(4, "big") + shared_info)
        out.extend(digest.digest())
        counter += 1
    return bytes(out[:length])


def _decrypt_scheme_output(
    shared_secret: bytes,
    kdf_public_key: bytes,
    ciphertext: bytes,
    provided_mac: bytes,
) -> bytes:
    material = ansi_x963_kdf(shared_secret, kdf_public_key)
    enc_key = material[:ENC_KEY_LEN]
    icb = material[ENC_KEY_LEN:ENC_KEY_LEN + ICB_LEN]
    mac_key = material[KDF_OUT_LEN - MAC_KEY_LEN:]

    expected = hmac.new(mac_key, ciphertext, hashlib.sha256).digest()[:MAC_LEN]
    if not hmac.compare_digest(expected, provided_mac):
        raise SuciAuthenticationFailed("MAC verification failed")
    if not ciphertext:
        raise SuciMalformed("empty ciphertext")

    decryptor = Cipher(algorithms.AES(enc_key), modes.CTR(icb)).decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def _msin_from_plaintext(plaintext: bytes) -> str:
    """Decrypted MSIN is low-nibble-first BCD padded with 0xF (TS 23.003)."""
    swapped = bytes((((b << 4) | (b >> 4)) & 0xFF) for b in plaintext)
    text = swapped.hex()
    if text.endswith("f"):
        text = text[:-1]
    if not text or not text.isdigit():
        raise SuciAuthenticationFailed("decrypted MSIN is not BCD digits")
    return text


def _imsi_from_output(parsed: ParsedSuci, plaintext: bytes) -> str:
    return f"{parsed.mcc}{parsed.mnc}{_msin_from_plaintext(plaintext)}"


def _profile_a(parsed: ParsedSuci, profile: SuciProfile) -> str:
    data = parsed.scheme_output
    if len(data) <= 32 + MAC_LEN:
        raise SuciMalformed("Profile A output shorter than public key plus MAC")
    pk_ue = data[:32]
    ciphertext = data[32:-MAC_LEN]
    mac = data[-MAC_LEN:]

    try:
        private = x25519.X25519PrivateKey.from_private_bytes(profile.private_key)
        public = x25519.X25519PublicKey.from_public_bytes(pk_ue)
        shared = private.exchange(public)
    except ValueError as exc:
        raise SuciAuthenticationFailed("invalid X25519 key material") from exc

    return _imsi_from_output(parsed, _decrypt_scheme_output(shared, pk_ue, ciphertext, mac))


def _decode_p256_public(raw: bytes):
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
    except ValueError as exc:
        raise SuciAuthenticationFailed("invalid P-256 public key") from exc


def _profile_b(parsed: ParsedSuci, profile: SuciProfile) -> str:
    data = parsed.scheme_output
    if data[0] in (0x02, 0x03):
        pk_len = 33
    elif data[0] == 0x04:
        pk_len = 65
    else:
        raise SuciMalformed("Profile B public key is not an SEC1 point")
    if len(data) <= pk_len + MAC_LEN:
        raise SuciMalformed("Profile B output shorter than public key plus MAC")

    pk_ue = data[:pk_len]
    ciphertext = data[pk_len:-MAC_LEN]
    mac = data[-MAC_LEN:]

    peer_public = _decode_p256_public(pk_ue)
    kdf_public = peer_public.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
    )
    try:
        private = ec.derive_private_key(
            int.from_bytes(profile.private_key, "big"), ec.SECP256R1()
        )
        shared = private.exchange(ec.ECDH(), peer_public)
    except ValueError as exc:
        raise SuciAuthenticationFailed("invalid P-256 key material") from exc

    return _imsi_from_output(parsed, _decrypt_scheme_output(shared, kdf_public, ciphertext, mac))


def _profiles_from_env() -> Dict[int, SuciProfile]:
    profiles: Dict[int, SuciProfile] = {}

    raw = os.getenv("SUCI_PROFILES", "").strip()
    if raw:
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SuciKeyNotConfigured(f"SUCI_PROFILES is not valid JSON: {exc}") from exc
        if not isinstance(entries, list):
            raise SuciKeyNotConfigured("SUCI_PROFILES must be a JSON array")
        for entry in entries:
            try:
                pkid = int(entry["pkid"])
                scheme = int(entry["scheme"])
                key = bytes.fromhex(entry["private_key"])
            except (KeyError, TypeError, ValueError) as exc:
                raise SuciKeyNotConfigured(f"bad SUCI_PROFILES entry: {exc}") from exc
            if scheme not in (SCHEME_PROFILE_A, SCHEME_PROFILE_B):
                raise SuciKeyNotConfigured(f"profile {pkid}: unknown scheme {scheme}")
            if len(key) != 32:
                raise SuciKeyNotConfigured(f"profile {pkid}: private key must be 32 octets")
            profiles[pkid] = SuciProfile(pkid=pkid, scheme=scheme, private_key=key)

    for scheme, pkid_var, key_var in (
        (SCHEME_PROFILE_A, "SUCI_PROFILE_A_PKID", "SUCI_PROFILE_A_PRIVATE_KEY"),
        (SCHEME_PROFILE_B, "SUCI_PROFILE_B_PKID", "SUCI_PROFILE_B_PRIVATE_KEY"),
    ):
        key_hex = os.getenv(key_var, "").strip()
        if not key_hex:
            continue
        try:
            key = bytes.fromhex(key_hex)
        except ValueError as exc:
            raise SuciKeyNotConfigured(f"{key_var} is not hex") from exc
        if len(key) != 32:
            raise SuciKeyNotConfigured(f"{key_var} must be 32 octets")
        pkid = int(os.getenv(pkid_var, "1"))
        profiles.setdefault(pkid, SuciProfile(pkid=pkid, scheme=scheme, private_key=key))

    return profiles


_cache: Optional[Dict[int, SuciProfile]] = None


def load_profiles(force: bool = False) -> Dict[int, SuciProfile]:
    global _cache
    if _cache is None or force:
        _cache = _profiles_from_env()
    return _cache


def configured_profiles() -> List[Dict[str, object]]:
    """Non-secret view for /health: pkid, scheme and public key only."""
    result = []
    for pkid, profile in sorted(load_profiles().items()):
        entry: Dict[str, object] = {"pkid": pkid, "scheme": profile.scheme}
        try:
            entry["public_key"] = public_key_hex(profile).upper()
        except SuciKeyNotConfigured:
            entry["public_key"] = None
        result.append(entry)
    return result


def public_key_hex(profile: SuciProfile) -> str:
    if profile.scheme == SCHEME_PROFILE_A:
        private = x25519.X25519PrivateKey.from_private_bytes(profile.private_key)
        return private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ).hex()
    if profile.scheme == SCHEME_PROFILE_B:
        private = ec.derive_private_key(
            int.from_bytes(profile.private_key, "big"), ec.SECP256R1()
        )
        return private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
        ).hex()
    raise SuciKeyNotConfigured(f"unknown scheme {profile.scheme}")


def deconceal(suci: str, profiles: Optional[Dict[int, SuciProfile]] = None) -> str:
    """Return the IMSI (digits only) for a SUCI. Raises SuciError."""
    parsed = parse_suci(suci)

    if parsed.scheme == SCHEME_NULL:
        return f"{parsed.mcc}{parsed.mnc}{parsed.scheme_output_hex.rstrip('f')}"

    table = load_profiles() if profiles is None else profiles
    if not table:
        raise SuciKeyNotConfigured(
            "no SUCI de-concealment key configured; set SUCI_PROFILES or "
            "SUCI_PROFILE_A_PRIVATE_KEY"
        )
    profile = table.get(parsed.pkid)
    if profile is None:
        raise SuciAuthenticationFailed(
            f"home network public key id {parsed.pkid} is not provisioned"
        )
    if profile.scheme != parsed.scheme:
        raise SuciUnsupported(
            f"key id {parsed.pkid} is for scheme {profile.scheme}, SUCI uses {parsed.scheme}"
        )

    if parsed.scheme == SCHEME_PROFILE_A:
        return _profile_a(parsed, profile)
    return _profile_b(parsed, profile)


# ---------------------------------------------------------------------------
# UE side (used by provisioning tests and by the SIM personalisation tooling;
# never called by the network service path)
# ---------------------------------------------------------------------------

def _bcd_encode_msin(msin: str) -> bytes:
    if not msin.isdigit():
        raise SuciMalformed("MSIN must be digits")
    padded = msin + ("f" if len(msin) % 2 else "")
    raw = bytes.fromhex(padded)
    return bytes((((b << 4) | (b >> 4)) & 0xFF) for b in raw)


def _build_suci(mcc: str, mnc: str, routing_indicator: str, scheme: int, pkid: int, out: bytes) -> str:
    return f"suci-0-{mcc}-{mnc}-{routing_indicator}-{scheme}-{pkid}-{out.hex()}"


def conceal(imsi: str, scheme: int, home_network_public_key: bytes,
            pkid: int = 1, routing_indicator: str = "0", mnc_digits: int = 0) -> str:
    """Produce a SUCI the way a UE would, for a 5G SUCI-enabled SIM."""
    if len(imsi) < 6 or not imsi.isdigit():
        raise SuciMalformed("IMSI must be at least 6 digits")
    digits = mnc_digits or (3 if len(imsi) == 15 else 2)
    mcc, mnc, msin = imsi[:3], imsi[3:3 + digits], imsi[3 + digits:]
    plaintext = _bcd_encode_msin(msin)

    if scheme == SCHEME_PROFILE_A:
        if len(home_network_public_key) != 32:
            raise SuciMalformed("Profile A home network public key must be 32 octets")
        ephemeral = x25519.X25519PrivateKey.generate()
        pk_ue = ephemeral.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        shared = ephemeral.exchange(
            x25519.X25519PublicKey.from_public_bytes(home_network_public_key)
        )
        out = _encrypt_scheme_output(shared, pk_ue, plaintext)
        return _build_suci(mcc, mnc, routing_indicator, scheme, pkid, pk_ue + out)

    if scheme == SCHEME_PROFILE_B:
        hn_public = _decode_p256_public(home_network_public_key)
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        pk_ue = ephemeral.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
        )
        shared = ephemeral.exchange(ec.ECDH(), hn_public)
        out = _encrypt_scheme_output(shared, pk_ue, plaintext)
        return _build_suci(mcc, mnc, routing_indicator, scheme, pkid, pk_ue + out)

    raise SuciUnsupported(f"cannot conceal with scheme {scheme}")


def _encrypt_scheme_output(shared_secret: bytes, kdf_public_key: bytes, plaintext: bytes) -> bytes:
    material = ansi_x963_kdf(shared_secret, kdf_public_key)
    enc_key = material[:ENC_KEY_LEN]
    icb = material[ENC_KEY_LEN:ENC_KEY_LEN + ICB_LEN]
    mac_key = material[KDF_OUT_LEN - MAC_KEY_LEN:]

    encryptor = Cipher(algorithms.AES(enc_key), modes.CTR(icb)).encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    mac = hmac.new(mac_key, ciphertext, hashlib.sha256).digest()[:MAC_LEN]
    return ciphertext + mac
