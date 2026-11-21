"""The SLs link between the MME and the E-SMLC.

SLs is SCTP in a real network. The transport has two implementations, as
DECISIONS.md D5 requires:

  * ``carrier="sctp"`` - one-to-one SCTP, message boundaries preserved by the
    association. Written against ``socket.IPPROTO_SCTP`` and **unverified**:
    no host in this repository has AF_SCTP, so it has never run.
  * ``carrier="tcp"`` - a four-octet big-endian length followed by the LCS-AP
    PDU. This is the lab carrier for the Windows development host, not a
    standards claim.

The payload is LCS-AP either way; only the framing differs. Every test that
uses the carrier says so.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from typing import Optional, Set

logger = logging.getLogger("sls")

DEFAULT_SLS_PORT = 9082
MAX_FRAME = 1 << 20
HEADER = struct.Struct("!I")

CARRIER_TCP = "tcp"
CARRIER_SCTP = "sctp"


class SlsError(Exception):
    pass


def sctp_available() -> bool:
    """True only when this host can actually open an SCTP socket."""
    proto = getattr(socket, "IPPROTO_SCTP", None)
    if proto is None:
        return False
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM, proto)
    except OSError:
        return False
    probe.close()
    return True


def _socket_kind(carrier: str):
    if carrier == CARRIER_TCP:
        return socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP
    if carrier == CARRIER_SCTP:
        proto = getattr(socket, "IPPROTO_SCTP", None)
        if proto is None:
            raise SlsError("this Python build has no SCTP support")
        return socket.AF_INET, socket.SOCK_STREAM, proto
    raise SlsError(f"unknown SLs carrier {carrier!r}")


def frame(payload: bytes) -> bytes:
    if len(payload) > MAX_FRAME:
        raise SlsError(f"frame of {len(payload)} octets exceeds {MAX_FRAME}")
    return HEADER.pack(len(payload)) + payload


def read_frame(sock: socket.socket, timeout: Optional[float] = None) -> bytes:
    """Read one length-framed message. Returns b'' when the peer closed."""
    if timeout is not None:
        sock.settimeout(timeout)
    header = _read_exactly(sock, HEADER.size)
    if not header:
        return b""
    (length,) = HEADER.unpack(header)
    if length == 0 or length > MAX_FRAME:
        raise SlsError(f"invalid frame length {length}")
    return _read_exactly(sock, length)


def _read_exactly(sock: socket.socket, count: int) -> bytes:
    chunks = b""
    while len(chunks) < count:
        try:
            chunk = sock.recv(count - len(chunks))
        except socket.timeout:
            raise SlsError("SLs peer did not answer in time")
        if not chunk:
            if chunks:
                raise SlsError("SLs peer closed mid-frame")
            return b""
        chunks += chunk
    return chunks


def read_message(sock: socket.socket, timeout: Optional[float] = None) -> bytes:
    """Read one SCTP message. SCTP preserves boundaries, so there is no
    length prefix; MAX_FRAME is far above any LCS-AP PDU, and a message that
    large would be truncated by the kernel and rejected downstream."""
    if timeout is not None:
        sock.settimeout(timeout)
    try:
        return sock.recv(MAX_FRAME)
    except socket.timeout:
        raise SlsError("SLs peer did not answer in time")


class SlsConnection:
    """One SCTP association, or the TCP carrier that stands in for it.

    A transaction is sequential: one Location-Request at a time per
    connection, matched by Correlation-ID. Concurrent sessions get their own
    connection, which is also what an SCTP multi-stream peer would expect.
    """

    def __init__(self, sock: socket.socket, carrier: str = CARRIER_TCP):
        self.sock = sock
        self.carrier = carrier
        self._lock = threading.Lock()

    @classmethod
    def connect(cls, host: str, port: int = DEFAULT_SLS_PORT,
                timeout: float = 5.0, carrier: str = CARRIER_TCP) -> "SlsConnection":
        if carrier == CARRIER_TCP:
            sock = socket.create_connection((host, port), timeout=timeout)
        else:
            family, kind, proto = _socket_kind(carrier)
            sock = socket.socket(family, kind, proto)
            sock.settimeout(timeout)
            sock.connect((host, port))
        sock.settimeout(timeout)
        return cls(sock, carrier)

    def send(self, pdu: bytes) -> None:
        with self._lock:
            if self.carrier == CARRIER_SCTP:
                sent = self.sock.send(pdu)
                if sent != len(pdu):
                    raise SlsError(
                        f"SCTP delivered {sent} of {len(pdu)} octets in one message"
                    )
            else:
                self.sock.sendall(frame(pdu))

    def receive(self, timeout: Optional[float] = None) -> bytes:
        if self.carrier == CARRIER_SCTP:
            return read_message(self.sock, timeout)
        return read_frame(self.sock, timeout)

    def exchange(self, pdu: bytes, timeout: float) -> bytes:
        self.send(pdu)
        return self.receive(timeout)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self) -> "SlsConnection":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class SlsServer:
    """Accept SLs peers and answer one PDU at a time.

    The handler is called with (pdu, connection) so it can continue an LPP
    relay dialogue before it answers. Several MME peers are served at once;
    the handler is responsible for keying any session state (D7).
    """

    def __init__(self, host: str, port: int, handler, name: str = "esmlc",
                 carrier: str = CARRIER_TCP):
        self.host = host
        self.port = port
        self.handler = handler
        self.name = name
        self.carrier = carrier
        self._listener: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._active_lock = threading.Lock()
        self._active: Set[socket.socket] = set()
        self.connections = 0
        self.messages_in = 0
        self.messages_out = 0
        self.errors = 0

    def start(self) -> None:
        family, kind, proto = _socket_kind(self.carrier)
        listener = socket.socket(family, kind, proto)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(8)
        listener.settimeout(0.5)
        self.port = listener.getsockname()[1]
        self._listener = listener
        self._thread = threading.Thread(target=self._accept_loop, daemon=True,
                                        name=f"{self.name}-sls")
        self._thread.start()
        logger.info("%s listening on %s:%s (%s)", self.name, self.host, self.port,
                    "SCTP" if self.carrier == CARRIER_SCTP else "TCP carrier")

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        with self._active_lock:
            active = list(self._active)
        for sock in active:
            try:
                sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                sock, peer = self._listener.accept()
            except (socket.timeout, OSError):
                continue
            sock.settimeout(10.0)
            with self._active_lock:
                self._active.add(sock)
            self.connections += 1
            threading.Thread(target=self._serve, args=(sock, peer),
                             daemon=True).start()

    def _serve(self, sock: socket.socket, peer) -> None:
        connection = SlsConnection(sock, self.carrier)
        try:
            while not self._stop.is_set():
                pdu = connection.receive()
                if not pdu:
                    break
                self.messages_in += 1
                try:
                    answer = self.handler(pdu, connection)
                except Exception:
                    # One bad dialogue must not take the listener down.
                    self.errors += 1
                    logger.exception("%s: handler failed for %s", self.name, peer)
                    continue
                if answer is not None:
                    connection.send(answer)
                    self.messages_out += 1
        except (SlsError, OSError):
            pass
        finally:
            with self._active_lock:
                self._active.discard(sock)
            connection.close()

    def stats(self) -> dict:
        return {
            "carrier": self.carrier,
            "connections": self.connections,
            "messages_in": self.messages_in,
            "messages_out": self.messages_out,
            "handler_errors": self.errors,
        }


def wait_for_port(host: str, port: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.02)
    return False
