"""S1AP codec: round trips and the shapes the location relay relies on.

    python tests/test_s1ap_codec.py
"""

import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.codecs import s1ap  # noqa: E402

CELL = (0x00A1B2C, 28)
TMSI = (b"\x01", b"\x00\x00\x00\x02")
IMSI = b"\x00\x10\x10\x00\x00\x00\x00"


class S1Setup(unittest.TestCase):
    def test_request_carries_the_global_enb_id_and_served_tracking_areas(self):
        wire = s1ap.s1_setup_request(enb_id=0xA1B2C, tac=b"\x00\xa1",
                                     name="lab-enb")
        message = s1ap.parse(wire)
        self.assertEqual(message.kind, s1ap.INITIATING)
        self.assertEqual(message.procedure, s1ap.PROC_S1_SETUP)
        self.assertEqual(message.name, "S1SetupRequest")
        global_id = message.ie("Global-ENB-ID")
        self.assertEqual(global_id["pLMNidentity"], s1ap.LAB_PLMN)
        self.assertEqual(global_id["eNB-ID"], ("macroENB-ID", (0xA1B2C, 20)))
        self.assertEqual(s1ap.supported_tas(message),
                         [s1ap.Tai(plmn=s1ap.LAB_PLMN, tac=b"\x00\xa1")])
        self.assertEqual(message.ie("PagingDRX"), "v128")
        self.assertEqual(s1ap.enb_name(message), "lab-enb")

    def test_request_without_a_name_omits_the_optional_ie(self):
        message = s1ap.parse(s1ap.s1_setup_request())
        self.assertIsNone(s1ap.enb_name(message))

    def test_response_names_the_mme_and_the_plmns_it_serves(self):
        wire = s1ap.s1_setup_response(mme_code=2, name="lab-mme")
        message = s1ap.parse(wire)
        self.assertEqual(message.kind, s1ap.SUCCESSFUL)
        self.assertEqual(message.procedure, s1ap.PROC_S1_SETUP)
        self.assertEqual(message.name, "S1SetupResponse")
        self.assertEqual(s1ap.mme_name(message), "lab-mme")
        self.assertEqual(s1ap.served_plmns(message), [s1ap.LAB_PLMN])
        item = message.ie("ServedGUMMEIs")[0]
        self.assertEqual(item["servedMMECs"], [b"\x02"])
        # RelativeMMECapacity is mandatory in the response IE set.
        self.assertEqual(message.ie("RelativeMMECapacity"), 255)

    def test_failure_is_unsuccessful_and_carries_the_cause(self):
        message = s1ap.parse(
            s1ap.s1_setup_failure(("misc", "unspecified")))
        self.assertEqual(message.kind, s1ap.UNSUCCESSFUL)
        self.assertEqual(s1ap.cause(message), ("misc", "unspecified"))


class InitialUEMessage(unittest.TestCase):
    def test_fields_the_location_relay_reads(self):
        wire = s1ap.initial_ue_message(7, b"\x07\x41", CELL, s_tmsi=TMSI)
        message = s1ap.parse(wire)
        self.assertEqual(message.kind, s1ap.INITIATING)
        self.assertEqual(message.procedure, s1ap.PROC_INITIAL_UE_MESSAGE)
        self.assertEqual(message.name, "InitialUEMessage")
        self.assertEqual(s1ap.ue_ids(message), (None, 7))
        self.assertEqual(s1ap.nas_pdu(message), b"\x07\x41")
        self.assertEqual(s1ap.ecgi(message),
                         s1ap.Ecgi(plmn=s1ap.LAB_PLMN, cell_id=0x00A1B2C))
        self.assertEqual(s1ap.ecgi(message).bit_string(), CELL)
        self.assertEqual(s1ap.tai(message),
                         s1ap.Tai(plmn=s1ap.LAB_PLMN, tac=b"\x00\xa1"))
        self.assertEqual(message.ie("RRC-Establishment-Cause"), "mo-Signalling")
        self.assertEqual(s1ap.s_tmsi(message), TMSI)

    def test_without_an_s_tmsi_the_ue_is_identified_by_the_enb_only(self):
        message = s1ap.parse(s1ap.initial_ue_message(9, b"\x07\x41", CELL))
        self.assertIsNone(s1ap.s_tmsi(message))
        self.assertEqual(s1ap.ue_ids(message), (None, 9))


class NasTransport(unittest.TestCase):
    def test_both_directions_carry_the_same_nas_pdu(self):
        downlink = s1ap.parse(
            s1ap.downlink_nas_transport(3, 9, b"\x07\x42"))
        uplink = s1ap.parse(
            s1ap.uplink_nas_transport(3, 9, b"\x07\x43"))
        self.assertEqual(downlink.procedure, s1ap.PROC_DOWNLINK_NAS_TRANSPORT)
        self.assertEqual(uplink.procedure, s1ap.PROC_UPLINK_NAS_TRANSPORT)
        self.assertEqual(downlink.name, "DownlinkNASTransport")
        self.assertEqual(uplink.name, "UplinkNASTransport")
        self.assertEqual(s1ap.ue_ids(downlink), (3, 9))
        self.assertEqual(s1ap.ue_ids(uplink), (3, 9))
        self.assertEqual(s1ap.nas_pdu(downlink), b"\x07\x42")
        self.assertEqual(s1ap.nas_pdu(uplink), b"\x07\x43")
        self.assertIsNone(s1ap.ecgi(downlink))


class PagingMessage(unittest.TestCase):
    def test_paging_by_s_tmsi(self):
        wire = s1ap.paging(s1ap.paging_index(TMSI[1]), s_tmsi=TMSI)
        message = s1ap.parse(wire)
        self.assertEqual(message.kind, s1ap.INITIATING)
        self.assertEqual(message.procedure, s1ap.PROC_PAGING)
        self.assertEqual(message.name, "Paging")
        self.assertEqual(s1ap.ue_identity_index(message), 2)
        self.assertEqual(s1ap.s_tmsi(message), TMSI)
        self.assertIsNone(s1ap.paged_imsi(message))
        self.assertEqual(message.ie("CNDomain"), s1ap.CN_DOMAIN_PS)
        self.assertEqual(message.ie("PagingDRX"), "v128")
        self.assertEqual(s1ap.tai_list(message),
                         [s1ap.Tai(plmn=s1ap.LAB_PLMN, tac=b"\x00\xa1")])

    def test_paging_by_imsi_when_there_is_no_s_tmsi(self):
        message = s1ap.parse(s1ap.paging(5, imsi=IMSI))
        self.assertIsNone(s1ap.s_tmsi(message))
        self.assertEqual(s1ap.paged_imsi(message), IMSI)


class PagingIndex(unittest.TestCase):
    def test_the_index_is_the_low_ten_bits_of_the_m_tmsi(self):
        self.assertEqual(s1ap.paging_index(b"\x00\x00\x00\x02"), 2)
        self.assertEqual(s1ap.paging_index(b"\x00\x00\x04\x01"), 1)
        self.assertEqual(s1ap.paging_index(b"\xff\xff\xff\xff"), 1023)

    def test_an_m_tmsi_is_four_octets(self):
        with self.assertRaises(s1ap.S1apError):
            s1ap.paging_index(b"\x00\x00\x02")


class Release(unittest.TestCase):
    def test_the_command_and_complete_carry_both_identities(self):
        command = s1ap.parse(s1ap.ue_context_release_command(7, 9))
        complete = s1ap.parse(s1ap.ue_context_release_complete(7, 9))
        self.assertEqual(command.procedure, s1ap.PROC_UE_CONTEXT_RELEASE)
        self.assertEqual(command.kind, s1ap.INITIATING)
        self.assertEqual(command.name, "UEContextReleaseCommand")
        self.assertEqual(complete.kind, s1ap.SUCCESSFUL)
        self.assertEqual(complete.name, "UEContextReleaseComplete")
        self.assertEqual(s1ap.ue_ids(command), (7, 9))
        self.assertEqual(s1ap.ue_ids(complete), (7, 9))
        self.assertEqual(s1ap.cause(command), ("nas", "normal-release"))


class LppaTransport(unittest.TestCase):
    def test_ue_associated_transports_carry_the_apdu_and_the_ue(self):
        pdu = b"\x00\x01\x02\x03"
        downlink = s1ap.parse(
            s1ap.downlink_ue_associated_lppa(7, 9, pdu))
        uplink = s1ap.parse(
            s1ap.uplink_ue_associated_lppa(7, 9, pdu, routing_id=3))
        self.assertEqual(downlink.procedure,
                         s1ap.PROC_DOWNLINK_UE_ASSOCIATED_LPPA)
        self.assertEqual(uplink.procedure,
                         s1ap.PROC_UPLINK_UE_ASSOCIATED_LPPA)
        self.assertEqual(downlink.name, "DownlinkUEAssociatedLPPaTransport")
        self.assertEqual(uplink.name, "UplinkUEAssociatedLPPaTransport")
        self.assertEqual(s1ap.lppa_pdu(downlink), pdu)
        self.assertEqual(s1ap.lppa_pdu(uplink), pdu)
        self.assertEqual(s1ap.routing_id(downlink), 0)
        self.assertEqual(s1ap.routing_id(uplink), 3)
        self.assertEqual(s1ap.ue_ids(downlink), (7, 9))
        self.assertEqual(s1ap.ue_ids(uplink), (7, 9))

    def test_non_ue_associated_transports_have_no_ue_identity(self):
        downlink = s1ap.parse(
            s1ap.downlink_non_ue_associated_lppa(7, b"\x00\x01"))
        uplink = s1ap.parse(
            s1ap.uplink_non_ue_associated_lppa(7, b"\x00\x01"))
        self.assertEqual(downlink.procedure,
                         s1ap.PROC_DOWNLINK_NON_UE_ASSOCIATED_LPPA)
        self.assertEqual(uplink.procedure,
                         s1ap.PROC_UPLINK_NON_UE_ASSOCIATED_LPPA)
        self.assertEqual(s1ap.ue_ids(downlink), (None, None))
        self.assertEqual(s1ap.routing_id(downlink), 7)
        self.assertEqual(s1ap.lppa_pdu(uplink), b"\x00\x01")


class ErrorIndication(unittest.TestCase):
    def test_error_indication_carries_a_cause(self):
        message = s1ap.parse(s1ap.error_indication())
        self.assertEqual(message.procedure, s1ap.PROC_ERROR_INDICATION)
        self.assertEqual(message.name, "ErrorIndication")
        self.assertEqual(s1ap.cause(message), ("misc", "unspecified"))


class ConcurrentCodec(unittest.TestCase):
    def test_the_shared_codec_object_is_not_corrupted_across_threads(self):
        # The MME relays LPPa for several subscribers at once, one S1
        # association each, so encode and decode run in parallel threads.
        def work(worker):
            for round_no in range(100):
                enb_ue_id = worker * 1000 + round_no
                apdu = bytes([worker, round_no & 0xFF])
                wire = s1ap.downlink_ue_associated_lppa(
                    enb_ue_id + 100000, enb_ue_id, apdu)
                message = s1ap.parse(wire)
                self.assertEqual(s1ap.ue_ids(message),
                                 (enb_ue_id + 100000, enb_ue_id))
                self.assertEqual(s1ap.lppa_pdu(message), apdu)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, range(8)))


class Rejections(unittest.TestCase):
    def test_garbage_is_rejected_not_decoded(self):
        with self.assertRaises(s1ap.S1apError):
            s1ap.parse(b"\xff\xff\xff")

    def test_a_truncated_message_is_rejected(self):
        wire = s1ap.initial_ue_message(7, b"\x07\x41", CELL)
        with self.assertRaises(s1ap.S1apError):
            s1ap.parse(wire[:6])

    def test_an_unknown_procedure_is_refused_by_number(self):
        # pycrate leaves an open type outside the generated object set as
        # raw octets. The message layer must refuse it, not invent a name.
        from lib.codecs import s1ap_codec
        obj = s1ap_codec.S1AP_PDU_Descriptions.S1AP_PDU
        obj.set_val((s1ap.INITIATING, {
            "procedureCode": 255, "criticality": "reject",
            "value": ("ErrorIndication", {"protocolIEs": []}),
        }))
        with self.assertRaises(s1ap.S1apError):
            s1ap.parse(obj.to_aper())

    def test_the_enb_identity_fits_twenty_bits(self):
        with self.assertRaises(s1ap.S1apError):
            s1ap.s1_setup_request(enb_id=1 << 20)

    def test_a_cell_identity_is_twenty_eight_bits(self):
        for cell in ((0x00A1B2C, 27), (1 << 28, 28)):
            with self.assertRaises(s1ap.S1apError):
                s1ap.initial_ue_message(7, b"\x07\x41", cell)

    def test_an_enb_ue_identity_fits_twenty_four_bits(self):
        with self.assertRaises(s1ap.S1apError):
            s1ap.downlink_nas_transport(1, 1 << 24, b"\x07")

    def test_paging_takes_exactly_one_identity(self):
        with self.assertRaises(s1ap.S1apError):
            s1ap.paging(1)
        with self.assertRaises(s1ap.S1apError):
            s1ap.paging(1, s_tmsi=TMSI, imsi=IMSI)

    def test_the_paging_index_fits_ten_bits(self):
        with self.assertRaises(s1ap.S1apError):
            s1ap.paging(1024, s_tmsi=TMSI)

    def test_bad_plmn_tac_name_and_drx_are_rejected(self):
        with self.assertRaises(s1ap.S1apError):
            s1ap.s1_setup_request(plmn=b"\x00\xf1")
        with self.assertRaises(s1ap.S1apError):
            s1ap.s1_setup_request(tac=b"\x00")
        with self.assertRaises(s1ap.S1apError):
            s1ap.s1_setup_request(name="")
        with self.assertRaises(s1ap.S1apError):
            s1ap.s1_setup_request(paging_drx="v1024")

    def test_a_ue_associated_lppa_transport_needs_both_identities(self):
        with self.assertRaises(s1ap.S1apError):
            s1ap._lppa_transport(
                s1ap.PROC_DOWNLINK_UE_ASSOCIATED_LPPA,
                "DownlinkUEAssociatedLPPaTransport", b"\x00", 0, 7, None)

    def test_a_cell_identity_that_is_not_28_bits_is_an_error(self):
        message = s1ap.S1apMessage(
            kind=s1ap.INITIATING, procedure=s1ap.PROC_INITIAL_UE_MESSAGE,
            criticality=s1ap.CRITICALITY_REJECT, name="InitialUEMessage",
            ies=[("EUTRAN-CGI", {"pLMNidentity": s1ap.LAB_PLMN,
                                 "cell-ID": (0x00A1B, 24)})],
        )
        with self.assertRaises(s1ap.S1apError):
            s1ap.ecgi(message)

    def test_a_tai_list_entry_that_is_not_a_tai_item_is_an_error(self):
        message = s1ap.S1apMessage(
            kind=s1ap.INITIATING, procedure=s1ap.PROC_PAGING,
            criticality=s1ap.CRITICALITY_REJECT, name="Paging",
            ies=[("TAIList", [{"id": 99, "criticality": "ignore",
                               "value": ("CSG-IdList", [])}])],
        )
        with self.assertRaises(s1ap.S1apError):
            s1ap.tai_list(message)


class GeneratedCodec(unittest.TestCase):
    def test_committed_codec_matches_the_committed_asn1(self):
        """The .asn file is the source; the .py beside it is generated from it."""
        import subprocess
        import tempfile

        generator = ROOT / "lib" / "codecs" / "s1ap_codec.py"
        asn = ROOT / "lib" / "codecs" / "asn1" / "s1ap.asn"
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
        self.assertTrue(header.startswith("# Generated by lib/codecs/build_s1ap.py"))
        self.assertEqual(committed[len(header):], generated,
                         "s1ap_codec.py is stale; rerun lib/codecs/build_s1ap.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
