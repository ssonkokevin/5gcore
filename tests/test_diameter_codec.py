"""Diameter AVP encoding and the two padding conventions in the field.

    python tests/test_diameter_codec.py

RFC 6733 excludes the padding octets from the AVP length; the next AVP
starts on the four-octet boundary. Some peers count the padding in the
length anyway. The MME must read either.
"""

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from corelib import diameter as d  # noqa: E402


def padded(avp: d.AVP) -> bytes:
    """Re-encode with the length counting the padding, as lenient peers do."""
    encoded = avp.encode()
    frame = len(encoded)
    out = bytearray(encoded)
    out[5] = (frame >> 16) & 0xFF
    out[6] = (frame >> 8) & 0xFF
    out[7] = frame & 0xFF
    return bytes(out)


class AvpFraming(unittest.TestCase):
    def test_encode_excludes_padding_from_the_length(self):
        encoded = d.AVP_UTF8(d.AVP_ORIGIN_HOST, "a").encode()
        self.assertEqual(len(encoded), 12)
        self.assertEqual(encoded[7], 9)
        self.assertEqual(encoded[8:9], b"a")
        self.assertEqual(encoded[9:], b"\x00\x00\x00")

    def test_round_trip(self):
        avps = [
            d.AVP_UTF8(d.AVP_ORIGIN_HOST, "mme.core.local"),
            d.AVP_U32(d.AVP_RESULT_CODE, d.RESULT_SUCCESS),
            d.AVP(d.AVP_ECGI, bytes.fromhex("00f110 000a1b2c".replace(" ", "")),
                  vendor_id=d.VENDOR_3GPP),
        ]
        decoded = d.decode_avps(b"".join(a.encode() for a in avps))
        self.assertEqual([a.code for a in decoded],
                         [d.AVP_ORIGIN_HOST, d.AVP_RESULT_CODE, d.AVP_ECGI])
        self.assertEqual(decoded[0].as_string(), "mme.core.local")
        self.assertEqual(decoded[1].as_uint32(), d.RESULT_SUCCESS)
        self.assertEqual(decoded[2].vendor_id, d.VENDOR_3GPP)
        # The ECGI is seven octets; its trailing padding is not in the value.
        self.assertEqual(decoded[2].value, bytes.fromhex("00f110000a1b2c"))

    def test_a_padded_sender_does_not_desynchronise_the_next_avp(self):
        # "peer.corp" is nine octets, so a peer that counts padding declares
        # twelve where RFC 6733 declares nine.
        stream = (padded(d.AVP_UTF8(d.AVP_ORIGIN_HOST, "peer.corp"))
                  + d.AVP_U32(d.AVP_RESULT_CODE, d.RESULT_SUCCESS).encode())
        decoded = d.decode_avps(stream)
        self.assertEqual([a.code for a in decoded],
                         [d.AVP_ORIGIN_HOST, d.AVP_RESULT_CODE])
        self.assertEqual(decoded[0].as_string(), "peer.corp")
        self.assertEqual(decoded[1].as_uint32(), d.RESULT_SUCCESS)

    def test_grouped_children_inherit_the_tolerance(self):
        child = padded(d.AVP_UTF8(1000, "abc", vendor_id=d.VENDOR_3GPP))
        group = d.AVP(d.AVP_LCS_EPS_CLIENT_NAME, child, vendor_id=d.VENDOR_3GPP)
        decoded = d.decode_avps(group.encode())
        self.assertEqual(len(decoded), 1)
        children = decoded[0].as_grouped()
        self.assertEqual(children[0].code, 1000)
        self.assertEqual(children[0].as_string(), "abc")

    def test_a_truncated_avp_is_refused(self):
        encoded = d.AVP_UTF8(d.AVP_ORIGIN_HOST, "gmlc.lab.local").encode()
        self.assertEqual(d.decode_avps(encoded[:10]), [])

    def test_a_zero_length_avp_is_refused(self):
        hostile = struct.pack("!II", (d.AVP_USER_NAME << 8) | 0x40, 0)
        self.assertEqual(d.decode_avps(hostile + b"\x00" * 4), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
