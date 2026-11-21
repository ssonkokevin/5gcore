"""The SLs link between the MME and the E-SMLC.

SLs is SCTP in a real network. The carrier has two implementations, as
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

from corelib import wire
from corelib.wire import (  # noqa: F401 - re-exported carrier interface
    CARRIER_SCTP,
    CARRIER_TCP,
    HEADER,
    MAX_FRAME,
    frame,
    read_frame,
    read_message,
    sctp_available,
    wait_for_port,
)

DEFAULT_SLS_PORT = 9082

SlsError = wire.WireError
SlsConnection = wire.Connection
SlsServer = wire.Server
