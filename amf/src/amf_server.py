"""Custom AMF - Access and Mobility Management Function.

Scope of this service, stated honestly:

  implemented   NRF registration/heartbeat with NF type AMF
                Namf_Location ProvideLocationInfo proxied to the LMF
                Explicit 501 causes where the procedure needs NGAP or NAS

  not built     N2/NGAP (SCTP, ASN.1), N1/NAS security, N11/N14/N15 signalling,
                UE context storage. A UE cannot attach through this process.
                For attach testing use the free5gc profile, or finish NGAP here.

The value of this service today is the service-based side: GMLC -> AMF ->
LMF discovery and location request forwarding, with failure causes that do not
pretend a position exists.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from corelib.http import TransportError, request_json  # noqa: E402
from corelib.nrf_client import NrfClient, service as nf_service  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("amf")

HOST = os.getenv("AMF_HOST", "0.0.0.0")
PORT = int(os.getenv("AMF_PORT", "8001"))
PUBLIC_HOST = os.getenv("AMF_PUBLIC_HOST", "amf.core.local")
IPV4 = os.getenv("AMF_IPV4", "")
NRF_URL = f"http://{os.getenv('NRF_ADDR', 'custom-nrf')}:{os.getenv('NRF_PORT', '8000')}"
PLMN = {
    "mcc": os.getenv("PLMN_MCC", "641"),
    "mnc": os.getenv("PLMN_MNC", "020"),
}
LMF_TIMEOUT = float(os.getenv("AMF_LMF_TIMEOUT", "5"))
DISCOVERY_TTL = float(os.getenv("AMF_DISCOVERY_TTL", "10"))

nf = NrfClient(
    base_url=NRF_URL,
    nf_instance_id=os.getenv("AMF_NF_INSTANCE_ID", f"amf-{uuid.uuid4()}"),
    nf_type="AMF",
    nf_services=[
        nf_service("namf-loc", "namf-loc-1", PORT),
        nf_service("namf-comm", "namf-comm-1", PORT),
    ],
    fqdn=PUBLIC_HOST,
    ipv4=IPV4,
    plmn=PLMN,
    heartbeat_seconds=int(os.getenv("NRF_HEARTBEAT_TIMER", "30")),
)

_lmf_cache: Dict[str, Any] = {"url": None, "at": 0.0}
_cache_lock = threading.Lock()


class LocationQoS(BaseModel):
    hResponseTime: Optional[str] = None
    horizontalAccuracy: Optional[int] = None
    verticalAccuracy: Optional[int] = None
    responseTime: Optional[str] = None


class ProvideLocInfoRequest(BaseModel):
    locationQoS: Optional[LocationQoS] = None
    supportedGADShapes: Optional[List[str]] = None
    ueLcsCapability: Optional[Dict[str, Any]] = None
    lcsServiceType: Optional[int] = None
    lcsClientType: Optional[str] = Field(None, description="emergency, value_added, ...")
    priority: Optional[str] = None


def discover_lmf_url() -> Optional[str]:
    now = time.time()
    with _cache_lock:
        if _lmf_cache["url"] and now - _lmf_cache["at"] < DISCOVERY_TTL:
            return _lmf_cache["url"]

    instances = nf.discover("LMF", ["nlmf-loc"])
    for instance in instances:
        for svc in instance.get("nfServices", []):
            if svc.get("serviceName") != "nlmf-loc":
                continue
            for endpoint in svc.get("ipEndPoints", []):
                host = endpoint.get("ipv4Address") or instance.get("fqdn")
                port = endpoint.get("port")
                if host and port:
                    url = f"http://{host}:{port}"
                    with _cache_lock:
                        _lmf_cache.update({"url": url, "at": now})
                    return url
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    nf.start()
    logger.info("AMF service-based API on %s:%s", HOST, PORT)
    yield
    nf.stop()


app = FastAPI(title="Hamiltel AMF", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok" if nf.registered else "degraded",
        "service": "amf",
        "mode": "service-based only",
        "n2_ngap": "not implemented",
        "n1_nas": "not implemented",
        "ue_attach": False,
        "plmn": PLMN,
        "registry": nf.status(),
    }


@app.get("/n2/status")
def n2_status():
    return {
        "transport": "sctp",
        "listening": False,
        "reason": "NGAP ASN.1 and SCTP association management are not implemented in this process",
    }


@app.post("/namf-loc/v1/{supi}/provide-loc-info")
def provide_loc_info(supi: str, req: ProvideLocInfoRequest):
    """TS 29.518 §5.2.2.2: the AMF asks the LMF and relays the answer."""
    lmf_url = discover_lmf_url()
    if not lmf_url:
        raise HTTPException(
            status_code=503,
            detail={"cause": "LMF_NOT_REGISTERED", "detail": "no LMF instance with nlmf-loc in the NRF"},
        )

    payload = {"supi": supi, "source": "amf", **req.model_dump(exclude_none=True)}
    try:
        status, body = request_json(
            "POST", f"{lmf_url}/nlmf-loc/v1/determine-location", payload, timeout=LMF_TIMEOUT
        )
    except TransportError as exc:
        logger.warning("LMF %s unreachable: %s", lmf_url, exc)
        raise HTTPException(
            status_code=504,
            detail={"cause": "LMF_UNREACHABLE", "detail": str(exc)},
        ) from exc

    if status == 200:
        return {"supi": supi, "locationInfo": body}
    raise HTTPException(
        status_code=status if status >= 400 else 502,
        detail={"cause": "LMF_ERROR", "lmf_status": status, "lmf_body": body},
    )


@app.post("/namf-loc/v1/{supi}/event-notify")
def event_notify(supi: str, body: Dict[str, Any]):
    raise HTTPException(
        status_code=501,
        detail={
            "cause": "DEFERRED_LOCATION_NOT_IMPLEMENTED",
            "detail": "periodic and event-triggered location need NGAP/NAS event reporting",
            "supi": supi,
        },
    )


@app.post("/namf-loc/v1/{supi}/cancel-pos-info")
def cancel_pos_info(supi: str, body: Optional[Dict[str, Any]] = None):
    raise HTTPException(
        status_code=501,
        detail={"cause": "DEFERRED_LOCATION_NOT_IMPLEMENTED", "supi": supi},
    )


@app.post("/namf-comm/v1/ue-contexts/{supi}/n1-n2-messages")
def n1_n2_messages(supi: str, body: Dict[str, Any]):
    raise HTTPException(
        status_code=501,
        detail={"cause": "NAS_NOT_IMPLEMENTED", "detail": "N1/N2 message transfer requires NAS and NGAP", "supi": supi},
    )


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level=os.getenv("LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
