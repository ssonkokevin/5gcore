"""The lab UE (esmlc/src/lpp_ue.py) and the E-SMLC's capability exchange.

    python tests/test_lpp_ue.py

The UE speaks real TS 37.355 messages over the same HTTP seam the MME's NAS
relay uses. Everything runs on the D5 TCP carrier with synthetic lab
coordinates (PLMN 001-01).
"""

import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "mme" / "src", ROOT / "esmlc" / "src"):
    sys.path.insert(0, str(_p))

from lib.codecs import lcsap, lpp, lpp_codec  # noqa: E402

import esmlc_sim  # noqa: E402
from lcsap_client import LcsApClient  # noqa: E402
from lpp_ue import LabUe, UeEndpoint  # noqa: E402

CORR = b"\x00\x00\x00\x21"
CELL = (0x00A1B2C, 28)
IMSI = lcsap.tbcd("001010000000001")
KAMPALA = (0.347596, 32.582520)


def ask(transaction=7):
    return lpp.request_location_information(transaction_number=transaction,
                                            accuracy_code=40)


class Answering(unittest.TestCase):
    def test_a_location_request_gets_an_answer_in_the_same_transaction(self):
        message = lpp.parse(LabUe().answer(ask(7)))
        self.assertEqual(message.kind, lpp.PROVIDE_LOCATION_INFORMATION)
        self.assertEqual(message.transaction_id,
                         lpp.TransactionId(lpp.INITIATOR_TARGET_DEVICE, 7))
        self.assertIsNone(lpp.location_estimate(message))
        self.assertIsNone(lpp.location_failure(message))

    def test_a_capability_request_gets_provide_capabilities(self):
        message = lpp.parse(LabUe().answer(
            lpp.request_capabilities(transaction_number=9)))
        self.assertEqual(message.kind, lpp.PROVIDE_CAPABILITIES)
        self.assertEqual(message.transaction_id.initiator,
                         lpp.INITIATOR_TARGET_DEVICE)
        self.assertEqual(message.transaction_id.number, 9)

    def test_a_configured_position_is_reported_with_its_uncertainty(self):
        area = lpp.circle(*KAMPALA, 25.0)
        decoded = lpp.location_estimate(
            lpp.parse(LabUe(position=area).answer(ask())))
        self.assertAlmostEqual(decoded.latitude, KAMPALA[0], places=4)
        self.assertAlmostEqual(decoded.longitude, KAMPALA[1], places=4)
        self.assertEqual(decoded.uncertainty_code, area.uncertainty_code)

    def test_the_answer_mirrors_end_transaction(self):
        wire = lpp.request_location_information(transaction_number=4,
                                                end_transaction=False)
        self.assertFalse(lpp.parse(LabUe().answer(wire)).end_transaction)

    def test_an_undecodable_apdu_is_not_answered(self):
        for wire in (b"", b"\xff\xff\xff", b"\x00\x01"):
            with self.subTest(wire=wire):
                self.assertIsNone(LabUe().answer(wire))

    def test_a_message_without_a_transaction_is_not_answered(self):
        obj = lpp_codec.LPP_PDU_Definitions.LPP_Message
        obj.set_val({
            "endTransaction": True,
            "lpp-MessageBody": ("c1", ("requestCapabilities", {
                "criticalExtensions": ("c1", ("requestCapabilities-r9", {})),
            })),
        })
        self.assertIsNone(LabUe().answer(obj.to_aper()))

    def test_a_request_the_ue_does_not_implement_is_not_answered(self):
        self.assertIsNone(LabUe().answer(
            lpp.request_assistance_data(transaction_number=1)))


class Misbehaving(unittest.TestCase):
    def test_ignore_stays_silent(self):
        self.assertIsNone(LabUe(behaviour="ignore").answer(ask()))

    def test_abort_carries_the_target_cause(self):
        message = lpp.parse(LabUe(behaviour="abort").answer(ask(5)))
        self.assertEqual(message.kind, lpp.ABORT)
        self.assertEqual(message.transaction_id,
                         lpp.TransactionId(lpp.INITIATOR_TARGET_DEVICE, 5))
        self.assertEqual(lpp.abort_cause(message), "targetDeviceAbort")

    def test_failure_answers_the_transaction_with_a_cause(self):
        message = lpp.parse(LabUe(behaviour="failure").answer(ask(5)))
        self.assertEqual(message.kind, lpp.PROVIDE_LOCATION_INFORMATION)
        self.assertIsNone(lpp.location_estimate(message))
        self.assertEqual(lpp.location_failure(message),
                         lpp.FAILURE_POSITION_METHOD)

    def test_error_carries_the_configured_cause(self):
        message = lpp.parse(LabUe(behaviour="error").answer(ask(5)))
        self.assertEqual(message.kind, lpp.ERROR)
        self.assertEqual(lpp.error_cause(message), "incorrectDataValue")

    def test_wrong_transaction_is_a_valid_answer_under_another_number(self):
        message = lpp.parse(LabUe(behaviour="wrong-transaction").answer(ask(5)))
        self.assertEqual(message.kind, lpp.PROVIDE_LOCATION_INFORMATION)
        self.assertEqual(message.transaction_id.number, 6)

    def test_the_shift_wraps_at_255(self):
        message = lpp.parse(
            LabUe(behaviour="wrong-transaction").answer(ask(255)))
        self.assertEqual(message.transaction_id.number, 0)

    def test_the_shift_is_configurable(self):
        message = lpp.parse(LabUe(behaviour="wrong-transaction",
                                  transaction_shift=3).answer(ask(5)))
        self.assertEqual(message.transaction_id.number, 8)


class Validation(unittest.TestCase):
    def test_unknown_behaviour_is_rejected(self):
        with self.assertRaises(ValueError):
            LabUe(behaviour="sleep")

    def test_transaction_shift_is_bounded(self):
        for bad in (0, 256, -1):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    LabUe(transaction_shift=bad)


class HttpEndpoint(unittest.TestCase):
    def post(self, endpoint, document):
        body = (json.dumps(document).encode() if isinstance(document, dict)
                else document)
        request = urllib.request.Request(
            endpoint.url, data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=2.0) as response:
            return response.status, response.read()

    def test_the_endpoint_answers_with_hex_and_records_the_post(self):
        with UeEndpoint(LabUe(position=lpp.circle(*KAMPALA, 30.0))) as endpoint:
            status, body = self.post(endpoint, {
                "imsi": "001010000000001", "apdu": ask(3).hex()})
            self.assertEqual(status, 200)
            answer = lpp.parse(bytes.fromhex(json.loads(body)["apdu"]))
            self.assertEqual(answer.kind, lpp.PROVIDE_LOCATION_INFORMATION)
            imsi, apdu = endpoint.requests[0]
            self.assertEqual(imsi, "001010000000001")
            self.assertEqual(lpp.parse(apdu).transaction_id.number, 3)

    def test_silence_is_204_with_no_body(self):
        with UeEndpoint(LabUe(behaviour="ignore")) as endpoint:
            status, body = self.post(
                endpoint, {"imsi": "x", "apdu": ask().hex()})
            self.assertEqual(status, 204)
            self.assertEqual(body, b"")

    def test_an_unreadable_body_is_400(self):
        with UeEndpoint(LabUe()) as endpoint:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.post(endpoint, b"not json")
            self.assertEqual(ctx.exception.code, 400)

    def test_an_apdu_that_is_not_hex_is_400(self):
        with UeEndpoint(LabUe()) as endpoint:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.post(endpoint, {"imsi": "x", "apdu": "zz"})
            self.assertEqual(ctx.exception.code, 400)


class CapabilityExchange(unittest.TestCase):
    """The opt-in capability transaction the E-SMLC now offers."""

    def setUp(self):
        self.table = esmlc_sim.PositionTable.from_dict({"positions": [{
            "imsi": "001010000000001",
            "cell": "0x00A1B2C",
            "latitude": KAMPALA[0],
            "longitude": KAMPALA[1],
            "radius_m": 35.0,
            "method": "e-cid",
            "lpp_rounds": 1,
        }]})
        self.sim = esmlc_sim.EsmlcSimulator(
            self.table, host="127.0.0.1", port=0, lpp_timeout=1.0,
            capability_exchange=True)
        self.sim.start()
        self.addCleanup(self.sim.stop)

    def locate(self, transport):
        with LcsApClient("127.0.0.1", self.sim.port, timeout=3.0) as client:
            return client.locate(CORR, CELL, imsi=IMSI,
                                 lpp_transport=transport)

    def test_capabilities_come_first_then_the_dialogue_locates(self):
        result = self.locate(LabUe().answer)
        self.assertTrue(result.positioned)
        # The MME relays LPP opaquely, so its round count includes the
        # capability transaction; the simulator separates them.
        self.assertEqual(result.lpp_rounds, 2)
        self.assertEqual(self.sim.counters["lpp_capabilities"], 1)
        self.assertEqual(self.sim.counters["lpp_rounds"], 1)
        self.assertEqual(self.sim.counters["lpp_rejected"], 0)

    def test_the_capability_transaction_takes_the_first_number(self):
        asked = []
        ue = LabUe()

        def transport(apdu):
            asked.append(lpp.parse(apdu))
            return ue.answer(apdu)

        self.locate(transport)
        self.assertEqual(asked[0].kind, lpp.REQUEST_CAPABILITIES)
        self.assertEqual(asked[0].transaction_id.number, CORR[-1])
        self.assertEqual(asked[1].kind, lpp.REQUEST_LOCATION_INFORMATION)
        self.assertEqual(asked[1].transaction_id.number, CORR[-1] + 1)

    def test_an_answer_under_the_wrong_number_fails_the_dialogue(self):
        result = self.locate(
            LabUe(behaviour="wrong-transaction").answer)
        self.assertFalse(result.positioned)
        self.assertEqual(self.sim.counters["lpp_rejected"], 1)
        self.assertEqual(self.sim.counters["lpp_rounds"], 0)

    def test_an_abort_at_capability_stage_fails_the_dialogue(self):
        result = self.locate(LabUe(behaviour="abort").answer)
        self.assertFalse(result.positioned)
        self.assertEqual(self.sim.counters["lpp_rejected"], 1)
        self.assertEqual(self.sim.counters["lpp_capabilities"], 1)

    def test_an_unreadable_capability_answer_is_rejected(self):
        result = self.locate(lambda apdu: b"\xff\x00")
        self.assertFalse(result.positioned)
        self.assertEqual(self.sim.counters["lpp_rejected"], 1)
        self.assertEqual(self.sim.counters["lpp_rounds"], 0)

    def test_a_ue_that_never_answers_capabilities_fails_the_dialogue(self):
        result = self.locate(LabUe(behaviour="ignore").answer)
        self.assertFalse(result.positioned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
