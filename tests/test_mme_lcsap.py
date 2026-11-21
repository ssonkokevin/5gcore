"""The MME's LCS-AP client against the E-SMLC simulator.

    python tests/test_mme_lcsap.py

Everything here runs over the length-framed TCP carrier (DECISIONS.md D5):
this host has no AF_SCTP, so the SCTP run is a separate, skipped case in
tests/test_sls.py. The LPP APDUs here are real TS 37.355 messages; the MME
still treats them as opaque bytes, so the tests also prove the relay does
not alter what it carries.
"""

import socket
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "mme" / "src", ROOT / "esmlc" / "src"):
    sys.path.insert(0, str(_p))

from corelib import sls  # noqa: E402
from lib.codecs import lcsap, lpp  # noqa: E402

import esmlc_sim  # noqa: E402
from lcsap_client import LcsApClient, LcsApClientError  # noqa: E402
from lpp_ue import LabUe  # noqa: E402

CORR = b"\x00\x00\x00\x07"
CELL = (0x00A1B2C, 28)
CELL_ONLY = (0x00A1B2E, 28)
UNKNOWN_CELL = (0x00FFFFFF, 28)
IMSI = lcsap.tbcd("001010000000001")
IMSI_TWO = lcsap.tbcd("001010000000002")
UE = LabUe()


def wait_until(predicate, seconds=2.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class AgainstTheSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = esmlc_sim.PositionTable.from_file(esmlc_sim.DEFAULT_CONFIG)
        cls.sim = esmlc_sim.EsmlcSimulator(cls.table, host="127.0.0.1", port=0,
                                          lpp_timeout=2.0)
        cls.sim.start()

    @classmethod
    def tearDownClass(cls):
        cls.sim.stop()

    def client(self, timeout=3.0):
        return LcsApClient("127.0.0.1", self.sim.port, timeout=timeout)

    def locate(self, **kwargs):
        kwargs.setdefault("cell_id", CELL)
        with self.client() as client:
            return client.locate(CORR, **kwargs)

    def test_position_with_lpp_relay(self):
        tokens = []

        def relay(apdu):
            tokens.append(apdu)
            return UE.answer(apdu)

        result = self.locate(imsi=IMSI, horizontal_accuracy_m=50,
                             lpp_transport=relay)
        self.assertTrue(result.positioned)
        self.assertEqual(result.correlation_id, CORR)
        self.assertAlmostEqual(result.circle.latitude, 0.347596, places=4)
        self.assertAlmostEqual(result.circle.longitude, 32.582520, places=4)
        self.assertEqual(result.circle.uncertainty_code,
                         lcsap.uncertainty_code(35.0))
        self.assertEqual(result.fulfilled, lcsap.ACCURACY_FULFILLED)
        self.assertIsNotNone(result.method)
        self.assertEqual(lcsap.positioning_method(result.method),
                         ("e-cid", "generated-location"))
        self.assertEqual(result.lpp_rounds, 1)
        self.assertEqual(len(tokens), 1)
        asked = lpp.parse(tokens[0])
        self.assertEqual(asked.kind, lpp.REQUEST_LOCATION_INFORMATION)
        self.assertTrue(asked.end_transaction)
        self.assertEqual(asked.transaction_id.number, CORR[-1])
        common = (asked.body["criticalExtensions"][1][1]
                  ["commonIEsRequestLocationInformation"])
        self.assertEqual(common["qos"]["horizontalAccuracy"]["accuracy"],
                         lcsap.uncertainty_code(35.0))

    def test_cell_only_target_uses_the_cell_method(self):
        result = self.locate(cell_id=CELL_ONLY, horizontal_accuracy_m=50)
        self.assertTrue(result.positioned)
        self.assertEqual(lcsap.positioning_method(result.method),
                         ("cell-id", "generated-location"))
        self.assertEqual(result.lpp_rounds, 0)
        # A 550 m coverage area cannot satisfy a 50 m request.
        self.assertEqual(result.fulfilled, lcsap.ACCURACY_NOT_FULFILLED)

    def test_requested_accuracy_is_judged_not_assumed(self):
        tokens = []
        result = self.locate(
            imsi=IMSI, horizontal_accuracy_m=20,
            lpp_transport=lambda apdu: tokens.append(apdu) or UE.answer(apdu))
        self.assertEqual(result.fulfilled, lcsap.ACCURACY_NOT_FULFILLED)

    def test_imsi_is_preferred_over_the_cell(self):
        result = self.locate(imsi=IMSI_TWO, cell_id=CELL,
                             lpp_transport=UE.answer)
        self.assertAlmostEqual(result.circle.latitude, 0.313600, places=4)
        self.assertEqual(lcsap.positioning_method(result.method)[0], "otdoa")
        self.assertEqual(result.lpp_rounds, 2)

    def test_unknown_target_fails_closed(self):
        result = self.locate(cell_id=UNKNOWN_CELL)
        self.assertFalse(result.positioned)
        self.assertIsNone(result.circle)
        self.assertEqual(result.cause, ("misc", "unspecified"))

    def test_lpp_without_a_nas_transport_is_an_error(self):
        with self.assertRaises(LcsApClientError) as ctx:
            self.locate(imsi=IMSI)
        self.assertIn("NAS", str(ctx.exception))

    def test_reset_is_acknowledged(self):
        client = self.client()
        try:
            client.connect()
            client.reset()
        finally:
            client.close()

    def test_the_simulator_reports_what_it_did(self):
        self.locate(imsi=IMSI, horizontal_accuracy_m=50,
                    lpp_transport=UE.answer)
        self.assertTrue(wait_until(lambda: self.sim.counters["positioned"] >= 1))
        last = self.sim.status()["last"]
        self.assertEqual(last["result"], "positioned")
        self.assertEqual(last["method"], "e-cid")


class MisbehavingPeers(unittest.TestCase):
    def start(self, handler):
        self.server = sls.SlsServer("127.0.0.1", 0, handler, name="misbehaving")
        self.server.start()
        self.addCleanup(self.server.stop)
        return self.server

    def test_correlation_mismatch_is_rejected(self):
        def wrong_correlation(pdu, connection):
            return lcsap.location_response(b"\x00\x00\x00\x99",
                                           lcsap.circle(0.0, 0.0, 50.0))

        self.start(wrong_correlation)
        with self.assertRaises(LcsApClientError) as ctx:
            with LcsApClient("127.0.0.1", self.server.port, timeout=1.0) as client:
                client.locate(CORR, CELL)
        self.assertIn("Correlation-ID", str(ctx.exception))

    def test_timeout_sends_an_abort(self):
        received = []

        def sink(pdu, connection):
            received.append(pdu)
            return None

        self.start(sink)
        with self.assertRaises(LcsApClientError) as ctx:
            with LcsApClient("127.0.0.1", self.server.port, timeout=0.3) as client:
                client.locate(CORR, CELL)
        self.assertIn("within", str(ctx.exception))

        def aborted():
            for pdu in received:
                try:
                    if lcsap.parse(pdu).procedure == lcsap.PROC_LOCATION_ABORT:
                        return True
                except lcsap.LcsApError:
                    continue
            return False

        self.assertTrue(wait_until(aborted), "the MME did not send Location-Abort-Request")

    def test_peer_close_is_an_error(self):
        def close_now(pdu, connection):
            connection.close()
            return None

        self.start(close_now)
        with self.assertRaises(LcsApClientError) as ctx:
            with LcsApClient("127.0.0.1", self.server.port, timeout=1.0) as client:
                client.locate(CORR, CELL)
        self.assertIn("closed", str(ctx.exception))

    def test_unreadable_answer_is_an_error(self):
        self.start(lambda pdu, connection: b"\xff\x00")
        with self.assertRaises(LcsApClientError) as ctx:
            with LcsApClient("127.0.0.1", self.server.port, timeout=1.0) as client:
                client.locate(CORR, CELL)
        self.assertIn("LCS-AP", str(ctx.exception))

    def test_unreachable_esmlc_is_a_client_error(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        with self.assertRaises(LcsApClientError) as ctx:
            LcsApClient("127.0.0.1", port, timeout=0.5).locate(CORR, CELL)
        self.assertIn("cannot reach", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
