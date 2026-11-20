#!/usr/bin/env python3
"""GMLC — Gateway Mobile Location Centre.

Business, privacy, routing and record layer for LCS. This process never
measures a position; measurements belong to E-SMLC/LMF. Until a real
leakage source (SLg, SLh or MAP) is configured, every request is answered
with an explicit failure — never with a synthesised position.
"""

import asyncio
import json
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("gmlc")

REQUEST_TTL_SECONDS = int(os.getenv("GMLC_REQUEST_TTL", "3600"))
REDIS_KEY_PREFIX = os.getenv("GMLC_REQUEST_PREFIX", "gmlc:req:")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class GMLCConfig:
    def __init__(self, config_path: str = "/app/config/gmlc.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f) or {}

        gmlc_cfg = self.config.get("gmlc", {})
        self.host = gmlc_cfg.get("host", "0.0.0.0")
        self.port = gmlc_cfg.get("port", 8082)
        self.realm = gmlc_cfg.get("realm", "core.local")
        self.origin_host = gmlc_cfg.get("origin_host", "gmlc.core.local")
        self.origin_realm = gmlc_cfg.get("origin_realm", "core.local")

        self.db_config = self.config.get("database", {})
        self.redis_config = self.config.get("redis", {})
        self.map_config = self.config.get("map", {})
        self.diameter_config = self.config.get("diameter", {})
        self.lcs_config = self.config.get("lcs", {})
        self.interfaces = self.config.get("interfaces", {})
        self.privacy = self.config.get("privacy", {})
        self.external_gmlc = self.config.get("external_gmlc", {})


class RequestStore:
    """Request state, Redis-backed so status polling survives a restart."""

    def __init__(self, redis_config: dict):
        self._redis = None
        self._memory = {}
        import socket

        host = redis_config.get("host", "redis")
        port = int(redis_config.get("port", 6379))
        try:
            socket.create_connection((host, port), timeout=0.5).close()
        except OSError as exc:
            logger.warning("Request store: memory (redis unreachable: %s)", exc)
            return
        try:
            import redis as redis_lib

            client = redis_lib.Redis(
                host=host,
                port=port,
                password=redis_config.get("password") or os.getenv("REDIS_PASSWORD"),
                socket_connect_timeout=0.5,
                socket_timeout=2,
                retry_on_timeout=False,
                decode_responses=True,
            )
            client.ping()
            self._redis = client
            logger.info("Request store: redis")
        except Exception as exc:
            logger.warning("Request store: memory (redis unavailable: %s)", exc)

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    def put(self, request_id: str, record: dict) -> None:
        payload = json.dumps(record)
        if self._redis:
            self._redis.setex(REDIS_KEY_PREFIX + request_id, REQUEST_TTL_SECONDS, payload)
        else:
            self._memory[request_id] = payload

    def get(self, request_id: str) -> Optional[dict]:
        if self._redis:
            raw = self._redis.get(REDIS_KEY_PREFIX + request_id)
        else:
            raw = self._memory.get(request_id)
        return json.loads(raw) if raw else None


class LocationRequest(BaseModel):
    msisdn: str = Field(..., description="MSISDN of target UE")
    imsi: Optional[str] = Field(None, description="IMSI of target UE")
    request_type: str = Field("immediate", pattern="^(immediate|deferred|periodic)$")
    accuracy: Optional[int] = Field(50, description="Horizontal accuracy in meters")
    response_time: Optional[int] = Field(20, description="Max response time in seconds")
    lcs_client_type: Optional[str] = Field("emergency_services")
    privacy_override: bool = False


class LocationResponse(BaseModel):
    request_id: str
    status: str = Field(pattern="^(success|failed|pending|not_authorized)$")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    accuracy: Optional[int] = None
    timestamp: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class Denial:
    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


class GMLCServer:
    def __init__(self, config: GMLCConfig):
        self.config = config
        self.app = FastAPI(title="Hamiltel GMLC", version="1.0.0")
        self.store = RequestStore(config.redis_config)
        self._setup_routes()
        self._running = False

    def _setup_routes(self):
        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "service": "gmlc",
                "version": "1.0.0",
                "interfaces": self.config.interfaces,
                "request_store": self.store.backend,
            }

        @self.app.post("/lcs/location-request", response_model=LocationResponse)
        async def location_request(req: LocationRequest):
            return await self._handle_location_request(req)

        @self.app.get("/lcs/location-request/{request_id}", response_model=LocationResponse)
        async def get_location_status(request_id: str):
            return await self._get_location_status(request_id)

        @self.app.post("/map/psl")
        async def map_psl(request: Request):
            return await self._handle_map_psl(await request.json())

        @self.app.post("/diameter/slh")
        async def diameter_slh(request: Request):
            return await self._handle_diameter_slh(await request.json())

        @self.app.post("/diameter/slg")
        async def diameter_slg(request: Request):
            return await self._handle_diameter_slg(await request.json())

    def _privacy_decision(self, req: LocationRequest) -> Optional[Denial]:
        privacy = self.config.privacy
        if not privacy.get("check_privacy", True):
            return None
        if req.privacy_override:
            if privacy.get("override_privacy_emergency", False) and req.lcs_client_type == "emergency_services":
                return None
            return Denial(
                "PRIVACY_OVERRIDE_REJECTED",
                "Privacy override not permitted for this client type",
            )
        if privacy.get("default_privacy_class") != "location_allowed":
            return Denial(
                "PRIVACY_VIOLATION",
                "Location request not authorized by privacy policy",
            )
        return None

    async def _handle_location_request(self, req: LocationRequest) -> LocationResponse:
        request_id = f"lcs-{uuid.uuid4().hex[:12]}"
        logger.info("Location request %s: MSISDN=%s type=%s", request_id, req.msisdn, req.request_type)

        denial = self._privacy_decision(req)
        if denial:
            return self._finalise(
                LocationResponse(
                    request_id=request_id,
                    status="not_authorized",
                    timestamp=_now_iso(),
                    error_code=denial.code,
                    error_message=denial.message,
                )
            )

        if req.request_type == "immediate":
            return self._finalise(
                LocationResponse(
                    request_id=request_id,
                    status="failed",
                    timestamp=_now_iso(),
                    error_code="NO_LCS_SOURCE",
                    error_message=(
                        "No LCS source configured. SLg, SLh and MAP are disabled in "
                        "gmlc.yaml; configure a serving node before enabling LCS."
                    ),
                )
            )

        return self._finalise(
            LocationResponse(
                request_id=request_id,
                status="failed",
                timestamp=_now_iso(),
                error_code="NO_LCS_SOURCE",
                error_message=(
                    "Deferred/periodic requests need an E-SMLC or LMF to schedule; "
                    "none is configured, so the request was not queued."
                ),
            )
        )

    def _finalise(self, response: LocationResponse) -> LocationResponse:
        self.store.put(response.request_id, response.model_dump())
        return response

    async def _get_location_status(self, request_id: str) -> LocationResponse:
        record = self.store.get(request_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": 404,
                    "cause": "REQUEST_NOT_FOUND",
                    "detail": f"No location request {request_id} in the last {REQUEST_TTL_SECONDS}s",
                },
            )
        return LocationResponse(**record)

    async def _handle_map_psl(self, payload: dict) -> dict:
        logger.warning("MAP PSL received but the MAP stack is not configured: %s", payload)
        return {
            "status": "rejected",
            "error_code": "MAP_STACK_NOT_CONFIGURED",
            "error_message": "Provide-subscriber-location requires an STP-connected MAP stack; none is configured",
        }

    async def _handle_diameter_slh(self, payload: dict) -> dict:
        logger.warning("SLh RIR received on the HTTP shim; no SCTP listener is configured")
        return {
            "transport": "http-shim",
            "command_code": 8388622,
            "result_code": 5010,
            "session_id": payload.get("session_id", ""),
            "error_message": "SLh not implemented — no RIR/RIA server available",
        }

    async def _handle_diameter_slg(self, payload: dict) -> dict:
        logger.warning("SLg PLR received on the HTTP shim; no SCTP listener is configured")
        return {
            "transport": "http-shim",
            "command_code": 8388620,
            "result_code": 5010,
            "session_id": payload.get("session_id", ""),
            "error_message": "SLg not implemented — no PLR/PLA server available",
        }

    async def start(self):
        self._running = True
        import uvicorn

        config = uvicorn.Config(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def stop(self):
        self._running = False
        logger.info("GMLC server stopping...")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GMLC starting up...")
    yield
    logger.info("GMLC shutting down...")


async def main():
    config_path = os.getenv("GMLC_CONFIG", "/app/config/gmlc.yaml")
    config = GMLCConfig(config_path)

    server = GMLCServer(config)

    def signal_handler(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        asyncio.create_task(server.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
