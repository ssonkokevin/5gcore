"""corelib.http header pass-through, exercised over a real loopback socket.

The UDR client's conditional writes depend on reading ETag from both 200 and
412 responses; returning headers only on success would silently break the CAS.
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from corelib.http import TransportError, request_json, request_json_with_headers  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload, etag=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, {"sequenceNumber": "000000000001"}, etag='"abc"')

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.headers.get("If-Match") == '"abc"':
            self._send(200, {"sequenceNumber": "000000000002"}, etag='"def"')
        else:
            self._send(412, {"cause": "PRECONDITION_FAILED"})

    def log_message(self, *args):
        pass


class TestHeaderPassThrough(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_success_headers_are_lower_cased(self):
        status, headers, body = request_json_with_headers("GET", self.base + "/x")
        self.assertEqual(status, 200)
        self.assertEqual(headers["etag"], '"abc"')
        self.assertEqual(body["sequenceNumber"], "000000000001")

    def test_error_status_returns_headers_and_body_not_an_exception(self):
        status, headers, body = request_json_with_headers(
            "PATCH", self.base + "/x", payload=[],
            headers={"Content-Type": "application/json-patch+json", "If-Match": '"stale"'},
        )
        self.assertEqual(status, 412)
        self.assertEqual(body["cause"], "PRECONDITION_FAILED")
        self.assertNotIn("etag", headers)

    def test_plain_helper_keeps_its_two_value_contract(self):
        status, body = request_json("GET", self.base + "/x")
        self.assertEqual(status, 200)
        self.assertEqual(body["sequenceNumber"], "000000000001")

    def test_refused_connection_is_a_transport_error(self):
        with self.assertRaises(TransportError):
            request_json_with_headers("GET", "http://127.0.0.1:1/nope", timeout=1)


if __name__ == "__main__":
    unittest.main()
