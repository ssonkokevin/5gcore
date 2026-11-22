"""The MME's LCS function: contexts, paging, SLs, LPP relay, cell fallback.

    python tests/test_mme_location.py

The E-SMLC here is the lab simulator over the D5 TCP carrier. Everything the
simulator returns comes from esmlc/config/lab_positions.json, which is
synthetic data for lab PLMN 001-01. The UE is the lab peer from
esmlc/src/lpp_ue.py behind its HTTP endpoint, because a real UE would answer
LPP on a bearer this MME does not have.
"""

import asyncio
import json
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "mme" / "src", ROOT / "esmlc" / "src"):
    sys.path.insert(0, str(_p))

from corelib import diameter as d  # noqa: E402
from lib.codecs import lcsap, lpp  # noqa: E402

import cell_plan  # noqa: E402
import esmlc_sim  # noqa: E402
import mme_server  # noqa: E402
import nas_relay  # noqa: E402
import slg  # noqa: E402
import ue_contexts  # noqa: E402
from location_service import LocationService  # noqa: E402
from lpp_ue import LabUe, UeEndpoint  # noqa: E402

PLMN = lcsap.LAB_PLMN
CELL_A = 0x00A1B2C
CELL_B = 0x00A1B2D
CELL_C = 0x00A1B2E
LAB_UE_A = "001010000000001"
LAB_UE_B = "001010000000002"
LAB_UE_C = "001010000000003"
UNKNOWN_CELL = 0x00FFFFFF


def free_port() -> int:
    """A port nothing listens on, for the E-SMLC-unreachable case."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def context(imsi=LAB_UE_A, cell=CELL_A, **kwargs):
    return ue_contexts.UeContext(imsi=imsi, plmn=PLMN, cell=cell, **kwargs)


def plr(identity, accuracy_m=None, client_type=None, location_type=1):
    avps = [
        d.AVP_UTF8(d.AVP_SESSION_ID, "gmlc;test;1"),
        d.AVP_UTF8(d.AVP_ORIGIN_HOST, "peer.core.local"),
        d.AVP_UTF8(d.AVP_ORIGIN_REALM, "core.local"),
        d.AVP_UTF8(d.AVP_DESTINATION_REALM, mme_server.ORIGIN_REALM),
        d.AVP_UTF8(d.AVP_USER_NAME, identity),
        d.AVP_U32(d.AVP_SLG_LOCATION_TYPE, location_type, vendor_id=d.VENDOR_3GPP),
    ]
    if accuracy_m is not None:
        avps.append(d.AVP_GROUPED(
            d.AVP_LCS_QOS,
            [d.AVP_U32(d.AVP_HORIZONTAL_ACCURACY,
                       lcsap.uncertainty_code(accuracy_m), vendor_id=d.VENDOR_3GPP)],
            vendor_id=d.VENDOR_3GPP))
    if client_type is not None:
        avps.append(d.AVP_U32(d.AVP_LCS_CLIENT_TYPE, client_type,
                              vendor_id=d.VENDOR_3GPP))
    return d.Message(command_code=d.CMD_PLR, app_id=d.APP_SLG, avps=avps,
                     flags=d.FLAG_REQUEST | d.FLAG_PROXYABLE)


class StoreAndPaging(unittest.TestCase):
    def test_connected_ue_is_reachable_without_paging(self):
        store = ue_contexts.UeContextStore([context()])
        self.assertEqual(store.ensure_reachable(LAB_UE_A),
                         (True, ue_contexts.PAGE_CONNECTED))
        self.assertEqual(store.get(LAB_UE_A).pages, 0)

    def test_idle_ue_that_answers_becomes_connected(self):
        store = ue_contexts.UeContextStore([context(rrc_state="idle")])
        self.assertEqual(store.ensure_reachable(LAB_UE_A),
                         (True, ue_contexts.PAGE_ANSWERED))
        stored = store.get(LAB_UE_A)
        self.assertEqual(stored.rrc_state, "connected")
        self.assertEqual(stored.pages, 1)

    def test_idle_ue_that_ignores_the_page_stays_idle(self):
        store = ue_contexts.UeContextStore(
            [context(rrc_state="idle", answers_pages=False)])
        self.assertEqual(store.ensure_reachable(LAB_UE_A),
                         (False, ue_contexts.PAGE_IGNORED))
        stored = store.get(LAB_UE_A)
        self.assertEqual(stored.rrc_state, "idle")
        self.assertEqual(stored.pages, 1)

    def test_unknown_ue(self):
        store = ue_contexts.UeContextStore()
        self.assertEqual(store.ensure_reachable(LAB_UE_A),
                         (False, ue_contexts.PAGE_UNKNOWN))

    def test_snapshot_and_remove(self):
        store = ue_contexts.UeContextStore([context()])
        snapshot = store.snapshot()
        self.assertEqual(snapshot[0]["imsi"], LAB_UE_A)
        self.assertEqual(snapshot[0]["cell"], "0x00A1B2C")
        self.assertTrue(store.remove(LAB_UE_A))
        self.assertFalse(store.remove(LAB_UE_A))

    def test_bad_contexts_are_rejected(self):
        good = {"imsi": LAB_UE_A, "mcc": "001", "mnc": "01", "cell": "0x00A1B2C"}
        ue_contexts.parse_context(good)
        for bad in (
            {**good, "imsi": "12ab"},
            {**good, "cell": "0x10000000"},
            {**good, "rrc_state": "sleeping"},
            {**good, "answers_pages": "yes"},
            {**good, "mcc": "01"},
            {**good, "cell": "not-a-number"},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ue_contexts.UeContextError):
                    ue_contexts.parse_context(bad)


class CellPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = cell_plan.CellPlan.from_file(cell_plan.DEFAULT_CONFIG)

    def test_committed_plan_has_the_three_lab_cells(self):
        self.assertEqual(len(self.plan), 3)
        row = self.plan.lookup(PLMN, CELL_A)
        self.assertIsNotNone(row)
        self.assertEqual(row.radius_m, 35)
        self.assertEqual(row.latitude, 0.347596)

    def test_unknown_cell_has_no_position(self):
        self.assertIsNone(self.plan.lookup(PLMN, UNKNOWN_CELL))
        self.assertIsNone(self.plan.lookup(b"\x13\x00\x62", CELL_A))

    def test_a_cell_without_a_radius_is_rejected(self):
        with self.assertRaises(cell_plan.CellPlanError):
            cell_plan.CellPlan.from_dict({
                "plmn": "001-01",
                "cells": [{"cell": "0x00A1B2C", "latitude": 0.1,
                           "longitude": 32.5, "radius_m": 0}],
            })

    def test_duplicate_cells_are_rejected(self):
        row = {"cell": "0x00A1B2C", "latitude": 0.1, "longitude": 32.5,
               "radius_m": 10}
        with self.assertRaises(cell_plan.CellPlanError):
            cell_plan.CellPlan.from_dict({"plmn": "001-01", "cells": [row, row]})

    def test_out_of_range_coordinates_are_rejected(self):
        with self.assertRaises(cell_plan.CellPlanError):
            cell_plan.CellPlan.from_dict({
                "plmn": "001-01",
                "cells": [{"cell": "0x00A1B2C", "latitude": 91.0,
                           "longitude": 32.5, "radius_m": 10}],
            })


class SlgAvps(unittest.TestCase):
    def test_ecgi_is_seven_octets_in_the_gmlc_order(self):
        self.assertEqual(slg.ecgi(PLMN, CELL_A), b"\x00\xf1\x10\x00\x0a\x1b\x2c")

    def test_ecgi_rejects_a_cell_that_is_not_28_bits(self):
        with self.assertRaises(ValueError):
            slg.ecgi(PLMN, 1 << 28)

    def test_subscriber_prefers_user_name(self):
        message = d.Message(command_code=d.CMD_PLR, app_id=d.APP_SLG, avps=[
            d.AVP_UTF8(d.AVP_USER_NAME, LAB_UE_A),
            d.AVP(d.AVP_MSISDN, lcsap.tbcd("256700000001"),
                  vendor_id=d.VENDOR_3GPP),
        ])
        self.assertEqual(slg.subscriber(message), LAB_UE_A)

    def test_subscriber_falls_back_to_a_tbcd_msisdn(self):
        message = d.Message(command_code=d.CMD_PLR, app_id=d.APP_SLG, avps=[
            d.AVP(d.AVP_MSISDN, lcsap.tbcd("256700000001"),
                  vendor_id=d.VENDOR_3GPP)])
        self.assertEqual(slg.subscriber(message), "256700000001")
        self.assertIsNone(slg.subscriber(d.Message(
            command_code=d.CMD_PLR, app_id=d.APP_SLG)))

    def test_subscriber_refuses_a_msisdn_that_is_not_tbcd(self):
        # A peer that writes the digits as text sends 12 octets, which no
        # TBCD E.164 number can be. Reading it as TBCD would invent a number.
        message = d.Message(command_code=d.CMD_PLR, app_id=d.APP_SLG, avps=[
            d.AVP_UTF8(d.AVP_MSISDN, "256700000001")])
        with self.assertRaises(d.DiameterError):
            slg.subscriber(message)

    def test_accuracy_is_an_uncertainty_code(self):
        code = lcsap.uncertainty_code(50.0)
        accuracy = slg.requested_accuracy(plr(LAB_UE_A, accuracy_m=50.0))
        self.assertEqual(accuracy, lcsap.uncertainty_metres(code))
        self.assertGreaterEqual(accuracy, 50.0)
        self.assertLess(accuracy, 55.0)

    def test_accuracy_absent_means_absent(self):
        self.assertIsNone(slg.requested_accuracy(plr(LAB_UE_A)))

    def test_client_types_are_mapped(self):
        self.assertEqual(slg.client_type(plr(LAB_UE_A, client_type=0)),
                         lcsap.CLIENT_EMERGENCY)
        self.assertEqual(slg.client_type(plr(LAB_UE_A, client_type=1)),
                         lcsap.CLIENT_VALUE_ADDED)
        self.assertEqual(slg.client_type(plr(LAB_UE_A)),
                         lcsap.CLIENT_PLMN_OPERATOR)

    def test_location_type_is_read(self):
        self.assertEqual(slg.location_type(plr(LAB_UE_A)), 1)
        self.assertEqual(slg.location_type(plr(LAB_UE_A, location_type=3)), 3)

    def test_answer_avps_are_vendor_3gpp_and_survive_the_wire(self):
        from location_service import LocationOutcome
        outcome = LocationOutcome(
            positioned=True, result_code=d.RESULT_SUCCESS,
            latitude=0.347596, longitude=32.582520, radius_m=35.96,
            method="e-cid", source="SLS", fulfilled=False, age_seconds=0,
            cell=CELL_A, plmn=PLMN)
        encoded = [avp.encode() for avp in slg.location_answer_avps(outcome)]
        decoded = d.decode_avps(b"".join(encoded))
        by_code = {avp.code: avp for avp in decoded}
        # AVP length includes RFC 6733 padding, which is one octet here.
        self.assertEqual(by_code[d.AVP_ECGI].value[:7], slg.ecgi(PLMN, CELL_A))
        self.assertEqual(by_code[d.AVP_ECGI].vendor_id, d.VENDOR_3GPP)
        self.assertEqual(by_code[d.AVP_ACCURACY_FULFILMENT].as_uint32(),
                         slg.FULFILMENT_NOT_FULFILLED)
        self.assertEqual(by_code[d.AVP_AGE_OF_LOCATION].as_uint32(), 0)

    def test_a_failure_carries_no_position(self):
        from location_service import LocationOutcome
        outcome = LocationOutcome(positioned=False, result_code=d.RESULT_USER_UNKNOWN,
                                  cell=CELL_A, plmn=PLMN)
        self.assertEqual(slg.location_answer_avps(outcome), [])


class _NasHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length))
        self.server.requests.append(request)
        status, payload = self.server.reply
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class NasStub:
    def __init__(self, reply, status=200):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _NasHandler)
        self.server.requests = []
        self.server.reply = (status, reply)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}/lpp"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    @property
    def requests(self):
        return self.server.requests


class HttpNasLink(unittest.TestCase):
    def test_posts_the_imsi_and_apdu_and_returns_the_answer(self):
        with NasStub({"apdu": "deadbeef"}) as stub:
            answer = nas_relay.HttpNasLink(stub.url, LAB_UE_A)(b"\x01\x02")
            self.assertEqual(answer, b"\xde\xad\xbe\xef")
            self.assertEqual(stub.requests,
                             [{"imsi": LAB_UE_A, "apdu": "0102"}])

    def test_204_means_nothing_to_send(self):
        with NasStub(None, status=204) as stub:
            self.assertIsNone(nas_relay.HttpNasLink(stub.url, LAB_UE_A)(b"\x01"))
            self.assertEqual(len(stub.requests), 1)

    def test_an_unreachable_ue_returns_none(self):
        link = nas_relay.HttpNasLink(f"http://127.0.0.1:{free_port()}/lpp",
                                     LAB_UE_A, timeout=0.5)
        self.assertIsNone(link(b"\x01"))

    def test_an_unreadable_answer_returns_none(self):
        with NasStub({"apdu": "not-hex"}) as stub:
            self.assertIsNone(nas_relay.HttpNasLink(stub.url, LAB_UE_A)(b"\x01"))

    def test_an_error_status_returns_none(self):
        with NasStub({"detail": "no"}, status=500) as stub:
            self.assertIsNone(nas_relay.HttpNasLink(stub.url, LAB_UE_A)(b"\x01"))


class AgainstTheSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = esmlc_sim.PositionTable.from_file(esmlc_sim.DEFAULT_CONFIG)
        cls.sim = esmlc_sim.EsmlcSimulator(cls.table, host="127.0.0.1", port=0,
                                          lpp_timeout=1.0)
        cls.sim.start()
        cls.plan = cell_plan.CellPlan.from_file(cell_plan.DEFAULT_CONFIG)
        # Target A asks for one LPP round; this UE answers real LPP.
        cls.ue = UeEndpoint(LabUe()).start()

    @classmethod
    def tearDownClass(cls):
        cls.ue.stop()
        cls.sim.stop()

    def ctx(self, imsi=LAB_UE_A, cell=CELL_A, **kwargs):
        kwargs.setdefault("nas_url", self.ue.url)
        return ue_contexts.UeContext(imsi=imsi, plmn=PLMN, cell=cell, **kwargs)

    def service(self, *contexts, port=None, plan=None):
        store = ue_contexts.UeContextStore(contexts)
        return LocationService(store, plan or self.plan,
                               esmlc_host="127.0.0.1",
                               esmlc_port=self.sim.port if port is None else port,
                               timeout=3.0)

    def test_ecid_position_is_fulfilled_at_fifty_metres(self):
        outcome = self.service(self.ctx()).locate(LAB_UE_A, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "SLS")
        self.assertEqual(outcome.method, "e-cid")
        self.assertTrue(outcome.fulfilled)
        self.assertEqual(outcome.age_seconds, 0)
        self.assertAlmostEqual(outcome.latitude, 0.347596, places=5)
        self.assertLess(outcome.radius_m, 40.0)

    def test_twenty_metres_is_not_fulfilled(self):
        outcome = self.service(self.ctx()).locate(LAB_UE_A, 20.0)
        self.assertTrue(outcome.positioned)
        self.assertFalse(outcome.fulfilled)

    def test_no_accuracy_request_means_no_verdict(self):
        outcome = self.service(self.ctx()).locate(LAB_UE_A)
        self.assertTrue(outcome.positioned)
        self.assertIsNone(outcome.fulfilled)

    def test_imsi_wins_over_the_serving_cell(self):
        # The IMSI's table entry is the otdoa cell, while the context says
        # cell C. The simulator must answer from the IMSI.
        outcome = self.service(self.ctx(imsi=LAB_UE_B, cell=CELL_C)).locate(LAB_UE_B, 200.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.method, "otdoa")
        self.assertEqual(outcome.lpp_rounds, 2)
        self.assertTrue(outcome.fulfilled)

    def test_a_cell_only_target_is_answered_from_the_cell(self):
        outcome = self.service(self.ctx(imsi=LAB_UE_C, cell=CELL_C)).locate(LAB_UE_C, 600.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.method, "cell-id")
        self.assertGreater(outcome.radius_m, 500.0)

    def test_paging_makes_an_idle_ue_reachable(self):
        svc = self.service(self.ctx(rrc_state="idle"))
        outcome = svc.locate(LAB_UE_A, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.reached_by, ue_contexts.PAGE_ANSWERED)
        self.assertEqual(svc.contexts.get(LAB_UE_A).rrc_state, "connected")

    def test_a_ue_that_ignores_the_page_gets_4221(self):
        svc = self.service(self.ctx(rrc_state="idle", answers_pages=False))
        outcome = svc.locate(LAB_UE_A, 50.0)
        self.assertFalse(outcome.positioned)
        self.assertEqual(outcome.result_code, d.RESULT_UNREACHABLE_USER)
        self.assertIn("page", outcome.detail)
        self.assertEqual(svc.contexts.get(LAB_UE_A).rrc_state, "idle")

    def test_an_unknown_subscriber_gets_5001(self):
        outcome = self.service().locate("001019999999999")
        self.assertFalse(outcome.positioned)
        self.assertEqual(outcome.result_code, d.RESULT_USER_UNKNOWN)

    def test_lpp_is_relayed_to_the_ue_and_back(self):
        seen = len(self.ue.requests)
        outcome = self.service(self.ctx()).locate(LAB_UE_A, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.lpp_rounds, 1)
        imsi, apdu = self.ue.requests[seen]
        asked = lpp.parse(apdu)
        self.assertEqual(asked.kind, lpp.REQUEST_LOCATION_INFORMATION)
        self.assertEqual(asked.transaction_id.initiator,
                         lpp.INITIATOR_LOCATION_SERVER)
        self.assertTrue(asked.end_transaction)
        common = (asked.body["criticalExtensions"][1][1]
                  ["commonIEsRequestLocationInformation"])
        self.assertEqual(common["qos"]["horizontalAccuracy"]["accuracy"],
                         lcsap.uncertainty_code(35.0))
        self.assertEqual(imsi, LAB_UE_A)

    def test_an_answer_for_another_transaction_fails_the_dialogue(self):
        before = self.sim.counters["lpp_rejected"]
        ue = LabUe(behaviour="wrong-transaction")
        with UeEndpoint(ue) as endpoint:
            outcome = self.service(
                self.ctx(nas_url=endpoint.url)).locate(LAB_UE_A, 50.0)
        self.assertEqual(outcome.source, "CELL_PLAN")
        self.assertIn("E-SMLC", outcome.detail)
        self.assertGreater(self.sim.counters["lpp_rejected"], before)

    def test_a_ue_abort_fails_the_dialogue(self):
        with UeEndpoint(LabUe(behaviour="abort")) as endpoint:
            outcome = self.service(
                self.ctx(nas_url=endpoint.url)).locate(LAB_UE_A, 50.0)
        self.assertEqual(outcome.source, "CELL_PLAN")

    def test_a_ue_failure_cause_fails_the_dialogue(self):
        with UeEndpoint(LabUe(behaviour="failure")) as endpoint:
            outcome = self.service(
                self.ctx(nas_url=endpoint.url)).locate(LAB_UE_A, 50.0)
        self.assertEqual(outcome.source, "CELL_PLAN")

    def test_a_ue_that_ignores_lpp_falls_back_to_the_plan(self):
        with UeEndpoint(LabUe(behaviour="ignore")) as endpoint:
            outcome = self.service(
                self.ctx(nas_url=endpoint.url)).locate(LAB_UE_A, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "CELL_PLAN")
        self.assertEqual(outcome.method, "cell-id")
        self.assertIn("E-SMLC", outcome.detail)

    def test_a_ue_without_a_nas_endpoint_cannot_satisfy_lpp(self):
        outcome = self.service(self.ctx(nas_url=None)).locate(LAB_UE_A, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "CELL_PLAN")
        self.assertIn("no NAS transport", outcome.detail)

    def test_an_unreachable_esmlc_falls_back_to_the_plan(self):
        outcome = self.service(self.ctx(), port=free_port()).locate(LAB_UE_A, 50.0)
        self.assertTrue(outcome.positioned)
        self.assertEqual(outcome.source, "CELL_PLAN")
        self.assertEqual(outcome.method, "cell-id")
        self.assertEqual(outcome.radius_m, 35.0)
        self.assertTrue(outcome.fulfilled)
        self.assertIsNone(outcome.age_seconds)

    def test_an_unreachable_esmlc_without_a_plan_row_gets_4225(self):
        outcome = self.service(self.ctx(cell=UNKNOWN_CELL),
                               port=free_port()).locate(LAB_UE_A, 50.0)
        self.assertFalse(outcome.positioned)
        self.assertEqual(outcome.result_code, d.RESULT_POSITIONING_FAILED)
        self.assertIn("cell plan", outcome.detail)

    def test_the_diameter_handler_answers_with_ecgi_and_fulfilment(self):
        original = mme_server.LOCATION
        mme_server.LOCATION = self.service(self.ctx())
        try:
            answer = asyncio.run(mme_server.handle_message(
                plr(LAB_UE_A, accuracy_m=50.0)))
        finally:
            mme_server.LOCATION = original
        self.assertFalse(answer.is_request)
        self.assertEqual(answer.avp(d.AVP_RESULT_CODE).as_uint32(), d.RESULT_SUCCESS)
        self.assertEqual(answer.avp(d.AVP_ECGI).as_octets(),
                         slg.ecgi(PLMN, CELL_A))
        self.assertEqual(answer.avp(d.AVP_ECGI).vendor_id, d.VENDOR_3GPP)
        self.assertEqual(answer.avp(d.AVP_ACCURACY_FULFILMENT).as_uint32(),
                         slg.FULFILMENT_FULFILLED)
        self.assertEqual(answer.avp(d.AVP_AGE_OF_LOCATION).as_uint32(), 0)

    def test_the_diameter_handler_refuses_location_reporting(self):
        answer = asyncio.run(mme_server.handle_message(
            plr(LAB_UE_A, location_type=3)))
        self.assertEqual(answer.avp(d.AVP_RESULT_CODE).as_uint32(),
                         d.RESULT_UNABLE_TO_COMPLY)
        self.assertIsNone(answer.avp(d.AVP_ECGI))


if __name__ == "__main__":
    unittest.main(verbosity=2)
