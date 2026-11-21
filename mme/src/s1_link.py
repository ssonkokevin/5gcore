"""The MME side of S1-MME: the association, the UE bindings and the LPPa relay.

S1-MME is SCTP in a real network. This module uses the D5 carrier in
``corelib/wire.py``, so the lab talks length-framed TCP and an SCTP host can
use the same code unverified. What is implemented is the subset a location
session needs:

    S1 setup                     eNB -> MME, answered with S1SetupResponse
    InitialUEMessage             the NAS Attach Request binds an IMSI to a cell
    Downlink / Uplink UE-associated LPPa transport       the relay
    UEContextReleaseCommand / Complete                   the teardown
    Paging                       MME -> eNB, when the MME asks for it

What is not implemented: S1 handover, E-RABs, bearer management, a NAS
stack, or the MME-initiated Initial Context Setup. The MME does not answer
an Attach Request with an Attach Accept; it records what the request says
about the subscriber and where it is. That is why ``/health`` still says the
MME is an LCS function.

The relay is block-and-wait: one LPPa exchange per UE at a time, keyed by
the S1AP Routing-ID the MME allocates. A second concurrent relay for the
same UE is refused rather than interleaved. An uplink LPPa PDU that matches
no outstanding relay is counted and dropped: the MME has no SLs session to
attach it to (the E-SMLC's own timer decides what that means).
"""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from corelib import wire  # noqa: E402
from lib.codecs import lcsap, nas, s1ap  # noqa: E402

from ue_contexts import (  # noqa: E402
    RRC_CONNECTED, RRC_IDLE, UeContext, UeContextStore,
)

logger = logging.getLogger("mme.s1")

DEFAULT_S1_PORT = 36412
DEFAULT_LPPA_TIMEOUT = 5.0


class S1LinkError(RuntimeError):
    """The association, the UE binding or the relay cannot do what was asked."""


@dataclass
class EnbAssociation:
    connection: wire.Connection
    name: Optional[str] = None
    plmn: bytes = s1ap.LAB_PLMN
    tac: bytes = b"\x00\xa1"
    enb_id: Optional[int] = None
    connected_at: float = field(default_factory=time.monotonic)
    pages: int = 0

    def as_dict(self) -> dict:
        peer = getattr(self.connection, "peer", None)
        return {
            "peer": None if peer is None else f"{peer[0]}:{peer[1]}",
            "name": self.name,
            "plmn": self.plmn.hex(),
            "tac": self.tac.hex(),
            "enb_id": self.enb_id,
            "pages": self.pages,
            "up_s": round(max(0.0, time.monotonic() - self.connected_at), 3),
        }


@dataclass
class S1Ue:
    mme_ue_id: int
    enb_ue_id: int
    association: EnbAssociation
    imsi: Optional[str]
    plmn: bytes
    cell: int
    tac: bytes
    s_tmsi: Optional[Tuple[bytes, bytes]] = None
    created: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    lppa_in: int = 0
    lppa_out: int = 0
    pages: int = 0
    last_routing: int = 0
    pending_routing: Optional[int] = None
    pending_event: Optional[threading.Event] = None
    pending_answer: Optional[bytes] = None
    pending_error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "mme_ue_id": self.mme_ue_id,
            "enb_ue_id": self.enb_ue_id,
            "imsi": self.imsi,
            "plmn": self.plmn.hex(),
            "cell": f"0x{self.cell:07X}",
            "tac": self.tac.hex(),
            "s_tmsi": (None if self.s_tmsi is None
                       else (self.s_tmsi[0].hex(), self.s_tmsi[1].hex())),
            "lppa_in": self.lppa_in,
            "lppa_out": self.lppa_out,
            "lppa_pending": self.pending_event is not None,
            "pages": self.pages,
            "age_s": round(max(0.0, time.monotonic() - self.created), 3),
            "enb": (None if self.association.connection.peer is None
                    else f"{self.association.connection.peer[0]}:"
                         f"{self.association.connection.peer[1]}"),
        }


class S1Server:
    """Accept eNBs, bind UEs and relay LPPa between an E-SMLC and an eNB.

    One server instance is one S1-MME endpoint. State is keyed by the MME UE
    S1AP identity, which this side allocates; the eNB's own identity is kept
    beside it because a UE-associated message carries both.
    """

    def __init__(self, host: str, port: int, contexts: UeContextStore, *,
                 name: str = "mme", carrier: str = wire.CARRIER_TCP,
                 plmn: bytes = s1ap.LAB_PLMN, mme_code: int = 1,
                 lppa_timeout: float = DEFAULT_LPPA_TIMEOUT):
        self.host = host
        self.port = port
        self.contexts = contexts
        self.name = name
        self.carrier = carrier
        self.plmn = plmn
        self.mme_code = mme_code
        self.lppa_timeout = lppa_timeout
        self._lock = threading.RLock()
        self._enbs: Dict[wire.Connection, EnbAssociation] = {}
        self._ues: Dict[int, S1Ue] = {}
        self._by_imsi: Dict[str, int] = {}
        self._by_pair: Dict[Tuple[wire.Connection, int], int] = {}
        self._next_mme = 0
        self._started = False
        self.counters: Dict[str, int] = {
            "setups": 0,
            "setup_failures": 0,
            "initial_ue": 0,
            "attaches": 0,
            "no_imsi": 0,
            "nas_errors": 0,
            "incomplete": 0,
            "unreadable": 0,
            "downlink_lppa": 0,
            "uplink_lppa": 0,
            "unmatched_lppa": 0,
            "uplink_nas": 0,
            "releases_sent": 0,
            "releases": 0,
            "pages": 0,
            "disconnects": 0,
            "unsupported": 0,
        }
        self.server = wire.Server(host, port, self._handle, name=f"{name}-s1",
                                  carrier=carrier, on_close=self._connection_closed)

    @property
    def listening(self) -> bool:
        return self._started

    def start(self) -> None:
        self.server.start()
        self.port = self.server.port
        self._started = True
        logger.info("%s S1 endpoint on %s:%s (%s)", self.name, self.host,
                    self.port, "SCTP" if self.carrier == wire.CARRIER_SCTP
                    else "TCP carrier")

    def stop(self) -> None:
        self._started = False
        self.server.stop()

    def enbs(self) -> List[dict]:
        with self._lock:
            return [association.as_dict() for association in self._enbs.values()]

    def ues(self) -> List[dict]:
        with self._lock:
            return [ue.as_dict() for ue in self._ues.values()]

    def ue_for_imsi(self, imsi: str) -> Optional[dict]:
        with self._lock:
            ue = self._ues.get(self._by_imsi.get(imsi))
            return None if ue is None else ue.as_dict()

    def status(self) -> dict:
        with self._lock:
            enbs, ues, imsis = len(self._enbs), len(self._ues), len(self._by_imsi)
            counters = dict(self.counters)
        return {
            "listening": self._started,
            "host": self.host,
            "port": self.port,
            "carrier": self.carrier,
            "plmn": self.plmn.hex(),
            "enbs": enbs,
            "ues": ues,
            "imsis": imsis,
            "counters": counters,
            **self.server.stats(),
        }

    def _handle(self, pdu: bytes, connection: wire.Connection) -> Optional[bytes]:
        try:
            message = s1ap.parse(pdu)
        except s1ap.S1apError as exc:
            self.counters["unreadable"] += 1
            logger.warning("unreadable S1AP PDU (%d octets, %s): %s",
                           len(pdu), pdu[:16].hex(), exc)
            return None
        if message.procedure == s1ap.PROC_S1_SETUP:
            return self._s1_setup(message, connection)
        if message.procedure == s1ap.PROC_INITIAL_UE_MESSAGE:
            self._initial_ue(message, connection)
            return None
        if message.procedure == s1ap.PROC_UPLINK_UE_ASSOCIATED_LPPA:
            self._uplink_lppa(message)
            return None
        if message.procedure == s1ap.PROC_UPLINK_NON_UE_ASSOCIATED_LPPA:
            self.counters["unmatched_lppa"] += 1
            logger.warning("non-UE-associated LPPa is not used for a per-UE "
                           "E-CID relay; PDU dropped")
            return None
        if message.procedure == s1ap.PROC_UPLINK_NAS_TRANSPORT:
            self.counters["uplink_nas"] += 1
            return None
        if message.procedure == s1ap.PROC_UE_CONTEXT_RELEASE:
            self._released(message)
            return None
        if message.procedure == s1ap.PROC_ERROR_INDICATION:
            return None
        self.counters["unsupported"] += 1
        logger.warning("S1AP procedure %s (%s) is not handled", message.procedure,
                       message.name)
        return None

    def _s1_setup(self, message: s1ap.S1apMessage,
                  connection: wire.Connection) -> Optional[bytes]:
        if message.kind != s1ap.INITIATING:
            return None
        tracking_areas = s1ap.supported_tas(message)
        plmns = {ta.plmn for ta in tracking_areas}
        if not tracking_areas or self.plmn not in plmns:
            self.counters["setup_failures"] += 1
            return s1ap.s1_setup_failure(("misc", "unspecified"))
        enb_id = None
        global_id = message.ie("Global-ENB-ID")
        if isinstance(global_id, dict):
            choice = global_id.get("eNB-ID")
            if isinstance(choice, tuple) and choice[0] == "macroENB-ID":
                enb_id = choice[1][0]
        association = EnbAssociation(
            connection=connection,
            name=s1ap.enb_name(message),
            plmn=self.plmn,
            tac=tracking_areas[0].tac,
            enb_id=enb_id,
        )
        with self._lock:
            self._enbs[connection] = association
            self.counters["setups"] += 1
        return s1ap.s1_setup_response(plmn=self.plmn, mme_code=self.mme_code,
                                      name=self.name)

    def _initial_ue(self, message: s1ap.S1apMessage,
                    connection: wire.Connection) -> None:
        if message.kind != s1ap.INITIATING:
            return
        with self._lock:
            association = self._enbs.get(connection)
        if association is None:
            raise S1LinkError("InitialUEMessage arrived before S1 setup")
        enb_ue_id = message.ie("ENB-UE-S1AP-ID")
        if not isinstance(enb_ue_id, int):
            raise S1LinkError("InitialUEMessage carried no ENB-UE-S1AP-ID")
        cell = s1ap.ecgi(message)
        if cell is None:
            self.counters["incomplete"] += 1
            raise S1LinkError("InitialUEMessage carried no E-UTRAN CGI, so the "
                              "UE cannot be bound to a cell")
        tai = s1ap.tai(message)
        tac = tai.tac if tai is not None else association.tac
        imsi = None
        nas_pdu = s1ap.nas_pdu(message)
        if nas_pdu:
            try:
                imsi = nas.imsi_from_attach_request(nas_pdu)
            except nas.NasError as exc:
                self.counters["nas_errors"] += 1
                logger.warning("NAS Attach Request could not be read: %s", exc)
        if imsi is not None:
            existing = self.contexts.get(imsi)
            self.contexts.upsert(UeContext(
                imsi=imsi, plmn=cell.plmn, cell=cell.cell_id,
                rrc_state=RRC_CONNECTED,
                answers_pages=(existing.answers_pages if existing else True),
                nas_url=(existing.nas_url if existing else None)))
            self.counters["attaches"] += 1
        else:
            self.counters["no_imsi"] += 1
        s_tmsi = s1ap.s_tmsi(message)
        with self._lock:
            previous = self._by_pair.get((connection, enb_ue_id))
            if previous is not None:
                old = self._ues.pop(previous, None)
                if old is not None:
                    self._forget(old)
            mme_ue_id = self._allocate_mme_id()
            ue = S1Ue(mme_ue_id=mme_ue_id, enb_ue_id=enb_ue_id,
                      association=association, imsi=imsi, plmn=cell.plmn,
                      cell=cell.cell_id, tac=tac, s_tmsi=s_tmsi)
            self._ues[mme_ue_id] = ue
            self._by_pair[(connection, enb_ue_id)] = mme_ue_id
            if imsi is not None:
                self._by_imsi[imsi] = mme_ue_id
            self.counters["initial_ue"] += 1

    def _uplink_lppa(self, message: s1ap.S1apMessage) -> None:
        mme_ue_id, enb_ue_id = s1ap.ue_ids(message)
        apdu = s1ap.lppa_pdu(message)
        routing = s1ap.routing_id(message)
        if apdu is None:
            self.counters["incomplete"] += 1
            return
        with self._lock:
            ue = self._ues.get(mme_ue_id)
            if ue is None or ue.enb_ue_id != enb_ue_id:
                self.counters["unmatched_lppa"] += 1
                logger.warning("uplink LPPa names no live UE (%s, %s)",
                               mme_ue_id, enb_ue_id)
                return
            ue.lppa_in += 1
            ue.last_seen = time.monotonic()
            self.counters["uplink_lppa"] += 1
            if (ue.pending_event is None or routing is None
                    or ue.pending_routing != routing):
                self.counters["unmatched_lppa"] += 1
                logger.warning("uplink LPPa for UE %s has no outstanding relay "
                               "(routing %s); PDU dropped", mme_ue_id, routing)
                return
            ue.pending_answer = bytes(apdu)
            ue.pending_error = None
            ue.pending_event.set()

    def _released(self, message: s1ap.S1apMessage) -> None:
        mme_ue_id, _ = s1ap.ue_ids(message)
        with self._lock:
            ue = self._ues.pop(mme_ue_id, None)
            if ue is None:
                return
            self._forget(ue)
            self.counters["releases"] += 1
        self._mark_idle(ue)

    def _connection_closed(self, connection: wire.Connection) -> None:
        with self._lock:
            self._enbs.pop(connection, None)
            lost = [ue for ue in self._ues.values()
                    if ue.association.connection is connection]
            for ue in lost:
                self._ues.pop(ue.mme_ue_id, None)
                self._forget(ue)
                if ue.pending_event is not None:
                    ue.pending_error = "the S1 association closed"
                    ue.pending_event.set()
            self.counters["disconnects"] += 1
        for ue in lost:
            self._mark_idle(ue)

    def relay_lppa(self, imsi: str, apdu: bytes,
                   timeout: Optional[float] = None) -> bytes:
        """Send one LPPa PDU to the eNB serving ``imsi`` and return its answer.

        The call blocks: the eNB's uplink LPPa PDU arrives on the association
        thread and is handed over through the UE's pending slot. No second
        relay is allowed for the same UE until this one finishes.
        """
        if not isinstance(apdu, (bytes, bytearray)) or not apdu:
            raise S1LinkError("an LPPa PDU is a non-empty octet string")
        budget = self.lppa_timeout if timeout is None else timeout
        with self._lock:
            ue = self._ues.get(self._by_imsi.get(imsi))
            if ue is None:
                raise S1LinkError(
                    f"no S1 UE context for IMSI {imsi}; the eNB has not sent "
                    "an InitialUEMessage for it")
            if ue.pending_event is not None:
                raise S1LinkError(
                    f"another LPPa relay is already outstanding for IMSI {imsi}")
            routing = (ue.last_routing + 1) & 0xFF
            ue.last_routing = routing
            event = threading.Event()
            ue.pending_event = event
            ue.pending_routing = routing
            ue.pending_answer = None
            ue.pending_error = None
            pdu = s1ap.downlink_ue_associated_lppa(
                ue.mme_ue_id, ue.enb_ue_id, bytes(apdu), routing)
            connection = ue.association.connection
        try:
            connection.send(pdu)
        except (wire.WireError, OSError) as exc:
            with self._lock:
                ue.pending_event = None
                ue.pending_routing = None
            raise S1LinkError(f"cannot send LPPa to the eNB: {exc}") from exc
        with self._lock:
            ue.lppa_out += 1
            self.counters["downlink_lppa"] += 1
        if not event.wait(budget):
            with self._lock:
                error = ue.pending_error
                self._clear_pending(ue)
            raise S1LinkError(
                f"the eNB did not answer LPPa within {budget:g}s"
                + (f": {error}" if error else ""))
        with self._lock:
            answer = ue.pending_answer
            error = ue.pending_error
            self._clear_pending(ue)
        if error is not None:
            raise S1LinkError(error)
        if answer is None:
            raise S1LinkError("the LPPa relay finished without an APDU")
        return answer

    def page(self, imsi: str) -> dict:
        """Page one UE over S1, by S-TMSI when it has one, by IMSI when not.

        This is the signalling only: whether the UE answers is the eNB's and
        the UE's business, and the MME does not invent an answer.
        """
        with self._lock:
            ue = self._ues.get(self._by_imsi.get(imsi))
            if ue is None:
                raise S1LinkError(f"no S1 UE context for IMSI {imsi}")
            if ue.s_tmsi is not None:
                index = s1ap.paging_index(ue.s_tmsi[1])
                pdu = s1ap.paging(index, s_tmsi=ue.s_tmsi, plmn=ue.plmn,
                                  tac=ue.tac)
                identity = "s-tmsi"
            else:
                index = int(imsi) & 0x3FF
                pdu = s1ap.paging(index, imsi=lcsap.tbcd(imsi), plmn=ue.plmn,
                                  tac=ue.tac)
                identity = "imsi"
            connection = ue.association.connection
            ue.pages += 1
            ue.association.pages += 1
            self.counters["pages"] += 1
        connection.send(pdu)
        return {"imsi": imsi, "identity": identity, "ue_index": index}

    def release(self, imsi: str) -> dict:
        with self._lock:
            ue = self._ues.get(self._by_imsi.get(imsi))
            if ue is None:
                raise S1LinkError(f"no S1 UE context for IMSI {imsi}")
            pdu = s1ap.ue_context_release_command(ue.mme_ue_id, ue.enb_ue_id)
            connection = ue.association.connection
            self.counters["releases_sent"] += 1
        connection.send(pdu)
        return {"imsi": imsi, "mme_ue_id": ue.mme_ue_id,
                "enb_ue_id": ue.enb_ue_id}

    def _allocate_mme_id(self) -> int:
        for _ in range(1 << 16):
            self._next_mme = (self._next_mme + 1) & s1ap.MAX_MME_UE_S1AP_ID
            if self._next_mme == 0:
                continue
            if self._next_mme not in self._ues:
                return self._next_mme
        raise S1LinkError("no free MME-UE-S1AP identity")

    def _forget(self, ue: S1Ue) -> None:
        """Drop the indexes for a UE. The caller holds the lock."""
        self._by_pair.pop((ue.association.connection, ue.enb_ue_id), None)
        if ue.imsi is not None and self._by_imsi.get(ue.imsi) == ue.mme_ue_id:
            self._by_imsi.pop(ue.imsi, None)

    def _clear_pending(self, ue: S1Ue) -> Optional[str]:
        error = ue.pending_error
        ue.pending_event = None
        ue.pending_routing = None
        ue.pending_answer = None
        ue.pending_error = None
        return error

    def _mark_idle(self, ue: S1Ue) -> None:
        if ue.imsi is None:
            return
        context = self.contexts.get(ue.imsi)
        if context is not None:
            self.contexts.upsert(dataclasses.replace(context, rrc_state=RRC_IDLE))


class S1Client:
    """The eNB side: one S1 association, setup and the messages a lab eNB
    sends. It keeps no UE state beyond the eNB UE S1AP identity it allocated;
    the component that owns the radio side does that."""

    def __init__(self, host: str, port: int = DEFAULT_S1_PORT,
                 timeout: float = 5.0, carrier: str = wire.CARRIER_TCP):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.carrier = carrier
        self._connection: Optional[wire.Connection] = None
        self._next_enb = 0
        self.plmns: List[bytes] = []
        self.mme_name: Optional[str] = None

    @property
    def connected(self) -> bool:
        return self._connection is not None

    def connect(self) -> "S1Client":
        if self._connection is None:
            try:
                self._connection = wire.Connection.connect(
                    self.host, self.port, self.timeout, self.carrier)
            except OSError as exc:
                raise S1LinkError(
                    f"cannot reach the MME S1 endpoint at {self.host}:{self.port}: "
                    f"{exc}") from exc
        return self

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "S1Client":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    def setup(self, name: Optional[str] = None, enb_id: int = 0,
              tac: bytes = b"\x00\xa1",
              plmn: bytes = s1ap.LAB_PLMN) -> s1ap.S1apMessage:
        self.connect()
        self._connection.send(s1ap.s1_setup_request(
            plmn=plmn, enb_id=enb_id, tac=tac, name=name))
        raw = self._connection.receive(self.timeout)
        if not raw:
            raise S1LinkError("the MME closed during S1 setup")
        try:
            message = s1ap.parse(raw)
        except s1ap.S1apError as exc:
            raise S1LinkError(f"the MME answered setup with unreadable bytes: "
                              f"{exc}") from exc
        if message.procedure != s1ap.PROC_S1_SETUP:
            raise S1LinkError(
                f"the MME answered setup with procedure {message.procedure}")
        if message.kind == s1ap.UNSUCCESSFUL:
            raise S1LinkError(f"the MME refused S1 setup: {s1ap.cause(message)}")
        if message.kind != s1ap.SUCCESSFUL:
            raise S1LinkError(
                f"the MME answered setup with kind {message.kind}")
        self.plmns = s1ap.served_plmns(message)
        self.mme_name = s1ap.mme_name(message)
        if plmn not in self.plmns:
            raise S1LinkError(
                f"the MME does not serve PLMN {plmn.hex()}; it serves "
                f"{[p.hex() for p in self.plmns]}")
        return message

    def initial_ue(self, imsi: str, cell: Tuple[int, int], *,
                   plmn: bytes = s1ap.LAB_PLMN, tac: bytes = b"\x00\xa1",
                   s_tmsi: Optional[Tuple[bytes, bytes]] = None,
                   nas_pdu: Optional[bytes] = None) -> int:
        """Send the NAS Attach Request that binds ``imsi`` to ``cell`` and
        return the eNB UE S1AP identity this client allocated."""
        self.connect()
        if nas_pdu is None:
            nas_pdu = nas.attach_request(imsi)
        self._next_enb = ((self._next_enb + 1)
                          & s1ap.MAX_ENB_UE_S1AP_ID) or 1
        enb_ue_id = self._next_enb
        self._connection.send(s1ap.initial_ue_message(
            enb_ue_id, nas_pdu, cell, plmn=plmn, tac=tac, s_tmsi=s_tmsi))
        return enb_ue_id

    def receive(self, timeout: Optional[float] = None) -> Optional[s1ap.S1apMessage]:
        """One downlink message, or None when the MME closed. A timeout is a
        wire.WireError; the caller decides whether that is idleness or
        failure."""
        self.connect()
        raw = self._connection.receive(timeout)
        if not raw:
            return None
        try:
            return s1ap.parse(raw)
        except s1ap.S1apError as exc:
            raise S1LinkError(f"the MME sent unreadable S1AP: {exc}") from exc

    def send(self, pdu: bytes) -> None:
        self.connect()
        self._connection.send(pdu)

    def uplink_lppa(self, mme_ue_id: int, enb_ue_id: int, apdu: bytes,
                    routing_id: int = 0) -> None:
        self.send(s1ap.uplink_ue_associated_lppa(
            mme_ue_id, enb_ue_id, apdu, routing_id))

    def uplink_nas(self, mme_ue_id: int, enb_ue_id: int, nas_pdu: bytes) -> None:
        self.send(s1ap.uplink_nas_transport(mme_ue_id, enb_ue_id, nas_pdu))

    def release_complete(self, mme_ue_id: int, enb_ue_id: int) -> None:
        self.send(s1ap.ue_context_release_complete(mme_ue_id, enb_ue_id))
