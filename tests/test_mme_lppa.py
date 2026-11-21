"""An E-SMLC's LPPa E-CID request travelling through the MME to the eNB.

    python tests/test_mme_lppa.py

Three real components over the D5 TCP carrier: the E-SMLC simulator in
``ecid_over_lppa`` mode (SLs), the MME's LocationService with its S1 server,
and the lab eNB (S1). The MME must route by Payload-Type: an lPPa APDU goes
to the eNB, never to the UE's NAS endpoint.

The position in the answer is the simulator table's synthetic value, because
this harness has no solver; the eNB's E-CID result is validated and counted,
not used. Every coordinate is invented for lab PLMN 001-01.
"""

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "mme" / "src", ROOT / "esmlc" / "src"):
    sys.path.insert(0, str(_p))

from lib.codecs import lcsap  # noqa: E402

import cell_plan  # noqa: E402
import esmlc_sim  # noqa: E402
import lab_enb  # noqa: E402
import s1_link  # noqa: E402
import ue_contexts  # noqa: E402
from location_service import LocationService  # noqa: E402

IMSI = "001010000000001"
CELL = 0x00A1B2C
PLMN = lcsap.LAB_PLMN
PLAN = ROOT / "mme" / "config" / "lab_cells.json"


def wait_until(predicate, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class ThroughTheMme(unittest.TestCase):
    def setUp(self):
        self.contexts = ue_contexts.UeContextStore()
        self.s1 = s1_link.S1Server("127.0.0.1", 0, self.contexts,
                                   lppa_timeout=2.0)
        self.s1.start()
        self.addCleanup(self.s1.stop)
        self.plan = cell_plan.CellPlan.from_file(PLAN)
        self.enb = lab_enb.LabEnb(
            "127.0.0.1", self.s1.port, imsi=IMSI, cell=CELL,
            position=self.plan.lookup(PLMN, CELL))
        self.enb.start()
        self.addCleanup(self.enb.stop)
        self.assertTrue(
            wait_until(lambda: self.s1.ue_for_imsi(IMSI) is not None),
            "the MME did not bind the eNB's attach")
        table = esmlc_sim.PositionTable.from_file(esmlc_sim.DEFAULT_CONFIG)
        self.sim = esmlc_sim.EsmlcSimulator(
            table, host="127.0.0.1", port=0, lpp_timeout=2.0,
            ecid_over_lppa=True)
        self.sim.start()
        self.addCleanup(self.sim.stop)

    def service(self, with_relay=True):
        factory = ((lambda imsi: lambda apdu: self.s1.relay_lppa(imsi, apdu))
                   if with_relay else None)
        return LocationService(
            self.contexts, self.plan, esmlc_host="127.0.0.1",
            esmlc_port=self.sim.port, timeout=3.0,
            lppa_transport_factory=factory)

    def test_the_e_cid_request_round_trips_through_the_enb(self):
        outcome = self.service().locate(IMSI, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "SLS")
        self.assertEqual(outcome.method, "e-cid")
        self.assertEqual(outcome.lppa_rounds, 1)
        self.assertEqual(outcome.lpp_rounds, 0)
        self.assertTrue(outcome.fulfilled)
        self.assertAlmostEqual(outcome.latitude, 0.347596, places=5)
        self.assertLess(outcome.radius_m, 40.0)
        self.assertEqual(self.sim.counters["lppa_rounds"], 1)
        self.assertEqual(self.sim.counters["lppa_rejected"], 0)
        self.assertEqual(self.enb.counters["lppa_requests"], 1)
        self.assertEqual(self.enb.counters["lppa_responses"], 1)

    def test_without_an_s1_binding_the_dialogue_is_aborted(self):
        outcome = self.service(with_relay=False).locate(IMSI, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "CELL_PLAN")
        self.assertEqual(outcome.method, "cell-id")
        self.assertIn("LPPa", outcome.detail)
        self.assertIn("S1", outcome.detail)
        # The E-SMLC asked once; the MME answered with Location-Abort rather
        # than dropping the request and leaving the E-SMLC to time out.
        self.assertEqual(self.sim.counters["lppa_rounds"], 1)
        self.assertTrue(
            wait_until(lambda: self.sim.counters["aborts"] == 1),
            "the E-SMLC never saw the Location-Abort")

    def test_an_enb_that_has_gone_away_leaves_the_location_to_the_plan(self):
        self.enb.stop()
        self.assertTrue(
            wait_until(lambda: self.s1.ue_for_imsi(IMSI) is None),
            "the MME kept the UE context of a closed S1 association")
        outcome = self.service().locate(IMSI, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "CELL_PLAN")
        self.assertIn("relaying lPPa", outcome.detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
