"""S6a and MAP authentication vectors derived from the same subscriber row.

Both signalling services are imported with a fake MySQL connector. The test
recomputes every returned vector from the RAND it received, so a fabricated
(or hash-derived) AUTN/XRES/KASME cannot pass. It also proves the SQN advance
is a compare-and-set: a forced conflict must leave the stored SQN untouched.
"""

import struct
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STORE = {}
REFUSE_UPDATES = {"on": False}


class FakeCursor:
    def __init__(self):
        self.rowcount = 0
        self._row = None
        self._rows = []

    def execute(self, sql, params=None):
        self._row = None
        self._rows = []
        text = " ".join(sql.split())
        if text.startswith("UPDATE tbl_subscriber SET sqn="):
            new_sqn, imsi, expected = params
            self.rowcount = 0
            row = STORE.get(imsi)
            if row is not None and not REFUSE_UPDATES["on"] and int(row["sqn"]) == int(expected):
                row["sqn"] = int(new_sqn)
                self.rowcount = 1
        elif text.startswith("SELECT * FROM tbl_subscriber WHERE imsi"):
            self._row = STORE.get(params[0])
        elif text.startswith("SELECT imsi FROM tbl_subscriber"):
            self._rows = [{"imsi": row["imsi"]} for row in STORE.values()]
        elif text.startswith("SELECT imsi, msisdn FROM tbl_subscriber"):
            self._rows = [{"imsi": row["imsi"], "msisdn": row.get("msisdn")} for row in STORE.values()]

    def fetchone(self):
        return dict(self._row) if self._row else None

    def fetchall(self):
        return [dict(row) for row in self._rows]

    def close(self):
        pass


class FakeConnection:
    def cursor(self, dictionary=False):
        return FakeCursor()

    def commit(self):
        pass

    def close(self):
        pass


if "mysql" not in sys.modules:
    mysql = types.ModuleType("mysql")
    connector = types.ModuleType("mysql.connector")
    connector.connect = lambda **kwargs: FakeConnection()
    mysql.connector = connector
    sys.modules["mysql"] = mysql
    sys.modules["mysql.connector"] = connector
else:  # another test module already installed a stub
    sys.modules["mysql.connector"].connect = lambda **kwargs: FakeConnection()

sys.path.insert(0, str(ROOT / "diameter" / "src"))
import diameter_server as s6a  # noqa: E402

sys.path.insert(0, str(ROOT / "map_sccp" / "src"))
import map_sccp_server as map_sccp  # noqa: E402

from corelib.milenage import Milenage  # noqa: E402

IMSI = "001010000000001"
KI = bytes.fromhex("465b5ce8b199b49faa5f0a2ee238a6bc")
OPC = bytes.fromhex("cd63cb71954a9f4e48a5994e37a02baf")
AMF = bytes.fromhex("8000")
VISITED = bytes.fromhex("00f110")  # lab PLMN 001/01 (TS 23.003 §12.1)


def subscriber(sqn=5, with_opc=True, **overrides):
    row = {
        "imsi": IMSI,
        "msisdn": "256700000001",
        "ki": KI.hex().upper(),
        "k": KI.hex().upper(),
        "opc": OPC.hex().upper() if with_opc else None,
        "op": None,
        "amf": AMF.hex().upper(),
        "sqn": sqn,
    }
    row.update(overrides)
    return row


def avp(code, data):
    return {"code": code, "flags": 0xC0, "vendor_id": 10415, "data": data, "raw_len": 0}


def sai_request(count=1, imsi=IMSI, visited=VISITED, resync=None):
    requested = b""
    if count is not None:
        requested += s6a.encode_uint32_avp(s6a.AVP_NUMBER_OF_REQUESTED_VECTORS, count, s6a.config.vendor_id)
    if resync is not None:
        requested += s6a.encode_avp(s6a.AVP_RESYNC_INFO, 0xC0, s6a.config.vendor_id, resync)

    avps = [avp(s6a.AVP_USER_NAME, imsi.encode())]
    if requested:
        avps.append(avp(s6a.AVP_REQUESTED_EUTRAN_AUTH_INFO, requested))
    if visited is not None:
        avps.append(avp(s6a.AVP_VISITED_PLMN_ID, visited))
    return avps


def result_code(raw):
    top = {item["code"]: item for item in s6a.decode_avps(raw[20:])}
    return struct.unpack("!I", top[s6a.AVP_RESULT_CODE]["data"])[0], top


def e_utran_vectors(top):
    auth_info = s6a.decode_avps(top[s6a.AVP_AUTHENTICATION_INFO]["data"])
    vectors = []
    for grouped in auth_info:
        if grouped["code"] != s6a.AVP_EUTRAN_AUTH_INFO:
            continue
        fields = {item["code"]: item["data"] for item in s6a.decode_avps(grouped["data"])}
        vectors.append(fields)
    return vectors


def parse_quintet(sequence: bytes):
    fields = {}
    offset = 0
    while offset + 2 <= len(sequence):
        tag, length = sequence[offset], sequence[offset + 1]
        fields[tag] = sequence[offset + 2:offset + 2 + length]
        offset += 2 + length
    return fields


class SignallingAuthTest(unittest.TestCase):
    def setUp(self):
        STORE.clear()
        REFUSE_UPDATES["on"] = False
        STORE[IMSI] = subscriber()

    # -- S6a ---------------------------------------------------------------

    def test_s6a_vectors_match_milenage_and_advance_sqn(self):
        code, top = result_code(s6a.handle_sai(sai_request(count=2)))
        self.assertEqual(code, 2001)

        vectors = e_utran_vectors(top)
        self.assertEqual(len(vectors), 2)
        self.assertEqual(
            [struct.unpack("!I", fields[s6a.AVP_ITEM_NUMBER])[0] for fields in vectors],
            [0, 1],
        )

        for offset, fields in enumerate(vectors):
            rand = fields[s6a.AVP_RAND]
            expected = Milenage(OPC).generate_eps_av(KI, 5 + offset, AMF, VISITED, rand=rand)
            self.assertEqual(fields[s6a.AVP_AUTN], expected["autn"], "AUTN is not Milenage f1")
            self.assertEqual(fields[s6a.AVP_XRES], expected["xres"], "XRES is not Milenage f2")
            self.assertEqual(fields[s6a.AVP_KASME], expected["k_asme"], "KASME is not the TS 33.401 KDF")

        self.assertEqual(STORE[IMSI]["sqn"], 7)

    def test_s6a_default_serving_network_is_the_lab_plmn(self):
        code, top = result_code(s6a.handle_sai(sai_request(count=1, visited=None)))
        self.assertEqual(code, 2001)
        fields = e_utran_vectors(top)[0]
        expected = Milenage(OPC).generate_eps_av(
            KI, 5, AMF, bytes.fromhex("00f110"), rand=fields[s6a.AVP_RAND]
        )
        self.assertEqual(fields[s6a.AVP_KASME], expected["k_asme"])

    def test_s6a_requested_vector_count_is_capped_at_five(self):
        code, top = result_code(s6a.handle_sai(sai_request(count=99)))
        self.assertEqual(code, 2001)
        self.assertEqual(len(e_utran_vectors(top)), 5)
        self.assertEqual(STORE[IMSI]["sqn"], 10)

    def test_s6a_unknown_subscriber_is_5003(self):
        code, _ = result_code(s6a.handle_sai(sai_request(imsi="001010000000099")))
        self.assertEqual(code, 5003)

    def test_s6a_without_opc_or_op_is_rejected(self):
        STORE[IMSI] = subscriber(with_opc=False)
        code, _ = result_code(s6a.handle_sai(sai_request()))
        self.assertEqual(code, 5001)
        self.assertEqual(STORE[IMSI]["sqn"], 5)

    def test_s6a_resync_without_stored_rand_is_refused(self):
        code, top = result_code(s6a.handle_sai(sai_request(resync=b"\x00" * 14)))
        self.assertEqual(code, 5012)
        self.assertIn(b"AUTS", top[s6a.AVP_ERROR_MESSAGE]["data"])
        self.assertEqual(STORE[IMSI]["sqn"], 5)

    def test_s6a_sqn_conflict_does_not_consume_a_vector(self):
        REFUSE_UPDATES["on"] = True
        code, _ = result_code(s6a.handle_sai(sai_request()))
        self.assertEqual(code, 5012)
        self.assertEqual(STORE[IMSI]["sqn"], 5)

    # -- MAP ---------------------------------------------------------------

    def test_map_quintet_matches_milenage_and_advances_sqn(self):
        response = map_sccp.handle_sai(map_sccp.encode_imsi(IMSI), invoke_id=33)

        # The returned TCAP/ASN.1 lengths must describe the bytes that follow.
        self.assertEqual(response[0], 0x62)
        self.assertEqual(len(response), 2 + response[1])

        start = response.find(b"\x30\x52")
        self.assertGreater(start, 0, "AuthenticationQuintuplet SEQUENCE not found")
        fields = parse_quintet(response[start + 2:start + 2 + 0x52])

        expected = Milenage(OPC).generate_eps_av(KI, 5, AMF, rand=fields[0x80])
        self.assertEqual(fields[0x80], expected["rand"])
        self.assertEqual(fields[0x81], expected["res"], "XRES is not Milenage f2")
        self.assertEqual(fields[0x82], expected["ck"], "CK is not Milenage f3")
        self.assertEqual(fields[0x83], expected["ik"], "IK is not Milenage f4")
        self.assertEqual(fields[0x84], expected["autn"], "AUTN is not Milenage f1")
        self.assertEqual(STORE[IMSI]["sqn"], 6)

    def test_map_unknown_subscriber_returns_an_error_component(self):
        response = map_sccp.handle_sai(map_sccp.encode_imsi("001010000000099"), invoke_id=33)
        self.assertIn(bytes([0x6A]), response)
        self.assertEqual(STORE[IMSI]["sqn"], 5)

    def test_map_sqn_conflict_returns_system_failure(self):
        REFUSE_UPDATES["on"] = True
        response = map_sccp.handle_sai(map_sccp.encode_imsi(IMSI), invoke_id=33)
        error_code = bytes([0x02, 0x01, map_sccp.MAP_ERR_SYSTEM_FAILURE])
        self.assertIn(error_code, response)
        self.assertEqual(STORE[IMSI]["sqn"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
