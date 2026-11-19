"""Custom LMF - Location Management Function (TS 29.572).

There is no positioning without a measurement source. This service speaks the
Nlmf_Location API and forwards to whatever measurement source the operator
configures (LMF_PROVIDER_URL). With nothing configured it answers
501 NO_POSITIONING_SOURCE - it never invents coordinates.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from corelib.http import TransportError, request_json  # noqa: E402
from corelib.nrf_client import NrfClient, service as nf_service  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("lmf")

HOST = os.getenv("LMF_HOST", "0.0.0.0")
PORT = int(os.getenv("LMF_PORT", "8003"))
PUBLIC_HOST = os.getenv("LMF_PUBLIC_HOST", "lmf.core.local")
IPV4 = os.getenv("LMF_IPV4", "")
NRF_URL = f"http://{os.getenv('NRF_ADDR', 'custom-nrf')}:{os.getenv('NRF_PORT', '8000')}"
PROVIDER_URL = os.getenv("LMF_PROVIDER_URL", "").strip()
PROVIDER_TIMEOUT = float(os.getenv("LMF_PROVIDER_TIMEOUT", "8"))
PROVIDER_TOKEN = os.getenv("LMF_PROVIDER_TOKEN", "")

nf = NrfClient(
    base_url=NRF_URL,
    nf_instance_id=os.getenv("LMF_NF_INSTANCE_ID", f"lmf-{uuid.uuid4()}"),
    nf_type="LMF",
    nf_services=[nf_service("nlmf-loc", "nlmf-loc-1", PORT)],
    fqdn=PUBLIC_HOST,
    ipv4=IPV4,
    heartbeat_seconds=int(os.getenv("NRF_HEARTBEAT_TIMER", "30")),
)


class LocationQoS(BaseModel):
    hResponseTime: Optional[str] = None
    horizontalAccuracy: Optional[int] = None
    verticalAccuracy: Optional[int] = None


class DetermineLocationRequest(BaseModel):
    supi: Optional[str] = None
    ueLocation: Optional[Dict[str, Any]] = None
    locationQoS: Optional[LocationQoS] = None
    supportedGADShapes: Optional[List[str]] = None
    source: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    nf.start()
    if not PROVIDER_URL:
        logger.warning("LMF_PROVIDER_URL is empty: all location requests will answer 501")
    yield
    nf.stop()


app = FastAPI(title="Hamiltel LMF", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok" if nf.registered else "degraded",
        "service": "lmf",
        "provider": "http" if PROVIDER_URL else "none",
        "provider_url": PROVIDER_URL or None,
        "registry": nf.status(),
    }


@app.post("/nlmf-loc/v1/determine-location")
def determine_location(req: DetermineLocationRequest):
    if not PROVIDER_URL:
        raise HTTPException(
            status_code=501,
            detail={
                "cause": "NO_POSITIONING_SOURCE",
                "detail": "set LMF_PROVIDER_URL to an LCS measurement source; "
                          "this LMF does not simulate positions",
            },
        )

    payload = req.model_dump(exclude_none=True)
    headers = {"Authorization": f"Bearer {PROVIDER_TOKEN}"} if PROVIDER_TOKEN else {}
    try:
        status, result = request_json(
            "POST", PROVIDER_URL, payload, headers=headers, timeout=PROVIDER_TIMEOUT
        )
    except TransportError as exc:
        raise HTTPException(
            status_code=504,
            detail={"cause": "PROVIDER_UNREACHABLE", "detail": str(exc)},
        ) from exc

    if status != 200:
        raise HTTPException(
            status_code=502,
            detail={"cause": "PROVIDER_ERROR", "provider_status": status,
                    "provider_body": str(result)[:300]},
        )
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=502,
            detail={"cause": "PROVIDER_INVALID_RESPONSE", "detail": "not a JSON object"},
        )

    latitude = result.get("latitude")
    longitude = result.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise HTTPException(
            status_code=502,
            detail={"cause": "PROVIDER_INVALID_RESPONSE",
                    "detail": "latitude and longitude are required"},
        )
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise HTTPException(
            status_code=502,
            detail={"cause": "PROVIDER_INVALID_RESPONSE", "detail": "coordinate out of range"},
        )

    return {
        "supi": req.supi,
        "locationEstimate": {
            "geographicArea": {
                "shape": "POINT",
                "point": {"lat": latitude, "lon": longitude},
                "accuracy": result.get("accuracy"),
            }
        },
        "ageOfLocationEstimate": result.get("age_seconds"),
        "timestamp": result.get("timestamp"),
        "provider": result.get("provider", "configured"),
    }


@app.post("/nlmf-loc/v1/location-context-transfer")
def location_context_transfer(body: Dict[str, Any]):
    raise HTTPException(
        status_code=501,
        detail={"cause": "NOT_IMPLEMENTED", "detail": "UE positioning context transfer is not built"},
    )


@app.post("/nlmf-loc/v1/upiuci/{supi}/cancel-location")
def cancel_location(supi: str):
    raise HTTPException(
        status_code=501,
        detail={"cause": "DEFERRED_LOCATION_NOT_IMPLEMENTED", "supi": supi},
    )


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level=os.getenv("LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
