"""LPP codec (TS 37.355): round trips and the shapes the E-SMLC relies on.

    python tests/test_lpp_codec.py
"""

import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.codecs import lpp  # noqa: E402
from lib.codecs import lpp_codec  # noqa: E402

KAMPALA = (0.347596, 32.582520)


def provide_circle(area, **options):
    return lpp.provide_location_information(area=area,
                                            initiator=lpp.INITIATOR_TARGET_DEVICE,
                                            **options)


class RoundTrip(unittest.TestCase):
    def test_request_capabilities_names_the_body_and_transaction(self):
        message = lpp.parse(lpp.request_capabilities(transaction_number=3))
        self.assertEqual(message.kind, lpp.REQUEST_CAPABILITIES)
        self.assertEqual(message.transaction_id,
                         lpp.TransactionId(lpp.INITIATOR_LOCATION_SERVER, 3))
        self.assertTrue(message.end_transaction)
        self.assertIsNone(message.sequence_number)

    def test_provide_capabilities_travels_the_other_way(self):
        wire = lpp.provide_capabilities(
            initiator=lpp.INITIATOR_TARGET_DEVICE, transaction_number=3
        )
        message = lpp.parse(wire)
        self.assertEqual(message.kind, lpp.PROVIDE_CAPABILITIES)
        self.assertEqual(message.transaction_id.initiator,
                         lpp.INITIATOR_TARGET_DEVICE)

    def test_request_and_provide_assistance_data_round_trip(self):
        asked = lpp.parse(lpp.request_assistance_data(transaction_number=4))
        given = lpp.parse(lpp.provide_assistance_data(transaction_number=4))
        self.assertEqual(asked.kind, lpp.REQUEST_ASSISTANCE_DATA)
        self.assertEqual(given.kind, lpp.PROVIDE_ASSISTANCE_DATA)

    def test_request_location_information_carries_the_accuracy_code(self):
        wire = lpp.request_location_information(transaction_number=5,
                                                accuracy_code=27,
                                                response_time_seconds=25)
        message = lpp.parse(wire)
        self.assertEqual(message.kind, lpp.REQUEST_LOCATION_INFORMATION)
        common = (message.body["criticalExtensions"][1][1]
                  ["commonIEsRequestLocationInformation"])
        self.assertEqual(common["locationInformationType"],
                         lpp.LOCATION_ESTIMATE_REQUIRED)
        self.assertEqual(common["qos"]["horizontalAccuracy"],
                         {"accuracy": 27, "confidence": 67})
        # 25 seconds is rounded up to the three ten-second units LPP has.
        self.assertEqual(common["qos"]["responseTime"], {"time": 3})
        self.assertFalse(common["qos"]["velocityRequest"])
        self.assertFalse(common["qos"]["verticalCoordinateRequest"])

    def test_a_position_round_trips_without_losing_uncertainty(self):
        area = lpp.circle(*KAMPALA, 35.0)
        message = lpp.parse(provide_circle(area, transaction_number=6))
        self.assertEqual(message.kind, lpp.PROVIDE_LOCATION_INFORMATION)
        decoded = lpp.location_estimate(message)
        self.assertIsNotNone(decoded)
        # 23 bits over 90 degrees is about 1.1e-5 degrees per step.
        self.assertAlmostEqual(decoded.latitude, area.latitude, places=4)
        self.assertAlmostEqual(decoded.longitude, area.longitude, places=4)
        self.assertEqual(decoded.uncertainty_code, area.uncertainty_code)
        self.assertEqual(decoded.uncertainty_m, area.uncertainty_m)
        self.assertIsNone(lpp.location_failure(message))

    def test_the_southern_hemisphere_and_negative_longitude(self):
        area = lpp.circle(-33.9249, -18.4241, 20.0)
        decoded = lpp.location_estimate(
            lpp.parse(provide_circle(area, transaction_number=7)))
        self.assertAlmostEqual(decoded.latitude, -33.9249, places=4)
        self.assertAlmostEqual(decoded.longitude, -18.4241, places=4)

    def test_abort_and_error_carry_their_cause(self):
        aborted = lpp.parse(lpp.abort(
            "targetDeviceAbort", initiator=lpp.INITIATOR_TARGET_DEVICE,
            transaction_number=8))
        self.assertEqual(aborted.kind, lpp.ABORT)
        self.assertEqual(lpp.abort_cause(aborted), "targetDeviceAbort")
        err = lpp.parse(lpp.error("incorrectDataValue", transaction_number=8))
        self.assertEqual(err.kind, lpp.ERROR)
        self.assertEqual(lpp.error_cause(err), "incorrectDataValue")

    def test_a_message_without_a_transaction_id_parses(self):
        obj = lpp_codec.LPP_PDU_Definitions.LPP_Message
        obj.set_val({
            "endTransaction": True,
            "lpp-MessageBody": ("c1", ("requestCapabilities", {
                "criticalExtensions": ("c1", ("requestCapabilities-r9", {})),
            })),
        })
        message = lpp.parse(obj.to_aper())
        self.assertIsNone(message.transaction_id)
        self.assertTrue(message.end_transaction)


class Position(unittest.TestCase):
    def test_an_empty_answer_is_not_a_position(self):
        message = lpp.parse(lpp.provide_location_information(
            initiator=lpp.INITIATOR_TARGET_DEVICE, transaction_number=1))
        self.assertIsNone(lpp.location_estimate(message))
        self.assertIsNone(lpp.location_failure(message))

    def test_a_failure_cause_is_read(self):
        message = lpp.parse(lpp.provide_location_information(
            failure=lpp.FAILURE_POSITION_METHOD,
            initiator=lpp.INITIATOR_TARGET_DEVICE, transaction_number=1))
        self.assertIsNone(lpp.location_estimate(message))
        self.assertEqual(lpp.location_failure(message),
                         lpp.FAILURE_POSITION_METHOD)

    def test_a_shape_other_than_a_circle_is_refused_not_flattened(self):
        obj = lpp_codec.LPP_PDU_Definitions.LPP_Message
        obj.set_val({
            "endTransaction": True,
            "lpp-MessageBody": ("c1", ("provideLocationInformation", {
                "criticalExtensions": ("c1", (
                    "provideLocationInformation-r9", {
                        "commonIEsProvideLocationInformation": {
                            "locationEstimate": ("ellipsoidPoint", {
                                "latitudeSign": "north",
                                "degreesLatitude": 100,
                                "degreesLongitude": 200,
                            }),
                        },
                    })),
            })),
        })
        message = lpp.parse(obj.to_aper())
        with self.assertRaises(lpp.LppError):
            lpp.location_estimate(message)

    def test_garbage_is_rejected(self):
        for wire in (b"", b"\xff\xff\xff", b"\x00\x01"):
            with self.assertRaises(lpp.LppError):
                lpp.parse(wire)

    def test_an_estimate_is_only_read_from_an_estimate_answer(self):
        message = lpp.parse(lpp.request_location_information(
            transaction_number=2))
        with self.assertRaises(lpp.LppError):
            lpp.location_estimate(message)


class Validation(unittest.TestCase):
    def test_transaction_ids_are_bounded(self):
        with self.assertRaises(lpp.LppError):
            lpp.request_capabilities(transaction_number=256)
        with self.assertRaises(lpp.LppError):
            lpp.request_capabilities(initiator="someoneElse")

    def test_accuracy_and_response_time_are_bounded(self):
        with self.assertRaises(lpp.LppError):
            lpp.request_location_information(accuracy_code=128)
        with self.assertRaises(lpp.LppError):
            lpp.request_location_information(response_time_seconds=2000)

    def test_raw_ies_and_convenience_fields_are_mutually_exclusive(self):
        with self.assertRaises(lpp.LppError):
            lpp.request_location_information({}, accuracy_code=10)
        with self.assertRaises(lpp.LppError):
            lpp.provide_location_information(
                {}, area=lpp.circle(*KAMPALA, 10.0))


class ConcurrentCodec(unittest.TestCase):
    def test_the_shared_codec_object_is_not_corrupted_across_threads(self):
        def work(worker):
            for round_no in range(30):
                number = worker * 30 + round_no
                latitude = 0.30 + worker * 0.01
                wire = provide_circle(
                    lpp.circle(latitude, 32.5, 40.0), transaction_number=number)
                message = lpp.parse(wire)
                self.assertEqual(message.transaction_id.number, number)
                decoded = lpp.location_estimate(message)
                self.assertAlmostEqual(decoded.latitude, latitude, places=3)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, range(8)))


class GeneratedCodec(unittest.TestCase):
    def test_committed_codec_matches_the_committed_asn1(self):
        """The .asn file is the source; the .py beside it is generated from it."""
        import subprocess
        import tempfile

        generator = ROOT / "lib" / "codecs" / "lpp_codec.py"
        asn = ROOT / "lib" / "codecs" / "asn1" / "lpp.asn"
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
        self.assertTrue(header.startswith("# Generated by lib/codecs/build_lpp.py"))
        self.assertEqual(committed[len(header):], generated,
                         "lpp_codec.py is stale; rerun lib/codecs/build_lpp.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
