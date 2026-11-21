"""MME LCS failure modes (PLAN 2g) and the no-session-leak check (2h).

    python tests/test_mme_failure_modes.py

Every E-SMLC answer here is synthetic and every position comes from
esmlc/config/lab_positions.json or mme/config/lab_cells.json, for lab PLMN
001-01. The SLs link uses the D5 TCP carrier, not SCTP.

A "malformed ASN.1" test can only exercise LCS-AP: the MME relays LPP as an
opaque APDU (TS 37.355 decoding is a later work package), so it cannot judge
an LPP APDU by itself. When the UE or the E-SMLC rejects a dialogue, the MME
falls back to Cell-ID and says so. There is no S1AP transport yet, so a
handover can only be simulated as the UE context changing under a live
request: the request keeps the cell it started with and the next request uses
the new one.
"""

import concurrent.futures
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "mme" / "src", ROOT / "esmlc" / "src", ROOT / "tests"):
    sys.path.insert(0, str(_p))

from corelib import diameter as d  # noqa: E402
from corelib import sls  # noqa: E402
from lib.codecs import lcsap  # noqa: E402

import cell_plan  # noqa: E402
import esmlc_sim  # noqa: E402
import ue_contexts  # noqa: E402
from lcsap_client import LcsApClient, LcsApClientError  # noqa: E402
from location_service import LocationService  # noqa: E402
from test_mme_location import NasStub  # noqa: E402

PLMN = lcsap.LAB_PLMN
CELL_A = 0x00A1B2C
CELL_C = 0x00A1B2E
LAB_UE_A = "001010000000001"
LAB_UE_C = "001010000000003"


def connected(imsi=LAB_UE_A, cell=CELL_A, **kwargs):
    return ue_contexts.UeContext(imsi=imsi, plmn=PLMN, cell=cell, **kwargs)


class ScriptedEsmc:
    """An SLs listener that follows one named script, for failure injection."""

    def __init__(self, script):
        self.script = script
        self.received = []
        self.arrived = threading.Event()
        self.release = threading.Event()
        self.aborted = threading.Event()
        self.server = sls.SlsServer("127.0.0.1", 0, self._handle,
                                    name="scripted-esmlc")

    @property
    def port(self):
        return self.server.port

    def __enter__(self):
        self.server.start()
        return self

    def __exit__(self, *exc):
        self.release.set()
        self.server.stop()

    def _handle(self, pdu, connection):
        self.received.append(pdu)
        try:
            message = lcsap.parse(pdu)
        except lcsap.LcsApError:
            return None
        if message.procedure == lcsap.PROC_LOCATION_ABORT:
            self.aborted.set()
            return None
        correlation = lcsap.correlation_id(message)
        if correlation is None:
            return None
        self.arrived.set()
        if self.script == "silent":
            self.release.wait(5.0)
            try:
                late = connection.receive(0.5)
            except (sls.SlsError, OSError):
                return None
            if late:
                try:
                    answer = lcsap.parse(late)
                except lcsap.LcsApError:
                    return None
                if answer.procedure == lcsap.PROC_LOCATION_ABORT:
                    self.aborted.set()
            return None
        if self.script == "malformed":
            return b"\x00\x01"
        if self.script == "wrong-correlation":
            return lcsap.location_response(
                b"\xde\xad\xbe\xef", lcsap.circle(0.3, 32.5, 10.0))
        if self.script == "refuse":
            return lcsap.location_response(
                correlation, None, cause=("misc", "unspecified"))
        if self.script == "gated":
            self.release.wait(5.0)
            return lcsap.location_response(
                correlation, lcsap.circle(0.347596, 32.582520, 35.0),
                fulfilled=lcsap.ACCURACY_FULFILLED)
        if self.script == "rounds":
            for _ in range(9):
                connection.send(lcsap.connection_oriented_information(
                    correlation, b"\x01"))
                try:
                    connection.receive(0.5)
                except (sls.SlsError, OSError):
                    return None
            return lcsap.location_response(
                correlation, None, cause=("misc", "unspecified"))
        raise AssertionError(f"unknown script {self.script!r}")


class FailureModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = cell_plan.CellPlan.from_file(cell_plan.DEFAULT_CONFIG)

    def service(self, port, *, timeout=2.0, contexts=(connected(),)):
        return LocationService(
            ue_contexts.UeContextStore(contexts), self.plan,
            esmlc_host="127.0.0.1", esmlc_port=port, timeout=timeout)

    def assert_cell_plan_fallback(self, outcome, detail=""):
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "CELL_PLAN")
        self.assertEqual(outcome.method, "cell-id")
        self.assertEqual(outcome.radius_m, 35.0)
        self.assertIsNone(outcome.age_seconds)
        self.assertIsNone(outcome.fulfilled)
        self.assertIn(detail, outcome.detail)

    def test_a_silent_esmlc_times_out_and_the_mme_aborts_the_dialogue(self):
        with ScriptedEsmc("silent") as fake:
            started = time.monotonic()
            outcome = self.service(fake.port, timeout=0.3).locate(LAB_UE_A)
            elapsed = time.monotonic() - started
            fake.release.set()
            self.assertTrue(fake.aborted.wait(2.0),
                            "the MME did not send a Location-Abort")
        self.assertLess(elapsed, 2.0)
        self.assert_cell_plan_fallback(outcome, "within 0.3s")

    def test_a_malformed_lcs_ap_answer_falls_back_and_is_not_read_as_a_position(self):
        with ScriptedEsmc("malformed") as fake:
            outcome = self.service(fake.port).locate(LAB_UE_A)
        self.assert_cell_plan_fallback(outcome)

    def test_an_answer_for_a_different_correlation_is_refused(self):
        with ScriptedEsmc("wrong-correlation") as fake:
            outcome = self.service(fake.port).locate(LAB_UE_A)
        self.assert_cell_plan_fallback(outcome, "different Correlation-ID")

    def test_a_refused_dialogue_keeps_the_cause_in_the_detail(self):
        with ScriptedEsmc("refuse") as fake:
            outcome = self.service(fake.port).locate(LAB_UE_A)
        self.assert_cell_plan_fallback(outcome, "the E-SMLC refused: misc/unspecified")

    def test_more_than_eight_measurement_rounds_aborts_the_client(self):
        with ScriptedEsmc("rounds") as fake:
            client = LcsApClient("127.0.0.1", fake.port, timeout=5.0)
            with self.assertRaises(LcsApClientError) as caught:
                client.locate(b"\x00\x00\x00\x07", (CELL_A, 28),
                              lpp_transport=lambda apdu: b"\x01")
            client.close()
        # The cap covers LPP and LPPa rounds together, so the message names
        # measurement rounds rather than LPP rounds.
        self.assertIn("more than 8 measurement rounds", str(caught.exception))

    def test_a_ue_that_cannot_answer_lpp_makes_the_esmlc_refuse(self):
        table = esmlc_sim.PositionTable.from_file(esmlc_sim.DEFAULT_CONFIG)
        sim = esmlc_sim.EsmlcSimulator(table, host="127.0.0.1", port=0,
                                       lpp_timeout=0.5)
        sim.start()
        try:
            with NasStub({"detail": "LPP not supported"}, status=500) as nas:
                store = ue_contexts.UeContextStore([connected(nas_url=nas.url)])
                service = LocationService(
                    store, self.plan, esmlc_host="127.0.0.1",
                    esmlc_port=sim.port, timeout=3.0)
                outcome = service.locate(LAB_UE_A)
            self.assertEqual(sim.counters["requests"], 1)
            self.assertEqual(sim.counters["positioned"], 0)
        finally:
            sim.stop()
        self.assert_cell_plan_fallback(outcome, "protocol/")

    def test_a_context_removed_mid_dialogue_does_not_break_the_live_answer(self):
        store = ue_contexts.UeContextStore([connected()])
        with ScriptedEsmc("gated") as fake:
            service = LocationService(
                store, self.plan, esmlc_host="127.0.0.1",
                esmlc_port=fake.port, timeout=3.0)
            result = {}
            worker = threading.Thread(
                target=lambda: result.setdefault("outcome", service.locate(LAB_UE_A)))
            worker.start()
            self.assertTrue(fake.arrived.wait(2.0), "the request never arrived")
            self.assertTrue(store.remove(LAB_UE_A))
            fake.release.set()
            worker.join(5.0)
        self.assertFalse(worker.is_alive())
        outcome = result["outcome"]
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "SLS")
        self.assertEqual(outcome.cell, CELL_A)
        # The removal applies to the next request, not to the one in flight.
        self.assertEqual(service.locate(LAB_UE_A).result_code,
                         d.RESULT_USER_UNKNOWN)


class NoSessionLeak(unittest.TestCase):
    """2h without a pcap: 300 concurrent dialogues, associations back to zero."""

    @classmethod
    def setUpClass(cls):
        cls.plan = cell_plan.CellPlan.from_file(cell_plan.DEFAULT_CONFIG)
        table = esmlc_sim.PositionTable.from_file(esmlc_sim.DEFAULT_CONFIG)
        cls.sim = esmlc_sim.EsmlcSimulator(table, host="127.0.0.1", port=0,
                                          lpp_timeout=1.0)
        cls.sim.start()

    @classmethod
    def tearDownClass(cls):
        cls.sim.stop()

    @staticmethod
    def _wait_for_idle(server, seconds=5.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if server.stats()["active_connections"] == 0:
                return True
            time.sleep(0.02)
        return False

    def test_three_hundred_dialogues_leave_no_usable_state_behind(self):
        store = ue_contexts.UeContextStore([connected(LAB_UE_C, CELL_C)])
        service = LocationService(store, self.plan, esmlc_host="127.0.0.1",
                                  esmlc_port=self.sim.port, timeout=3.0)

        def one(_):
            return service.locate(LAB_UE_C, 600.0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(one, range(300)))

        self.assertEqual(len(outcomes), 300)
        self.assertTrue(all(o.positioned for o in outcomes))
        self.assertTrue(all(o.source == "SLS" for o in outcomes))
        self.assertTrue(all(o.fulfilled for o in outcomes))
        self.assertTrue(all(o.age_seconds == 0 for o in outcomes))
        self.assertEqual(service.stats()["requests"], 300)
        self.assertEqual(service.stats()["via_sls"], 300)
        self.assertEqual(self.sim.counters["requests"], 300)
        self.assertTrue(self._wait_for_idle(self.sim.server),
                        self.sim.server.stats())
        self.assertEqual(len(store), 1)
        # The next request still works, so nothing was left half-open.
        self.assertTrue(service.locate(LAB_UE_C, 600.0).positioned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
