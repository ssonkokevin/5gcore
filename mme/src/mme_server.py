"""Custom MME - mobility management, SLg side only.

What this process is:

  * a Diameter SLg server (TS 29.172) on TCP that accepts Capabilities-Exchange
    and Device-Watchdog and answers Provide-Location-Request with
    5012 DIAMETER_UNABLE_TO_COMPLY, because this MME has no S1-MME and no
    location procedure to run;
  * a management HTTP API on 8075 exposing listener state and an SLg shim
    used by the test suite.

What this process is not: S1AP, S11, S6a, SGs, paging, bearer management, or
MAP LCS. A UE cannot attach to this MME. For attach testing use the free5gc
profile (5G) or attach an MME from the EPC side and point its SLg peer here.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from corelib import diameter as d  # noqa: E402

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

stats = {"plr": 0, "unsupported": 0, "bad_realm": 0, "last_plr": None}

diameter_server: Optional[d.DiameterServer] = None


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


def _plr_answer(request: d.Message) -> d.Message:
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
    subscriber = request.avp(d.AVP_USER_NAME) or request.avp(d.AVP_MSISDN)
    stats["last_plr"] = {
        "session_id": session.as_string(),
        "subscriber": subscriber.as_string() if subscriber else None,
    }
    logger.info("SLg PLR session=%s subscriber=%s", session.as_string(),
                stats["last_plr"]["subscriber"])
    return d.answer(
        request, d.RESULT_UNABLE_TO_COMPLY, ORIGIN_HOST, ORIGIN_REALM,
        error_message=(
            "MME location procedure not implemented: no S1-MME/S1AP association, "
            "so the UE cannot be paged or measured"
        ),
    )


def handle_message(request: d.Message) -> Optional[d.Message]:
    if request.command_code == d.CMD_CAPABILITIES_EXCHANGE:
        return _capabilities_answer(request)
    if request.command_code == d.CMD_DEVICE_WATCHDOG:
        return _watchdog_answer(request)
    if request.command_code == d.CMD_PLR and request.app_id == d.APP_SLG:
        return _plr_answer(request)
    if request.command_code == d.CMD_RIR:
        return d.answer(
            request, d.RESULT_UNABLE_TO_COMPLY, ORIGIN_HOST, ORIGIN_REALM,
            error_message="SLh is served by the HSS, not by this MME",
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global diameter_server
    diameter_server = d.DiameterServer(HOST, SLG_PORT, handle_message, name="mme-slg")
    await diameter_server.start()
    logger.info("MME management API on %s:%s", HOST, HTTP_PORT)
    yield
    await diameter_server.stop()


app = FastAPI(title="Hamiltel MME (SLg)", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "mme",
        "scope": "SLg only",
        "s1ap": "not implemented",
        "s11": "not implemented",
        "s6a": "not implemented",
        "sgs": "not implemented",
        "diameter": {
            "transport": "tcp",
            "port": SLG_PORT,
            "origin_host": ORIGIN_HOST,
            "origin_realm": ORIGIN_REALM,
            **(diameter_server.stats() if diameter_server else {}),
        },
        "stats": stats,
    }


@app.get("/slg/status")
def slg_status() -> Dict[str, Any]:
    return {
        "listening": diameter_server is not None,
        "advertised_applications": [d.APP_SLG],
        "stats": diameter_server.stats() if diameter_server else None,
        "plr": stats,
    }


@app.post("/slg/plr")
def slg_plr_shim(request: SlgShimRequest) -> Dict[str, Any]:
    """Same decision path as the Diameter handler, without needing a peer."""
    avps = [
        d.AVP_UTF8(d.AVP_SESSION_ID, request.session_id),
        d.AVP_UTF8(d.AVP_ORIGIN_HOST, "shim.core.local"),
        d.AVP_UTF8(d.AVP_ORIGIN_REALM, "core.local"),
    ]
    if request.destination_realm:
        avps.append(d.AVP_UTF8(d.AVP_DESTINATION_REALM, request.destination_realm))
    else:
        avps.append(d.AVP_UTF8(d.AVP_DESTINATION_REALM, ORIGIN_REALM))
    if request.subscriber:
        avps.append(d.AVP_UTF8(d.AVP_USER_NAME, request.subscriber))
    if request.msisdn:
        avps.append(d.AVP_UTF8(d.AVP_MSISDN, request.msisdn))

    synthetic = d.Message(command_code=d.CMD_PLR, app_id=d.APP_SLG, avps=avps)
    answer = _plr_answer(synthetic)
    result = answer.avp(d.AVP_RESULT_CODE)
    error = answer.avp(d.AVP_ERROR_MESSAGE)
    return {
        "command_code": answer.command_code,
        "app_id": answer.app_id,
        "result_code": result.as_uint32() if result else None,
        "error_message": error.as_string() if error else None,
        "origin_host": ORIGIN_HOST,
    }


@app.get("/scope")
def scope() -> Dict[str, Any]:
    return {
        "implemented": [
            "Diameter SLg over TCP (PLR/PLA, CER/CEA, DWR/DWA)",
            "Management API with SLg status and shim",
        ],
        "not_implemented": [
            "S1AP / S1-MME",
            "S11 (SGW-C), S6a (HSS), SGs (MSC)",
            "MAP LCS SLR/SLA (MSC side)",
            "UE attach, paging, bearer management",
        ],
        "note": "MSC with MAP LCS is not built; see docs/STAGING_AND_CORE_BUILD_PLAN.txt",
    }


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=HTTP_PORT, log_level=os.getenv("LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
