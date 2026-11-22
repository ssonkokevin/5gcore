"""RFC 6733 clause 4.1 framing for every Diameter AVP encoder in the core.

The core has three AVP encoders: ``corelib.diameter`` (MME/SLg and anything new),
``diameter_server`` (S6a/Cx) and ``ocs_client`` (Ro). They were written
independently and two of them had drifted from the wire format: a three-octet
code followed by a four-octet length. A peer reads the first four octets as the
code, so those frames carried no usable AVPs. These tests pin the header layout
and keep the three encoders byte-identical.
"""

import struct
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "diameter" / "src"))
sys.path.insert(0, str(ROOT / "ocs" / "src"))

# diameter_server imports mysql.connector at module level; the framing tests
# never touch the database.
if "mysql" not in sys.modules:
    mysql = types.ModuleType("mysql")
    connector = types.ModuleType("mysql.connector")
    connector.connect = lambda **kwargs: None
    mysql.connector = connector
    sys.modules["mysql"] = mysql
    sys.modules["mysql.connector"] = connector

from corelib import diameter as d  # noqa: E402
import diameter_server as s6a  # noqa: E402
import ocs_client as ocs  # noqa: E402

MSISDN = bytes.fromhex("527600000010")


class AvpHeaderLayout(unittest.TestCase):
    def test_base_avp_header_matches_rfc_6733(self):
        encoded = d.AVP(d.AVP_SESSION_ID, b"gmlc;golden;0001").encode()
        # code 263 four octets | flags 0x40 (M) | length 24 three octets
        self.assertEqual(encoded[:8].hex(), "0000010740000018")
        self.assertEqual(len(encoded), 24)

    def test_vendor_avp_header_matches_rfc_6733(self):
        encoded = d.AVP(d.AVP_MSISDN, MSISDN, vendor_id=d.VENDOR_3GPP).encode()
        # code 701 | flags 0xC0 (V|M) | length 18 | vendor 10415 | 6 data | 2 pad
        self.assertEqual(encoded.hex(), "000002bdc0000012000028af5276000000100000")
        self.assertEqual(len(encoded), 20)

    def test_decode_reads_what_encode_wrote(self):
        encoded = d.AVP(d.AVP_MSISDN, MSISDN, vendor_id=d.VENDOR_3GPP).encode()
        code, flags, length, vendor_id, data, next_offset = s6a.decode_avp(encoded)
        self.assertEqual((code, flags, length, vendor_id), (701, 0xC0, 18, 10415))
        self.assertEqual(data, MSISDN)
        self.assertEqual(next_offset, len(encoded))

    def test_padding_is_skipped_between_avps(self):
        first = d.AVP(d.AVP_MSISDN, MSISDN, vendor_id=d.VENDOR_3GPP)
        second = d.AVP(d.AVP_SESSION_ID, b"abc")
        decoded = s6a.decode_all_avps(first.encode() + second.encode())
        self.assertEqual([item["code"] for item in decoded], [701, 263])
        self.assertEqual(decoded[1]["data"], b"abc")


class EncodersAgree(unittest.TestCase):
    """The server and OCS encoders must emit the same octets as corelib."""

    def test_diameter_server_encoder_agrees_with_corelib(self):
        self.assertEqual(
            s6a.encode_avp(701, 0xC0, d.VENDOR_3GPP, MSISDN),
            d.AVP(701, MSISDN, d.VENDOR_3GPP).encode())

    def test_ocs_encoder_agrees_with_corelib(self):
        self.assertEqual(
            ocs.encode_avp(701, 0xC0, d.VENDOR_3GPP, MSISDN),
            d.AVP(701, MSISDN, d.VENDOR_3GPP).encode())

    def test_ocs_message_header_is_the_twenty_octet_rfc_layout(self):
        frame = ocs.build_diameter_message(
            272, 0x80, 4, [ocs.encode_uint32_avp(268, 2001)])
        self.assertEqual(frame[0], 1)
        self.assertEqual(int.from_bytes(frame[1:4], "big"), len(frame))
        self.assertEqual(frame[4], 0x80)
        self.assertEqual(int.from_bytes(frame[5:8], "big"), 272)
        self.assertEqual(struct.unpack("!I", frame[8:12])[0], 4)


if __name__ == "__main__":
    unittest.main()
