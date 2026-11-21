"""The UE contexts this MME knows about, and the paging model on top of them.

A real MME learns a UE's serving cell from S1AP and tracks whether the UE is
RRC-connected. This MME has no S1-MME, so the lab API in mme_server seeds the
same fields explicitly. Paging is modelled, not performed: an idle UE that is
configured to answer a page is moved to connected; one that is not stays idle
and the caller gets an honest "not reachable" instead of a position.

The store is read and written from HTTP worker threads and from the SLg
handler's worker thread, so every operation holds the lock.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.codecs import lcsap  # noqa: E402

RRC_CONNECTED = "connected"
RRC_IDLE = "idle"
RRC_STATES = (RRC_CONNECTED, RRC_IDLE)

PAGE_CONNECTED = "already-connected"
PAGE_ANSWERED = "page-answered"
PAGE_IGNORED = "page-not-answered"
PAGE_UNKNOWN = "no-context"


class UeContextError(ValueError):
    """The context description is not usable."""


@dataclass
class UeContext:
    imsi: str
    plmn: bytes
    cell: int                       # 28-bit E-UTRAN cell identity
    rrc_state: str = RRC_CONNECTED
    answers_pages: bool = True
    nas_url: Optional[str] = None
    last_seen: float = field(default_factory=time.monotonic)
    pages: int = 0

    def as_dict(self) -> dict:
        return {
            "imsi": self.imsi,
            "plmn": self.plmn.hex(),
            "cell": f"0x{self.cell:07X}",
            "rrc_state": self.rrc_state,
            "answers_pages": self.answers_pages,
            "nas_url": self.nas_url,
            "pages": self.pages,
            "last_seen_s": round(max(0.0, time.monotonic() - self.last_seen), 3),
        }


def parse_context(document: dict) -> UeContext:
    """Build a context from the lab API body, rejecting anything that would
    make a later positioning request lie about the UE."""
    imsi = document.get("imsi")
    if not isinstance(imsi, str) or not imsi.isdigit() or not 6 <= len(imsi) <= 15:
        raise UeContextError("imsi must be 6..15 decimal digits")
    mcc = str(document.get("mcc", ""))
    mnc = str(document.get("mnc", ""))
    try:
        plmn = lcsap.plmn_identity(mcc, mnc)
    except lcsap.LcsApError as exc:
        raise UeContextError(str(exc)) from exc
    cell_text = document.get("cell")
    if cell_text is None:
        raise UeContextError("cell is mandatory")
    try:
        cell = int(str(cell_text), 0)
    except ValueError as exc:
        raise UeContextError(f"cell {cell_text!r} is not a number") from exc
    if not 0 <= cell < (1 << 28):
        raise UeContextError("cell must be a 28-bit E-UTRAN cell identity")
    state = str(document.get("rrc_state", RRC_CONNECTED))
    if state not in RRC_STATES:
        raise UeContextError(f"rrc_state must be one of {RRC_STATES}")
    answers = document.get("answers_pages", True)
    if not isinstance(answers, bool):
        raise UeContextError("answers_pages must be true or false")
    nas_url = document.get("nas_url")
    if nas_url is not None and not isinstance(nas_url, str):
        raise UeContextError("nas_url must be a string")
    return UeContext(imsi=imsi, plmn=plmn, cell=cell, rrc_state=state,
                     answers_pages=answers, nas_url=nas_url)


class UeContextStore:
    def __init__(self, contexts: Iterable[UeContext] = ()):
        self._lock = threading.Lock()
        self._contexts: Dict[str, UeContext] = {c.imsi: c for c in contexts}

    def upsert(self, context: UeContext) -> UeContext:
        with self._lock:
            self._contexts[context.imsi] = context
            return context

    def get(self, imsi: str) -> Optional[UeContext]:
        with self._lock:
            return self._contexts.get(imsi)

    def remove(self, imsi: str) -> bool:
        with self._lock:
            return self._contexts.pop(imsi, None) is not None

    def snapshot(self) -> List[dict]:
        with self._lock:
            return [c.as_dict() for c in self._contexts.values()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._contexts)

    def ensure_reachable(self, imsi: str) -> Tuple[bool, str]:
        """Return whether the UE can be measured now, and how that was decided.

        An idle UE that answers a page is moved to connected, which is the
        observable effect of a successful page. A UE that does not answer is
        left idle: the MME must not invent reachability it did not obtain.
        """
        with self._lock:
            context = self._contexts.get(imsi)
            if context is None:
                return False, PAGE_UNKNOWN
            if context.rrc_state == RRC_CONNECTED:
                return True, PAGE_CONNECTED
            context.pages += 1
            if not context.answers_pages:
                return False, PAGE_IGNORED
            context.rrc_state = RRC_CONNECTED
            context.last_seen = time.monotonic()
            return True, PAGE_ANSWERED
