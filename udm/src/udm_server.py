"""UDM - Unified Data Management reference implementation.

FastAPI REST service exposing subscriber data (HLR/HSS/UDM tri-mode schema
mirrored from hssdbInitial.sql in protei-scp-platform/udm-build).

Extended for 5G/4G/3G/2G with full key hierarchy, batch provisioning.

Endpoints:
  GET    /health
  GET    /subscribers/{imsi}
  POST   /subscribers
  PUT    /subscribers/{imsi}
  DELETE /subscribers/{imsi}
  GET    /subscribers/{imsi}/auth-vector
  POST   /subscribers/batch          # Batch upload CSV/JSON
  GET    /batches/{batch_id}         # Batch status
  GET    /imsi-ranges/               # List IMSI ranges
  POST   /imsi-ranges/               # Create IMSI range
  POST   /imsi-ranges/allocate       # Allocate from range
"""

import csv
import io
import json
import os
import uuid
from typing import Optional, List

import mysql.connector
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field, field_validator
import redis

app = FastAPI(title="UDM Tri-Mode (5G/4G/3G/2G)", version="2.0.0")

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


# ============================================================================
# Pydantic Models
# ============================================================================
class SubscriberBase(BaseModel):
    imsi: str = Field(..., pattern=r"^\d{15}$")
    msisdn: Optional[str] = Field(None, pattern=r"^\d+$")
    imei: Optional[str] = Field(None, pattern=r"^\d{15}$")
    
    # 5G/4G Keys
    k: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$", description="5G root key (K4) - 256-bit hex")
    ki: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$", description="4G/3G/2G root key (Ki) - 128-bit hex")
    op: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$", description="OP (Operator Variant) - 128-bit hex")
    opc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$", description="OPc (derived) - 128-bit hex")
    
    # Sequence & AMF
    sqn: int = Field(0, ge=0, le=2**48-1, description="Sequence number")
    amf: str = Field("8000", pattern=r"^[0-9A-Fa-f]{4}$", description="Auth Management Field (hex)")
    
    # Derived 5G Keys (auto-computed if not provided)
    k_asme: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    k_seaf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    k_ausf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    
    # 2G/3G
    kc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{16}$", description="Kc (64-bit hex)")
    sres: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{8}$", description="SRES (32-bit hex)")
    
    # Network
    network_access_mode: int = Field(2, ge=0, le=3, description="0=GPRS,1=CS,2=Both,3=5G")
    subscriber_status: int = Field(0, ge=0, le=2, description="0=Active,1=Barred,2=Suspended")
    roaming_restricted: bool = False
    ambr_ul: Optional[str] = None
    ambr_dl: Optional[str] = None
    
    # Batch
    batch_id: Optional[str] = None

    @field_validator('k', 'ki', 'op', 'opc', 'k_asme', 'k_seaf', 'k_ausf', mode='before')
    @classmethod
    def upper_hex(cls, v):
        return v.upper() if v else v

    @field_validator('amf', mode='before')
    @classmethod
    def upper_amf(cls, v):
        return v.upper() if v else v


class SubscriberCreate(SubscriberBase):
    pass


class SubscriberUpdate(BaseModel):
    msisdn: Optional[str] = Field(None, pattern=r"^\d+$")
    imei: Optional[str] = Field(None, pattern=r"^\d{15}$")
    k: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    ki: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    op: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    opc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    sqn: Optional[int] = Field(None, ge=0, le=2**48-1)
    amf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{4}$")
    k_asme: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    k_seaf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    k_ausf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    kc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{16}$")
    sres: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{8}$")
    network_access_mode: Optional[int] = Field(None, ge=0, le=3)
    subscriber_status: Optional[int] = Field(None, ge=0, le=2)
    roaming_restricted: Optional[bool] = None
    ambr_ul: Optional[str] = None
    ambr_dl: Optional[str] = None


class SubscriberResponse(SubscriberBase):
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class AuthVectorRequest(BaseModel):
    rand: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")


class AuthVectorResponse(BaseModel):
    imsi: str
    rand: str
    autn: str
    res: str
    xres: str
    ck: str
    ik: str
    k_asme: str
    k_seaf: str
    k_ausf: str


class BatchUploadResponse(BaseModel):
    batch_id: str
    status: str
    total_records: int
    successful_records: int
    failed_records: int
    message: str


class BatchStatusResponse(BaseModel):
    batch_id: str
    status: str
    total_records: int
    successful_records: int
    failed_records: int
    error_log: Optional[dict] = None
    created_at: str
    completed_at: Optional[str] = None


class IMSIRangeCreate(BaseModel):
    range_name: str
    mcc: str = Field(..., pattern=r"^\d{3}$")
    mnc: str = Field(..., pattern=r"^\d{3}$")
    msisdn_prefix: Optional[str] = None
    imsi_start: str = Field(..., pattern=r"^\d{15}$")
    imsi_end: str = Field(..., pattern=r"^\d{15}$")


class IMSIRangeResponse(BaseModel):
    range_name: str
    mcc: str
    mnc: str
    msisdn_prefix: Optional[str]
    imsi_start: str
    imsi_end: str
    next_imsi: str
    allocated_count: int
    total_count: int
    status: str


class IMSIAllocateRequest(BaseModel):
    range_name: str
    count: int = Field(1, ge=1, le=10000)
    ki: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    op: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    k: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    network_access_mode: int = 2
    subscriber_status: int = 0


# ============================================================================
# DB / Redis Helpers
# ============================================================================
def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def get_redis():
    return redis.Redis(**REDIS_CONFIG)


def derive_opc(op: str, k: str) -> str:
    """Derive OPc from OP and K using AES-128 (simplified - use lib in production)."""
    # In production: use pycryptodome AES.OPc = AES_K(OP)
    # For now: return OPc if provided, else hash
    import hashlib
    return hashlib.sha256((op + k).encode()).hexdigest()[:32].upper()


def derive_5g_keys(k: str, sqn: int, amf: str, rand: str = None) -> dict:
    """Derive 5G key hierarchy (simplified - use 3GPP TS 33.501 in production)."""
    import hashlib
    base = k + f"{sqn:012X}" + amf + (rand or "00" * 16)
    k_asme = hashlib.sha256((base + "asme").encode()).hexdigest()[:32].upper()
    k_seaf = hashlib.sha256((base + "seaf").encode()).hexdigest()[:32].upper()
    k_ausf = hashlib.sha256((base + "ausf").encode()).hexdigest()[:32].upper()
    return {"k_asme": k_asme, "k_seaf": k_seaf, "k_ausf": k_ausf}


def derive_2g3g_keys(ki: str, rand: str) -> dict:
    """Derive 2G/3G Kc and SRES (simplified - use A3/A8 algorithms in production)."""
    import hashlib
    base = ki + rand
    kc = hashlib.md5((base + "kc").encode()).hexdigest()[:16].upper()
    sres = hashlib.md5((base + "sres").encode()).hexdigest()[:8].upper()
    return {"kc": kc, "sres": sres}


# ============================================================================
# Health
# ============================================================================
@app.get("/health")
def health():
    return {"status": "ok", "service": "udm", "version": "2.0.0", "modes": ["5G", "4G", "3G", "2G"]}


# ============================================================================
# Subscriber CRUD
# ============================================================================
@app.get("/subscribers/{imsi}", response_model=SubscriberResponse)
def get_subscriber(imsi: str):
    r = get_redis()
    cache_key = f"udm:subscriber:{imsi}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi = %s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        r.setex(cache_key, 300, json.dumps(row, default=str))
        return row
    finally:
        conn.close()


@app.post("/subscribers", response_model=SubscriberResponse, status_code=201)
def create_subscriber(sub: SubscriberCreate):
    conn = get_db()
    try:
        cur = conn.cursor()
        
        # Auto-derive OPc if OP+K provided
        opc = sub.opc
        if sub.op and sub.k and not opc:
            opc = derive_opc(sub.op.upper(), sub.k.upper())
        elif sub.op and sub.ki and not opc:
            opc = derive_opc(sub.op.upper(), sub.ki.upper())
        
        # Auto-derive 5G keys if K provided
        keys_5g = {"k_asme": sub.k_asme, "k_seaf": sub.k_seaf, "k_ausf": sub.k_ausf}
        if sub.k and not any(keys_5g.values()):
            derived = derive_5g_keys(sub.k.upper(), sub.sqn, sub.amf.upper())
            keys_5g = derived
        
        cur.execute(
            """INSERT INTO tbl_subscriber
               (imsi, msisdn, imei, k, ki, op, opc, sqn, amf,
                k_asme, k_seaf, k_ausf, kc, sres,
                network_access_mode, subscriber_status, roaming_restricted,
                ambr_ul, ambr_dl, batch_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (sub.imsi, sub.msisdn, sub.imei, sub.k, sub.ki, sub.op, opc,
             sub.sqn, sub.amf.upper(),
             keys_5g["k_asme"], keys_5g["k_seaf"], keys_5g["k_ausf"],
             sub.kc, sub.sres,
             sub.network_access_mode, sub.subscriber_status, sub.roaming_restricted,
             sub.ambr_ul, sub.ambr_dl, sub.batch_id),
        )
        conn.commit()
        
        r = get_redis()
        r.delete(f"udm:subscriber:{sub.imsi}")
        return get_subscriber(sub.imsi)
    finally:
        conn.close()


@app.put("/subscribers/{imsi}", response_model=SubscriberResponse)
def update_subscriber(imsi: str, sub: SubscriberUpdate):
    conn = get_db()
    try:
        cur = conn.cursor()
        
        # Build dynamic update
        fields = []
        values = []
        for field, value in sub.model_dump(exclude_unset=True).items():
            if field in ("k", "ki", "op", "opc", "k_asme", "k_seaf", "k_ausf", "amf") and value:
                value = value.upper()
            fields.append(f"{field}=%s")
            values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.append(imsi)
        cur.execute(f"UPDATE tbl_subscriber SET {', '.join(fields)} WHERE imsi=%s", values)
        conn.commit()
        
        r = get_redis()
        r.delete(f"udm:subscriber:{imsi}")
        return get_subscriber(imsi)
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


# ============================================================================
# Authentication Vector Generation
# ============================================================================
@app.get("/subscribers/{imsi}/auth-vector", response_model=AuthVectorResponse)
def get_auth_vector(imsi: str, rand: Optional[str] = None):
    """Generate authentication vector for 5G/4G/3G/2G AKA."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        # Generate RAND if not provided
        import secrets
        rand = rand or secrets.token_hex(16).upper()
        
        # 5G AKA (if K present)
        k_asme = k_seaf = k_ausf = autn = xres = ck = ik = ""
        if row.get("k"):
            keys_5g = derive_5g_keys(row["k"], row["sqn"], row["amf"], rand)
            k_asme = keys_5g["k_asme"]
            k_seaf = keys_5g["k_seaf"]
            k_ausf = keys_5g["k_ausf"]
            # AUTN = SQN ⊕ AK || AMF || MAC (simplified)
            import hashlib
            autn = hashlib.sha256((row["k"] + rand + f"{row['sqn']:012X}" + row["amf"]).encode()).hexdigest()[:32].upper()
            xres = hashlib.sha256((row["k"] + rand).encode()).hexdigest()[:32].upper()
            ck = ik = hashlib.sha256((row["k"] + rand + "ckik").encode()).hexdigest()[:32].upper()
        
        # 4G AKA (if Ki present)
        if row.get("ki") and not row.get("k"):
            import hashlib
            autn = hashlib.sha256((row["ki"] + rand + f"{row['sqn']:012X}" + row["amf"]).encode()).hexdigest()[:32].upper()
            xres = hashlib.sha256((row["ki"] + rand).encode()).hexdigest()[:16].upper()
            ck = ik = hashlib.sha256((row["ki"] + rand + "ckik").encode()).hexdigest()[:32].upper()
        
        # 2G/3G (if Ki present)
        res = row.get("sres") or ""
        kc = row.get("kc") or ""
        if row.get("ki"):
            keys_2g3g = derive_2g3g_keys(row["ki"], rand)
            res = keys_2g3g["sres"]
            kc = keys_2g3g["kc"]
        
        # Update SQN
        new_sqn = row["sqn"] + 1
        cur.execute("UPDATE tbl_subscriber SET sqn=%s WHERE imsi=%s", (new_sqn, imsi))
        conn.commit()
        
        r = get_redis()
        r.delete(f"udm:subscriber:{imsi}")
        
        return AuthVectorResponse(
            imsi=imsi,
            rand=rand,
            autn=autn or "00" * 32,
            res=res or "00" * 8,
            xres=xres or "00" * 32,
            ck=ck or "00" * 32,
            ik=ik or "00" * 32,
            k_asme=k_asme or "00" * 32,
            k_seaf=k_seaf or "00" * 32,
            k_ausf=k_ausf or "00" * 32,
        )
    finally:
        conn.close()


# ============================================================================
# Batch Upload (CSV/JSON)
# ============================================================================
@app.post("/subscribers/batch", response_model=BatchUploadResponse)
async def batch_upload(
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
    auto_derive: bool = Form(True),
    default_ki: Optional[str] = Form(None),
    default_op: Optional[str] = Form(None),
    default_k: Optional[str] = Form(None),
    default_network_access_mode: int = Form(2),
    default_subscriber_status: int = Form(0),
):
    """Upload CSV/JSON with 10k+ SIMs.
    
    CSV columns: imsi,msisdn,imei,k,ki,op,opc,sqn,amf,k_asme,k_seaf,k_ausf,kc,sres,
                 network_access_mode,subscriber_status,roaming_restricted,ambr_ul,ambr_dl
    
    Minimum required: imsi (15 digits). Others auto-derived if keys provided.
    """
    batch_id = batch_id or f"batch-{uuid.uuid4().hex[:12]}"
    content = await file.read()
    
    # Parse CSV or JSON
    records = []
    if file.filename.endswith('.json'):
        records = json.loads(content.decode())
    else:
        # CSV
        text = content.decode()
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            # Convert empty strings to None
            records.append({k: (v if v else None) for k, v in row.items()})
    
    total = len(records)
    successful = 0
    failed = 0
    errors = []
    
    conn = get_db()
    try:
        cur = conn.cursor()
        
        # Create batch record
        cur.execute(
            "INSERT INTO tbl_batch_upload (batch_id, filename, total_records, status, created_by) VALUES (%s,%s,%s,'processing','api')",
            (batch_id, file.filename, total)
        )
        conn.commit()
        
        for i, rec in enumerate(records):
            try:
                imsi = rec.get("imsi")
                if not imsi or len(imsi) != 15 or not imsi.isdigit():
                    raise ValueError("Invalid IMSI (must be 15 digits)")
                
                # Use defaults if not provided
                ki = rec.get("ki") or default_ki
                op = rec.get("op") or default_op
                k = rec.get("k") or default_k
                
                # Auto-derive OPc
                opc = rec.get("opc")
                if auto_derive and not opc:
                    if op and k:
                        opc = derive_opc(op.upper(), k.upper())
                    elif op and ki:
                        opc = derive_opc(op.upper(), ki.upper())
                
                # Auto-derive 5G keys
                keys_5g = {"k_asme": None, "k_seaf": None, "k_ausf": None}
                if auto_derive and k and not any([rec.get("k_asme"), rec.get("k_seaf"), rec.get("k_ausf")]):
                    sqn = int(rec.get("sqn", 0))
                    amf = rec.get("amf", "8000").upper()
                    keys_5g = derive_5g_keys(k.upper(), sqn, amf)
                
                cur.execute(
                    """INSERT INTO tbl_subscriber
                       (imsi, msisdn, imei, k, ki, op, opc, sqn, amf,
                        k_asme, k_seaf, k_ausf, kc, sres,
                        network_access_mode, subscriber_status, roaming_restricted,
                        ambr_ul, ambr_dl, batch_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                        msisdn=VALUES(msisdn), imei=VALUES(imei), k=VALUES(k), ki=VALUES(ki),
                        op=VALUES(op), opc=VALUES(opc), sqn=VALUES(sqn), amf=VALUES(amf),
                        k_asme=VALUES(k_asme), k_seaf=VALUES(k_seaf), k_ausf=VALUES(k_ausf),
                        kc=VALUES(kc), sres=VALUES(sres),
                        network_access_mode=VALUES(network_access_mode),
                        subscriber_status=VALUES(subscriber_status),
                        roaming_restricted=VALUES(roaming_restricted),
                        ambr_ul=VALUES(ambr_ul), ambr_dl=VALUES(ambr_dl),
                        batch_id=VALUES(batch_id)""",
                    (imsi,
                     rec.get("msisdn"), rec.get("imei"), k, ki, op, opc,
                     int(rec.get("sqn", 0)), rec.get("amf", "8000").upper(),
                     keys_5g["k_asme"], keys_5g["k_seaf"], keys_5g["k_ausf"],
                     rec.get("kc"), rec.get("sres"),
                     int(rec.get("network_access_mode", default_network_access_mode)),
                     int(rec.get("subscriber_status", default_subscriber_status)),
                     rec.get("roaming_restricted", "false").lower() == "true",
                     rec.get("ambr_ul"), rec.get("ambr_dl"), batch_id),
                )
                successful += 1
            except Exception as e:
                failed += 1
                errors.append({"row": i+1, "imsi": rec.get("imsi"), "error": str(e)})
        
        cur.execute(
            """UPDATE tbl_batch_upload 
               SET successful_records=%s, failed_records=%s, status=%s, error_log=%s, completed_at=NOW()
               WHERE batch_id=%s""",
            (successful, failed, 'completed' if failed == 0 else 'completed', json.dumps(errors), batch_id)
        )
        conn.commit()
        
    finally:
        conn.close()
    
    return BatchUploadResponse(
        batch_id=batch_id,
        status="completed" if failed == 0 else "partial",
        total_records=total,
        successful_records=successful,
        failed_records=failed,
        message=f"Processed {total}: {successful} ok, {failed} failed"
    )


@app.get("/batches/{batch_id}", response_model=BatchStatusResponse)
def get_batch_status(batch_id: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_batch_upload WHERE batch_id=%s", (batch_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Batch not found")
        return row
    finally:
        conn.close()


# ============================================================================
# IMSI Range Management
# ============================================================================
@app.get("/imsi-ranges/", response_model=List[IMSIRangeResponse])
def list_imsi_ranges():
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_imsi_range ORDER BY created_at DESC")
        return cur.fetchall()
    finally:
        conn.close()


@app.post("/imsi-ranges/", response_model=IMSIRangeResponse, status_code=201)
def create_imsi_range(range_data: IMSIRangeCreate):
    conn = get_db()
    try:
        cur = conn.cursor()
        
        # Calculate total count
        start_num = int(range_data.imsi_start)
        end_num = int(range_data.imsi_end)
        total = end_num - start_num + 1
        
        cur.execute(
            """INSERT INTO tbl_imsi_range
               (range_name, mcc, mnc, msisdn_prefix, imsi_start, imsi_end, next_imsi, total_count)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (range_data.range_name, range_data.mcc, range_data.mnc,
             range_data.msisdn_prefix, range_data.imsi_start, range_data.imsi_end,
             range_data.imsi_start, total)
        )
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_imsi_range WHERE range_name=%s", (range_data.range_name,))
        return cur.fetchone()
    finally:
        conn.close()


@app.post("/imsi-ranges/allocate")
def allocate_from_range(req: IMSIAllocateRequest):
    """Allocate N IMSIs from a range, auto-create subscribers with keys."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        
        # Get range with lock
        cur.execute("SELECT * FROM tbl_imsi_range WHERE range_name=%s FOR UPDATE", (req.range_name,))
        range_row = cur.fetchone()
        if not range_row:
            raise HTTPException(status_code=404, detail="Range not found")
        if range_row["status"] != "available":
            raise HTTPException(status_code=400, detail=f"Range status: {range_row['status']}")
        
        next_num = int(range_row["next_imsi"])
        end_num = int(range_row["imsi_end"])
        available = end_num - next_num + 1
        count = min(req.count, available)
        
        if count <= 0:
            raise HTTPException(status_code=400, detail="Range exhausted")
        
        allocated = []
        for i in range(count):
            imsi = f"{next_num + i:015d}"
            
            # Derive keys
            opc = None
            keys_5g = {"k_asme": None, "k_seaf": None, "k_ausf": None}
            if req.op and req.k:
                opc = derive_opc(req.op.upper(), req.k.upper())
                keys_5g = derive_5g_keys(req.k.upper(), 0, "8000")
            elif req.op and req.ki:
                opc = derive_opc(req.op.upper(), req.ki.upper())
            
            cur.execute(
                """INSERT INTO tbl_subscriber
                   (imsi, k, ki, op, opc, sqn, amf,
                    k_asme, k_seaf, k_ausf,
                    network_access_mode, subscriber_status, batch_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (imsi, req.k, req.ki, req.op, opc, 0, "8000",
                 keys_5g["k_asme"], keys_5g["k_seaf"], keys_5g["k_ausf"],
                 req.network_access_mode, req.subscriber_status, req.range_name)
            )
            allocated.append(imsi)
        
        # Update range
        new_next = f"{next_num + count:015d}"
        new_allocated = range_row["allocated_count"] + count
        new_status = "exhausted" if new_allocated >= range_row["total_count"] else "available"
        
        cur.execute(
            "UPDATE tbl_imsi_range SET next_imsi=%s, allocated_count=%s, status=%s WHERE range_name=%s",
            (new_next, new_allocated, new_status, req.range_name)
        )
        conn.commit()
        
        return {"allocated": allocated, "count": count, "next_imsi": new_next}
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("UDM_PORT", "8080")))
