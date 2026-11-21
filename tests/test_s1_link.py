"""The MME's S1 association and the LPPa relay.

    python tests/test_s1_link.py

Everything runs over the D5 TCP carrier: this host has no AF_SCTP, so the
SCTP path in corelib/wire.py is unverified. The eNB here is S1Client itself,
not the lab eNB; tests/test_lab_enb.py starts the full peer.
"""

import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "mme" / "src"):
    sys.path.insert(0, str(_p))

from lib.codecs import lcsap, lppa, nas, s1ap  # noqa: E402

import s1_link  # noqa: E402
import ue_contexts  # noqa: E402

IMSI = "001010000000001"
IMSI_TWO = "001010000000002"
CELL = (0x00A1B2C, 28)
CELL_TWO = (0x00A1B2D, 28)
TMSI = (b"\x01", b"\x00\x00\x00\x02")
GUTI_ATTACH = bytes([0x07, 0x41, 0x71, 11, 0xF6]) + bytes(10)


def wait_until(predicate, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class Base(unittest.TestCase):
    def setUp(self):
        self.contexts = ue_contexts.UeContextStore()
        self.server = s1_link.S1Server("127.0.0.1", 0, self.contexts,
                                       lppa_timeout=1.0)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.client = s1_link.S1Client("127.0.0.1", self.server.port,
                                       timeout=2.0)
        self.addCleanup(self.client.close)

    def attach(self, client=None, imsi=IMSI, cell=CELL, s_tmsi=None,
               nas_pdu=None):
        client = client or self.client
        client.setup(name="test-enb", tac=b"\x00\xa1")
        enb_ue_id = client.initial_ue(imsi, cell, s_tmsi=s_tmsi,
                                      nas_pdu=nas_pdu)
        self.assertTrue(wait_until(
            lambda: self.server.ue_for_imsi(imsi) is not None),
            "the MME did not bind the IMSI")
        return enb_ue_id

    def relay_in_background(self, apdu, imsi=IMSI, timeout=2.0):
        box = {}

        def run():
            try:
                box["answer"] = self.server.relay_lppa(imsi, apdu, timeout)
            except Exception as exc:  # the assertion below reports it
                box["error"] = exc

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, box

    def answer_lppa(self, client, message, answer):
        mme_ue_id, enb_ue_id = s1ap.ue_ids(message)
        routing = s1ap.routing_id(message)
        client.uplink_lppa(mme_ue_id, enb_ue_id, answer, routing or 0)
        return mme_ue_id, enb_ue_id, routing


class Setup(Base):
    def test_setup_is_answered_with_the_served_plmn(self):
        message = self.client.setup(name="test-enb", enb_id=0xA1B2C)
        self.assertEqual(message.kind, s1ap.SUCCESSFUL)
        self.assertEqual(s1ap.served_plmns(message), [s1ap.LAB_PLMN])
        self.assertEqual(self.client.plmns, [s1ap.LAB_PLMN])
        self.assertEqual(self.client.mme_name, self.server.name)
        self.assertTrue(wait_until(lambda: len(self.server.enbs()) == 1))
        enb = self.server.enbs()[0]
        self.assertEqual(enb["name"], "test-enb")
        self.assertEqual(enb["enb_id"], 0xA1B2C)
        self.assertEqual(enb["tac"], b"\x00\xa1".hex())
        self.assertEqual(self.server.counters["setups"], 1)

    def test_setup_for_another_plmn_is_refused(self):
        other = lcsap.plmn_identity("001", "02")
        client = s1_link.S1Client("127.0.0.1", self.server.port, timeout=2.0)
        self.addCleanup(client.close)
        with self.assertRaises(s1_link.S1LinkError):
            client.setup(plmn=other)
        self.assertEqual(self.server.counters["setup_failures"], 1)

    def test_initial_ue_before_setup_is_an_error_but_keeps_the_connection(self):
        self.client.connect()
        self.client.send(s1ap.initial_ue_message(5, b"\x07\x41", CELL))
        self.assertTrue(wait_until(lambda: self.server.server.errors >= 1))
        self.client.setup(name="after-error")
        self.assertEqual(len(self.server.enbs()), 1)


class InitialUEMessage(Base):
    def test_attach_binds_the_imsi_and_the_serving_cell(self):
        enb_ue_id = self.attach()
        ue = self.server.ue_for_imsi(IMSI)
        self.assertIsNotNone(ue)
        self.assertEqual(ue["enb_ue_id"], enb_ue_id)
        self.assertEqual(ue["cell"], f"0x{CELL[0]:07X}")
        self.assertEqual(ue["plmn"], s1ap.LAB_PLMN.hex())
        context = self.contexts.get(IMSI)
        self.assertEqual(context.cell, CELL[0])
        self.assertEqual(context.plmn, s1ap.LAB_PLMN)
        self.assertEqual(context.rrc_state, ue_contexts.RRC_CONNECTED)
        self.assertEqual(self.server.counters["attaches"], 1)

    def test_guti_attach_creates_no_imsi_binding(self):
        self.client.setup(name="test-enb")
        enb_ue_id = self.client.initial_ue(IMSI, CELL, nas_pdu=GUTI_ATTACH)
        self.assertTrue(wait_until(
            lambda: self.server.counters["initial_ue"] == 1))
        ues = self.server.ues()
        self.assertEqual(len(ues), 1)
        self.assertEqual(ues[0]["enb_ue_id"], enb_ue_id)
        self.assertIsNone(ues[0]["imsi"])
        self.assertIsNone(self.contexts.get(IMSI))
        self.assertEqual(self.server.counters["no_imsi"], 1)
        with self.assertRaises(s1_link.S1LinkError):
            self.server.relay_lppa(IMSI, b"\x01")

    def test_unreadable_nas_does_not_break_the_binding(self):
        self.client.setup(name="test-enb")
        self.client.initial_ue(IMSI, CELL, nas_pdu=b"\x07\x41\xff\xff")
        self.assertTrue(wait_until(
            lambda: self.server.counters["initial_ue"] == 1))
        self.assertEqual(self.server.counters["nas_errors"], 1)
        self.assertEqual(len(self.server.ues()), 1)

    def test_a_second_attach_with_the_same_enb_identity_replaces_the_first(self):
        self.client.setup(name="test-enb")
        self.client.send(s1ap.initial_ue_message(
            7, nas.attach_request(IMSI), CELL))
        self.assertTrue(wait_until(
            lambda: self.server.ue_for_imsi(IMSI) is not None))
        first = self.server.ue_for_imsi(IMSI)["mme_ue_id"]
        self.client.send(s1ap.initial_ue_message(
            7, nas.attach_request(IMSI), CELL))
        self.assertTrue(wait_until(
            lambda: self.server.ue_for_imsi(IMSI)["mme_ue_id"] != first))
        self.assertEqual(len(self.server.ues()), 1)

    def test_tai_defaults_to_the_setup_tracking_area_when_absent(self):
        # initial_ue_message always carries a TAI; a hand-built message that
        # does not still binds, using the association's tracking area.
        self.client.setup(name="test-enb", tac=b"\x00\xa1")
        pdu = s1ap.initial_ue_message(9, b"\x07\x41", CELL)
        self.client.send(pdu)
        self.assertTrue(wait_until(lambda: len(self.server.ues()) == 1))
        self.assertEqual(self.server.ues()[0]["tac"], b"\x00\xa1".hex())


class Relay(Base):
    def test_lppa_round_trip_keeps_the_envelope_fields(self):
        enb_ue_id = self.attach()
        request = lppa.measurement_initiation_request(11, 3)
        thread, box = self.relay_in_background(request)
        message = self.client.receive(2.0)
        self.assertIsNotNone(message)
        self.assertEqual(message.procedure, s1ap.PROC_DOWNLINK_UE_ASSOCIATED_LPPA)
        mme_ue_id, downlink_enb = s1ap.ue_ids(message)
        self.assertEqual(downlink_enb, enb_ue_id)
        routing = s1ap.routing_id(message)
        self.assertIsNotNone(routing)
        self.assertEqual(s1ap.lppa_pdu(message), request)
        answer = lppa.measurement_initiation_response(11, 3, 2)
        self.answer_lppa(self.client, message, answer)
        thread.join(2.0)
        self.assertNotIn("error", box)
        self.assertEqual(box["answer"], answer)
        ue = self.server.ue_for_imsi(IMSI)
        self.assertEqual(ue["lppa_in"], 1)
        self.assertEqual(ue["lppa_out"], 1)
        self.assertFalse(ue["lppa_pending"])
        self.assertEqual(self.server.counters["downlink_lppa"], 1)
        self.assertEqual(self.server.counters["uplink_lppa"], 1)

    def test_a_second_concurrent_relay_is_refused(self):
        self.attach()
        request = lppa.measurement_initiation_request(12, 1)
        thread, box = self.relay_in_background(request, timeout=2.0)
        message = self.client.receive(2.0)
        with self.assertRaises(s1_link.S1LinkError) as ctx:
            self.server.relay_lppa(IMSI, request)
        self.assertIn("outstanding", str(ctx.exception))
        self.answer_lppa(self.client, message,
                         lppa.measurement_initiation_response(12, 1, 1))
        thread.join(2.0)
        self.assertNotIn("error", box)

    def test_no_answer_times_out(self):
        self.attach()
        with self.assertRaises(s1_link.S1LinkError) as ctx:
            self.server.relay_lppa(
                IMSI, lppa.measurement_initiation_request(13, 1), timeout=0.2)
        self.assertIn("did not answer", str(ctx.exception))
        # Drain the downlink the relay sent so the connection stays usable.
        drained = self.client.receive(1.0)
        self.assertEqual(drained.procedure,
                         s1ap.PROC_DOWNLINK_UE_ASSOCIATED_LPPA)

    def test_an_unsolicited_uplink_is_counted_and_dropped(self):
        enb_ue_id = self.attach()
        mme_ue_id = self.server.ue_for_imsi(IMSI)["mme_ue_id"]
        self.client.uplink_lppa(
            mme_ue_id, enb_ue_id, lppa.measurement_report(
                1, 1, 1, lppa.MeasurementResult(
                    cell=lppa.Ecgi(s1ap.LAB_PLMN, CELL[0]),
                    tac=b"\x00\xa1")), routing_id=7)
        self.assertTrue(wait_until(
            lambda: self.server.counters["unmatched_lppa"] == 1))
        self.assertEqual(self.server.ue_for_imsi(IMSI)["lppa_pending"], False)

    def test_two_ues_relay_concurrently(self):
        other = s1_link.S1Client("127.0.0.1", self.server.port, timeout=2.0)
        self.addCleanup(other.close)
        self.attach()
        self.attach(client=other, imsi=IMSI_TWO, cell=CELL_TWO)
        request = lppa.measurement_initiation_request(21, 1)
        thread_a, box_a = self.relay_in_background(request)
        thread_b, box_b = self.relay_in_background(request, imsi=IMSI_TWO)
        for client in (self.client, other):
            message = client.receive(2.0)
            self.assertEqual(message.procedure,
                             s1ap.PROC_DOWNLINK_UE_ASSOCIATED_LPPA)
            self.answer_lppa(
                client, message,
                lppa.measurement_initiation_response(21, 1, 1))
        thread_a.join(2.0)
        thread_b.join(2.0)
        self.assertNotIn("error", box_a)
        self.assertNotIn("error", box_b)
        self.assertEqual(box_a["answer"],
                         lppa.measurement_initiation_response(21, 1, 1))
        self.assertEqual(box_b["answer"],
                         lppa.measurement_initiation_response(21, 1, 1))


class Paging(Base):
    def test_page_by_imsi_when_the_ue_has_no_s_tmsi(self):
        self.attach()
        result = self.server.page(IMSI)
        self.assertEqual(result["identity"], "imsi")
        message = self.client.receive(2.0)
        self.assertEqual(message.procedure, s1ap.PROC_PAGING)
        self.assertEqual(s1ap.paged_imsi(message), lcsap.tbcd(IMSI))
        self.assertEqual(s1ap.ue_identity_index(message), int(IMSI) & 0x3FF)
        self.assertEqual(self.server.counters["pages"], 1)

    def test_page_by_s_tmsi_when_the_ue_has_one(self):
        self.attach(s_tmsi=TMSI)
        result = self.server.page(IMSI)
        self.assertEqual(result["identity"], "s-tmsi")
        message = self.client.receive(2.0)
        self.assertEqual(s1ap.s_tmsi(message), TMSI)
        self.assertEqual(s1ap.ue_identity_index(message),
                         s1ap.paging_index(TMSI[1]))


class Release(Base):
    def test_release_completes_and_leaves_the_context_idle(self):
        self.attach()
        self.server.release(IMSI)
        command = self.client.receive(2.0)
        self.assertEqual(command.procedure, s1ap.PROC_UE_CONTEXT_RELEASE)
        self.assertEqual(command.name, "UEContextReleaseCommand")
        mme_ue_id, enb_ue_id = s1ap.ue_ids(command)
        self.client.release_complete(mme_ue_id, enb_ue_id)
        self.assertTrue(wait_until(lambda: len(self.server.ues()) == 0))
        self.assertIsNone(self.server.ue_for_imsi(IMSI))
        self.assertEqual(self.contexts.get(IMSI).rrc_state, ue_contexts.RRC_IDLE)
        self.assertEqual(self.server.counters["releases"], 1)

    def test_release_for_an_unknown_ue_is_refused(self):
        with self.assertRaises(s1_link.S1LinkError):
            self.server.release(IMSI)


class Resilience(Base):
    def test_garbage_does_not_take_the_listener_down(self):
        self.client.setup(name="test-enb")
        self.client.send(b"\xff" * 6)
        self.assertTrue(wait_until(
            lambda: self.server.counters["unreadable"] == 1))
        self.client.initial_ue(IMSI, CELL)
        self.assertTrue(wait_until(
            lambda: self.server.ue_for_imsi(IMSI) is not None))

    def test_closing_the_association_forgets_the_ue(self):
        self.attach()
        self.client.close()
        self.assertTrue(wait_until(lambda: len(self.server.enbs()) == 0))
        self.assertTrue(wait_until(lambda: len(self.server.ues()) == 0))
        self.assertEqual(self.contexts.get(IMSI).rrc_state, ue_contexts.RRC_IDLE)
        self.assertEqual(self.server.counters["disconnects"], 1)

    def test_a_pending_relay_is_released_when_the_association_closes(self):
        self.attach()
        thread, box = self.relay_in_background(
            lppa.measurement_initiation_request(31, 1), timeout=3.0)
        self.client.receive(2.0)
        self.client.close()
        thread.join(3.0)
        self.assertIn("error", box)
        self.assertIn("closed", str(box["error"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
