"""DRA - Diameter Routing Agent engine.

Mirrors production STP/DRA patterns from srg_db.sql schema:
  tbl_dra_local, tbl_dra_peer, tbl_dra_peer_set, tbl_dra_route,
  tbl_dra_translate, tbl_m3ua_link, tbl_m3ua_as, tbl_stp_route.

Routes Diameter (Cx/Dx/S6a/SLh/SLg) messages between peers, with M3UA/SIGTRAN
translation for interworking with the STP.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("dra")
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))


# ---------------------------------------------------------------------------
# Configuration models (matching production dra.json format)
# ---------------------------------------------------------------------------
class LocalConfig(BaseModel):
    ip: str
    port: int
    realm: str
    host: str
    name: str
    AppID: List[int] = []
    protocol: str = "sctp"
    vendorID: int = 10415
    productName: str = "Open5GS-DRA"


class PeerConfig(BaseModel):
    ip: str = ""
    peer_id: int
    peer_set: str
    name: str
    AppID: List[int] = []
    group: str = ""
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    remote_type: str = "server"
    local_host: str
    local_realm: str
    remote_host: str
    remote_realm: str
    protocol: str = "sctp"
    vendorID: int = 10415
    productName: str = ""
    enable: bool = True
    priority: int = 1
    watchdog_interval: int = 5
    retransmit_timer: int = 10
    max_retransmit: int = 3


class PeerSetConfig(BaseModel):
    peer_set_name: str
    mode: str = "redundancy"


class RouteConfig(BaseModel):
    name: str
    route_id: int
    origin_peer_set: str
    dest_peer_set: str
    imsi: str = ""
    msisdn: str = ""
    impu: str = ""
    impi: str = ""
    origin_realm: str = ""
    origin_host: str = ""
    destination_host: str = ""
    destination_realm: str = ""
    priority: int = 1
    application_id: str = ""


class CmmConfig(BaseModel):
    log_level: str = "info"
    log_file: str = "/var/log/srg/dra.log"
    configLocal: int = 0
    profile_listen: str = "41100"


class DraConfig(BaseModel):
    local: List[LocalConfig] = []
    peer: List[PeerConfig] = []
    peer_set: List[PeerSetConfig] = []
    route: List[RouteConfig] = []
    translate: Optional[Dict] = None
    cmm_cfg: CmmConfig = CmmConfig()


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
            p.name: PeerState(p) for p in config.peer
        }
        self.routes: List[RouteConfig] = config.route
        self.peer_sets: Dict[str, PeerSetConfig] = {
            ps.peer_set_name: ps for ps in config.peer_set
        }
        self.local_endpoints: List[LocalConfig] = config.local
        self.redis: Optional[redis.Redis] = None
        self._stop = asyncio.Event()

    async def start(self):
        local = self.config.local[0] if self.config.local else None
        host = local.host if local else "dra.core.local"
        port = local.port if local else 3868
        logger.info("Starting DRA on %s:%d", host, port)
        
        self.redis = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD"),
            decode_responses=True,
        )
        await self._load_routes_from_db()
        await self._register_origin()
        logger.info("DRA ready with %d peers, %d routes", len(self.peers), len(self.routes))

    async def stop(self):
        self._stop.set()
        if self.redis:
            await self.redis.close()
        logger.info("DRA stopped")

    async def _load_routes_from_db(self):
        """Mirror tbl_dra_route into Redis; fall back to config routes."""
        logger.info("Loading %d routes from config", len(self.routes))
        for r in self.routes:
            key = f"dra:route:{r.dest_peer_set}:{r.application_id}:{r.imsi}"
            await self.redis.set(key, r.model_dump_json())

    async def _register_origin(self):
        local = self.config.local[0] if self.config.local else None
        if local:
            await self.redis.set(
                f"dra:origin:{local.host}",
                json.dumps({
                    "host": local.host,
                    "realm": local.realm,
                    "port": local.port,
                    "vendor_id": local.vendorID,
                    "product_name": local.productName,
                }),
            )

    def route_message(self, dest_peer_set: str, app_id: str, imsi: str = "") -> Optional[RouteConfig]:
        for r in self.routes:
            if (r.dest_peer_set == dest_peer_set
                    and r.application_id == app_id
                    and (not r.imsi or r.imsi == imsi or imsi.startswith(r.imsi.replace("*", "")))):
                return r
        return None

    def get_peers_for_set(self, peer_set_name: str) -> List[PeerConfig]:
        return [p for p in self.config.peer if p.peer_set == peer_set_name and p.enable]

    def translate_m3ua_to_diameter(self, si: int, ssn: int) -> Dict[str, Any]:
        if si == 3 and ssn == 8:
            return {
                "application_id": 16777216,
                "action": "translate",
            }
        return {}

    def translate_diameter_to_m3ua(self, app_id: int, cmd_code: int) -> Dict[str, Any]:
        if app_id == 16777216 and cmd_code == 272:
            return {
                "si": 3,
                "ssn": 8,
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
