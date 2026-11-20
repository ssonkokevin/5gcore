"""NRF registration and discovery client (TS 29.510 subset).

Registers the NF, sends heartbeats on the NRF's `heartbeatTimer`, and
de-registers on shutdown. Failures never stop the calling service: they are
recorded in status() so /health can report them honestly.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from corelib.http import TransportError, request_json, with_query

logger = logging.getLogger("nrf-client")


class NrfClient:
    def __init__(
        self,
        base_url: str,
        nf_instance_id: str,
        nf_type: str,
        nf_services: List[Dict[str, Any]],
        fqdn: str = "",
        ipv4: str = "",
        plmn: Optional[Dict[str, str]] = None,
        heartbeat_seconds: int = 30,
        timeout: float = 3.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.nf_instance_id = nf_instance_id
        self.nf_type = nf_type
        self.nf_services = nf_services
        self.fqdn = fqdn
        self.ipv4 = ipv4
        self.plmn = plmn
        self.heartbeat_seconds = max(5, heartbeat_seconds)
        self.timeout = timeout

        self.registered = False
        self.last_heartbeat: Optional[float] = None
        self.last_error: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- profile ------------------------------------------------------------
    def profile(self) -> Dict[str, Any]:
        profile: Dict[str, Any] = {
            "nfInstanceID": self.nf_instance_id,
            "nfType": self.nf_type,
            "nfStatus": "REGISTERED",
            "nfServices": self.nf_services,
        }
        if self.ipv4:
            profile["ipv4Addresses"] = [self.ipv4]
        if self.fqdn:
            profile["fqdn"] = self.fqdn
        if self.plmn:
            profile["plmnList"] = [self.plmn]
        return profile

    # -- operations ---------------------------------------------------------
    def register(self) -> bool:
        url = f"{self.base_url}/nnrf-nfm/v1/nf-instances/{self.nf_instance_id}"
        try:
            status, body = request_json("PUT", url, self.profile(), timeout=self.timeout)
        except TransportError as exc:
            self._fail(f"register: {exc}")
            return False
        if status in (200, 201):
            self.registered = True
            self.last_heartbeat = time.time()
            self.last_error = None
            logger.info("%s registered with NRF as %s", self.nf_type, self.nf_instance_id)
            return True
        self._fail(f"register: HTTP {status} {str(body)[:200]}")
        return False

    def heartbeat(self) -> bool:
        url = f"{self.base_url}/nnrf-nfm/v1/nf-instances/{self.nf_instance_id}"
        try:
            status, _ = request_json(
                "PATCH",
                url,
                {"nfStatus": "REGISTERED"},
                headers={"Content-Type": "application/merge-patch+json"},
                timeout=self.timeout,
            )
        except TransportError as exc:
            self.registered = False
            self._fail(f"heartbeat: {exc}")
            return False
        if status in (200, 204):
            self.registered = True
            self.last_heartbeat = time.time()
            self.last_error = None
            return True
        self.registered = False
        self._fail(f"heartbeat: HTTP {status}")
        return False

    def deregister(self) -> bool:
        url = f"{self.base_url}/nnrf-nfm/v1/nf-instances/{self.nf_instance_id}"
        try:
            status, _ = request_json("DELETE", url, timeout=self.timeout)
        except TransportError as exc:
            self._fail(f"deregister: {exc}")
            return False
        self.registered = False
        return status in (200, 204, 404)

    def discover(self, nf_type: str, service_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        params: Dict[str, str] = {"target-nf-type": nf_type}
        if service_names:
            params["service-names"] = ",".join(service_names)
        url = with_query(f"{self.base_url}/nnrf-disc/v1/nf-instances", params)
        try:
            status, body = request_json("GET", url, timeout=self.timeout)
        except TransportError as exc:
            self._fail(f"discover {nf_type}: {exc}")
            return []
        if status == 404:
            return []
        if status != 200:
            self._fail(f"discover {nf_type}: HTTP {status}")
            return []
        if isinstance(body, dict):
            return body.get("nfInstances", []) or []
        return []

    # -- background loop ----------------------------------------------------
    def _fail(self, message: str) -> None:
        self.last_error = message
        logger.warning("%s: %s", self.nf_type, message)

    def _loop(self) -> None:
        retry_seconds = 5
        while not self._stop.is_set():
            if not self.registered:
                if self.register():
                    retry_seconds = 5
                else:
                    self._stop.wait(retry_seconds)
                    retry_seconds = min(retry_seconds * 2, 60)
                    continue
            self._stop.wait(self.heartbeat_seconds)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name=f"nrf-{self.nf_type}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.timeout)
            self._thread = None
        if self.registered:
            self.deregister()

    def status(self) -> Dict[str, Any]:
        return {
            "nrf": self.base_url,
            "nf_instance_id": self.nf_instance_id,
            "registered": self.registered,
            "last_heartbeat_age_s": (
                round(time.time() - self.last_heartbeat, 1) if self.last_heartbeat else None
            ),
            "last_error": self.last_error,
        }


def service(
    name: str,
    instance_id: str,
    port: int,
    api_version: str = "v1",
    scheme: str = "http",
) -> Dict[str, Any]:
    """Build an NFService entry for an HTTP API."""
    return {
        "serviceInstanceID": instance_id,
        "serviceName": name,
        "versions": [{"apiVersionInUri": api_version, "apiFullVersion": "1.0.0"}],
        "scheme": scheme,
        "nfServiceStatus": "REGISTERED",
        "ipEndPoints": [{"transport": "TCP", "port": port}],
    }
