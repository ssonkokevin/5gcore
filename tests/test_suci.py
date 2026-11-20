"""SUCI de-concealment (TS 33.501 Annex C).

    python tests/test_suci.py
"""

import json
import os
import sys
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, x25519

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "udm" / "src"))

import suci  # noqa: E402


def x25519_profile(pkid=1):
    private = x25519.X25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {pkid: suci.SuciProfile(pkid=pkid, scheme=1, private_key=raw)}, public


def p256_profile(pkid=2):
    private = ec.generate_private_key(ec.SECP256R1())
    raw = private.private_numbers().private_value.to_bytes(32, "big")
    public = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
    )
    return {pkid: suci.SuciProfile(pkid=pkid, scheme=2, private_key=raw)}, public


class ProfileATest(unittest.TestCase):
    def test_round_trip(self):
        profiles, public = x25519_profile()
        for imsi in ("641020123456789", "641020000000001"):
            concealed = suci.conceal(imsi, 1, public, pkid=1)
            self.assertTrue(concealed.startswith("suci-0-641-020-0-1-1-"))
            self.assertEqual(suci.deconceal(concealed, profiles), imsi)

    def test_mac_is_verified(self):
        profiles, public = x25519_profile()
        concealed = suci.conceal("641020123456789", 1, public, pkid=1)
        tampered = concealed[:-2] + ("00" if concealed[-2:] != "00" else "11")
        with self.assertRaises(suci.SuciAuthenticationFailed):
            suci.deconceal(tampered, profiles)

    def test_wrong_key_is_rejected(self):
        _, public = x25519_profile()
        other, _ = x25519_profile()
        concealed = suci.conceal("641020123456789", 1, public, pkid=1)
        with self.assertRaises(suci.SuciAuthenticationFailed):
            suci.deconceal(concealed, other)


class ProfileBTest(unittest.TestCase):
    def test_round_trip(self):
        profiles, public = p256_profile()
        for imsi in ("641020123456789", "64102012345678"):
            concealed = suci.conceal(imsi, 2, public, pkid=2)
            self.assertEqual(suci.deconceal(concealed, profiles), imsi)

    def test_public_key_derivation_matches(self):
        profiles, public = p256_profile()
        self.assertEqual(suci.public_key_hex(profiles[2]), public.hex())


class SchemeTest(unittest.TestCase):
    def test_null_scheme(self):
        self.assertEqual(
            suci.deconceal("suci-0-641-020-0-0-0-0123456789", {}),
            "6410200123456789",
        )

    def test_missing_key_is_a_server_error(self):
        with self.assertRaises(suci.SuciKeyNotConfigured) as ctx:
            suci.deconceal("suci-0-641-020-0-1-1-" + "00" * 48, {})
        self.assertEqual(ctx.exception.http_status, 500)

    def test_unknown_pkid(self):
        profiles, _ = x25519_profile()
        with self.assertRaises(suci.SuciAuthenticationFailed):
            suci.deconceal("suci-0-641-020-0-1-9-" + "00" * 48, profiles)

    def test_scheme_mismatch(self):
        profiles, _ = x25519_profile()
        with self.assertRaises(suci.SuciUnsupported):
            suci.deconceal("suci-0-641-020-0-2-1-" + "ab" * 48, profiles)

    def test_malformed(self):
        for bad in (
            "imsi-641020123456789",
            "suci-0-641-02-12345-0-0-0-12",
            "suci-1-nai.example.com-0-0-0-00",
            "suci-0-641-020-0-0-0-zz",
        ):
            with self.assertRaises(suci.SuciError):
                suci.deconceal(bad, {})


class EnvTest(unittest.TestCase):
    def test_profiles_from_json(self):
        profiles, _ = x25519_profile(pkid=7)
        entry = {
            "pkid": 7,
            "scheme": 1,
            "private_key": profiles[7].private_key.hex(),
        }
        os.environ["SUCI_PROFILES"] = json.dumps([entry])
        try:
            loaded = suci.load_profiles(force=True)
        finally:
            os.environ.pop("SUCI_PROFILES", None)
            suci.load_profiles(force=True)
        self.assertEqual(set(loaded), {7})
        self.assertEqual(loaded[7].scheme, 1)

    def test_summary_never_contains_private_key(self):
        profiles, public = x25519_profile(pkid=3)
        entry = {"pkid": 3, "scheme": 1, "private_key": profiles[3].private_key.hex()}
        os.environ["SUCI_PROFILES"] = json.dumps([entry])
        try:
            suci.load_profiles(force=True)
            summary = suci.configured_profiles()
        finally:
            os.environ.pop("SUCI_PROFILES", None)
            suci.load_profiles(force=True)
        self.assertEqual(summary[0]["pkid"], 3)
        self.assertEqual(summary[0]["public_key"], public.hex().upper())
        self.assertNotIn("private_key", json.dumps(summary))

    def test_bad_json_is_rejected(self):
        os.environ["SUCI_PROFILES"] = "{not json"
        try:
            with self.assertRaises(suci.SuciKeyNotConfigured):
                suci.load_profiles(force=True)
        finally:
            os.environ.pop("SUCI_PROFILES", None)
            suci.load_profiles(force=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
