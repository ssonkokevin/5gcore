"""UDR Nudr_DataRepository authentication subscription against a fake MariaDB.

No MySQL server is needed. The fake cursor understands exactly the statements
the UDR issues and models row locking, so a stale If-Match or a concurrent
writer produces the same 412 the real transactional path produces.
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

sys.path.insert(0, str(ROOT / "udr" / "src"))
from fastapi.testclient import TestClient  # noqa: E402

import udr_server as udr  # noqa: E402

IMSI = "001010000000001"
UE_ID = f"imsi-{IMSI}"
K = "465B5CE8B199B49FAA5F0A2EE238A6BC"
OPC = "CD63CB71954A9F4E48A5994E37A02BAF"
OP = "CDC202D5123E20F62B6D676AC72CB318"
PATH = f"/nudr-dr/v2/subscription-data/{UE_ID}/authentication-data/authentication-subscription"


class _Cursor:
    def __init__(self, state):
        self.state = state
        self.rowcount = 0
        self._row = None

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        if s.startswith("SELECT 1"):
            self._row = (1,)
            return
        if s.startswith("SELECT imsi, k, ki, op, opc, sqn, amf"):
            row = self.state["row"]
            self._row = dict(row) if row else None
            return
        if s.startswith("UPDATE tbl_subscriber SET sqn=") and "AND sqn=" in s:
            new_sqn, imsi, old_sqn = params
            row = self.state["row"]
            if row and row["imsi"] == imsi and int(row["sqn"]) == int(old_sqn):
                row["sqn"] = new_sqn
                self.rowcount = 1
            else:
                self.rowcount = 0
            return
        if s.startswith("UPDATE tbl_subscriber SET k="):
            k, ki, op, opc, sqn, amf, imsi = params
            self.state["row"].update(
                {"k": k, "ki": ki, "op": op, "opc": opc, "sqn": sqn, "amf": amf, "imsi": imsi}
            )
            self.rowcount = 1
            return
        if s.startswith("INSERT INTO tbl_subscriber"):
            imsi, k, ki, op, opc, sqn, amf = params
            self.state["row"] = {
                "imsi": imsi, "k": k, "ki": ki, "op": op, "opc": opc, "sqn": sqn, "amf": amf,
            }
            self.rowcount = 1
            return
        raise AssertionError(f"unexpected SQL: {s}")

    def fetchone(self):
        return self._row

    def close(self):
        pass


class _Conn:
    def __init__(self, state):
        self.state = state

    def cursor(self, dictionary=False):
        return _Cursor(self.state)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class TestAuthenticationSubscription(unittest.TestCase):
    def setUp(self):
        self.state = {
            "row": {
                "imsi": IMSI,
                "k": K,
                "ki": None,
                "op": OP,
                "opc": OPC,
                "sqn": 1,
                "amf": "8000",
            }
        }
        udr.get_db = lambda: _Conn(self.state)
        self.client = TestClient(udr.app)

    def _get(self):
        return self.client.get(PATH)

    def test_get_returns_spec_fields_and_a_strong_etag(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["sequenceNumber"], "000000000001")
        self.assertEqual(body["permanentKey"]["permanentKeyValue"], K)
        self.assertEqual(body["opc"]["opcValue"], OPC)
        self.assertEqual(body["milenage"]["op"], OP)
        etag = resp.headers.get("etag")
        self.assertTrue(etag and etag.startswith('"') and etag.endswith('"'), etag)

    def test_unknown_subscriber_is_404(self):
        self.state["row"] = None
        resp = self._get()
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertEqual(resp.json()["detail"]["cause"], "USER_NOT_FOUND")

    def test_bare_imsi_is_accepted_as_ue_id(self):
        bare = PATH.replace(UE_ID, IMSI)
        resp = self.client.get(bare)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_patch_replaces_sequence_number_with_matching_etag(self):
        etag = self._get().headers["etag"]
        resp = self.client.patch(
            PATH,
            json=[{"op": "replace", "path": "/sequenceNumber", "value": "000000000002"}],
            headers={"If-Match": etag, "Content-Type": "application/json-patch+json"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["sequenceNumber"], "000000000002")
        self.assertEqual(self.state["row"]["sqn"], 2)
        self.assertNotEqual(resp.headers["etag"], etag, "the ETag must change with the body")

    def test_patch_without_if_match_is_428(self):
        resp = self.client.patch(
            PATH,
            json=[{"op": "replace", "path": "/sequenceNumber", "value": "000000000002"}],
        )
        self.assertEqual(resp.status_code, 428, resp.text)
        self.assertEqual(self.state["row"]["sqn"], 1)

    def test_patch_with_stale_etag_is_412_and_changes_nothing(self):
        stale = self._get().headers["etag"]
        self.state["row"]["sqn"] = 5  # another NF advanced SQN meanwhile
        resp = self.client.patch(
            PATH,
            json=[{"op": "replace", "path": "/sequenceNumber", "value": "000000000006"}],
            headers={"If-Match": stale},
        )
        self.assertEqual(resp.status_code, 412, resp.text)
        self.assertEqual(self.state["row"]["sqn"], 5)

    def test_patch_rejects_paths_outside_sequence_number(self):
        etag = self._get().headers["etag"]
        resp = self.client.patch(
            PATH,
            json=[{"op": "replace", "path": "/permanentKey/permanentKeyValue", "value": K}],
            headers={"If-Match": etag},
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["detail"]["cause"], "UNSUPPORTED_PATCH")
        self.assertEqual(self.state["row"]["k"], K)

    def test_put_creates_then_requires_if_match_to_replace(self):
        body = {
            "authenticationMethod": "5G_AKA",
            "sequenceNumber": "000000000000",
            "authenticationManagementField": "8000",
            "permanentKey": {"permanentKeyValue": K},
            "opc": {"opcValue": OPC},
        }
        self.state["row"] = None
        created = self.client.put(PATH, json=body)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(self.state["row"]["imsi"], IMSI)

        replacement = dict(body, sequenceNumber="00000000000A")
        refused = self.client.put(PATH, json=replacement)
        self.assertEqual(refused.status_code, 428, refused.text)

        accepted = self.client.put(
            PATH, json=replacement, headers={"If-Match": created.headers["etag"]}
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.state["row"]["sqn"], 0xA)

    def test_put_with_wrong_etag_is_412(self):
        body = {
            "authenticationMethod": "5G_AKA",
            "sequenceNumber": "000000000009",
            "authenticationManagementField": "8000",
            "opc": {"opcValue": OPC},
        }
        resp = self.client.put(PATH, json=body, headers={"If-Match": '"nope"'})
        self.assertEqual(resp.status_code, 412, resp.text)
        self.assertEqual(self.state["row"]["sqn"], 1)

    def test_sequence_number_must_be_48_bits(self):
        etag = self._get().headers["etag"]
        resp = self.client.patch(
            PATH,
            json=[{"op": "replace", "path": "/sequenceNumber", "value": "1000000000000"}],
            headers={"If-Match": etag},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_health_reports_storage(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["service"], "udr")
        self.assertEqual(body["storage"], "ok")


if __name__ == "__main__":
    unittest.main()
