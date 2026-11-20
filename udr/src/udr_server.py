"""UDR — Unified Data Repository (Nudr_DataRepository, TS 29.504 / TS 29.505).

Scope, stated honestly:

  implemented   Nudr_DataRepository authentication-subscription resource
                  GET    -> stored subscription + strong ETag
                  PUT    -> create (201) or replace (200), If-Match required
                            when the resource already exists
                  PATCH  -> JSON Patch replace of /sequenceNumber only, with
                            a compare-and-set UPDATE so two NFs cannot both
                            advance the same SQN
                NRF registration (NF type UDR, service nudr-dr)
                /health reports database reachability, not just process liveness

  not built     the other Nudr resources (access-and-mobility, session
                management, policy, exposure, ...). They are not mounted, so
                callers get 404 instead of a fabricated body.

Storage is the canonical hssdb.tbl_subscriber row. Provisioning still writes
that table through the UDM; this service is the only reader/writer of the
authentication subscription and sequence number. HSS keeps its own EPS-UDR
store (TS 23.632 vector-ownership option 1) and is not behind this resource.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import mysql.connector
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

for _p in (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "/app"):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from corelib.nrf_client import NrfClient, service as nf_service  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("udr")

PORT = int(os.getenv("UDR_PORT", "8006"))
NRF_URL = f"http://{os.getenv('NRF_ADDR', 'custom-nrf')}:{os.getenv('NRF_PORT', '8000')}"
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "hssdb"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "hss"),
    "password": os.getenv("DB_PASSWORD", "change-me"),
    "database": os.getenv("DB_NAME", "hssdb"),
}

AUTH_SUBSCRIPTION_PATH = (
    "/nudr-dr/v2/subscription-data/{ue_id}"
    "/authentication-data/authentication-subscription"
)

nf = NrfClient(
    base_url=NRF_URL,
    nf_instance_id=os.getenv("UDR_NF_INSTANCE_ID", f"udr-{uuid.uuid4()}"),
    nf_type="UDR",
    nf_services=[nf_service("nudr-dr", "nudr-dr-1", PORT, api_version="v2")],
    fqdn=os.getenv("UDR_PUBLIC_HOST", "udr.core.local"),
    heartbeat_seconds=int(os.getenv("NRF_HEARTBEAT_TIMER", "30")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    nf.start()
    logger.info("UDR Nudr_DataRepository on port %s", PORT)
    yield
    nf.stop()


app = FastAPI(title="Hamiltel UDR", version="0.1.0", lifespan=lifespan)


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


# ============================================================================
# Models (TS 29.505 §6.1.6.2 authentication subscription)
# ============================================================================
_HEX12 = r"^[0-9A-Fa-f]{12}$"
_HEX4 = r"^[0-9A-Fa-f]{4}$"
_HEX32 = r"^[0-9A-Fa-f]{32}$"
_HEX_32_64 = r"^[0-9A-Fa-f]{32,64}$"


class PermanentKey(BaseModel):
    permanentKeyValue: str = Field(..., pattern=_HEX_32_64)


class Opc(BaseModel):
    opcValue: str = Field(..., pattern=_HEX32)
    opcKformat: Optional[str] = None


class Milenage(BaseModel):
    op: str = Field(..., pattern=_HEX32)


class AuthenticationSubscription(BaseModel):
    authenticationMethod: str = Field("5G_AKA", description="AuthMethod (TS 29.505 §6.1.6.2.2)")
    sequenceNumber: str = Field(..., pattern=_HEX12)
    authenticationManagementField: str = Field(..., pattern=_HEX4)
    permanentKey: Optional[PermanentKey] = None
    opc: Optional[Opc] = None
    milenage: Optional[Milenage] = None
    # Implementation extension: TS 29.505 models 5G credentials only. EPS/2G/3G
    # Ki lives in the same canonical record (TS 23.632 L.4), so it is carried
    # here under an explicit name rather than being dropped or duplicated.
    ki: Optional[str] = Field(None, pattern=_HEX32)


# ============================================================================
# Serialisation helpers
# ============================================================================
def _imsi(ue_id: str) -> str:
    """Accept both bare IMSI and the TS 29.505 SUPI form imsi-<digits>."""
    value = ue_id[5:] if ue_id.startswith("imsi-") else ue_id
    if not (value.isdigit() and len(value) == 15):
        raise HTTPException(
            status_code=400,
            detail={"cause": "INVALID_UE_ID", "detail": "expected imsi-<15 digits>"},
        )
    return value


def _row_to_body(row: Dict[str, Any]) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "authenticationMethod": "5G_AKA",
        "sequenceNumber": f"{int(row.get('sqn') or 0):012X}",
        "authenticationManagementField": (row.get("amf") or "8000").upper(),
    }
    if row.get("k"):
        body["permanentKey"] = {"permanentKeyValue": row["k"].upper()}
    if row.get("opc"):
        body["opc"] = {"opcValue": row["opc"].upper(), "opcKformat": "OPC"}
    if row.get("op"):
        body["milenage"] = {"op": row["op"].upper()}
    if row.get("ki"):
        body["ki"] = row["ki"].upper()
    return body


def _etag(body: Dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return '"' + hashlib.sha256(canonical).hexdigest() + '"'


def _columns(body: AuthenticationSubscription) -> Dict[str, Any]:
    return {
        "k": body.permanentKey.permanentKeyValue.upper() if body.permanentKey else None,
        "ki": body.ki.upper() if body.ki else None,
        "op": body.milenage.op.upper() if body.milenage else None,
        "opc": body.opc.opcValue.upper() if body.opc else None,
        "sqn": int(body.sequenceNumber, 16),
        "amf": body.authenticationManagementField.upper(),
    }


def _respond(body: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        body,
        status_code=status_code,
        headers={"ETag": _etag(body), "Cache-Control": "no-store"},
    )


_SELECT = "SELECT imsi, k, ki, op, opc, sqn, amf FROM tbl_subscriber WHERE imsi=%s"


def _locked_row(cur, imsi: str) -> Optional[Dict[str, Any]]:
    cur.execute(_SELECT + " FOR UPDATE", (imsi,))
    return cur.fetchone()


def _resulting_body(conn, imsi: str) -> Dict[str, Any]:
    cur = conn.cursor(dictionary=True)
    cur.execute(_SELECT, (imsi,))
    row = cur.fetchone()
    return _row_to_body(row)


# ============================================================================
# Health
# ============================================================================
@app.get("/health")
def health():
    storage = "ok"
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - report the class, never the DSN
        storage = f"error: {exc.__class__.__name__}"
    return {
        "status": "ok" if storage == "ok" and nf.registered else "degraded",
        "service": "udr",
        "resources": ["authentication-subscription"],
        "storage": storage,
        "registry": nf.status(),
    }


# ============================================================================
# Nudr_DataRepository - authentication subscription
# ============================================================================
@app.get(AUTH_SUBSCRIPTION_PATH)
def get_authentication_subscription(ue_id: str):
    """TS 29.504 §5.3.2.2: Query Authentication Subscription."""
    imsi = _imsi(ue_id)
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(_SELECT, (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail={"cause": "USER_NOT_FOUND", "ueId": ue_id}
            )
        return _respond(_row_to_body(row))
    finally:
        conn.close()


@app.put(AUTH_SUBSCRIPTION_PATH)
def put_authentication_subscription(
    ue_id: str, body: AuthenticationSubscription, if_match: Optional[str] = Header(None)
):
    """TS 29.504 §5.3.2.3: Create or Replace Authentication Subscription."""
    imsi = _imsi(ue_id)
    cols = _columns(body)
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        existing = _locked_row(cur, imsi)
        if existing:
            if not if_match:
                raise HTTPException(
                    status_code=428,
                    detail={
                        "cause": "PRECONDITION_REQUIRED",
                        "detail": "If-Match is required to replace an existing subscription",
                    },
                )
            current = _etag(_row_to_body(existing))
            if if_match.strip() != current:
                raise HTTPException(
                    status_code=412,
                    detail={"cause": "PRECONDITION_FAILED", "detail": "ETag does not match"},
                )
            cur.execute(
                "UPDATE tbl_subscriber SET k=%s, ki=%s, op=%s, opc=%s, sqn=%s, amf=%s "
                "WHERE imsi=%s",
                (cols["k"], cols["ki"], cols["op"], cols["opc"], cols["sqn"], cols["amf"], imsi),
            )
            status_code = 200
        else:
            if if_match and if_match.strip() != "*":
                raise HTTPException(
                    status_code=412,
                    detail={"cause": "PRECONDITION_FAILED", "detail": "subscriber does not exist"},
                )
            cur.execute(
                "INSERT INTO tbl_subscriber (imsi, k, ki, op, opc, sqn, amf) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (imsi, cols["k"], cols["ki"], cols["op"], cols["opc"], cols["sqn"], cols["amf"]),
            )
            status_code = 201
        conn.commit()
        return _respond(_resulting_body(conn, imsi), status_code)
    finally:
        conn.close()


def _parse_patch(raw: Any) -> int:
    """Return the replacement SQN; reject anything outside the one supported op."""
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=400, detail={"cause": "MALFORMED_PATCH", "detail": "expected a JSON Patch array"}
        )
    if len(raw) != 1:
        raise HTTPException(
            status_code=400,
            detail={
                "cause": "UNSUPPORTED_PATCH",
                "detail": "only a single replace of /sequenceNumber is implemented",
            },
        )
    op = raw[0] if isinstance(raw[0], dict) else {}
    if op.get("op") != "replace" or op.get("path") != "/sequenceNumber":
        raise HTTPException(
            status_code=400,
            detail={
                "cause": "UNSUPPORTED_PATCH",
                "detail": "only a single replace of /sequenceNumber is implemented",
            },
        )
    value = op.get("value")
    if not isinstance(value, str) or len(value) != 12:
        raise HTTPException(
            status_code=400, detail={"cause": "MALFORMED_PATCH", "detail": "sequenceNumber must be 12 hex digits"}
        )
    try:
        sqn = int(value, 16)
    except ValueError:
        raise HTTPException(
            status_code=400, detail={"cause": "MALFORMED_PATCH", "detail": "sequenceNumber must be 12 hex digits"}
        )
    if not 0 <= sqn <= 2**48 - 1:
        raise HTTPException(
            status_code=400, detail={"cause": "MALFORMED_PATCH", "detail": "sequenceNumber exceeds 48 bits"}
        )
    return sqn


@app.patch(AUTH_SUBSCRIPTION_PATH)
async def patch_authentication_subscription(
    ue_id: str, request: Request, if_match: Optional[str] = Header(None)
):
    """TS 29.504 §5.3.2.4: Modify Authentication Subscription.

    Only `/sequenceNumber` is mutable here. The update is a compare-and-set:
    the row is locked, the ETag the caller observed is re-derived from the
    locked row, and the UPDATE repeats the old SQN in its WHERE clause, so a
    concurrent writer that slipped in after the caller's GET gets 412, never
    a silent lost update.
    """
    imsi = _imsi(ue_id)
    if not if_match:
        raise HTTPException(
            status_code=428,
            detail={"cause": "PRECONDITION_REQUIRED", "detail": "If-Match is required for PATCH"},
        )
    try:
        raw = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail={"cause": "MALFORMED_PATCH", "detail": "body is not JSON"})
    new_sqn = _parse_patch(raw)

    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        existing = _locked_row(cur, imsi)
        if not existing:
            raise HTTPException(
                status_code=404, detail={"cause": "USER_NOT_FOUND", "ueId": ue_id}
            )
        current = _etag(_row_to_body(existing))
        if if_match.strip() != current:
            raise HTTPException(
                status_code=412,
                detail={"cause": "PRECONDITION_FAILED", "detail": "ETag does not match"},
            )
        old_sqn = int(existing.get("sqn") or 0)
        cur.execute(
            "UPDATE tbl_subscriber SET sqn=%s WHERE imsi=%s AND sqn=%s",
            (new_sqn, imsi, old_sqn),
        )
        if cur.rowcount != 1:
            conn.rollback()
            raise HTTPException(
                status_code=412,
                detail={"cause": "PRECONDITION_FAILED", "detail": "sequence number changed"},
            )
        conn.commit()
        return _respond(_resulting_body(conn, imsi))
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
