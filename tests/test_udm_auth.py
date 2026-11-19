"""Nudm_UEAU generate-auth-data against a stubbed database.

No MySQL is needed: `get_db`/`get_redis` are replaced with in-memory fakes.
The assertions compare the HTTP response with an independent Milenage
computation for the RAND the UDM actually returned, so a mismatched
RAND/AUTN/XRES*/KAUSF pair fails the test.
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if "mysql" not in sys.modules:  # the UDM imports mysql.connector at module load
    mysql = types.ModuleType("mysql")
    connector = types.ModuleType("mysql.connector")
    connector.connect = lambda **kwargs: None
    mysql.connector = connector
    sys.modules["mysql"] = mysql
    sys.modules["mysql.connector"] = connector

try:  # FastAPI only needs the module present to register Form/File routes
    import python_multipart  # noqa: F401
except ImportError:
    _multipart = types.ModuleType("python_multipart")
    _multipart.__version__ = "0.0.20"
    sys.modules["python_multipart"] = _multipart
    sys.modules["multipart"] = _multipart

sys.path.insert(0, str(ROOT / "udm" / "src"))
from fastapi.testclient import TestClient  # noqa: E402

import udm_server as udm  # noqa: E402
from corelib.milenage import Milenage  # noqa: E402

SNN = "5G:mnc001.mcc001.3gppnetwork.org"
IMSI = "001010000000001"
K = bytes.fromhex("465b5ce8b199b49faa5f0a2ee238a6bc")
OPC = bytes.fromhex("cd63cb71954a9f4e48a5994e37a02baf")
AMF = bytes.fromhex("b9b9")


class _Cursor:
    def __init__(self, state):
        self.state = state

    def execute(self, sql, params=None):
        self.state["executed"].append((" ".join(sql.split()), params))

    def fetchone(self):
        return dict(self.state["row"])

    def close(self):
        pass


class _Conn:
    def __init__(self, state):
        self.state = state

    def cursor(self, dictionary=False):
        return _Cursor(self.state)

    def commit(self):
        pass

    def close(self):
        pass


class _Redis:
    def delete(self, *keys):
        return 1


class TestGenerateAuthData(unittest.TestCase):
    def setUp(self):
        self.state = {
            "row": {
                "imsi": IMSI,
                "k": K.hex().upper(),
                "ki": None,
                "opc": OPC.hex().upper(),
                "sqn": 1,
                "amf": AMF.hex().upper(),
            },
            "executed": [],
        }
        udm.get_db = lambda: _Conn(self.state)
        udm.get_redis = lambda: _Redis()
        self.client = TestClient(udm.app)
        self.m = Milenage(OPC)

    def _post(self, payload):
        return self.client.post(
            f"/nudm-ueau/v1/imsi-{IMSI}/security-information/generate-auth-data",
            json=payload,
        )

    def _expected(self, rand, sqn):
        return self.m.generate_5g_he_av(K, sqn, AMF, SNN, rand=rand)

    def test_vector_matches_returned_rand(self):
        resp = self._post({"serving_network_name": SNN})
        self.assertEqual(resp.status_code, 200, resp.text)
        av = resp.json()["auth_vectors"][0]

        rand = bytes.fromhex(av["rand"])
        expected = self._expected(rand, sqn=1)
        self.assertEqual(av["autn"], expected["autn"].hex().upper())
        self.assertEqual(av["xres_star"], expected["xres_star"].hex().upper())
        self.assertEqual(av["kausf"], expected["k_ausf"].hex().upper())

        updates = [e for e in self.state["executed"] if e[0].startswith("UPDATE")]
        self.assertEqual(updates[-1][1], (2, IMSI))

    def test_auts_resynchronises_sqn(self):
        sqn_ms = 0x2A
        rand = bytes.fromhex("23553cbe9637a89d218ae64dae47bf35")
        sqn_bytes = sqn_ms.to_bytes(6, "big")
        auts = (
            bytes(a ^ b for a, b in zip(sqn_bytes, self.m.f5_star(K, rand)))
            + self.m.f1_star(K, rand, sqn_bytes, b"\x00\x00")
        )

        resp = self._post({
            "serving_network_name": SNN,
            "resynchronization_info": {"rand": rand.hex(), "auts": auts.hex()},
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        av = resp.json()["auth_vectors"][0]

        used_rand = bytes.fromhex(av["rand"])
        recovered = int.from_bytes(
            bytes(a ^ b for a, b in zip(bytes.fromhex(av["autn"])[:6],
                                        self.m.f5(K, used_rand))),
            "big",
        )
        self.assertEqual(recovered, sqn_ms)

        updates = [e for e in self.state["executed"] if e[0].startswith("UPDATE")]
        self.assertEqual(updates[-1][1], (sqn_ms + 1, IMSI))

    def test_bad_auts_is_rejected(self):
        rand = bytes.fromhex("23553cbe9637a89d218ae64dae47bf35")
        auts = bytearray(b"\x00" * 14)
        auts[13] ^= 0xFF
        resp = self._post({
            "serving_network_name": SNN,
            "resynchronization_info": {"rand": rand.hex(), "auts": bytes(auts).hex()},
        })
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertFalse(
            [e for e in self.state["executed"] if e[0].startswith("UPDATE")],
            "a failed AUTS must not advance SQN",
        )


if __name__ == "__main__":
    unittest.main()
