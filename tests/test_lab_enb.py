"""The lab eNB answering E-CID initiations over S1.

    python tests/test_lab_enb.py

The MME is a real S1Server and the eNB is mme/src/lab_enb.py, both over the
D5 TCP carrier. The position the eNB reports is read from the synthetic lab
cell plan, so the numbers here are the plan's, not a measured signal.
"""

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "mme" / "src"):
    sys.path.insert(0, str(_p))

from lib.codecs import lcsap, lppa, s1ap  # noqa: E402

import cell_plan  # noqa: E402
import lab_enb  # noqa: E402
import s1_link  # noqa: E402
import ue_contexts  # noqa: E402

IMSI = "001010000000003"
CELL = 0x00A1B2C
PLAN = Path(__file__).resolve().parent.parent / "mme" / "config" / "lab_cells.json"


def wait_until(predicate, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class Base(unittest.TestCase):
    enb_kwargs = {}

    def setUp(self):
        self.contexts = ue_contexts.UeContextStore()
        self.server = s1_link.S1Server("127.0.0.1", 0, self.contexts,
                                       lppa_timeout=2.0)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.plan = cell_plan.CellPlan.from_file(PLAN)
        self.enb = lab_enb.LabEnb(
            "127.0.0.1", self.server.port, imsi=IMSI, cell=CELL,
            **{"position": self.plan.lookup(s1ap.LAB_PLMN, CELL),
               **self.enb_kwargs})
        self.enb.start()
        self.addCleanup(self.enb.stop)
        self.assertTrue(wait_until(
            lambda: self.server.ue_for_imsi(IMSI) is not None),
            "the MME did not bind the eNB's attach")


class Measurement(Base):
    def test_e_cid_initiation_is_answered_with_the_plan_position(self):
        request = lppa.measurement_initiation_request(
            5, 1, quantities=("cell-ID",))
        answer = self.server.relay_lppa(IMSI, request, timeout=2.0)
        message = lppa.parse(answer)
        self.assertEqual(message.kind, lppa.SUCCESSFUL)
        self.assertEqual(message.procedure, lppa.PROC_E_CID_INITIATION)
        self.assertEqual(message.transaction_id, 5)
        self.assertEqual(lppa.esmlc_measurement_id(message), 1)
        self.assertEqual(lppa.enb_measurement_id(message), 1)
        result = lppa.measurement_result(message)
        self.assertEqual(result.cell, lppa.Ecgi(plmn=s1ap.LAB_PLMN, cell_id=CELL))
        self.assertEqual(result.tac, b"\x00\xa1")
        self.assertIsNotNone(result.position)
        cell = self.plan.lookup(s1ap.LAB_PLMN, CELL)
        position = result.position
        self.assertEqual(position.latitude_sign, "north")
        self.assertAlmostEqual(position.latitude * 90.0 / (1 << 23),
                               cell.latitude, places=4)
        self.assertAlmostEqual(position.longitude * 360.0 / (1 << 24),
                               cell.longitude, places=4)
        self.assertEqual(position.uncertainty_semi_major,
                         lcsap.uncertainty_code(float(cell.radius_m)))
        self.assertEqual(position.uncertainty_semi_minor,
                         position.uncertainty_semi_major)
        self.assertEqual(position.confidence, lab_enb.PLAN_CONFIDENCE)
        self.assertEqual(self.enb.counters["lppa_requests"], 1)
        self.assertEqual(self.enb.counters["lppa_responses"], 1)
        self.assertEqual(self.enb.counters["lppa_without_position"], 0)

    def test_a_request_without_the_cell_identity_gets_no_position(self):
        request = lppa.measurement_initiation_request(
            6, 2, quantities=("timingAdvanceType1",))
        message = lppa.parse(
            self.server.relay_lppa(IMSI, request, timeout=2.0))
        result = lppa.measurement_result(message)
        self.assertEqual(result.cell.cell_id, CELL)
        self.assertIsNone(result.position)
        self.assertEqual(self.enb.counters["lppa_without_position"], 1)

    def test_the_e_cid_measurement_identity_is_the_enbs_own(self):
        message = lppa.parse(self.server.relay_lppa(
            IMSI, lppa.measurement_initiation_request(7, 4), timeout=2.0))
        self.assertEqual(lppa.esmlc_measurement_id(message), 4)
        self.assertEqual(lppa.enb_measurement_id(message),
                         self.enb.measurement_id)

    def test_termination_is_recorded_and_answered_by_nothing(self):
        # E-CID Measurement Termination has no response message (TS 36.455).
        # The block-and-wait relay sends it and then times out, which is the
        # honest behaviour; the eNB's handling is what this test checks.
        with self.assertRaises(s1_link.S1LinkError):
            self.server.relay_lppa(
                IMSI, lppa.measurement_termination_command(8, 1, 1),
                timeout=0.3)
        self.assertTrue(wait_until(
            lambda: self.enb.counters["terminations"] == 1))

    def test_a_garbage_apdu_is_counted_without_killing_the_association(self):
        with self.assertRaises(s1_link.S1LinkError):
            self.server.relay_lppa(IMSI, b"\xff\xff", timeout=0.3)
        self.assertTrue(wait_until(
            lambda: self.enb.counters["unreadable"] == 1))
        message = lppa.parse(self.server.relay_lppa(
            IMSI, lppa.measurement_initiation_request(10, 1), timeout=2.0))
        self.assertEqual(message.kind, lppa.SUCCESSFUL)


class Peer(Base):
    def test_paging_reaches_the_enb(self):
        self.server.page(IMSI)
        self.assertTrue(wait_until(lambda: self.enb.counters["pages"] == 1))

    def test_release_is_acknowledged(self):
        result = self.server.release(IMSI)
        self.assertEqual(result["imsi"], IMSI)
        self.assertTrue(wait_until(lambda: self.enb.counters["releases"] == 1))
        self.assertTrue(wait_until(lambda: len(self.server.ues()) == 0))
        self.assertEqual(self.contexts.get(IMSI).rrc_state,
                         ue_contexts.RRC_IDLE)

    def test_status_reports_the_attach(self):
        status = self.enb.status()
        self.assertTrue(status["running"])
        self.assertEqual(status["imsi"], IMSI)
        self.assertEqual(status["cell"], f"0x{CELL:07X}")
        self.assertEqual(status["mme_name"], "mme")
        self.assertEqual(status["carrier"], "tcp")
        self.assertEqual(status["counters"]["attaches"], 1)


class NoPlan(Base):
    enb_kwargs = {"position": None}

    def test_without_a_plan_the_result_carries_no_position(self):
        message = lppa.parse(self.server.relay_lppa(
            IMSI, lppa.measurement_initiation_request(11, 1), timeout=2.0))
        result = lppa.measurement_result(message)
        self.assertEqual(result.cell.cell_id, CELL)
        self.assertIsNone(result.position)
        self.assertEqual(self.enb.counters["lppa_without_position"], 1)


class Coding(unittest.TestCase):
    def test_southern_and_western_coordinates_keep_their_sign(self):
        position = lab_enb.coded_position(-1.5, -33.25, 120.0)
        self.assertEqual(position.latitude_sign, "south")
        self.assertAlmostEqual(-position.latitude * 90.0 / (1 << 23), -1.5,
                               places=4)
        self.assertAlmostEqual(position.longitude * 360.0 / (1 << 24), -33.25,
                               places=4)
        self.assertEqual(position.uncertainty_semi_major,
                         lcsap.uncertainty_code(120.0))

    def test_out_of_range_coordinates_are_refused(self):
        for latitude, longitude in ((91.0, 0.0), (-90.5, 1.0), (0.0, 181.0)):
            with self.subTest(latitude=latitude, longitude=longitude), \
                    self.assertRaises(lab_enb.LabEnbError):
                lab_enb.coded_position(latitude, longitude, 50.0)

    def test_an_unknown_cell_loads_no_position(self):
        self.assertIsNone(lab_enb.load_position(
            PLAN, s1ap.LAB_PLMN, 0x00FFFFFF))


if __name__ == "__main__":
    unittest.main(verbosity=2)
