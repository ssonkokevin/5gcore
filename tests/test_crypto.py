"""Milenage and 3GPP KDF conformance vectors.

Vector sources:
  * TS 35.208 Annex B, Test Set 1 (K, RAND, SQN, AMF, OP, OPc and f1..f5*)
  * RFC 5448 Appendix A (CK'/IK' KDF, FC 0x20)

Run: python -m unittest discover -s tests
"""

import hmac
import sys
import unittest
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corelib.milenage import (  # noqa: E402
    CryptoUnavailable,
    Milenage,
    derive_opc,
    hxres_star,
    kasme,
    kdf,
    kausf,
    plmn_id,
    res_star,
)


def h(value):
    return bytes.fromhex(value)


# --- TS 35.208 Annex B, Test Set 1 -----------------------------------------
TS1_K = h("465b5ce8b199b49faa5f0a2ee238a6bc")
TS1_OP = h("cdc202d5123e20f62b6d676ac72cb318")
TS1_OPC = h("cd63cb71954a9f4e48a5994e37a02baf")
TS1_RAND = h("23553cbe9637a89d218ae64dae47bf35")
TS1_SQN = h("ff9bb4d0b607")
TS1_AMF = h("b9b9")
TS1_MAC_A = h("4a9ffac354dfafb3")
TS1_MAC_S = h("01cfaf9ec4e871e9")
TS1_RES = h("a54211d5e3ba50bf")
TS1_CK = h("b40ba9a3c58b2a05bbf0d987b21bf8cb")
TS1_IK = h("f769bcd751044604127672711c6d3441")
TS1_AK = h("aa689c648370")
TS1_AK_STAR = h("451e8beca43b")

# --- RFC 5448 Appendix A ----------------------------------------------------
SNN = "WLAN"
SQN_XOR_AK = h("bb52e91c747a")
CK_PRIME_INPUT = h("5349fbe098649f948f5d2e973a81c00f9744871ad32bf9bbd1dd5ce54e3e2e5a")
CK_IK_PRIME = h(
    "0093962d0dd84aa5684b045c9edffa04ccfc230ca74fcc96c0a5d61164f5a76c"
)


class TestMilenage(unittest.TestCase):
    def setUp(self):
        try:
            self.m = Milenage(TS1_OPC)
        except CryptoUnavailable as exc:
            self.skipTest(str(exc))

    def test_opc_derivation(self):
        self.assertEqual(derive_opc(TS1_OP, TS1_K), TS1_OPC)

    def test_from_op(self):
        self.assertEqual(Milenage.from_op(TS1_OP, TS1_K).opc, TS1_OPC)

    def test_f1_and_f1star_share_one_out1(self):
        mac_a, mac_s = self.m.f1_f1star(TS1_K, TS1_RAND, TS1_SQN, TS1_AMF)
        self.assertEqual(mac_a, TS1_MAC_A)
        self.assertEqual(mac_s, TS1_MAC_S)
        self.assertEqual(self.m.f1(TS1_K, TS1_RAND, TS1_SQN, TS1_AMF), TS1_MAC_A)
        self.assertEqual(
            self.m.f1_star(TS1_K, TS1_RAND, TS1_SQN, TS1_AMF), TS1_MAC_S
        )

    def test_f2345(self):
        keys = self.m._f2345(TS1_K, TS1_RAND)
        self.assertEqual(keys["res"], TS1_RES)
        self.assertEqual(keys["ck"], TS1_CK)
        self.assertEqual(keys["ik"], TS1_IK)
        self.assertEqual(keys["ak"], TS1_AK)
        self.assertEqual(keys["ak_star"], TS1_AK_STAR)
        self.assertNotEqual(keys["ak"], keys["ak_star"])

    def test_auts_round_trip_uses_ak_star(self):
        auts = bytes(
            a ^ b for a, b in zip(TS1_SQN, self.m.f5_star(TS1_K, TS1_RAND))
        ) + self.m.f1_star(TS1_K, TS1_RAND, TS1_SQN, b"\x00\x00")
        self.assertEqual(self.m.auts_sqn(TS1_K, TS1_RAND, auts), int.from_bytes(TS1_SQN, "big"))

    def test_auts_rejects_bad_mac_s(self):
        auts = bytearray(
            bytes(a ^ b for a, b in zip(TS1_SQN, self.m.f5_star(TS1_K, TS1_RAND)))
            + self.m.f1_star(TS1_K, TS1_RAND, TS1_SQN, b"\x00\x00")
        )
        auts[13] ^= 0xFF
        with self.assertRaises(ValueError):
            self.m.auts_sqn(TS1_K, TS1_RAND, bytes(auts))

    def test_5g_he_av_uses_f5_ak_in_autn(self):
        av = self.m.generate_5g_he_av(
            TS1_K, int.from_bytes(TS1_SQN, "big"), TS1_AMF, "5G:mnc001.mcc001.3gppnetwork.org",
            rand=TS1_RAND,
        )
        self.assertEqual(av["rand"], TS1_RAND)
        self.assertEqual(av["autn"][:6], bytes(a ^ b for a, b in zip(TS1_SQN, TS1_AK)))
        self.assertEqual(av["autn"][6:8], TS1_AMF)
        self.assertEqual(av["autn"][8:], TS1_MAC_A)
        self.assertEqual(av["xres_star"], res_star(
            TS1_CK, TS1_IK, "5G:mnc001.mcc001.3gppnetwork.org", TS1_RAND, TS1_RES
        ))
        self.assertEqual(av["k_ausf"], kausf(
            TS1_CK, TS1_IK, "5G:mnc001.mcc001.3gppnetwork.org",
            bytes(a ^ b for a, b in zip(TS1_SQN, TS1_AK)),
        ))

    def test_5g_he_av_requires_serving_network_name(self):
        with self.assertRaises(ValueError):
            self.m.generate_5g_he_av(TS1_K, 0, TS1_AMF, "", rand=TS1_RAND)

    def test_eps_av_kasme_matches_kdf(self):
        av = self.m.generate_eps_av(
            TS1_K, int.from_bytes(TS1_SQN, "big"), TS1_AMF,
            sn_id=plmn_id("001", "01"), rand=TS1_RAND,
        )
        self.assertEqual(av["autn"][:6], bytes(a ^ b for a, b in zip(TS1_SQN, TS1_AK)))
        self.assertEqual(av["xres"], TS1_RES)
        self.assertEqual(
            av["k_asme"],
            kasme(TS1_CK, TS1_IK, plmn_id("001", "01"),
                  bytes(a ^ b for a, b in zip(TS1_SQN, TS1_AK))),
        )

    def test_2g3g_vector_is_sres_and_kc(self):
        av = self.m.generate_2g3g_av(TS1_K, rand=TS1_RAND)
        self.assertEqual(av["sres"], TS1_RES[:4])
        self.assertEqual(av["kc"], TS1_CK[:8])


class TestKDF(unittest.TestCase):
    def test_rfc5448_ck_ik_prime(self):
        try:
            derived = kdf(CK_PRIME_INPUT, 0x20, SNN.encode(), SQN_XOR_AK)
        except CryptoUnavailable as exc:  # pragma: no cover
            self.skipTest(str(exc))
        self.assertEqual(derived, CK_IK_PRIME)

    def test_kdf_lengths_are_two_octet_big_endian(self):
        key = b"\x11" * 32
        expected = hmac.new(
            key, b"\x20" + b"WLAN" + b"\x00\x04" + SQN_XOR_AK + b"\x00\x06", sha256
        ).digest()
        self.assertEqual(kdf(key, 0x20, b"WLAN", SQN_XOR_AK), expected)

    def test_hxres_star_is_last_128_bits(self):
        self.assertEqual(hxres_star(TS1_RES), sha256(TS1_RES).digest()[16:])


class TestPlmnId(unittest.TestCase):
    def test_two_digit_mnc_pads_f(self):
        self.assertEqual(plmn_id("001", "01"), h("00f110"))

    def test_three_digit_mnc(self):
        self.assertEqual(plmn_id("310", "410"), h("130014"))

    def test_rejects_bad_mnc(self):
        with self.assertRaises(ValueError):
            plmn_id("001", "1")


if __name__ == "__main__":
    unittest.main()
