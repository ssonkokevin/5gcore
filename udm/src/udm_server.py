"""UDM - Unified Data Management reference implementation.

FastAPI REST service exposing subscriber data (HLR/HSS/UDM tri-mode schema
mirrored from hssdbInitial.sql in protei-scp-platform/udm-build).

Endpoints:
  GET    /health
  GET    /subscribers/{imsi}
  POST   /subscribers
  PUT    /subscribers/{imsi}
  DELETE /subscribers/{imsi}
  GET    /subscribers/{imsi}/auth-vector
"""

import os
from typing import Optional

import mysql.connector
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis

app = FastAPI(title="UDM Reference", version="1.0.0")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "hss"),
    "password": os.getenv("DB_PASSWORD", "hss123"),
    "database": os.getenv("DB_NAME", "hssdb"),
}

REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "redis"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "password": os.getenv("REDIS_PASSWORD", "123456"),
    "decode_responses": True,
}


class Subscriber(BaseModel):
    imsi: str
    msisdn: Optional[str] = None
    imei: Optional[str] = None
    authentication_key: Optional[str] = None  # Ki
    opc: Optional[str] = None
    network_access_mode: int = 0
    subscriber_status: int = 0
    roaming_restricted: bool = False
    ambr_ul: Optional[str] = None
    ambr_dl: Optional[str] = None


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def get_redis():
    return redis.Redis(**REDIS_CONFIG)


@app.get("/health")
def health():
    return {"status": "ok", "service": "udm"}


@app.get("/subscribers/{imsi}")
def get_subscriber(imsi: str):
    r = get_redis()
    cache_key = f"udm:subscriber:{imsi}"
    cached = r.get(cache_key)
    if cached:
        import json
        return json.loads(cached)

    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi = %s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        import json
        r.setex(cache_key, 300, json.dumps(row, default=str))
        return row
    finally:
        conn.close()


@app.post("/subscribers")
def create_subscriber(sub: Subscriber):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tbl_subscriber
               (imsi, msisdn, imei, authentication_key, opc, network_access_mode,
                subscriber_status, roaming_restricted, ambr_ul, ambr_dl)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (sub.imsi, sub.msisdn, sub.imei, sub.authentication_key, sub.opc,
             sub.network_access_mode, sub.subscriber_status, sub.roaming_restricted,
             sub.ambr_ul, sub.ambr_dl),
        )
        conn.commit()
        r = get_redis()
        r.delete(f"udm:subscriber:{sub.imsi}")
        return {"status": "created", "imsi": sub.imsi}
    finally:
        conn.close()


@app.put("/subscribers/{imsi}")
def update_subscriber(imsi: str, sub: Subscriber):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE tbl_subscriber SET msisdn=%s, imei=%s, authentication_key=%s,
               opc=%s, network_access_mode=%s, subscriber_status=%s,
               roaming_restricted=%s, ambr_ul=%s, ambr_dl=%s WHERE imsi=%s""",
            (sub.msisdn, sub.imei, sub.authentication_key, sub.opc,
             sub.network_access_mode, sub.subscriber_status, sub.roaming_restricted,
             sub.ambr_ul, sub.ambr_dl, imsi),
        )
        conn.commit()
        r = get_redis()
        r.delete(f"udm:subscriber:{imsi}")
        return {"status": "updated", "imsi": imsi}
    finally:
        conn.close()


@app.delete("/subscribers/{imsi}")
def delete_subscriber(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_subscriber WHERE imsi = %s", (imsi,))
        conn.commit()
        r = get_redis()
        r.delete(f"udm:subscriber:{imsi}")
        return {"status": "deleted", "imsi": imsi}
    finally:
        conn.close()


@app.get("/subscribers/{imsi}/auth-vector")
def get_auth_vector(imsi: str, rand: Optional[str] = None):
    """Return authentication vector (HEA / HSS style)."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT authentication_key, opc FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        return {
            "imsi": imsi,
            "rand": rand,
            "autn": "00" * 16,
            "res": "00" * 8,
            "ck": "00" * 16,
            "ik": "00" * 16,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("UDM_PORT", "8080")))
