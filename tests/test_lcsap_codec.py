"""LCS-AP codec: round trips and the shapes the location function relies on.

    python tests/test_lcsap_codec.py
"""

import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.codecs import lcsap  # noqa: E402

CORR = b"\x00\x00\x00\x07"
CELL = (0x00A1B2C, 28)


class RoundTrip(unittest.TestCase):
    def test_location_request_fields(self):
        wire = lcsap.location_request(CORR, CELL, imsi=lcsap.tbcd("001010000000001"),
                                      horizontal_accuracy_m=50)
        message = lcsap.parse(wire)
        self.assertEqual(message.kind, lcsap.INITIATING)
        self.assertEqual(message.procedure, lcsap.PROC_LOCATION_SERVICE)
        self.assertEqual(message.name, "Location-Request")
        self.assertEqual(lcsap.correlation_id(message), CORR)
        self.assertEqual(message.ie("Location-Type"), "geographic-Information")
        self.assertEqual(message.ie("IMSI"), lcsap.tbcd("001010000000001"))
        ecgi = message.ie("E-CGI")
        self.assertEqual(ecgi["pLMNidentity"], lcsap.LAB_PLMN)
        self.assertEqual(ecgi["cell-ID"], CELL)
        self.assertEqual(message.ie("LCS-QoS"), {"horizontal-Accuracy": 19})

    def test_response_with_a_circle_round_trips_without_losing_uncertainty(self):
        area = lcsap.circle(0.347596, 32.582520, 35.0)
        wire = lcsap.location_response(CORR, area,
                                       fulfilled=lcsap.ACCURACY_NOT_FULFILLED,
                                       positioning_method=b"\x01")
        message = lcsap.parse(wire)
        self.assertEqual(message.kind, lcsap.SUCCESSFUL)
        self.assertEqual(message.name, "Location-Response")
        decoded = lcsap.decode_area(message)
        self.assertIsNotNone(decoded)
        # 24 bits over 360 degrees is about 2.1e-5 degrees per step.
        self.assertAlmostEqual(decoded.latitude, area.latitude, places=4)
        self.assertAlmostEqual(decoded.longitude, area.longitude, places=4)
        self.assertEqual(decoded.uncertainty_code, area.uncertainty_code)
        self.assertEqual(decoded.uncertainty_m, area.uncertainty_m)
        self.assertEqual(message.ie("Accuracy-Fulfillment-Indicator"),
                         lcsap.ACCURACY_NOT_FULFILLED)
        self.assertEqual(message.ie("Positioning-Data"),
                         {"positioning-Data-Set": [b"\x01"]})

    def test_failure_response_is_unsuccessful_and_carries_a_cause(self):
        wire = lcsap.location_response(CORR, None, cause=("misc", "unspecified"))
        message = lcsap.parse(wire)
        self.assertEqual(message.kind, lcsap.UNSUCCESSFUL)
        self.assertIsNone(lcsap.decode_area(message))
        self.assertEqual(message.ie("LCS-Cause"), ("misc", "unspecified"))

    def test_abort_request(self):
        message = lcsap.parse(lcsap.location_abort(CORR, ("misc", "unspecified")))
        self.assertEqual(message.procedure, lcsap.PROC_LOCATION_ABORT)
        self.assertEqual(message.name, "Location-Abort-Request")
        self.assertEqual(lcsap.correlation_id(message), CORR)

    def test_lpp_relay_message(self):
        apdu = b"\x01\x02\x03\x04"
        message = lcsap.parse(lcsap.connection_oriented_information(CORR, apdu))
        self.assertEqual(message.procedure, lcsap.PROC_CONNECTION_ORIENTED_INFORMATION)
        self.assertEqual(message.ie("Payload-Type"), lcsap.PAYLOAD_LPP)
        self.assertEqual(lcsap.lpp_apdu(message), apdu)

    def test_reset(self):
        self.assertEqual(lcsap.parse(lcsap.reset_request()).procedure,
                         lcsap.PROC_RESET)
        self.assertEqual(lcsap.parse(lcsap.reset_acknowledge()).kind,
                         lcsap.SUCCESSFUL)

    def test_garbage_is_rejected_not_decoded(self):
        with self.assertRaises(lcsap.LcsApError):
            lcsap.parse(b"\xff\xff\xff")


class ConcurrentCodec(unittest.TestCase):
    def test_the_shared_codec_object_is_not_corrupted_across_threads(self):
        # The MME opens one SLs dialogue per session, so encodes and decodes
        # for different subscribers run in different threads at the same time.
        def work(worker):
            for round_no in range(100):
                correlation = (worker * 100000 + round_no).to_bytes(4, "big")
                area = lcsap.circle(0.3 + worker * 0.01, 32.5, 40.0)
                wire = lcsap.location_response(
                    correlation, area, fulfilled=lcsap.ACCURACY_FULFILLED)
                message = lcsap.parse(wire)
                self.assertEqual(lcsap.correlation_id(message), correlation)
                decoded = lcsap.decode_area(message)
                self.assertEqual(decoded.uncertainty_code, area.uncertainty_code)
                self.assertAlmostEqual(decoded.latitude, area.latitude, places=3)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, range(8)))


class Uncertainty(unittest.TestCase):
    def test_codes_follow_ts_23_032(self):
        self.assertEqual(lcsap.uncertainty_metres(0), 0.0)
        self.assertAlmostEqual(lcsap.uncertainty_metres(1), 1.0, places=6)
        self.assertAlmostEqual(lcsap.uncertainty_metres(2), 2.1, places=6)
        self.assertEqual(lcsap.uncertainty_code(1.0), 1)
        self.assertEqual(lcsap.uncertainty_code(2.1), 2)
        # A requested radius is rounded up to the next representable code.
        self.assertEqual(lcsap.uncertainty_code(2.05), 2)
        self.assertEqual(lcsap.uncertainty_code(2.2), 3)

    def test_radius_must_be_positive(self):
        with self.assertRaises(lcsap.LcsApError):
            lcsap.circle(0.0, 0.0, 0.0)

    def test_large_radius_does_not_fit(self):
        with self.assertRaises(lcsap.LcsApError):
            lcsap.circle(0.0, 0.0, 10 * 1.1 ** 130)


class GeneratedCodec(unittest.TestCase):
    def test_committed_codec_matches_the_committed_asn1(self):
        """The .asn file is the source; the .py beside it is generated from it."""
        import subprocess
        import tempfile

        generator = ROOT / "lib" / "codecs" / "lcsap_codec.py"
        asn = ROOT / "lib" / "codecs" / "asn1" / "lcsap.asn"
        script = (
            "import sys\n"
            "from pycrate_asn1c.asnproc import compile_text\n"
            "from pycrate_asn1c.generator import PycrateGenerator\n"
            "compile_text(open(sys.argv[1], encoding='utf-8').read(), checkconst=True)\n"
            "PycrateGenerator(sys.argv[2])\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "fresh.py"
            subprocess.run([sys.executable, "-c", script, str(asn), str(fresh)],
                           check=True, capture_output=True)
            generated = fresh.read_text(encoding="utf-8")
        committed = generator.read_text(encoding="utf-8")
        header = committed.split("# -*- coding: UTF-8 -*-", 1)[0]
        self.assertTrue(header.startswith("# Generated by lib/codecs/build_lcsap.py"))
        self.assertEqual(committed[len(header):], generated,
                         "lcsap_codec.py is stale; rerun lib/codecs/build_lcsap.py")


class PlmnIdentity(unittest.TestCase):
    def test_two_digit_mnc_matches_the_committed_lab_plmn(self):
        # 001-01 in TS 29.274 order is 00 f1 10, the same bytes the GMLC
        # parses out of an ECGI. It is not the TBCD digit order.
        self.assertEqual(lcsap.plmn_identity("001", "01"), b"\x00\xf1\x10")
        self.assertEqual(lcsap.plmn_identity("001", "01"), lcsap.LAB_PLMN)
        self.assertNotEqual(lcsap.tbcd("00101"), lcsap.LAB_PLMN)

    def test_three_digit_mnc(self):
        self.assertEqual(lcsap.plmn_identity("310", "260"), b"\x13\x00\x62")

    def test_bad_digits_are_rejected(self):
        with self.assertRaises(lcsap.LcsApError):
            lcsap.plmn_identity("01", "01")
        with self.assertRaises(lcsap.LcsApError):
            lcsap.plmn_identity("001", "1")


class PositioningMethod(unittest.TestCase):
    def test_method_and_usage_are_decoded_from_the_octet(self):
        for octet, name in ((lcsap.METHOD_CELL_ID, "cell-id"),
                            (lcsap.METHOD_E_CID, "e-cid"),
                            (lcsap.METHOD_OTDOA, "otdoa"),
                            (lcsap.METHOD_U_TDOA, "u-tdoa")):
            self.assertEqual(lcsap.positioning_method(octet),
                             (name, "generated-location"))

    def test_reserved_bits_are_reported_not_guessed(self):
        self.assertEqual(lcsap.positioning_method(0x09)[0],
                         "reserved-method-00001")
        self.assertEqual(lcsap.positioning_method(0x07)[1], "reserved-usage")

    def test_positioning_data_reads_the_first_method(self):
        wire = lcsap.location_response(
            CORR, lcsap.circle(0.0, 0.0, 35.0),
            positioning_method=bytes([lcsap.METHOD_E_CID]))
        self.assertEqual(lcsap.positioning_data(lcsap.parse(wire)),
                         lcsap.METHOD_E_CID)


class Rejections(unittest.TestCase):
    def test_correlation_id_must_be_four_octets(self):
        with self.assertRaises(lcsap.LcsApError):
            lcsap.location_request(b"\x00", CELL)

    def test_a_shape_the_mme_does_not_flatten_is_an_error(self):
        message = lcsap.LcsApMessage(
            kind=lcsap.SUCCESSFUL, procedure=0, criticality="reject",
            name="Location-Response",
            ies=[("Geographical-Area", {"point": {
                "geographical-Coordinates": {
                    "latitudeSign": "north",
                    "degreesLatitude": 0,
                    "degreesLongitude": 0,
                }
            }})],
        )
        with self.assertRaises(lcsap.LcsApError):
            lcsap.decode_area(message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
