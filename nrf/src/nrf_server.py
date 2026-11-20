"""NRF — Network Repository Function (TS 29.510 subset).

Scope: registration, heartbeat, deregistration, discovery and subscription
storage for the custom core. This is not a full 29.510 implementation; it
covers the operations our own NFs call:

  PUT    /nnrf-nfm/v1/nf-instances/{nfInstanceId}      register / replace
  PATCH  /nnrf-nfm/v1/nf-instances/{nfInstanceId}      merge-patch, heartbeat
  DELETE /nnrf-nfm/v1/nf-instances/{nfInstanceId}      deregister
  GET    /nnrf-nfm/v1/nf-instances/{nfInstanceId}      read
  GET    /nnrf-nfm/v1/nf-instances                     list
  GET    /nnrf-disc/v1/nf-instances                    discovery
  POST   /nnrf-nfm/v1/subscriptions                    subscription storage
  DELETE /nnrf-nfm/v1/subscriptions/{subscriptionId}

Storage is Redis when reachable, an in-process dict otherwise. Redis keys
carry a TTL of heartbeatTimer * expiry_factor, so an NF that stops sending
heartbeats disappears without a sweeper.
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("nrf")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
HEARTBEAT_TIMER = int(os.getenv("NRF_HEARTBEAT_TIMER", "30"))
EXPIRY_FACTOR = int(os.getenv("NRF_EXPIRY_FACTOR", "4"))
KEY_PREFIX = os.getenv("NRF_KEY_PREFIX", "nrf:nf:")
SUB_PREFIX = os.getenv("NRF_SUB_PREFIX", "nrf:sub:")

try:
    import redis as redis_lib

    _redis = redis_lib.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    _redis.ping()
    REDIS_AVAILABLE = True
except Exception as exc:  # redis missing or unreachable at startup
    _redis = None
    REDIS_AVAILABLE = False
    log.warning("Redis unavailable (%s); using in-process registry", exc)

_lock = threading.Lock()
_memory: Dict[str, Dict[str, Any]] = {}
_memory_subs: Dict[str, Dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def _put(nf_id: str, doc: Dict[str, Any]) -> None:
    ttl = HEARTBEAT_TIMER * EXPIRY_FACTOR
    if REDIS_AVAILABLE:
        _redis.setex(KEY_PREFIX + nf_id, ttl, json.dumps(doc))
    else:
        with _lock:
            _memory[nf_id] = doc


def _get(nf_id: str) -> Optional[Dict[str, Any]]:
    if REDIS_AVAILABLE:
        raw = _redis.get(KEY_PREFIX + nf_id)
        return json.loads(raw) if raw else None
    with _lock:
        doc = _memory.get(nf_id)
        if not doc:
            return None
        if doc["meta"]["expiresAt"] < _now():
            _memory.pop(nf_id, None)
            return None
        return doc


def _delete(nf_id: str) -> bool:
    if REDIS_AVAILABLE:
        return bool(_redis.delete(KEY_PREFIX + nf_id))
    with _lock:
        return _memory.pop(nf_id, None) is not None


def _all() -> List[Dict[str, Any]]:
    if REDIS_AVAILABLE:
        docs = []
        for key in _redis.scan_iter(match=KEY_PREFIX + "*", count=500):
            raw = _redis.get(key)
            if raw:
                docs.append(json.loads(raw))
        return docs
    cutoff = _now()
    with _lock:
        stale = [k for k, v in _memory.items() if v["meta"]["expiresAt"] < cutoff]
        for k in stale:
            _memory.pop(k, None)
        return list(_memory.values())


def _save_sub(sub_id: str, body: Dict[str, Any]) -> None:
    if REDIS_AVAILABLE:
        _redis.set(SUB_PREFIX + sub_id, json.dumps(body))
    else:
        with _lock:
            _memory_subs[sub_id] = body


def _delete_sub(sub_id: str) -> bool:
    if REDIS_AVAILABLE:
        return bool(_redis.delete(SUB_PREFIX + sub_id))
    with _lock:
        return _memory_subs.pop(sub_id, None) is not None


def _problem(status: int, cause: str, detail: str = "") -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"status": status, "cause": cause, "detail": detail},
    )


def _needs_heartbeat(nf_type: str) -> bool:
    return nf_type not in ("NRF", "NSSF")


def _matches(doc: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    profile = doc["profile"]
    if filters.get("target-nf-type") and profile.get("nfType") != filters["target-nf-type"]:
        return False
    if filters.get("target-nf-instance-id") and profile.get("nfInstanceId") != filters["target-nf-instance-id"]:
        return False
    status = filters.get("nf-status")
    if status and profile.get("nfStatus", "REGISTERED") != status:
        return False
    names = filters.get("service-names")
    if names:
        offered = {s.get("serviceName") for s in profile.get("nfServices", [])}
        if not set(names).issubset(offered):
            return False
    snssais = filters.get("snssais")
    if snssais:
        have = {(s.get("sst"), s.get("sd")) for s in profile.get("snssais", [])}
        if not {(s[0], s[1]) for s in snssais}.issubset(have):
            return False
    plmn = filters.get("plmn")
    if plmn:
        have = {(p.get("mcc"), p.get("mnc")) for p in profile.get("plmnList", [])}
        if (plmn[0], plmn[1]) not in have:
            return False
    return True


class NfProfile(BaseModel):
    nfInstanceId: str
    nfType: str
    nfStatus: Optional[str] = "REGISTERED"
    heartBeatTimer: Optional[int] = None
    nfServices: Optional[List[Dict[str, Any]]] = None
    snssais: Optional[List[Dict[str, Any]]] = None
    plmnList: Optional[List[Dict[str, Any]]] = None

    class Config:
        extra = "allow"


class Subscription(BaseModel):
    nfStatusNotificationUri: str
    reqNfInstanceId: Optional[str] = None
    subscriptionCond: Optional[Dict[str, Any]] = None
    validityTime: Optional[str] = None
    reqNotifEvents: Optional[List[str]] = None

    class Config:
        extra = "allow"


app = FastAPI(title="Hamiltel NRF", version="0.1.0")


def _snssai_pairs(values: Optional[List[str]]) -> List[tuple]:
    pairs = []
    for value in values or []:
        sst, _, sd = value.partition("-")
        pairs.append((sst, sd or None))
    return pairs


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "nrf",
        "registered": len(_all()),
        "storage": "redis" if REDIS_AVAILABLE else "memory",
        "heartbeatTimer": HEARTBEAT_TIMER,
        "spec": "TS 29.510",
    }


@app.put("/nnrf-nfm/v1/nf-instances/{nf_instance_id}")
def register_nf(nf_instance_id: str, profile: NfProfile):
    body = profile.model_dump()
    if body["nfInstanceId"] != nf_instance_id:
        raise _problem(400, "NF_INSTANCE_ID_MISMATCH", "Body nfInstanceId does not match path")
    existing = _get(nf_instance_id)
    body.setdefault("nfStatus", "REGISTERED")
    doc = {
        "profile": body,
        "meta": {
            "created": existing["meta"]["created"] if existing else _now(),
            "lastHeartbeat": _now(),
            "expiresAt": _now() + HEARTBEAT_TIMER * EXPIRY_FACTOR,
        },
    }
    _put(nf_instance_id, doc)
    log.info("NF %s (%s) registered", nf_instance_id, body["nfType"])
    return Response(
        content=json.dumps(body),
        status_code=200 if existing else 201,
        media_type="application/json",
        headers={"Location": f"/nnrf-nfm/v1/nf-instances/{nf_instance_id}"},
    )


@app.patch("/nnrf-nfm/v1/nf-instances/{nf_instance_id}")
async def update_nf(nf_instance_id: str, request: Request):
    doc = _get(nf_instance_id)
    if not doc:
        raise _problem(404, "NF_INSTANCE_NOT_FOUND", nf_instance_id)
    patch = await request.json()
    for key, value in patch.items():
        if key == "nfStatus" and value == "REGISTERED":
            doc["meta"]["lastHeartbeat"] = _now()
        if value is None:
            doc["profile"].pop(key, None)
        else:
            doc["profile"][key] = value
    doc["meta"]["expiresAt"] = _now() + HEARTBEAT_TIMER * EXPIRY_FACTOR
    _put(nf_instance_id, doc)
    return Response(content=json.dumps(doc["profile"]), status_code=200, media_type="application/json")


@app.delete("/nnrf-nfm/v1/nf-instances/{nf_instance_id}")
def deregister_nf(nf_instance_id: str):
    if not _delete(nf_instance_id):
        raise _problem(404, "NF_INSTANCE_NOT_FOUND", nf_instance_id)
    log.info("NF %s deregistered", nf_instance_id)
    return Response(status_code=204)


@app.get("/nnrf-nfm/v1/nf-instances/{nf_instance_id}")
def read_nf(nf_instance_id: str):
    doc = _get(nf_instance_id)
    if not doc:
        raise _problem(404, "NF_INSTANCE_NOT_FOUND", nf_instance_id)
    return doc["profile"]


@app.get("/nnrf-nfm/v1/nf-instances")
def list_nf(nf_type: Optional[str] = Query(None, alias="nf-type")):
    docs = _all()
    if nf_type:
        docs = [d for d in docs if d["profile"].get("nfType") == nf_type]
    return {"nfInstances": [d["profile"] for d in docs]}


@app.get("/nnrf-disc/v1/nf-instances")
def discover(
    target_nf_type: str = Query(..., alias="target-nf-type"),
    requester_nf_type: Optional[str] = Query(None, alias="requester-nf-type"),
    target_nf_instance_id: Optional[str] = Query(None, alias="target-nf-instance-id"),
    service_names: Optional[List[str]] = Query(None, alias="service-names"),
    nf_status: Optional[str] = Query(None, alias="nf-status"),
    mcc: Optional[str] = None,
    mnc: Optional[str] = None,
):
    filters = {
        "target-nf-type": target_nf_type,
        "target-nf-instance-id": target_nf_instance_id,
        "service-names": service_names,
        "nf-status": nf_status,
        "plmn": (mcc, mnc) if mcc and mnc else None,
    }
    if requester_nf_type and requester_nf_type == target_nf_type and not target_nf_instance_id:
        filters["target-nf-instance-id"] = None
    matches = [d["profile"] for d in _all() if _matches(d, filters)]
    if not matches:
        raise _problem(404, "NF_INSTANCE_NOT_FOUND", f"No {target_nf_type} matches")
    log.info("Discovery %s for %s -> %d match(es)", target_nf_type, requester_nf_type, len(matches))
    return {"nfInstances": matches, "validityPeriod": HEARTBEAT_TIMER}


@app.post("/nnrf-nfm/v1/subscriptions")
def create_subscription(sub: Subscription):
    sub_id = uuid.uuid4().hex
    body = sub.model_dump()
    body["subscriptionId"] = sub_id
    _save_sub(sub_id, body)
    return Response(
        content=json.dumps(body),
        status_code=201,
        media_type="application/json",
        headers={"Location": f"/nnrf-nfm/v1/subscriptions/{sub_id}"},
    )


@app.delete("/nnrf-nfm/v1/subscriptions/{subscription_id}")
def delete_subscription(subscription_id: str):
    if not _delete_sub(subscription_id):
        raise _problem(404, "SUBSCRIPTION_NOT_FOUND", subscription_id)
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("NRF_HOST", "0.0.0.0"),
        port=int(os.getenv("NRF_PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
