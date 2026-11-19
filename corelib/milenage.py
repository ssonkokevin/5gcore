"""Milenage and 3GPP key derivation, shared by UDM, HSS, AUSF and AMF.

Algorithm references:
  * TS 35.206 / TS 33.102 Annex B — Milenage f1..f5, f1*, f5*
  * TS 33.220 Annex B.2 — generic key derivation function (KDF)
  * TS 33.401 Annex A.2 — KASME derivation for EPS AKA
  * TS 33.501 Annex A.2, A.5, A.7 — KAUSF, RES*/XRES*, KSEAF, KAMF

AES-128-ECB comes from pycryptodome in the containers and from `cryptography`
on hosts that only have that library. If neither is installed every entry point
raises CryptoUnavailable; nothing here ever falls back to a hash.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256
from typing import Dict, Optional, Tuple

try:  # container images
    from Crypto.Cipher import AES as _AES

    CRYPTO_BACKEND: Optional[str] = "pycryptodome"
except ImportError:  # pragma: no cover - exercised on hosts without pycryptodome
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        _AES = None
        CRYPTO_BACKEND = "cryptography"
    except ImportError:
        _AES = None
        CRYPTO_BACKEND = None


class CryptoUnavailable(RuntimeError):
    """No AES backend is installed; the caller must fail closed."""


class AutsVerificationError(ValueError):
    """AUTS did not carry a valid MAC-S."""


def _encrypt(key: bytes, block: bytes) -> bytes:
    if CRYPTO_BACKEND == "pycryptodome":
        return _AES.new(key, _AES.MODE_ECB).encrypt(block)
    if CRYPTO_BACKEND == "cryptography":
        encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        return encryptor.update(block) + encryptor.finalize()
    raise CryptoUnavailable(
        "no AES backend: install pycryptodome (containers) or cryptography (host)"
    )


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def rotate_left(block: bytes, bits: int) -> bytes:
    """Rotate a 128-bit block left by `bits` (TS 35.206 r1..r5)."""
    bits %= 128
    if bits == 0:
        return block
    value = int.from_bytes(block, "big")
    value = ((value << bits) | (value >> (128 - bits))) & ((1 << 128) - 1)
    return value.to_bytes(16, "big")


def derive_opc(op: bytes, k: bytes) -> bytes:
    """OPc = E_K(OP) ⊕ OP (TS 35.206 §3)."""
    return _xor(_encrypt(k, op), op)


# ---------------------------------------------------------------------------
# KDF (TS 33.220 Annex B.2)
# ---------------------------------------------------------------------------

FC_RES_STAR = 0x6B      # RES*/XRES* from CK||IK (TS 33.501 A.5)
FC_KAUSF = 0x6A         # KAUSF from CK||IK      (TS 33.501 A.6)
FC_KSEAF = 0x6C         # KSEAF from KAUSF       (TS 33.501 A.7)
FC_KAMF = 0x6D          # KAMF from KSEAF        (TS 33.501 A.7)
FC_KASME = 0x10         # KASME from CK||IK      (TS 33.401 A.2)
FC_CK_IK_PRIME = 0x20   # CK'/IK' for EAP-AKA'   (TS 33.402)


def kdf(key: bytes, fc: int, *params: bytes) -> bytes:
    """S = FC || P0 || L0 || P1 || L1 ...; output = HMAC-SHA-256(key, S).

    Each Pi is followed by its two-octet big-endian length, as required by
    TS 33.220 Annex B.2.
    """
    payload = bytes([fc])
    for param in params:
        payload += param + len(param).to_bytes(2, "big")
    return hmac.new(key, payload, sha256).digest()


def res_star(ck: bytes, ik: bytes, snn: str, rand: bytes, res: bytes) -> bytes:
    """RES*/XRES* — TS 33.501 Annex A.5. 128 bits, the last half of the KDF."""
    return kdf(ck + ik, FC_RES_STAR, snn.encode(), rand, res)[16:]


def kausf(ck: bytes, ik: bytes, snn: str, sqn_xor_ak: bytes) -> bytes:
    """KAUSF — TS 33.501 Annex A.6. 256 bits."""
    return kdf(ck + ik, FC_KAUSF, snn.encode(), sqn_xor_ak)


def kseaf(kausf_value: bytes, snn: str) -> bytes:
    """KSEAF — TS 33.501 Annex A.7. 256 bits."""
    return kdf(kausf_value, FC_KSEAF, snn.encode())


def kamf(kseaf_value: bytes, supi: str, abba: bytes = b"\x00\x00") -> bytes:
    """KAMF — TS 33.501 Annex A.7. 256 bits."""
    return kdf(kseaf_value, FC_KAMF, supi.encode(), abba)


def kasme(ck: bytes, ik: bytes, sn_id: bytes, sqn_xor_ak: bytes) -> bytes:
    """KASME — TS 33.401 Annex A.2. `sn_id` is the 3-octet PLMN identity."""
    return kdf(ck + ik, FC_KASME, sn_id, sqn_xor_ak)


def hxres_star(res_star_value: bytes) -> bytes:
    """HXRES* — SHA-256(RES*), last 128 bits (AUSF, TS 33.501 §6.1.3.2)."""
    return sha256(res_star_value).digest()[16:]


# ---------------------------------------------------------------------------
# Milenage
# ---------------------------------------------------------------------------

_C2 = (1).to_bytes(1, "big")
_C3 = (2).to_bytes(1, "big")
_C4 = (4).to_bytes(1, "big")
_C5 = (8).to_bytes(1, "big")


def _with_c(block: bytes, c: bytes) -> bytes:
    """XOR cX into the least significant byte (TS 35.206 c1..c5)."""
    return block[:15] + _xor(block[15:], c)


class Milenage:
    """Milenage algorithm set for one OPc (TS 35.206 §4)."""

    def __init__(self, opc: bytes):
        if len(opc) != 16:
            raise ValueError("OPc must be 16 bytes")
        self.opc = opc

    @classmethod
    def from_op(cls, op: bytes, k: bytes) -> "Milenage":
        return cls(derive_opc(op, k))

    def _temp(self, k: bytes, rand: bytes) -> bytes:
        return _encrypt(k, _xor(rand, self.opc))

    # -- f1 / f1* ----------------------------------------------------------
    def f1_f1star(
        self, k: bytes, rand: bytes, sqn: bytes, amf: bytes
    ) -> Tuple[bytes, bytes]:
        """Return (MAC-A, MAC-S) from one OUT1 (TS 35.206 §4.1)."""
        if len(sqn) != 6 or len(amf) != 2:
            raise ValueError("SQN must be 6 bytes and AMF 2 bytes")
        temp = self._temp(k, rand)
        in1 = (sqn + amf) * 2
        block = _xor(rotate_left(_xor(in1, self.opc), 64), temp)
        out1 = _xor(_encrypt(k, block), self.opc)
        return out1[:8], out1[8:]

    def f1(self, k: bytes, rand: bytes, sqn: bytes, amf: bytes) -> bytes:
        return self.f1_f1star(k, rand, sqn, amf)[0]

    def f1_star(self, k: bytes, rand: bytes, sqn: bytes, amf: bytes) -> bytes:
        return self.f1_f1star(k, rand, sqn, amf)[1]

    # -- f2..f5 ------------------------------------------------------------
    def _f2345(self, k: bytes, rand: bytes) -> Dict[str, bytes]:
        temp = self._temp(k, rand)
        base = _xor(temp, self.opc)

        out2 = _xor(_encrypt(k, _with_c(rotate_left(base, 0), _C2)), self.opc)
        out3 = _xor(_encrypt(k, _with_c(rotate_left(base, 32), _C3)), self.opc)
        out4 = _xor(_encrypt(k, _with_c(rotate_left(base, 64), _C4)), self.opc)
        out5 = _xor(_encrypt(k, _with_c(rotate_left(base, 96), _C5)), self.opc)

        return {
            "res": out2[8:16],
            "ak": out2[0:6],
            "ck": out3,
            "ik": out4,
            "ak_star": out5[0:6],
        }

    def f2(self, k: bytes, rand: bytes) -> bytes:
        return self._f2345(k, rand)["res"]

    def f3(self, k: bytes, rand: bytes) -> bytes:
        return self._f2345(k, rand)["ck"]

    def f4(self, k: bytes, rand: bytes) -> bytes:
        return self._f2345(k, rand)["ik"]

    def f5(self, k: bytes, rand: bytes) -> bytes:
        return self._f2345(k, rand)["ak"]

    def f5_star(self, k: bytes, rand: bytes) -> bytes:
        return self._f2345(k, rand)["ak_star"]

    # -- AUTS ---------------------------------------------------------------
    def auts_sqn(self, k: bytes, rand: bytes, auts: bytes) -> int:
        """Verify MAC-S and return SQN_MS (TS 33.102 §6.3.3).

        AUTS = (SQN_MS ⊕ AK*) || MAC-S, 14 octets. The ME always sets AMF to
        0x0000 in the f1* computation, so no subscriber AMF is involved.
        """
        if len(auts) != 14:
            raise ValueError("AUTS must be 14 bytes")
        sqn_ms = _xor(auts[:6], self.f5_star(k, rand))
        _, mac_s = self.f1_f1star(k, rand, sqn_ms, b"\x00\x00")
        if not hmac.compare_digest(mac_s, auts[6:]):
            raise AutsVerificationError("MAC-S mismatch in AUTS")
        return int.from_bytes(sqn_ms, "big")

    # -- authentication vectors --------------------------------------------
    def generate_5g_he_av(
        self,
        k: bytes,
        sqn: int,
        amf: bytes,
        serving_network_name: str,
        rand: Optional[bytes] = None,
    ) -> Dict[str, bytes]:
        """5G HE AV: RAND, AUTN, XRES* and KAUSF (TS 33.501 §6.1.3.2).

        The UDM returns this; only the AUSF derives KSEAF and HXRES*.
        """
        if not serving_network_name:
            raise ValueError("serving network name is required to derive KAUSF")
        rand = rand or secrets.token_bytes(16)
        sqn_bytes = sqn.to_bytes(6, "big")

        keys = self._f2345(k, rand)
        mac_a, _ = self.f1_f1star(k, rand, sqn_bytes, amf)
        # AUTN conceals SQN with AK (f5); AK* (f5*) is only used in AUTS.
        sqn_xor_ak = _xor(sqn_bytes, keys["ak"])
        autn = sqn_xor_ak + amf + mac_a

        return {
            "rand": rand,
            "autn": autn,
            "xres_star": res_star(keys["ck"], keys["ik"], serving_network_name, rand, keys["res"]),
            "k_ausf": kausf(keys["ck"], keys["ik"], serving_network_name, sqn_xor_ak),
            "res": keys["res"],
            "ck": keys["ck"],
            "ik": keys["ik"],
        }

    def generate_eps_av(
        self,
        ki: bytes,
        sqn: int,
        amf: bytes,
        sn_id: Optional[bytes] = None,
        rand: Optional[bytes] = None,
    ) -> Dict[str, bytes]:
        """EPS AV per TS 33.401. KASME is returned only when `sn_id` is known."""
        rand = rand or secrets.token_bytes(16)
        sqn_bytes = sqn.to_bytes(6, "big")

        keys = self._f2345(ki, rand)
        mac_a, _ = self.f1_f1star(ki, rand, sqn_bytes, amf)
        sqn_xor_ak = _xor(sqn_bytes, keys["ak"])
        autn = sqn_xor_ak + amf + mac_a

        vector = {
            "rand": rand,
            "autn": autn,
            "xres": keys["res"],
            "res": keys["res"],
            "ck": keys["ck"],
            "ik": keys["ik"],
            "k_asme": None,
        }
        if sn_id is not None:
            if len(sn_id) != 3:
                raise ValueError("serving network id must be 3 bytes (PLMN identity)")
            vector["k_asme"] = kasme(keys["ck"], keys["ik"], sn_id, sqn_xor_ak)
        return vector

    def generate_2g3g_av(
        self, ki: bytes, rand: Optional[bytes] = None
    ) -> Dict[str, bytes]:
        """GSM/UMTS vector: RAND, SRES (4), Kc (8)."""
        rand = rand or secrets.token_bytes(16)
        keys = self._f2345(ki, rand)
        return {"rand": rand, "sres": keys["res"][:4], "kc": keys["ck"][:8]}


def plmn_id(mcc: str, mnc: str) -> bytes:
    """3-octet PLMN identity for the KASME KDF (TS 23.003 §12.1).

    Octet 1 = MCC2|MCC1, octet 2 = MNC3|MCC3, octet 3 = MNC2|MNC1. A 2-digit
    MNC puts 0xF in the MNC3 nibble, so 001/01 encodes as 00 F1 10 and
    310/410 as 13 00 14.
    """
    mcc = mcc.zfill(3)
    if len(mnc) == 2:
        mnc = mnc.zfill(2)
    elif len(mnc) == 3:
        mnc = mnc.zfill(3)
    else:
        raise ValueError("MNC must be 2 or 3 digits")

    first = (int(mcc[1]) << 4) | int(mcc[0])
    second = (int(mnc[2]) << 4) | int(mcc[2]) if len(mnc) == 3 else 0xF0 | int(mcc[2])
    third = (int(mnc[1]) << 4) | int(mnc[0])
    return bytes([first, second, third])
