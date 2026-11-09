"""DRA - Diameter Routing Agent engine.

Mirrors production STP/DRA patterns from srg_db.sql schema:
  tbl_dra_local, tbl_dra_peer, tbl_dra_peer_set, tbl_dra_route,
  tbl_dra_translate, tbl_m3ua_link, tbl_m3ua_as, tbl_stp_route.

Routes Diameter (Cx/Dx/S6a) messages between peers, with M3UA/SIGTRAN
translation for interworking with the STP.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any, Dict, Optional

import redis.asyncio as redis
import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("dra")
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------
class PeerConfig(BaseModel):
    name: str
    host: str
    port: int
    realm: str
    protocol: str = "diameter"


class RouteConfig(BaseModel):
    destination_realm: str
    application_id: int
    command_code: int
    peer: str
    action: str = "route"  # route | proxy | translate


class TranslationConfig(BaseModel):
    m3ua_to_diameter: Dict[str, Any]
    diameter_to_m3ua: Dict[str, Any]


class DraConfig(BaseModel):
    origin_host: str
    origin_realm: str
    product_name: str
    vendor_id: int
    port: int
    realm: str
    db: Dict[str, Any]
    redis: Dict[str, Any]
    peers: list[PeerConfig]
    routes: list[RouteConfig]
    translation: TranslationConfig
    log_level: str = "INFO"


def load_config(path: str = "/app/config/dra.json") -> DraConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return DraConfig(**raw)


# ---------------------------------------------------------------------------
# Peer / route state
# ---------------------------------------------------------------------------
class PeerState:
    def __init__(self, peer: PeerConfig):
        self.peer = peer
        self.connected: bool = False
        self.last_seen: float = 0.0


class DRAEngine:
    def __init__(self, config: DraConfig):
        self.config = config
        self.peers: Dict[str, PeerState] = {
            p.name: PeerState(p) for p in config.peers
        }
        self.routes: list[RouteConfig] = config.routes
        self.redis: Optional[redis.Redis] = None
        self._stop = asyncio.Event()

    async def start(self):
        logger.info("Starting DRA on %s:%d", self.config.origin_host, self.config.port)
        self.redis = redis.Redis(
            host=self.config.redis["host"],
            port=self.config.redis["port"],
            password=self.config.redis["password"],
            decode_responses=True,
        )
        await self._load_routes_from_db()
        await self._register_origin()
        logger.info("DRA ready")

    async def stop(self):
        self._stop.set()
        if self.redis:
            await self.redis.close()
        logger.info("DRA stopped")

    async def _load_routes_from_db(self):
        """Mirror tbl_dra_route into memory; fall back to config routes."""
        logger.info("Loading %d routes from config", len(self.routes))
        for r in self.routes:
            await self.redis.set(
                f"dra:route:{r.destination_realm}:{r.application_id}:{r.command_code}",
                r.model_dump_json(),
            )

    async def _register_origin(self):
        await self.redis.set(
            f"dra:origin:{self.config.origin_host}",
            json.dumps({
                "host": self.config.origin_host,
                "realm": self.config.origin_realm,
                "port": self.config.port,
            }),
        )

    def route_message(self, dest_realm: str, app_id: int, cmd_code: int) -> Optional[RouteConfig]:
        key = f"dra:route:{dest_realm}:{app_id}:{cmd_code}"
        # sync lookup via redis is async; here we do a config fallback
        for r in self.routes:
            if (r.destination_realm == dest_realm
                    and r.application_id == app_id
                    and r.command_code == cmd_code):
                return r
        return None

    def translate_m3ua_to_diameter(self, si: int, ssn: int) -> Dict[str, Any]:
        t = self.config.translation.m3ua_to_diameter
        if si == t.get("si") and ssn == t.get("ssn"):
            return {
                "application_id": int(t.get("target_application", 0)),
                "action": "translate",
            }
        return {}

    def translate_diameter_to_m3ua(self, app_id: int, cmd_code: int) -> Dict[str, Any]:
        t = self.config.translation.diameter_to_m3ua
        if app_id == int(t.get("application_id", 0)) and cmd_code == int(t.get("command_code", 0)):
            return {
                "si": int(t.get("target_si", 0)),
                "ssn": int(t.get("target_ssn", 0)),
                "action": "translate",
            }
        return {}


async def main():
    config = load_config()
    engine = DRAEngine(config)
    await engine.start()

    loop = asyncio.get_running_loop()

    def handle_signal():
        asyncio.create_task(engine.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    try:
        await engine._stop.wait()
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
