#!/usr/bin/env python3
"""SCP - Service Control Plane (CAMEL/INAP) engine.

Service control layer sitting above the STP/DRA routing plane.
Receives CAMEL/INAP triggers from the STP (via Diameter proxy or SIGTRAN
translation) and applies service logic before routing back to the core.

Integration points:
  - SCP <-> DRA: Diameter (port 3868) for session control
  - SCP <-> STP: SIGTRAN M3UA (port 2905) via DRA translation
  - SCP <-> UDM: REST for subscriber data
"""

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any, Dict, Optional

import redis.asyncio as redis

logger = logging.getLogger("scp")
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))


class ScpConfig:
    def __init__(self):
        self.origin_host = os.getenv("SCP_ORIGIN_HOST", "scp.core.local")
        self.origin_realm = os.getenv("SCP_ORIGIN_REALM", "core.local")
        self.port = int(os.getenv("SCP_PORT", "3868"))
        self.camel_port = int(os.getenv("SCP_CAMEL_PORT", "2905"))
        self.realm = os.getenv("SCP_REALM", "core.local")
        self.dra_host = os.getenv("DRA_HOST", "dra")
        self.dra_port = int(os.getenv("DRA_PORT", "3868"))
        self.redis_host = os.getenv("REDIS_HOST", "redis")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD", "123456")


class SCPServiceControl:
    def __init__(self, config: ScpConfig):
        self.config = config
        self.redis: Optional[redis.Redis] = None
        self._stop = asyncio.Event()
        self.service_logic: Dict[str, Dict[str, Any]] = {}

    async def start(self):
        logger.info("Starting SCP on %s:%d", self.config.origin_host, self.config.port)
        self.redis = redis.Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            password=self.config.redis_password,
            decode_responses=True,
        )
        await self._load_service_logic()
        await self._register_origin()
        logger.info("SCP ready - CAMEL/INAP service control active")

    async def stop(self):
        self._stop.set()
        if self.redis:
            await self.redis.close()
        logger.info("SCP stopped")

    async def _load_service_logic(self):
        """Load CAMEL/INAP service logic from Redis (provisioned by OAM)."""
        # Default stub service logic
        default_logic = {
            "camel:initialDP:*": {
                "action": "continue",
                "interrupt": False,
                "log": True,
            },
            "camel:connect:*": {
                "action": "continue",
                "interrupt": False,
            },
        }
        for trigger, logic in default_logic.items():
            await self.redis.set(trigger, json.dumps(logic))
        self.service_logic = default_logic
        logger.info("Loaded %d service logic entries", len(default_logic))

    async def _register_origin(self):
        await self.redis.set(
            f"scp:origin:{self.config.origin_host}",
            json.dumps({
                "host": self.config.origin_host,
                "realm": self.config.origin_realm,
                "port": self.config.port,
                "camel_port": self.config.camel_port,
            }),
        )

    async def handle_camel_initial_dp(self, trigger: Dict[str, Any]) -> Dict[str, Any]:
        """Process CAMEL initialDP trigger from STP via DRA."""
        called_party = trigger.get("called_party", "")
        key = f"camel:initialDP:{called_party}"
        logic_raw = await self.redis.get(key)
        logic = json.loads(logic_raw) if logic_raw else self.service_logic.get("camel:initialDP:*", {})

        decision = {
            "trigger": "initialDP",
            "called_party": called_party,
            "action": logic.get("action", "continue"),
            "interrupt": logic.get("interrupt", False),
            "scp_origin": self.config.origin_host,
        }
        logger.info("CAMEL initialDP decision: %s", decision)
        return decision

    async def handle_camel_connect(self, trigger: Dict[str, Any]) -> Dict[str, Any]:
        decision = {
            "trigger": "connect",
            "action": "continue",
            "scp_origin": self.config.origin_host,
        }
        logger.info("CAMEL connect decision: %s", decision)
        return decision

    def route_to_stp(self, diameter_msg: Dict[str, Any]) -> Dict[str, Any]:
        """Translate Diameter session control to SIGTRAN M3UA for STP."""
        return {
            "protocol": "sigtran",
            "si": 3,
            "ssn": 8,
            "dpc": "1.1.1",
            "opc": "2.2.2",
            "diameter_origin": diameter_msg.get("origin_host"),
            "action": "forward_to_stp",
        }


async def main():
    config = ScpConfig()
    scp = SCPServiceControl(config)
    await scp.start()

    loop = asyncio.get_running_loop()

    def handle_signal():
        asyncio.create_task(scp.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    try:
        await scp._stop.wait()
    finally:
        await scp.stop()


if __name__ == "__main__":
    asyncio.run(main())
