"""Cross-language codec check over the committed golden SLg frames.

The same fixture is read by the gateway's GoldenSignallingTest. Both codecs
must decode every octet to the same values and re-encode the frame byte for
byte; otherwise one side is reading a field the other wrote differently.

    python tests/test_golden_slg.py

The fixture lives in the sibling gmlc repository. When that repository is not
checked out the test is skipped, and docs/CONSISTENCY-AUDIT.md records the
cross-repo check as unavailable in that environment.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from corelib import diameter as d  # noqa: E402

GOLDEN = ROOT.parent / "gmlc" / "fixtures" / "golden" / "slg.json"


def compare_avps(test, where, expected, actual):
    test.assertEqual(len(actual), len(expected), f"{where}: AVP count")
    for index, (node, avp) in enumerate(zip(expected, actual)):
        at = f"{where} AVP {node['code']}"
        test.assertEqual(avp.code, node["code"], f"{at}: code")
        test.assertEqual(avp.vendor_id, node["vendor_id"], f"{at}: vendor")
        if "value_utf8" in node:
            test.assertEqual(avp.as_string(), node["value_utf8"], f"{at}: text")
        if "value_u32" in node:
            test.assertEqual(avp.as_uint32(), node["value_u32"], f"{at}: Unsigned32")
        if "value_hex" in node:
            test.assertEqual(avp.value.hex(), node["value_hex"], f"{at}: octets")
        if "value_tbcd" in node:
            test.assertEqual(d.tbcd_decode(avp.value), node["value_tbcd"], f"{at}: TBCD")
        if "children" in node:
            compare_avps(test, at, node["children"], avp.as_grouped())


class GoldenSlgFrames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GOLDEN.exists():
            raise unittest.SkipTest(f"golden fixture not available: {GOLDEN}")
        cls.vectors = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"]

    def test_every_frame_decodes_and_re_encodes(self):
        for vector in self.vectors:
            wire = bytes.fromhex(vector["hex"])
            message = d.decode_message(wire)
            expected = vector["message"]
            name = vector["name"]

            self.assertEqual(message.command_code, expected["command_code"], f"{name}: command")
            self.assertEqual(message.app_id, expected["application_id"], f"{name}: application")
            self.assertEqual(message.flags, expected["flags"], f"{name}: flags")
            self.assertEqual(message.hop_by_hop, expected["hop_by_hop"], f"{name}: hop-by-hop")
            self.assertEqual(message.end_to_end, expected["end_to_end"], f"{name}: end-to-end")

            compare_avps(self, name, expected["avps"], message.avps)

            self.assertEqual(message.encode(), wire, f"{name}: re-encoding")

    def test_the_msisdn_octets_are_tbcd_not_text(self):
        vector = next(v for v in self.vectors if v["name"] == "slg-plr-request")
        msisdn = next(avp for avp in vector["message"]["avps"] if avp["code"] == d.AVP_MSISDN)
        octets = bytes.fromhex(msisdn["value_hex"])

        self.assertEqual(d.tbcd_decode(octets), "256700000001")
        self.assertEqual(d.tbcd_encode("256700000001"), octets)
        self.assertNotEqual(octets, b"256700000001")
        self.assertEqual(d.tbcd_decode(d.tbcd_encode("256")), "256")


if __name__ == "__main__":
    unittest.main(verbosity=2)
