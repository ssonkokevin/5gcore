#!/usr/bin/env python3
"""
GMLC (Gateway Mobile Location Center) Server
5G Core Engine - Pilot Implementation
Aligned with PaiCore GMLC Documentation (3GPP TS 23.271, 29.171, 29.172)
Supports LCS (Location Services): SLh, SLg, LCS-AP, MAP/CAMEL
"""

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("gmlc")


class GMLCConfig:
    def __init__(self, config_path: str = "/app/config/gmlc.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        
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


class GMLCServer:
    def __init__(self, config: GMLCConfig):
        self.config = config
        self.app = FastAPI(title="5G Core GMLC", version="1.0.0")
        self._setup_routes()
        self._running = False
        self._request_counter = 0

    def _setup_routes(self):
        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "service": "gmlc",
                "version": "1.0.0",
                "interfaces": self.config.interfaces
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

    async def _handle_location_request(self, req: LocationRequest) -> LocationResponse:
        self._request_counter += 1
        request_id = f"lcs-{self._request_counter:06d}"
        
        logger.info(f"Location request {request_id}: MSISDN={req.msisdn}, Type={req.request_type}")
        
        if self.config.privacy.get("check_privacy", True) and not req.privacy_override:
            if self.config.privacy.get("default_privacy_class") != "location_allowed":
                return LocationResponse(
                    request_id=request_id,
                    status="not_authorized",
                    error_code="PRIVACY_VIOLATION",
                    error_message="Location request not authorized by privacy policy"
                )

        if req.request_type == "immediate":
            lat, lon, alt = self._simulate_location_lookup(req.msisdn, req.imsi)
            return LocationResponse(
                request_id=request_id,
                status="success",
                latitude=lat,
                longitude=lon,
                altitude=alt,
                accuracy=req.accuracy or self.config.lcs_config.get("horizontal_accuracy", 50),
                timestamp=asyncio.get_event_loop().time()
            )
        else:
            return LocationResponse(
                request_id=request_id,
                status="pending",
                error_code="DEFERRED_REQUEST",
                error_message="Deferred/periodic request queued for processing"
            )

    async def _get_location_status(self, request_id: str) -> LocationResponse:
        return LocationResponse(
            request_id=request_id,
            status="pending",
            error_code="NOT_IMPLEMENTED",
            error_message="Status polling not yet implemented"
        )

    async def _handle_map_psl(self, payload: dict) -> dict:
        logger.info(f"MAP PSL received: {payload}")
        return {"status": "accepted", "message": "MAP PSL processed"}

    async def _handle_diameter_slh(self, payload: dict) -> dict:
        logger.info(f"Diameter SLh (LIR) received: {payload}")
        msisdn = payload.get("msisdn", "")
        lat, lon, alt = self._simulate_location_lookup(msisdn, None)
        return {
            "command_code": 302,
            "result_code": 2001,
            "session_id": payload.get("session_id", ""),
            "location_info": {
                "latitude": lat,
                "longitude": lon,
                "altitude": alt,
                "accuracy": self.config.lcs_config.get("horizontal_accuracy", 50)
            }
        }

    async def _handle_diameter_slg(self, payload: dict) -> dict:
        logger.info(f"Diameter SLg (SLR) received: {payload}")
        return {
            "command_code": 303,
            "result_code": 2001,
            "session_id": payload.get("session_id", ""),
            "location_estimate": {
                "latitude": 0.0,
                "longitude": 0.0,
                "accuracy": self.config.lcs_config.get("horizontal_accuracy", 50)
            }
        }

    def _simulate_location_lookup(self, msisdn: str, imsi: Optional[str]) -> tuple:
        import hashlib
        hash_val = int(hashlib.md5(msisdn.encode()).hexdigest()[:8], 16)
        lat = 37.7749 + (hash_val % 1000) / 10000.0
        lon = -122.4194 + ((hash_val >> 10) % 1000) / 10000.0
        alt = 10.0 + (hash_val % 100)
        return round(lat, 6), round(lon, 6), round(alt, 1)

    async def start(self):
        self._running = True
        import uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="info"
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
        logger.info(f"Received signal {sig}, shutting down...")
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