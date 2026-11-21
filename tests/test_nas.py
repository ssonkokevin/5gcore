"""EPS NAS Attach Request, the slice TS 24.301 the MME reads.

    python tests/test_nas.py

Only the plain Attach Request is covered: the identity is readable there and
nowhere else in the procedure. A GUTI, an IMEI or a security-protected
message is not turned into a guessed IMSI.
"""

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.codecs import nas  # noqa: E402


class Encoding(unittest.TestCase):
    def test_known_15_digit_imsi(self):
        # 3GPP's own example, TS 24.301 figure 9.9.3.12.2.
        pdu = nas.attach_request("001010123456789")
        self.assertEqual(pdu, bytes.fromhex("074171080910101032547698"))

    def test_known_14_digit_imsi_gets_an_end_mark(self):
        pdu = nas.attach_request("00101012345678")
        self.assertEqual(pdu, bytes.fromhex("0741710801101010325476F8"))

    def test_known_6_digit_imsi(self):
        self.assertEqual(nas.attach_request("123456"),
                         bytes.fromhex("07417104113254F6"))

    def test_attach_type_overrides_the_low_nibble(self):
        pdu = nas.attach_request("123456", attach_type=0x5)
        self.assertEqual(pdu[2], 0x75)

    def test_rejects_out_of_range(self):
        for bad in ("12345", "1234567890123456", "00101012A45678", "", " ", "١٢٣٤٥٦"):
            with self.subTest(bad=bad), self.assertRaises(nas.NasError):
                nas.attach_request(bad)

    def test_rejects_bad_attach_type(self):
        for bad in (0, 8, -1, 0x1F):
            with self.subTest(bad=bad), self.assertRaises(nas.NasError):
                nas.attach_request("123456", attach_type=bad)

    def test_non_string_is_rejected(self):
        with self.assertRaises(nas.NasError):
            nas.attach_request(123456)


class RoundTrip(unittest.TestCase):
    def test_every_length_round_trips(self):
        digits = "123456789012345"
        for length in range(6, 16):
            imsi = digits[:length]
            with self.subTest(imsi=imsi):
                self.assertEqual(
                    nas.imsi_from_attach_request(nas.attach_request(imsi)), imsi)

    def test_leading_zero_is_kept(self):
        self.assertEqual(
            nas.imsi_from_attach_request(nas.attach_request("000000000000001")),
            "000000000000001")

    def test_random_imsis_round_trip(self):
        rng = random.Random(20261121)
        for _ in range(200):
            length = rng.randint(6, 15)
            first = rng.choice("123456789")
            imsi = first + "".join(rng.choice("0123456789")
                                   for _ in range(length - 1))
            with self.subTest(imsi=imsi):
                self.assertEqual(
                    nas.imsi_from_attach_request(nas.attach_request(imsi)), imsi)


class NotAnImsi(unittest.TestCase):
    def test_guti_is_not_an_imsi(self):
        pdu = bytes([0x07, 0x41, 0x71, 11, 0xF6]) + bytes(10)
        self.assertIsNone(nas.imsi_from_attach_request(pdu))

    def test_imei_is_not_an_imsi(self):
        pdu = bytes([0x07, 0x41, 0x71, 8, 0x13, 0x32, 0x54, 0x76, 0x98,
                     0x10, 0x32, 0x54])
        self.assertIsNone(nas.imsi_from_attach_request(pdu))

    def test_security_protected_message_is_not_read(self):
        pdu = bytearray(nas.attach_request("123456789012345"))
        pdu[0] = (2 << 4) | nas.PROTOCOL_DISCRIMINATOR_EMM
        self.assertIsNone(nas.imsi_from_attach_request(bytes(pdu)))

    def test_other_nas_message_is_not_read(self):
        pdu = bytearray(nas.attach_request("123456789012345"))
        pdu[1] = 0x42
        self.assertIsNone(nas.imsi_from_attach_request(bytes(pdu)))

    def test_other_protocol_is_not_read(self):
        pdu = bytearray(nas.attach_request("123456789012345"))
        pdu[0] = 0x02
        self.assertIsNone(nas.imsi_from_attach_request(bytes(pdu)))


class Malformed(unittest.TestCase):
    def _pdu(self, length, identity, *, odd_flag=None):
        first = identity[0]
        if odd_flag is not None:
            first = (first & 0xF7) | (0x08 if odd_flag else 0x00)
        identity = bytes([first]) + bytes(identity[1:])
        return bytes([0x07, 0x41, 0x71, length]) + identity

    def test_short_message(self):
        for data in (b"", b"\x07", b"\x07\x41", b"\x07\x41\x71"):
            with self.subTest(data=data), self.assertRaises(nas.NasError):
                nas.imsi_from_attach_request(data)

    def test_identity_length_out_of_range(self):
        for length in (0, 2, 13, 255):
            with self.subTest(length=length), self.assertRaises(nas.NasError):
                nas.imsi_from_attach_request(
                    bytes([0x07, 0x41, 0x71, length, 0x11, 0x32, 0x54, 0xF6]))

    def test_identity_runs_past_the_message(self):
        pdu = nas.attach_request("123456789012345")[:-1]
        with self.assertRaises(nas.NasError):
            nas.imsi_from_attach_request(pdu)

    def test_odd_flag_with_an_end_mark(self):
        pdu = self._pdu(8, bytes.fromhex("09101010325476F8"))
        with self.assertRaises(nas.NasError):
            nas.imsi_from_attach_request(pdu)

    def test_even_flag_without_an_end_mark(self):
        pdu = self._pdu(8, bytes.fromhex("0110101032547698"))
        with self.assertRaises(nas.NasError):
            nas.imsi_from_attach_request(pdu)

    def test_end_mark_before_the_last_octet(self):
        pdu = self._pdu(3, bytes.fromhex("01F010"), odd_flag=False)
        with self.assertRaises(nas.NasError):
            nas.imsi_from_attach_request(pdu)

    def test_non_decimal_nibble(self):
        pdu = self._pdu(3, bytes.fromhex("013AF6"))
        with self.assertRaises(nas.NasError):
            nas.imsi_from_attach_request(pdu)

    def test_too_few_digits(self):
        pdu = self._pdu(3, bytes.fromhex("0112F3"))
        with self.assertRaises(nas.NasError):
            nas.imsi_from_attach_request(pdu)

    def test_arbitrary_bytes_only_raise_nas_error(self):
        rng = random.Random(24)
        for _ in range(500):
            data = bytes(rng.randrange(256) for _ in range(rng.randrange(20)))
            try:
                value = nas.imsi_from_attach_request(data)
            except nas.NasError:
                continue
            self.assertTrue(value is None or value.isdigit())


if __name__ == "__main__":
    unittest.main(verbosity=2)
