"""Nudm_UEAU generate-auth-data with the UDR as the credential and SQN source.

No MySQL and no UDR process: `udm.udr` is replaced with an in-memory fake that
implements the Nudr authentication-subscription resource, including the 412
that a concurrent writer causes. The assertions compare the HTTP response with
an independent Milenage computation for the RAND the UDM actually returned, so
a mismatched RAND/AUTN/XRES*/KAUSF tuple fails the test.
"""

import copy
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
from corelib.http import TransportError  # noqa: E402
from corelib.milenage import Milenage  # noqa: E402

SNN = "5G:mnc001.mcc001.3gppnetwork.org"
IMSI = "001010000000001"
K = bytes.fromhex("465b5ce8b199b49faa5f0a2ee238a6bc")
OPC = bytes.fromhex("cd63cb71954a9f4e48a5994e37a02baf")
AMF = bytes.fromhex("b9b9")


class FakeUdr:
    """In-memory Nudr authentication subscription with ETag conditional writes."""

    def __init__(self, sqn=1, conflicts=0, missing=False):
        self.subscription = {
            "authenticationMethod": "5G_AKA",
            "sequenceNumber": f"{sqn:012X}",
            "authenticationManagementField": AMF.hex().upper(),
            "permanentKey": {"permanentKeyValue": K.hex().upper()},
            "opc": {"opcValue": OPC.hex().upper(), "opcKformat": "OPC"},
        }
        self.etag = '"v1"'
        self.conflicts = conflicts
        self.missing = missing
        self.gets = 0
        self.patches = []
        self.unreachable = False

    def get_authentication_subscription(self, ue_id):
        if self.unreachable:
            raise TransportError("http://udr", ConnectionRefusedError("down"))
        assert ue_id == f"imsi-{IMSI}", ue_id
        self.gets += 1
        if self.missing:
            return None
        return self.etag, copy.deepcopy(self.subscription)

    def patch_sequence_number(self, ue_id, sequence_hex, if_match):
        self.patches.append((ue_id, sequence_hex, if_match))
        if self.conflicts:
            # Another consumer advanced SQN between our GET and our PATCH.
            self.conflicts -= 1
            current = int(self.subscription["sequenceNumber"], 16)
            self.subscription["sequenceNumber"] = f"{current + 1:012X}"
            return 412, ""
        if if_match != self.etag:
            return 412, ""
        self.subscription["sequenceNumber"] = sequence_hex
        self.etag = f'"v{len(self.patches) + 1}"'
        return 200, self.etag


class _Redis:
    def delete(self, *keys):
        return 1


class TestGenerateAuthData(unittest.TestCase):
    def setUp(self):
        self.udr = FakeUdr()
        udm.udr = self.udr
        udm.get_redis = lambda: _Redis()

        def _no_db():
            raise AssertionError("the authentication path must go through the UDR, not SQL")

        udm.get_db = _no_db
        self.client = TestClient(udm.app)
        self.m = Milenage(OPC)

    def _post(self, payload):
        return self.client.post(
            f"/nudm-ueau/v1/imsi-{IMSI}/security-information/generate-auth-data",
            json=payload,
        )

    def _expected(self, rand, sqn):
        return self.m.generate_5g_he_av(K, sqn, AMF, SNN, rand=rand)

    def test_vector_matches_returned_rand_and_advances_sqn(self):
        resp = self._post({"serving_network_name": SNN})
        self.assertEqual(resp.status_code, 200, resp.text)
        av = resp.json()["auth_vectors"][0]

        rand = bytes.fromhex(av["rand"])
        expected = self._expected(rand, sqn=1)
        self.assertEqual(av["autn"], expected["autn"].hex().upper())
        self.assertEqual(av["xres_star"], expected["xres_star"].hex().upper())
        self.assertEqual(av["kausf"], expected["k_ausf"].hex().upper())

        self.assertEqual(
            self.udr.patches,
            [(f"imsi-{IMSI}", "000000000002", '"v1"')],
            "the SQN advance must be one conditional PATCH of the new value",
        )

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
        self.assertEqual(self.udr.patches[-1][1], f"{sqn_ms + 1:012X}")

    def test_bad_auts_is_rejected_without_advancing_sqn(self):
        rand = bytes.fromhex("23553cbe9637a89d218ae64dae47bf35")
        auts = bytearray(b"\x00" * 14)
        auts[13] ^= 0xFF
        resp = self._post({
            "serving_network_name": SNN,
            "resynchronization_info": {"rand": rand.hex(), "auts": bytes(auts).hex()},
        })
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(self.udr.patches, [], "a failed AUTS must not advance SQN")

    def test_concurrent_sqn_advance_is_retried_not_returned(self):
        self.udr.conflicts = 1
        resp = self._post({"serving_network_name": SNN})
        self.assertEqual(resp.status_code, 200, resp.text)
        av = resp.json()["auth_vectors"][0]

        self.assertEqual(self.udr.gets, 2, "the retry must re-read the subscription")
        self.assertEqual(len(self.udr.patches), 2)
        # The second attempt consumed the SQN the other writer left behind.
        self.assertEqual(self.udr.patches[-1][1], "000000000003")
        expected = self._expected(bytes.fromhex(av["rand"]), sqn=2)
        self.assertEqual(av["autn"], expected["autn"].hex().upper())
        self.assertEqual(av["xres_star"], expected["xres_star"].hex().upper())

    def test_two_conflicts_surface_as_409(self):
        self.udr.conflicts = 2
        resp = self._post({"serving_network_name": SNN})
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["cause"], "SQN_CONTENTION")

    def test_unknown_subscriber_is_404(self):
        self.udr.missing = True
        resp = self._post({"serving_network_name": SNN})
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertEqual(self.udr.patches, [])

    def test_unreachable_udr_is_503_not_a_local_fallback(self):
        self.udr.unreachable = True
        resp = self._post({"serving_network_name": SNN})
        self.assertEqual(resp.status_code, 503, resp.text)
        self.assertEqual(resp.json()["detail"]["cause"], "UDR_UNAVAILABLE")


class TestHssVectorsGoThroughTheUdr(unittest.TestCase):
    def setUp(self):
        self.udr = FakeUdr(sqn=7)
        self.udr.subscription["ki"] = K.hex().upper()
        udm.udr = self.udr
        udm.get_redis = lambda: _Redis()
        udm.get_db = lambda: (_ for _ in ()).throw(AssertionError("must not touch SQL"))
        self.client = TestClient(udm.app)

    def test_num_vectors_advances_once_by_count(self):
        resp = self.client.post(
            f"/nudm-ueau/v1/{IMSI}/hss-security-information/eps-aka/generate-av",
            json={"hss_auth_type": "eps-aka", "num_vectors": 2},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        vectors = resp.json()["auth_vectors"]
        self.assertEqual(len(vectors), 2)
        self.assertNotEqual(vectors[0]["rand"], vectors[1]["rand"], "each vector needs its own RAND")
        self.assertEqual(self.udr.patches, [(f"imsi-{IMSI}", "000000000009", '"v1"')])

    def test_eap_aka_prime_is_501_without_sqn_movement(self):
        resp = self.client.post(
            f"/nudm-ueau/v1/{IMSI}/hss-security-information/eap-aka-prime/generate-av",
            json={"hss_auth_type": "eap-aka-prime", "num_vectors": 1},
        )
        self.assertEqual(resp.status_code, 501, resp.text)
        self.assertEqual(self.udr.patches, [])


if __name__ == "__main__":
    unittest.main()
