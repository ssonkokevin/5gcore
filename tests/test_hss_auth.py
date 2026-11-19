"""HSS ARPF: 5G_AKA vectors, AUTS resynchronisation, EAP-AKA' refusal.

The HSS is the Option-1 ARPF for credentials held in the EPS-UDR. These tests
recompute the returned vector from its own RAND, so a hash-derived AUTN or a
vector issued at the wrong SQN fails. EAP-AKA' must stay a 501 and must not
touch the stored SQN.
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if "mysql" not in sys.modules:
    mysql = types.ModuleType("mysql")
    connector = types.ModuleType("mysql.connector")
    connector.connect = lambda **kwargs: None
    mysql.connector = connector
    sys.modules["mysql"] = mysql
    sys.modules["mysql.connector"] = connector

try:
    import python_multipart  # noqa: F401
except ImportError:
    _multipart = types.ModuleType("python_multipart")
    _multipart.__version__ = "0.0.20"
    sys.modules["python_multipart"] = _multipart
    sys.modules["multipart"] = _multipart

sys.path.insert(0, str(ROOT / "hss" / "src"))
from fastapi.testclient import TestClient  # noqa: E402

import nhss_server as hss  # noqa: E402
from corelib.milenage import Milenage  # noqa: E402

IMSI = "001010000000001"
K = bytes.fromhex("465b5ce8b199b49faa5f0a2ee238a6bc")
OPC = bytes.fromhex("cd63cb71954a9f4e48a5994e37a02baf")
AMF = bytes.fromhex("8000")
SNN = "5G:mnc001.mcc001.3gppnetwork.org"


class FakeCursor:
    def __init__(self, store, updates):
        self.store = store
        self.updates = updates
        self.description = None
        self.rowcount = 0
        self._row = None

    def execute(self, sql, params=None):
        text = " ".join(sql.split())
        if text.startswith("SELECT * FROM tbl_eps_subscriber"):
            self._row = self.store.get(params[0])
        elif text.startswith("UPDATE tbl_eps_subscriber SET sqn="):
            new_sqn, imsi = params
            self.updates.append((imsi, int(new_sqn)))
            self.rowcount = 0
            if imsi in self.store:
                self.store[imsi]["sqn"] = int(new_sqn)
                self.rowcount = 1
        elif "tbl_eps_auth_vector" in text or "tbl_sync_audit" in text:
            self.rowcount = 0
        else:
            self.rowcount = 0

    def fetchone(self):
        return dict(self._row) if self._row else None

    def close(self):
        pass


class FakeConnection:
    def __init__(self, store, updates):
        self.store = store
        self.updates = updates

    def cursor(self, dictionary=False):
        return FakeCursor(self.store, self.updates)

    def commit(self):
        pass

    def close(self):
        pass


def subscriber(sqn=7, with_credentials=True):
    return {
        "imsi": IMSI,
        "k": K.hex().upper() if with_credentials else None,
        "opc": OPC.hex().upper() if with_credentials else None,
        "amf": AMF.hex().upper(),
        "sqn": sqn,
    }


def auts_for(rand: bytes, sqn_ms: int) -> bytes:
    milenage = Milenage(OPC)
    ak_star = milenage.f5_star(K, rand)
    sqn_bytes = sqn_ms.to_bytes(6, "big")
    sqn_xor_ak = bytes(a ^ b for a, b in zip(sqn_bytes, ak_star))
    mac_s = milenage.f1_star(K, rand, sqn_bytes, b"\x00\x00")
    return sqn_xor_ak + mac_s


class HssAuthTest(unittest.TestCase):
    def setUp(self):
        self.store = {IMSI: subscriber()}
        self.updates = []

        def connect(**kwargs):
            return FakeConnection(self.store, self.updates)

        self._original = (hss.get_eps_udr, hss.get_db)
        hss.get_eps_udr = connect
        hss.get_db = connect
        self.client = TestClient(hss.app)

    def tearDown(self):
        hss.get_eps_udr, hss.get_db = self._original

    def generate(self, **overrides):
        body = {
            "imsi": IMSI,
            "authType": "5G_AKA",
            "servingNetworkName": SNN,
        }
        body.update(overrides)
        return self.client.post("/nhss-ueau/v1/generate-av", json=body)

    def test_5g_aka_vector_matches_milenage_and_advances_sqn(self):
        response = self.generate()
        self.assertEqual(response.status_code, 200, response.text)

        vector = response.json()["av5GHeAka"]
        rand = bytes.fromhex(vector["rand"])
        expected = Milenage(OPC).generate_5g_he_av(K, 7, AMF, SNN, rand=rand)

        self.assertEqual(bytes.fromhex(vector["autn"]), expected["autn"])
        self.assertEqual(bytes.fromhex(vector["xresStar"]), expected["xres_star"])
        self.assertEqual(bytes.fromhex(vector["kausf"]), expected["k_ausf"])
        self.assertEqual(self.updates, [(IMSI, 8)])

    def test_auts_resync_rebuilds_from_sqn_ms(self):
        rand = bytes.fromhex("00112233445566778899aabbccddeeff")
        auts = auts_for(rand, 42)

        response = self.generate(resynchronizationInfo={"rand": rand.hex(), "auts": auts.hex()})
        self.assertEqual(response.status_code, 200, response.text)

        vector = response.json()["av5GHeAka"]
        returned_rand = bytes.fromhex(vector["rand"])
        expected = Milenage(OPC).generate_5g_he_av(K, 42, AMF, SNN, rand=returned_rand)
        self.assertEqual(bytes.fromhex(vector["autn"]), expected["autn"])
        self.assertEqual(self.updates, [(IMSI, 43)])

    def test_bad_mac_s_is_rejected_without_touching_sqn(self):
        rand = bytes.fromhex("00112233445566778899aabbccddeeff")
        auts = auts_for(rand, 42)
        auts = auts[:-1] + bytes([auts[-1] ^ 0xFF])

        response = self.generate(resynchronizationInfo={"rand": rand.hex(), "auts": auts.hex()})
        self.assertEqual(response.status_code, 403)
        self.assertIn("AUTS_VERIFICATION_FAILED", response.text)
        self.assertEqual(self.updates, [])

    def test_eap_aka_prime_is_not_implemented(self):
        response = self.generate(authType="EAP_AKA_PRIME")
        self.assertEqual(response.status_code, 501)
        self.assertIn("EAP_AKA_PRIME_NOT_IMPLEMENTED", response.text)
        self.assertEqual(self.updates, [])

    def test_missing_credentials_are_rejected(self):
        self.store[IMSI] = subscriber(with_credentials=False)
        response = self.generate()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.updates, [])

    def test_unknown_subscriber_is_404(self):
        self.store.clear()
        response = self.generate()
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
