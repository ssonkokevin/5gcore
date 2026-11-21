"""SLs carrier and listener.

    python tests/test_sls.py

The TCP run is the length-framed lab carrier from DECISIONS.md D5, not an
SCTP claim. The SCTP cases run only on a host that can open an SCTP socket;
they are skipped here and have never been executed.
"""

import socket
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from corelib import sls  # noqa: E402


def wait_until(predicate, seconds=2.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class Framing(unittest.TestCase):
    def test_frame_round_trip(self):
        payload = b"\x01\x02\x03"
        framed = sls.frame(payload)
        self.assertEqual(len(framed), 4 + len(payload))
        self.assertEqual(sls.HEADER.unpack(framed[:4])[0], len(payload))
        self.assertEqual(framed[4:], payload)

    def test_oversize_frame_is_rejected(self):
        with self.assertRaises(sls.SlsError):
            sls.frame(b"\x00" * (sls.MAX_FRAME + 1))

    def test_zero_length_frame_is_rejected(self):
        left, right = socket.socketpair()
        try:
            right.sendall(sls.HEADER.pack(0))
            with self.assertRaises(sls.SlsError):
                sls.read_frame(left, timeout=1.0)
        finally:
            left.close()
            right.close()

    def test_truncated_frame_is_rejected(self):
        left, right = socket.socketpair()
        try:
            right.sendall(sls.HEADER.pack(10) + b"\x00\x01")
            right.close()
            with self.assertRaises(sls.SlsError):
                sls.read_frame(left, timeout=1.0)
        finally:
            left.close()


class ServerBase:
    carrier = sls.CARRIER_TCP

    def setUp(self):
        self.received = []
        self.server = sls.SlsServer("127.0.0.1", 0, self._answer,
                                    name="test-sls", carrier=self.carrier)
        self.server.start()

    def tearDown(self):
        self.server.stop()

    def _answer(self, pdu, connection):
        self.received.append(pdu)
        return b"answer:" + pdu

    def connect(self, **kwargs):
        kwargs.setdefault("timeout", 2.0)
        return sls.SlsConnection.connect("127.0.0.1", self.server.port,
                                         carrier=self.carrier, **kwargs)

    def test_round_trip(self):
        with self.connect() as connection:
            self.assertEqual(connection.exchange(b"hello", 2.0), b"answer:hello")

    def test_server_binds_an_ephemeral_port(self):
        self.assertGreater(self.server.port, 0)

    def test_receive_returns_empty_when_the_peer_closes(self):
        def close_after_reading(pdu, connection):
            connection.close()
            return None

        self.server.handler = close_after_reading
        connection = self.connect()
        try:
            connection.send(b"bye")
            self.assertEqual(connection.receive(2.0), b"")
        finally:
            connection.close()

    def test_stats_name_the_carrier(self):
        with self.connect() as connection:
            connection.exchange(b"one", 2.0)
            connection.exchange(b"two", 2.0)
        self.assertTrue(wait_until(lambda: self.server.messages_out >= 2))
        stats = self.server.stats()
        self.assertEqual(stats["carrier"], self.carrier)
        self.assertGreaterEqual(stats["connections"], 1)
        self.assertEqual(stats["messages_in"], 2)
        self.assertEqual(stats["messages_out"], 2)
        self.assertEqual(stats["handler_errors"], 0)

    def test_a_failing_handler_does_not_kill_the_listener(self):
        def failing(pdu, connection):
            raise RuntimeError("boom")

        self.server.handler = failing
        with self.connect() as connection:
            connection.send(b"bad")
            self.assertTrue(wait_until(lambda: self.server.errors >= 1))
            self.server.handler = self._answer
            self.assertEqual(connection.exchange(b"good", 2.0), b"answer:good")


class TcpCarrier(ServerBase, unittest.TestCase):
    carrier = sls.CARRIER_TCP


@unittest.skipUnless(sls.sctp_available(), "AF_SCTP is not available on this host")
class SctpCarrier(ServerBase, unittest.TestCase):
    carrier = sls.CARRIER_SCTP


class CarrierSelection(unittest.TestCase):
    def test_unknown_carrier_is_rejected(self):
        with self.assertRaises(sls.SlsError):
            sls.SlsConnection.connect("127.0.0.1", 9, timeout=0.1, carrier="udp")

    def test_tcp_is_the_default(self):
        server = sls.SlsServer("127.0.0.1", 0, lambda pdu, conn: None)
        self.assertEqual(server.carrier, sls.CARRIER_TCP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
