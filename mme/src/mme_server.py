"""Custom MME - the LCS function only: SLg in, SLs out.

What this process is:

  * a Diameter SLg server (TS 29.172) on TCP that accepts Capabilities-Exchange
    and Device-Watchdog and answers Provide-Location-Request with a position,
    or with an honest failure result code;
  * an SLs client (LCS-AP, TS 29.171) that asks the E-SMLC for the position
    and relays an LPP APDU to the UE's NAS endpoint and an LPPa APDU to the
    serving eNB over S1, both unchanged;
  * an S1 association server (S1AP, TS 36.413) that accepts a lab eNB's S1
    setup, learns the IMSI behind its UE from the NAS Attach Request, pages a
    known UE and releases its context;
  * a paging model and a Cell-ID fallback from the operator's cell plan;
  * a management HTTP API on 8075 exposing listener state, a lab UE registry
    and an SLg shim used by the test suite.

What this process is not: S11, S6a, SGs, bearer management, a NAS stack, or
MAP LCS. The S1 support is an association and LPPa relay for E-CID, not a
mobility engine: there is no handover, no E-RAB and no security-mode
procedure. LRR/LRA (location reporting) is a Phase 4 work package and is
refused rather than dropped.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
           os.path.dirname(os.path.abspath(__file__)), "/app", "/app/src"):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from corelib import diameter as d  # noqa: E402
from corelib import sls  # noqa: E402
from corelib import wire  # noqa: E402
from lib.codecs import lcsap  # noqa: E402

import cell_plan as cell_plan_module  # noqa: E402
import s1_link  # noqa: E402
import slg  # noqa: E402
import ue_contexts  # noqa: E402
from location_service import LocationService  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("mme")

HOST = os.getenv("MME_HOST", "0.0.0.0")
SLG_PORT = int(os.getenv("MME_SLG_PORT", "3875"))
HTTP_PORT = int(os.getenv("MME_HTTP_PORT", "8075"))
ORIGIN_HOST = os.getenv("MME_ORIGIN_HOST", "mme.core.local")
ORIGIN_REALM = os.getenv("MME_ORIGIN_REALM", "core.local")
PRODUCT_NAME = os.getenv("MME_PRODUCT_NAME", "Hamiltel-MME")
VENDOR_ID = int(os.getenv("DIAMETER_VENDOR_ID", "10415"))
FIRMWARE_REVISION = int(os.getenv("MME_FIRMWARE_REVISION", "1"))

ESMLC_HOST = os.getenv("ESMLC_ADDR", "127.0.0.1")
ESMLC_PORT = int(os.getenv("ESMLC_PORT", "9082"))
ESMLC_TIMEOUT = float(os.getenv("MME_ESMLC_TIMEOUT", "5.0"))
SLS_CARRIER = os.getenv("MME_SLS_CARRIER", sls.CARRIER_TCP)
S1_PORT = int(os.getenv("MME_S1_PORT", str(s1_link.DEFAULT_S1_PORT)))
S1_CARRIER = os.getenv("MME_S1_CARRIER", sls.CARRIER_TCP)
S1_ENABLE = os.getenv("MME_S1_ENABLE", "1").lower() in ("1", "true", "yes")
S1_LPPA_TIMEOUT = float(os.getenv("MME_S1_LPPA_TIMEOUT", "5.0"))
CELL_PLAN_PATH = os.getenv("MME_CELL_PLAN", str(cell_plan_module.DEFAULT_CONFIG))
LAB_MCC = os.getenv("MME_LAB_MCC", "001")
LAB_MNC = os.getenv("MME_LAB_MNC", "01")
LAB_SEED = os.getenv("MME_LAB_SEED", "1").lower() in ("1", "true", "yes")

# The same three synthetic UEs the lab E-SMLC knows (esmlc/config/lab_positions.json).
_LAB_SEED_CONTEXTS = (
    ("001010000000001", 0x00A1B2C),
    ("001010000000002", 0x00A1B2D),
    ("001010000000003", 0x00A1B2E),
)

try:
    CELL_PLAN = cell_plan_module.CellPlan.from_file(CELL_PLAN_PATH)
except (OSError, ValueError) as exc:
    logger.error("cell plan %s not loaded (%s); Cell-ID fallback is unavailable",
                 CELL_PLAN_PATH, exc)
    CELL_PLAN = cell_plan_module.CellPlan([])


def _seed_store() -> ue_contexts.UeContextStore:
    store = ue_contexts.UeContextStore()
    if not LAB_SEED:
        return store
    try:
        plmn = lcsap.plmn_identity(LAB_MCC, LAB_MNC)
    except lcsap.LcsApError as exc:
        logger.error("lab PLMN %s-%s is invalid (%s); not seeding UEs",
                     LAB_MCC, LAB_MNC, exc)
        return store
    for imsi, cell in _LAB_SEED_CONTEXTS:
        store.upsert(ue_contexts.UeContext(imsi=imsi, plmn=plmn, cell=cell))
    return store


CONTEXTS = _seed_store()

diameter_server: Optional[d.DiameterServer] = None
s1_server: Optional[s1_link.S1Server] = None


def _lppa_transport(imsi: str):
    """The E-SMLC's LPPa APDU goes to the eNB that serves this IMSI, or
    nowhere: without an S1 binding the dialogue is aborted, not faked."""
    server = s1_server
    if server is None:
        return None
    return lambda apdu: server.relay_lppa(imsi, apdu)


LOCATION = LocationService(
    CONTEXTS, CELL_PLAN,
    esmlc_host=ESMLC_HOST, esmlc_port=ESMLC_PORT,
    timeout=ESMLC_TIMEOUT, carrier=SLS_CARRIER,
    lppa_transport_factory=_lppa_transport)

stats = {"plr": 0, "unsupported": 0, "bad_realm": 0, "reporting_refused": 0,
         "last_plr": None}


def _capabilities_answer(request: d.Message) -> d.Message:
    avps = [
        d.AVP_U32(d.AVP_RESULT_CODE, d.RESULT_SUCCESS),
        d.AVP_UTF8(d.AVP_ORIGIN_HOST, ORIGIN_HOST),
        d.AVP_UTF8(d.AVP_ORIGIN_REALM, ORIGIN_REALM),
        d.AVP_UTF8(d.AVP_PRODUCT_NAME, PRODUCT_NAME, mandatory=False),
        d.AVP_U32(d.AVP_FIRMWARE_REVISION, FIRMWARE_REVISION, mandatory=False),
        d.AVP_U32(d.AVP_VENDOR_ID, VENDOR_ID, mandatory=False),
        d.AVP_U32(d.AVP_SUPPORTED_VENDOR_ID, VENDOR_ID, mandatory=False),
    ]
    return d.Message(
        command_code=request.command_code,
        app_id=request.app_id,
        avps=avps,
        flags=request.flags & ~d.FLAG_REQUEST,
        hop_by_hop=request.hop_by_hop,
        end_to_end=request.end_to_end,
    )


def _watchdog_answer(request: d.Message) -> d.Message:
    return _capabilities_answer(request)


async def _plr_answer(request: d.Message) -> d.Message:
    session = request.avp(d.AVP_SESSION_ID)
    if session is None:
        return d.answer(
            request, d.RESULT_MISSING_AVP, ORIGIN_HOST, ORIGIN_REALM,
            error_message="Session-Id is mandatory",
        )
    realm = request.avp(d.AVP_DESTINATION_REALM)
    if realm is not None and realm.as_string() != ORIGIN_REALM:
        stats["bad_realm"] += 1
        return d.answer(
            request, d.RESULT_REALM_NOT_SERVED, ORIGIN_HOST, ORIGIN_REALM,
            error_message=f"this MME serves realm {ORIGIN_REALM}",
        )

    stats["plr"] += 1
    identity = slg.subscriber(request)
    stats["last_plr"] = {
        "session_id": session.as_string(),
        "subscriber": identity,
    }
    logger.info("SLg PLR session=%s subscriber=%s", session.as_string(), identity)
    if identity is None:
        return d.answer(
            request, d.RESULT_MISSING_AVP, ORIGIN_HOST, ORIGIN_REALM,
            error_message="User-Name (IMSI) or MSISDN is mandatory",
        )
    if slg.location_type(request) == slg.LOCATION_TYPE_INITIATE_REPORTING:
        stats["reporting_refused"] += 1
        return d.answer(
            request, d.RESULT_UNABLE_TO_COMPLY, ORIGIN_HOST, ORIGIN_REALM,
            error_message=("location reporting (LRR/LRA) is a Phase 4 work "
                           "package; this MME only answers one-shot requests"),
        )

    outcome = await asyncio.to_thread(
        LOCATION.locate, identity,
        slg.requested_accuracy(request), slg.client_type(request))
    return d.answer(
        request, outcome.result_code, ORIGIN_HOST, ORIGIN_REALM,
        error_message=outcome.detail or None,
        extra=slg.location_answer_avps(outcome),
    )


async def handle_message(request: d.Message) -> Optional[d.Message]:
    if request.command_code == d.CMD_CAPABILITIES_EXCHANGE:
        return _capabilities_answer(request)
    if request.command_code == d.CMD_DEVICE_WATCHDOG:
        return _watchdog_answer(request)
    if request.command_code == d.CMD_PLR and request.app_id == d.APP_SLG:
        return await _plr_answer(request)
    if request.command_code == d.CMD_RIR:
        return d.answer(
            request, d.RESULT_UNABLE_TO_COMPLY, ORIGIN_HOST, ORIGIN_REALM,
            error_message="SLh is served by the HSS, not by this MME",
        )
    if request.command_code == d.CMD_LRR:
        return d.answer(
            request, d.RESULT_COMMAND_UNSUPPORTED, ORIGIN_HOST, ORIGIN_REALM,
            error_message="LRR/LRA is not implemented; this MME only answers PLR",
        )
    stats["unsupported"] += 1
    return d.answer(
        request, d.RESULT_COMMAND_UNSUPPORTED, ORIGIN_HOST, ORIGIN_REALM,
        error_message=f"command {request.command_code} is not supported",
    )


class SlgShimRequest(BaseModel):
    session_id: str
    subscriber: Optional[str] = None
    destination_realm: Optional[str] = None
    msisdn: Optional[str] = None
    horizontal_accuracy_m: Optional[float] = None
    client_type: Optional[int] = None
    location_type: int = slg.LOCATION_TYPE_CURRENT_OR_LAST_KNOWN


class LabUeRequest(BaseModel):
    imsi: str
    mcc: str = LAB_MCC
    mnc: str = LAB_MNC
    cell: Union[str, int]
    rrc_state: str = ue_contexts.RRC_CONNECTED
    answers_pages: bool = True
    nas_url: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global diameter_server, s1_server
    diameter_server = d.DiameterServer(HOST, SLG_PORT, handle_message, name="mme-slg")
    await diameter_server.start()
    if S1_ENABLE:
        candidate = s1_link.S1Server(HOST, S1_PORT, CONTEXTS, name="mme",
                                     carrier=S1_CARRIER,
                                     lppa_timeout=S1_LPPA_TIMEOUT)
        try:
            candidate.start()
            s1_server = candidate
        except (OSError, wire.WireError) as exc:
            # The location function still works without S1; only LPPa relay
            # to an eNB is lost, and the health endpoint says so.
            logger.error("S1 endpoint on %s:%s could not start (%s); "
                         "LPPa relay is unavailable", HOST, S1_PORT, exc)
    logger.info("MME management API on %s:%s; %d UE contexts, %d planned cells, "
                "E-SMLC %s:%s over %s, S1 %s", HOST, HTTP_PORT, len(CONTEXTS),
                len(CELL_PLAN), ESMLC_HOST, ESMLC_PORT, SLS_CARRIER,
                f"{HOST}:{S1_PORT} ({S1_CARRIER})" if s1_server else "off")
    yield
    if s1_server is not None:
        s1_server.stop()
        s1_server = None
    await diameter_server.stop()


app = FastAPI(title="Hamiltel MME (LCS function)", version="0.2.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "mme",
        "scope": "LCS function (SLg + SLs + S1 LPPa relay)",
        "s1ap": {
            "association": "S1 setup, InitialUEMessage, paging, release",
            "lppa": "UE-associated LPPa relay to the serving eNB; the lab eNB answers E-CID",
            "not_implemented": ["handover", "E-RAB setup", "NAS stack", "security mode"],
            "enabled": S1_ENABLE,
            "listening": s1_server is not None,
        },
        "s11": "not implemented",
        "s6a": "not implemented",
        "sgs": "not implemented",
        "lpp": ("relayed opaquely over the lab NAS endpoint; the E-SMLC and "
                "lab UE speak TS 37.355, the MME does not decode it"),
        "lppa": "relayed to the serving eNB over S1; E-CID only",
        "paging": ("over S1 by S-TMSI or IMSI for UEs with an S1 context; the "
                   "MME sends the page and does not invent the UE's answer"),
        "sls": {
            "esmlc": f"{ESMLC_HOST}:{ESMLC_PORT}",
            "carrier": SLS_CARRIER,
            "timeout_s": ESMLC_TIMEOUT,
        },
        "s1": (s1_server.status() if s1_server is not None else {
            "listening": False, "enabled": S1_ENABLE,
            "host": HOST, "port": S1_PORT, "carrier": S1_CARRIER}),
        "cell_plan": {"path": str(CELL_PLAN_PATH), "cells": len(CELL_PLAN)},
        "ue_contexts": len(CONTEXTS),
        "diameter": {
            "transport": "tcp",
            "port": SLG_PORT,
            "origin_host": ORIGIN_HOST,
            "origin_realm": ORIGIN_REALM,
            **(diameter_server.stats() if diameter_server else {}),
        },
        "location": LOCATION.stats(),
        "stats": stats,
    }


@app.get("/slg/status")
def slg_status() -> Dict[str, Any]:
    return {
        "listening": diameter_server is not None,
        "advertised_applications": [d.APP_SLG],
        "stats": diameter_server.stats() if diameter_server else None,
        "plr": stats,
        "location": LOCATION.stats(),
    }


@app.post("/slg/plr")
async def slg_plr_shim(request: SlgShimRequest) -> Dict[str, Any]:
    """Same decision path as the Diameter handler, without needing a peer."""
    avps = [
        d.AVP_UTF8(d.AVP_SESSION_ID, request.session_id),
        d.AVP_UTF8(d.AVP_ORIGIN_HOST, "shim.core.local"),
        d.AVP_UTF8(d.AVP_ORIGIN_REALM, "core.local"),
        d.AVP_U32(d.AVP_SLG_LOCATION_TYPE, request.location_type,
                  vendor_id=d.VENDOR_3GPP),
    ]
    if request.destination_realm:
        avps.append(d.AVP_UTF8(d.AVP_DESTINATION_REALM, request.destination_realm))
    else:
        avps.append(d.AVP_UTF8(d.AVP_DESTINATION_REALM, ORIGIN_REALM))
    if request.subscriber:
        avps.append(d.AVP_UTF8(d.AVP_USER_NAME, request.subscriber))
    if request.msisdn:
        avps.append(d.AVP(d.AVP_MSISDN, lcsap.tbcd(request.msisdn),
                          vendor_id=d.VENDOR_3GPP))
    if request.horizontal_accuracy_m is not None:
        avps.append(d.AVP_GROUPED(
            d.AVP_LCS_QOS,
            [d.AVP_U32(d.AVP_HORIZONTAL_ACCURACY,
                       lcsap.uncertainty_code(request.horizontal_accuracy_m),
                       vendor_id=d.VENDOR_3GPP)],
            vendor_id=d.VENDOR_3GPP))
    if request.client_type is not None:
        avps.append(d.AVP_U32(d.AVP_LCS_CLIENT_TYPE, request.client_type,
                              vendor_id=d.VENDOR_3GPP))

    synthetic = d.Message(command_code=d.CMD_PLR, app_id=d.APP_SLG, avps=avps)
    answer = await _plr_answer(synthetic)
    result = answer.avp(d.AVP_RESULT_CODE)
    error = answer.avp(d.AVP_ERROR_MESSAGE)
    ecgi = answer.avp(d.AVP_ECGI)
    fulfilment = answer.avp(d.AVP_ACCURACY_FULFILMENT)
    age = answer.avp(d.AVP_AGE_OF_LOCATION)
    last = LOCATION.stats().get("last") or {}
    return {
        "command_code": answer.command_code,
        "app_id": answer.app_id,
        "result_code": result.as_uint32() if result else None,
        "error_message": error.as_string() if error else None,
        "origin_host": ORIGIN_HOST,
        "positioned": last.get("positioned", False),
        "method": last.get("method"),
        "source": last.get("source"),
        "latitude": last.get("latitude"),
        "longitude": last.get("longitude"),
        "uncertainty_m": last.get("uncertainty_m"),
        "accuracy_fulfilled": ("not stated" if fulfilment is None
                               else fulfilment.as_uint32() == slg.FULFILMENT_FULFILLED),
        "age_seconds": age.as_uint32() if age else None,
        "ecgi": ecgi.as_octets()[:7].hex() if ecgi else None,
        "lpp_rounds": last.get("lpp_rounds"),
        "lppa_rounds": last.get("lppa_rounds"),
        "reached_by": last.get("reached_by"),
        "detail": last.get("detail"),
    }


@app.get("/s1/status")
def s1_status() -> Dict[str, Any]:
    if s1_server is None:
        return {"listening": False, "enabled": S1_ENABLE, "host": HOST,
                "port": S1_PORT, "carrier": S1_CARRIER,
                "detail": "the S1 listener is not running; LPPa relay is unavailable"}
    return s1_server.status()


@app.get("/s1/enbs")
def s1_enbs() -> Dict[str, Any]:
    enbs = s1_server.enbs() if s1_server is not None else []
    return {"count": len(enbs), "enbs": enbs}


@app.get("/s1/ues")
def s1_ues() -> Dict[str, Any]:
    ues = s1_server.ues() if s1_server is not None else []
    return {"count": len(ues), "ues": ues}


@app.post("/s1/page/{imsi}")
def s1_page(imsi: str) -> Dict[str, Any]:
    """Send one S1 paging message. Reaching the UE is then the radio's job."""
    if s1_server is None:
        raise HTTPException(status_code=503, detail="the S1 listener is not running")
    try:
        return s1_server.page(imsi)
    except s1_link.S1LinkError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/lab/ue")
def lab_list_ues() -> Dict[str, Any]:
    return {"count": len(CONTEXTS), "ues": CONTEXTS.snapshot()}


@app.post("/lab/ue", status_code=201)
def lab_upsert_ue(body: LabUeRequest) -> Dict[str, Any]:
    try:
        context = ue_contexts.parse_context(body.model_dump())
    except ue_contexts.UeContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    CONTEXTS.upsert(context)
    return context.as_dict()


@app.delete("/lab/ue/{imsi}")
def lab_remove_ue(imsi: str) -> Dict[str, Any]:
    if not CONTEXTS.remove(imsi):
        raise HTTPException(status_code=404, detail=f"no context for IMSI {imsi}")
    return {"removed": imsi}


@app.get("/lab/cells")
def lab_cells() -> Dict[str, Any]:
    return {"cells": [cell.as_dict() for cell in CELL_PLAN.cells()]}


@app.get("/scope")
def scope() -> Dict[str, Any]:
    return {
        "implemented": [
            "Diameter SLg over TCP (PLR/PLA, CER/CEA, DWR/DWA)",
            "SLs LCS-AP client (Location-Request/Response, Reset, Abort)",
            "LPP APDU relay over the lab NAS endpoint (opaque, unmodified)",
            "S1AP association: S1 setup, InitialUEMessage (IMSI from a plain Attach Request), paging, UE context release",
            "UE-associated LPPa relay to the serving eNB (Payload-Type lPPa)",
            "Paging and Cell-ID fallback from the operator cell plan",
            "Lab UE registry and SLg shim on the management API",
        ],
        "not_implemented": [
            "S1AP handover, E-RAB management, S1 paging response tracking",
            "S11 (SGW-C), S6a (HSS), SGs (MSC)",
            "MAP LCS SLR/SLA (MSC side)",
            "EPS NAS stack (only a plain Attach Request is read, for the IMSI)",
            "Security mode, authentication; GUTI/IMEI attaches bind no IMSI",
            "LPP codec (TS 37.355); LPPa beyond E-CID measurement initiation",
            "SLg LRR/LRA location reporting (Phase 4)",
        ],
        "note": "MSC with MAP LCS is not built; see docs/STAGING_AND_CORE_BUILD_PLAN.txt",
    }


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=HTTP_PORT, log_level=os.getenv("LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
