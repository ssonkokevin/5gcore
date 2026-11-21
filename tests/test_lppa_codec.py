"""LPPa codec: round trips and the shapes the E-CID relay relies on.

    python tests/test_lppa_codec.py
"""

import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.codecs import lppa  # noqa: E402

CELL = lppa.Ecgi(plmn=lppa.LAB_PLMN, cell_id=0x00A1B2C)
TAC = b"\x00\xa1"


class InitiationRequest(unittest.TestCase):
    def test_request_carries_the_quantities_the_esmlc_asked_for(self):
        wire = lppa.measurement_initiation_request(
            7, 3, quantities=("cell-ID", "timingAdvanceType1"))
        message = lppa.parse(wire)
        self.assertEqual(message.kind, lppa.INITIATING)
        self.assertEqual(message.procedure, lppa.PROC_E_CID_INITIATION)
        self.assertEqual(message.name, "E-CIDMeasurementInitiationRequest")
        self.assertEqual(message.transaction_id, 7)
        self.assertEqual(lppa.esmlc_measurement_id(message), 3)
        self.assertEqual(message.ie("ReportCharacteristics"), "onDemand")
        self.assertEqual(lppa.measurement_quantities(message),
                         ["cell-ID", "timingAdvanceType1"])
        self.assertEqual(message.ie("MeasurementQuantities")[0]["id"], 11)
        self.assertIsNone(lppa.enb_measurement_id(message))

    def test_a_periodic_report_names_its_periodicity(self):
        message = lppa.parse(lppa.measurement_initiation_request(
            8, 1, report_characteristics="periodic", periodicity="ms10240",
            quantities=("cell-ID",)))
        self.assertEqual(message.ie("ReportCharacteristics"), "periodic")
        self.assertEqual(message.ie("MeasurementPeriodicity"), "ms10240")

    def test_the_periodicity_is_conditional_on_a_periodic_report(self):
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_initiation_request(
                8, 1, report_characteristics="periodic")
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_initiation_request(
                8, 1, report_characteristics="onDemand", periodicity="ms240")

    def test_a_request_names_at_least_one_quantity(self):
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_initiation_request(1, 1, quantities=())


class Measurements(unittest.TestCase):
    RESULT = lppa.MeasurementResult(
        cell=CELL, tac=TAC,
        position=lppa.CellPosition(
            latitude_sign="north", latitude=81000, longitude=7590000,
            altitude_direction="height", altitude=1200,
            uncertainty_semi_major=40, uncertainty_semi_minor=30,
            orientation_of_major_axis=0, uncertainty_altitude=30,
            confidence=67),
        measured=(("valueTimingAdvanceType1", 123),
                  ("valueAngleOfArrival", 42)))

    def test_a_response_carries_the_enb_identity_and_the_cell(self):
        wire = lppa.measurement_initiation_response(
            7, 3, 9, self.RESULT)
        message = lppa.parse(wire)
        self.assertEqual(message.kind, lppa.SUCCESSFUL)
        self.assertEqual(message.name, "E-CIDMeasurementInitiationResponse")
        self.assertEqual(lppa.esmlc_measurement_id(message), 3)
        self.assertEqual(lppa.enb_measurement_id(message), 9)
        result = lppa.measurement_result(message)
        self.assertEqual(result.cell, CELL)
        self.assertEqual(result.cell.bit_string(), (0x00A1B2C, 28))
        self.assertEqual(result.tac, TAC)
        self.assertEqual(result.position.confidence, 67)
        self.assertEqual(result.position.latitude, 81000)
        self.assertEqual(result.measured,
                         (("valueTimingAdvanceType1", 123),
                          ("valueAngleOfArrival", 42)))
        self.assertEqual(lppa.measured_value(message, "valueTimingAdvanceType1"),
                         123)
        self.assertEqual(lppa.measured_value(message, "valueAngleOfArrival"), 42)
        self.assertIsNone(lppa.measured_value(message, "valueTimingAdvanceType2"))

    def test_a_response_without_a_result_has_no_result(self):
        message = lppa.parse(lppa.measurement_initiation_response(7, 3, 9))
        self.assertIsNone(lppa.measurement_result(message))
        self.assertIsNone(lppa.measured_value(message, "valueAngleOfArrival"))

    def test_the_two_measurement_identities_are_told_apart_by_id(self):
        # Both IEs are typed Measurement-ID; only the IE id distinguishes the
        # E-SMLC's number from the eNB's.
        message = lppa.parse(lppa.measurement_report(7, 3, 9, self.RESULT))
        self.assertEqual(message.ie("Measurement-ID"), 3)
        self.assertEqual(message.ie_by_id(lppa.IE_E_SMLC_UE_MEASUREMENT_ID), 3)
        self.assertEqual(message.ie_by_id(lppa.IE_ENB_UE_MEASUREMENT_ID), 9)

    def test_a_report_and_a_termination_round_trip(self):
        report = lppa.parse(lppa.measurement_report(7, 3, 9, self.RESULT))
        self.assertEqual(report.procedure, lppa.PROC_E_CID_REPORT)
        self.assertEqual(report.name, "E-CIDMeasurementReport")
        self.assertEqual(report.transaction_id, 7)
        termination = lppa.parse(
            lppa.measurement_termination_command(7, 3, 9))
        self.assertEqual(termination.procedure, lppa.PROC_E_CID_TERMINATION)
        self.assertEqual(termination.name, "E-CIDMeasurementTerminationCommand")


class Failures(unittest.TestCase):
    def test_initiation_failure_is_unsuccessful_and_carries_a_cause(self):
        message = lppa.parse(lppa.measurement_initiation_failure(
            7, 3, ("radioNetwork", "requested-item-not-supported")))
        self.assertEqual(message.kind, lppa.UNSUCCESSFUL)
        self.assertEqual(message.name, "E-CIDMeasurementInitiationFailure")
        self.assertEqual(lppa.cause(message),
                         ("radioNetwork", "requested-item-not-supported"))

    def test_a_failure_indication_names_both_identities(self):
        message = lppa.parse(lppa.measurement_failure_indication(
            7, 3, 9, ("misc", "unspecified")))
        self.assertEqual(message.procedure, lppa.PROC_E_CID_FAILURE_INDICATION)
        self.assertEqual(lppa.esmlc_measurement_id(message), 3)
        self.assertEqual(lppa.enb_measurement_id(message), 9)
        self.assertEqual(lppa.cause(message), ("misc", "unspecified"))

    def test_an_error_indication_carries_its_cause_when_there_is_one(self):
        message = lppa.parse(lppa.error_indication(1, ("misc", "unspecified")))
        self.assertEqual(message.procedure, lppa.PROC_ERROR_INDICATION)
        self.assertEqual(lppa.cause(message), ("misc", "unspecified"))
        self.assertIsNone(lppa.cause(lppa.parse(lppa.error_indication(1))))


class Rejections(unittest.TestCase):
    def test_garbage_is_rejected_not_decoded(self):
        with self.assertRaises(lppa.LppaError):
            lppa.parse(b"\xff\xff\xff")

    def test_a_truncated_message_is_rejected(self):
        wire = lppa.measurement_report(7, 3, 9, Measurements.RESULT)
        with self.assertRaises(lppa.LppaError):
            lppa.parse(wire[:5])

    def test_an_unknown_procedure_is_refused_by_number(self):
        # pycrate leaves an open type outside the generated object set as raw
        # octets. The message layer must refuse it, not invent a name.
        from lib.codecs import lppa_codec
        obj = lppa_codec.LPPA_PDU_Descriptions.LPPA_PDU
        obj.set_val((lppa.INITIATING, {
            "procedureCode": 255, "criticality": "reject",
            "lppatransactionID": 1,
            "value": ("ErrorIndication", {"protocolIEs": []}),
        }))
        with self.assertRaises(lppa.LppaError):
            lppa.parse(obj.to_aper())

    def test_transaction_and_measurement_identities_are_bounded(self):
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_termination_command(32768, 1, 1)
        for bad in (0, 16):
            with self.assertRaises(lppa.LppaError):
                lppa.measurement_initiation_request(1, bad)
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_initiation_response(1, 1, 16)

    def test_unknown_quantities_periodicities_and_cause_groups_are_rejected(self):
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_initiation_request(1, 1, quantities=("otdoa",))
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_initiation_request(
                1, 1, report_characteristics="periodic", periodicity="ms1")
        with self.assertRaises(lppa.LppaError):
            lppa.error_indication(1, ("transport", "unspecified"))

    def test_a_measured_result_kind_must_be_one_the_choice_defines(self):
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_report(1, 1, 1, lppa.MeasurementResult(
                cell=CELL, tac=TAC, measured=(("valueTimingAdvanceType3", 1),)))

    def test_a_result_names_a_well_formed_cell(self):
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_report(1, 1, 1, lppa.MeasurementResult(
                cell=lppa.Ecgi(lppa.LAB_PLMN, 1 << 28), tac=TAC))
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_report(1, 1, 1, lppa.MeasurementResult(
                cell=CELL, tac=b"\x00"))

    def test_a_cell_identity_that_is_not_28_bits_is_an_error(self):
        message = lppa.LppaMessage(
            kind=lppa.INITIATING, procedure=lppa.PROC_E_CID_REPORT,
            transaction_id=1, criticality=lppa.CRITICALITY_REJECT,
            name="E-CIDMeasurementReport",
            ies=[lppa.Ie(lppa.IE_E_CID_MEASUREMENT_RESULT,
                         lppa.CRITICALITY_IGNORE,
                         "E-CID-MeasurementResult", {
                             "servingCell-ID": {
                                 "pLMN-Identity": lppa.LAB_PLMN,
                                 "eUTRANcellIdentifier": (0x00A1B, 24),
                             },
                             "servingCellTAC": TAC,
                         })],
        )
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_result(message)

    def test_a_quantity_item_of_another_type_is_an_error(self):
        message = lppa.LppaMessage(
            kind=lppa.INITIATING, procedure=lppa.PROC_E_CID_INITIATION,
            transaction_id=1, criticality=lppa.CRITICALITY_REJECT,
            name="E-CIDMeasurementInitiationRequest",
            ies=[lppa.Ie(lppa.IE_MEASUREMENT_QUANTITIES,
                         lppa.CRITICALITY_REJECT, "MeasurementQuantities", [
                             {"id": 99, "criticality": "reject",
                              "value": ("CSG-IdList", [])},
                         ])],
        )
        with self.assertRaises(lppa.LppaError):
            lppa.measurement_quantities(message)


class ConcurrentCodec(unittest.TestCase):
    def test_the_shared_codec_object_is_not_corrupted_across_threads(self):
        def work(worker):
            for round_no in range(50):
                transaction = worker * 50 + round_no
                measured = 100 + round_no
                wire = lppa.measurement_report(
                    transaction, 1 + round_no % 15, 1 + worker % 15,
                    lppa.MeasurementResult(
                        cell=lppa.Ecgi(lppa.LAB_PLMN, 0x00A1B2C + worker),
                        tac=TAC,
                        measured=(("valueTimingAdvanceType1", measured),)))
                message = lppa.parse(wire)
                self.assertEqual(message.transaction_id, transaction)
                self.assertEqual(
                    lppa.measured_value(message, "valueTimingAdvanceType1"),
                    measured)
                self.assertEqual(lppa.measurement_result(message).cell.cell_id,
                                 0x00A1B2C + worker)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, range(8)))


class GeneratedCodec(unittest.TestCase):
    def test_committed_codec_matches_the_committed_asn1(self):
        """The .asn file is the source; the .py beside it is generated from it."""
        import subprocess
        import tempfile

        generator = ROOT / "lib" / "codecs" / "lppa_codec.py"
        asn = ROOT / "lib" / "codecs" / "asn1" / "lppa.asn"
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
        self.assertTrue(header.startswith("# Generated by lib/codecs/build_lppa.py"))
        self.assertEqual(committed[len(header):], generated,
                         "lppa_codec.py is stale; rerun lib/codecs/build_lppa.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
