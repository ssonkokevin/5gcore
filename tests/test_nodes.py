"""AMF, LMF and MME behaviour.

    python tests/test_nodes.py

The MME test opens a real TCP connection to the SLg listener and exchanges
encoded Diameter messages, so the codec and the server are exercised together.
"""

import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from corelib import diameter as d  # noqa: E402

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


for _src in ("amf", "lmf", "mme"):
    sys.path.insert(0, str(ROOT / _src / "src"))

import amf_server  # noqa: E402
import lmf_server  # noqa: E402
import mme_server  # noqa: E402


def read_pdu(sock):
    header = b""
    while len(header) < 20:
        chunk = sock.recv(20 - len(header))
        if not chunk:
            raise AssertionError("peer closed before a full header")
        header += chunk
    length = int.from_bytes(header[1:4], "big")
    body = b""
    while len(body) < length - 20:
        chunk = sock.recv(length - 20 - len(body))
        if not chunk:
            raise AssertionError("peer closed mid-message")
        body += chunk
    return d.decode_message(header + body)


def request(code, app_id, avps, flags=d.FLAG_REQUEST | d.FLAG_PROXYABLE):
    return d.Message(
        command_code=code, app_id=app_id, avps=avps, flags=flags,
        hop_by_hop=0x01020304, end_to_end=0x05060708,
    )


@unittest.skipIf(TestClient is None, "FastAPI TestClient unavailable")
class MME(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = mme_server
        cls.client = TestClient(cls.mod.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_health_states_what_is_missing(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["scope"], "SLg only")
        self.assertEqual(body["s1ap"], "not implemented")
        self.assertFalse(body["ue_attach"] if "ue_attach" in body else False)

    def test_plr_shim_answers_5012(self):
        response = self.client.post(
            "/slg/plr",
            json={"session_id": "gmlc;abc;1", "subscriber": "641020123456789"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["result_code"], d.RESULT_UNABLE_TO_COMPLY)
        self.assertEqual(body["command_code"], d.CMD_PLR)
        self.assertIn("not implemented", body["error_message"])

    def test_plr_for_other_realm_is_rejected(self):
        body = self.client.post(
            "/slg/plr",
            json={"session_id": "s;1", "destination_realm": "other.example"},
        ).json()
        self.assertEqual(body["result_code"], d.RESULT_REALM_NOT_SERVED)

    def test_scope_lists_gaps(self):
        body = self.client.get("/scope").json()
        joined = " ".join(body["not_implemented"]).lower()
        self.assertIn("s1ap", joined)
        self.assertIn("map lcs", joined)

    def test_diameter_tcp_round_trip(self):
        try:
            sock = socket.create_connection(("127.0.0.1", self.mod.SLG_PORT), timeout=5)
        except OSError as exc:
            self.skipTest(f"SLg listener not reachable: {exc}")
        try:
            cer = request(d.CMD_CAPABILITIES_EXCHANGE, 0, [
                d.AVP_UTF8(d.AVP_ORIGIN_HOST, "peer.core.local"),
                d.AVP_UTF8(d.AVP_ORIGIN_REALM, "core.local"),
                d.AVP_U32(d.AVP_VENDOR_ID, 10415, mandatory=False),
            ])
            sock.sendall(cer.encode())
            cea = read_pdu(sock)
            self.assertEqual(cea.command_code, d.CMD_CAPABILITIES_EXCHANGE)
            self.assertFalse(cea.is_request)
            self.assertEqual(cea.avp(d.AVP_RESULT_CODE).as_uint32(), d.RESULT_SUCCESS)
            self.assertEqual(cea.avp(d.AVP_ORIGIN_HOST).as_string(), self.mod.ORIGIN_HOST)

            plr = request(d.CMD_PLR, d.APP_SLG, [
                d.AVP_UTF8(d.AVP_SESSION_ID, "gmlc;tcp;1"),
                d.AVP_UTF8(d.AVP_ORIGIN_HOST, "peer.core.local"),
                d.AVP_UTF8(d.AVP_ORIGIN_REALM, "core.local"),
                d.AVP_UTF8(d.AVP_DESTINATION_REALM, self.mod.ORIGIN_REALM),
                d.AVP_UTF8(d.AVP_USER_NAME, "641020123456789"),
            ])
            sock.sendall(plr.encode())
            pla = read_pdu(sock)
            self.assertEqual(pla.command_code, d.CMD_PLR)
            self.assertEqual(pla.app_id, d.APP_SLG)
            self.assertEqual(pla.avp(d.AVP_RESULT_CODE).as_uint32(), d.RESULT_UNABLE_TO_COMPLY)
            self.assertEqual(pla.avp(d.AVP_SESSION_ID).as_string(), "gmlc;tcp;1")
            self.assertEqual(pla.avp(d.AVP_DESTINATION_REALM).as_string(), "core.local")
        finally:
            sock.close()


@unittest.skipIf(TestClient is None, "FastAPI TestClient unavailable")
class LMF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = lmf_server
        cls.client = TestClient(cls.mod.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_health_reports_no_provider(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["provider"], "none")

    def test_determine_location_fails_closed(self):
        response = self.client.post(
            "/nlmf-loc/v1/determine-location",
            json={"supi": "imsi-641020123456789", "locationQoS": {"horizontalAccuracy": 50}},
        )
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["detail"]["cause"], "NO_POSITIONING_SOURCE")

    def test_context_transfer_is_not_pretended(self):
        response = self.client.post("/nlmf-loc/v1/location-context-transfer", json={})
        self.assertEqual(response.status_code, 501)


@unittest.skipIf(TestClient is None, "FastAPI TestClient unavailable")
class AMF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = amf_server
        cls.client = TestClient(cls.mod.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_health_is_honest_about_n2(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["n2_ngap"], "not implemented")
        self.assertFalse(body["ue_attach"])

    def test_provide_loc_info_without_lmf(self):
        response = self.client.post(
            "/namf-loc/v1/imsi-641020123456789/provide-loc-info",
            json={"locationQoS": {"horizontalAccuracy": 50}},
        )
        self.assertIn(response.status_code, (503, 504))
        self.assertIn("LMF", str(response.json()))

    def test_event_notify_is_not_pretended(self):
        response = self.client.post(
            "/namf-loc/v1/imsi-641020123456789/event-notify", json={}
        )
        self.assertEqual(response.status_code, 501)


if __name__ == "__main__":
    unittest.main(verbosity=2)
