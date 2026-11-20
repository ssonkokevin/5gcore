"""GMLC behaviour — every request must resolve to an honest outcome.

Runs in-process with FastAPI's TestClient; Redis is not required (the store
falls back to memory when it cannot connect).

    python tests/test_gmlc_service.py
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None

MODULE_PATH = ROOT / "archive" / "python-gmlc-stub" / "src" / "gmlc_server.py"


def load_gmlc():
    spec = importlib.util.spec_from_file_location("gmlc_server_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE_CONFIG = {
    "gmlc": {"host": "127.0.0.1", "port": 8082},
    "redis": {"host": "127.0.0.1", "port": 6379, "password": ""},
    "interfaces": {"slh": False, "slg": False},
    "lcs": {"request_types": ["immediate", "deferred", "periodic"]},
    "privacy": {
        "check_privacy": True,
        "default_privacy_class": "location_allowed",
        "override_privacy_emergency": False,
    },
}


def build_client(overrides=None):
    gmlc = load_gmlc()
    cfg = yaml.safe_load(yaml.safe_dump(BASE_CONFIG))
    if overrides:
        cfg.update(overrides)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(cfg, fh)
        path = fh.name
    server = gmlc.GMLCServer(gmlc.GMLCConfig(path))
    return TestClient(server.app)


@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class TestLocationRequests(unittest.TestCase):
    def setUp(self):
        self.client = build_client()

    def test_immediate_request_fails_closed(self):
        r = self.client.post("/lcs/location-request", json={"msisdn": "256700000001"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["error_code"], "NO_LCS_SOURCE")
        self.assertIsNone(body["latitude"])
        self.assertIsNone(body["longitude"])
        self.assertTrue(body["timestamp"])

    def test_status_poll_returns_the_stored_outcome(self):
        created = self.client.post("/lcs/location-request", json={"msisdn": "256700000002"}).json()
        r = self.client.get(f"/lcs/location-request/{created['request_id']}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["error_code"], created["error_code"])

    def test_unknown_request_is_404_not_fake_pending(self):
        r = self.client.get("/lcs/location-request/lcs-doesnotexist")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["cause"], "REQUEST_NOT_FOUND")

    def test_deferred_is_not_reported_as_queued(self):
        r = self.client.post(
            "/lcs/location-request",
            json={"msisdn": "256700000003", "request_type": "deferred"},
        )
        body = r.json()
        self.assertEqual(body["status"], "failed")
        self.assertNotIn("queued for processing", body["error_message"])

    def test_map_psl_is_rejected(self):
        r = self.client.post("/map/psl", json={"msisdn": "256700000004"})
        self.assertEqual(r.json()["status"], "rejected")

    def test_diameter_shims_signal_non_compliance(self):
        for path, code in (("/diameter/slh", 8388622), ("/diameter/slg", 8388620)):
            body = self.client.post(path, json={"session_id": "s1"}).json()
            self.assertEqual(body["command_code"], code)
            self.assertEqual(body["result_code"], 5010)
            self.assertEqual(body["transport"], "http-shim")


@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class TestPrivacy(unittest.TestCase):
    def test_override_is_refused_when_not_configured(self):
        client = build_client()
        r = client.post(
            "/lcs/location-request",
            json={"msisdn": "256700000005", "lcs_client_type": "value_added", "privacy_override": True},
        )
        self.assertEqual(r.json()["status"], "not_authorized")
        self.assertEqual(r.json()["error_code"], "PRIVACY_OVERRIDE_REJECTED")

    def test_override_allowed_for_emergency_when_enabled(self):
        client = build_client(
            {"privacy": {"check_privacy": True, "default_privacy_class": "location_allowed",
                         "override_privacy_emergency": True}}
        )
        r = client.post(
            "/lcs/location-request",
            json={"msisdn": "256700000006", "privacy_override": True},
        )
        self.assertEqual(r.json()["error_code"], "NO_LCS_SOURCE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
