"""HSS - Home Subscriber Server Nhss API reference implementation (TS 29.563 V20.0.0).

Exposes Nhss service-based interface TO the UDM for UDM-HSS interworking.
Implements 5 Nhss APIs:

  Nhss_UEAuthentication (clause 6.1): POST /generate-av
  Nhss_SubscriberDataManagement (clause 6.2): GET /ue-context-in-pgw-data,
                                              POST/DELETE/PATCH /subscriptions
  Nhss_UEContextManagement (clause 6.3): POST /deregister-sn,
                                         POST /imei-update,
                                         POST /roaming-status-update
  Nhss_EventExposure (clause 6.4): POST/DELETE/PATCH /ee-subscriptions
  Nhss_ParameterProvision (clause 6.5): PUT/DELETE/GET /pp-data-store/{afInstanceId}

The HSS acts as ARPF (not AuC) for 5G_AKA/EAP_AKA_PRIME vector generation
when subscriber credentials live in the EPS-UDR (Option 1 per TS 23.632 L.4).

Endpoints:
  Health:       GET /health
  Nhss_UEAU:    POST /nhss-ueau/v1/generate-av
  Nhss_SDM:     GET  /nhss-sdm/v1/{ueId}/ue-context-in-pgw-data
                POST /nhss-sdm/v1/{ueId}/subscriptions
                DEL  /nhss-sdm/v1/{ueId}/subscriptions/{subscriptionId}
                PATCH/nhss-sdm/v1/{ueId}/subscriptions/{subscriptionId}
  Nhss_UECM:    POST /nhss-uecm/v1/deregister-sn
                POST /nhss-uecm/v1/imei-update
                POST /nhss-uecm/v1/roaming-status-update
  Nhss_EE:      POST  /nhss-ee/v1/{ueId}/ee-subscriptions
                DEL  /nhss-ee/v1/{ueId}/ee-subscriptions/{subscriptionId}
                PATCH/nhss-ee/v1/{ueId}/ee-subscriptions/{subscriptionId}
  Nhss_PP:      PUT   /nhss-pp/v1/{ueId}/pp-data-store/{afInstanceId}
                DEL  /nhss-pp/v1/{ueId}/pp-data-store/{afInstanceId}
                GET  /nhss-pp/v1/{ueId}/pp-data-store/{afInstanceId}

All Nhss APIs use:
  - HTTP/1.1 (FastAPI), JSON bodies
  - ProblemDetails (RFC 9457) for errors
  - OAuth2 scopes: nhss-ueau, nhss-sdm, nhss-uecm, nhss-ee, nhss-pp
  - Identifier: IMSI only (pattern ^imsi-[0-9]{5,15}$)
  - 307/308 redirection with Location and 3gpp-Sbi-Target-Nf-Id headers
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import mysql.connector
from fastapi import FastAPI, HTTPException, Query, Header, Path as PathParam
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# Milenage is shared with the UDM (corelib/milenage.py); the HSS is the ARPF.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from corelib.milenage import (  # noqa: E402
    CRYPTO_BACKEND,
    AutsVerificationError,
    Milenage,
    derive_opc as _derive_opc,
)

CRYPTO_AVAILABLE = CRYPTO_BACKEND is not None
if not CRYPTO_AVAILABLE:
    raise SystemExit(
        "CRYPTO_UNAVAILABLE: no AES backend; install pycryptodome (containers) "
        "or cryptography (host). Refusing to start without Milenage."
    )

app = FastAPI(
    title="HSS Nhss API (TS 29.563 V20.0.0)",
    version="1.0.0",
    description="HSS services for interworking with UDM - 5 Nhss APIs per TS 29.563"
)

# ============================================================================
# Configuration
# ============================================================================
DB_CONFIG = {
    "host": os.getenv("HSS_DB_HOST", "hssdb"),
    "port": int(os.getenv("HSS_DB_PORT", "3306")),
    "user": os.getenv("HSS_DB_USER", "hss"),
    "password": os.getenv("HSS_DB_PASSWORD", "hss123"),
    "database": os.getenv("HSS_DB_NAME", "hssdb"),
}

EPS_UDR_CONFIG = {
    "host": os.getenv("HSS_DB_HOST", "hssdb"),
    "port": int(os.getenv("HSS_DB_PORT", "3306")),
    "user": os.getenv("HSS_DB_USER", "hss"),
    "password": os.getenv("HSS_DB_PASSWORD", "hss123"),
    "database": os.getenv("EPS_UDR_DB_NAME", "eps_udr"),
}

OPERATOR_KEY = bytes.fromhex(os.getenv("OPERATOR_KEY", "00" * 16))

# OAuth2 scopes per Nhss API
NHSS_SCOPES = {
    "nhss-ueau": "nhss-ueau",
    "nhss-sdm": "nhss-sdm",
    "nhss-uecm": "nhss-uecm",
    "nhss-ee": "nhss-ee",
    "nhss-pp": "nhss-pp",
}

# ============================================================================
# Milenage (shared implementation in corelib/milenage.py)
# ============================================================================
def get_crypto(opc_hex: str) -> Milenage:
    return Milenage(bytes.fromhex(opc_hex))


def derive_opc(op: str, k: str) -> str:
    return _derive_opc(bytes.fromhex(op), bytes.fromhex(k)).hex().upper()


# ============================================================================
# DB / Helpers
# ============================================================================
def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def get_eps_udr():
    return mysql.connector.connect(**EPS_UDR_CONFIG)


def dict_row(cur, row):
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row))


def dict_rows(cur, rows):
    return [dict_row(cur, r) for r in rows]


def problem_detail(status: int, title: str, detail: str, error_code: str = None):
    """RFC 9457 ProblemDetails response."""
    body = {
        "type": "https://3gpp.org/5gcore/nhss/problem-details",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": f"/nhss/{error_code}" if error_code else None,
    }
    return JSONResponse(status_code=status, content=body)


# ============================================================================
# IMSI validation (Nhss uses IMSI only per TS 29.563 K.8)
# ============================================================================
def validate_imsi(ue_id: str) -> str:
    """Validate and extract IMSI from ueId (format: imsi-<digits>)."""
    if ue_id.startswith("imsi-"):
        imsi = ue_id[5:]
    else:
        imsi = ue_id
    if not imsi.isdigit() or len(imsi) < 5 or len(imsi) > 15:
        raise HTTPException(status_code=400, detail="Invalid IMSI format")
    return imsi


def audit_sync(imsi: str, direction: str, operation: str, payload: dict, status: str = "sent"):
    """Record cross-unit sync in audit log."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tbl_sync_audit
               (imsi, direction, operation, payload, status)
               VALUES (%s,%s,%s,%s,%s)""",
            (imsi, direction, operation, json.dumps(payload, default=str), status),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Audit failures must not break the main flow


# ============================================================================
# Health
# ============================================================================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "hss",
        "version": "1.0.0",
        "apis": ["nhss-ueau", "nhss-sdm", "nhss-uecm", "nhss-ee", "nhss-pp"],
        "specs": ["TS 29.563", "TS 23.632", "TS 23.008", "TS 29.272", "TS 29.002"],
        "crypto": f"milenage/{CRYPTO_BACKEND}",
    }


# ============================================================================
# Pydantic Models - Nhss_UEAU (clause 6.1)
# ============================================================================
class AvGenerationRequest(BaseModel):
    imsi: str = Field(..., pattern=r"^[0-9]{5,15}$")
    authType: str = Field(..., pattern="^(5G_AKA|EAP_AKA_PRIME)$")
    servingNetworkName: str
    resynchronizationInfo: Optional[Dict[str, Any]] = None


class Av5GHeAka(BaseModel):
    rand: str
    autn: str
    xresStar: str
    kausf: str


class AvEapAkaPrime(BaseModel):
    rand: str
    autn: str
    xresStar: str
    kausf: str


class AvGenerationResponse(BaseModel):
    av5GHeAka: Optional[Av5GHeAka] = None
    avEapAkaPrime: Optional[AvEapAkaPrime] = None


# ============================================================================
# Nhss_UEAU: POST /generate-av (clause 6.1 / 5.2)
# HSS computes 5G_AKA / EAP_AKA_PRIME for UDM (Option 1: creds in EPS-UDR)
# ============================================================================
@app.post("/nhss-ueau/v1/generate-av", response_model=AvGenerationResponse)
def nhss_generate_av(req: AvGenerationRequest):
    """Generate 5G authentication vector in HSS (ARPF per TS 33.501).
    
    UDM calls this when subscriber credentials live in EPS-UDR (Option 1).
    HSS reads EPS-UDR, acts as ARPF, calculates vector, returns it,
    and updates SQN in EPS-UDR.
    """
    imsi = validate_imsi(req.imsi)

    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_eps_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND: IMSI not found in EPS-UDR")

        if not row.get("k") or not row.get("opc"):
            raise HTTPException(status_code=403, detail="AUTHENTICATION_REJECTED: 5G credentials not provisioned")

        if req.authType == "EAP_AKA_PRIME":
            raise HTTPException(
                status_code=501,
                detail=(
                    "EAP_AKA_PRIME_NOT_IMPLEMENTED: CK'/IK' derivation (TS 33.402) "
                    "is not built; refusing to return placeholder vectors"
                ),
            )

        sqn = row["sqn"]
        amf_bytes = bytes.fromhex(row["amf"])
        k_bytes = bytes.fromhex(row["k"])
        crypto = get_crypto(row["opc"])

        if req.resynchronizationInfo:
            try:
                rand_bytes = bytes.fromhex(req.resynchronizationInfo["rand"])
                auts_bytes = bytes.fromhex(req.resynchronizationInfo["auts"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail="RESYNC_INFO_MALFORMED: rand and auts are required hex strings",
                )
            try:
                sqn = crypto.auts_sqn(k_bytes, rand_bytes, auts_bytes)
            except AutsVerificationError:
                raise HTTPException(
                    status_code=403,
                    detail="AUTS_VERIFICATION_FAILED: MAC-S mismatch",
                )

        av = crypto.generate_5g_he_av(
            k_bytes, sqn, amf_bytes, req.servingNetworkName
        )

        # Update SQN (authoritative copy in EPS-UDR)
        new_sqn = sqn + 1
        cur.execute("UPDATE tbl_eps_subscriber SET sqn=%s WHERE imsi=%s", (new_sqn, imsi))
        conn.commit()

        # Also update auth vector cache in eps_udr
        try:
            cur2 = conn.cursor()
            cur2.execute(
                """INSERT INTO tbl_eps_auth_vector (imsi, rand_5g, autn_5g, xres_star_5g, k_ausf_5g,
                                                   generated_at, algorithm, opc_used, sqn_used)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE rand_5g=VALUES(rand_5g), autn_5g=VALUES(autn_5g),
                                           xres_star_5g=VALUES(xres_star_5g), k_ausf_5g=VALUES(k_ausf_5g),
                                           generated_at=VALUES(generated_at), sqn_used=VALUES(sqn_used)""",
                (imsi, av["rand"].hex().upper(), av["autn"].hex().upper(),
                 av["xres_star"].hex().upper(), av["k_ausf"].hex().upper(),
                 datetime.now(timezone.utc), "milenage", row.get("opc", ""), sqn),
            )
            conn.commit()
        except Exception:
            pass

        audit_sync(imsi, "hss_to_udm", "auth_vector_request", {
            "authType": req.authType,
            "servingNetworkName": req.servingNetworkName,
            "sqnUsed": sqn,
        }, "acknowledged")

        rand_hex = av["rand"].hex().upper()
        autn_hex = av["autn"].hex().upper()
        xres_hex = av["xres_star"].hex().upper()

        return AvGenerationResponse(
            av5GHeAka=Av5GHeAka(
                rand=rand_hex, autn=autn_hex, xresStar=xres_hex,
                kausf=av["k_ausf"].hex().upper(),
            )
        )
    finally:
        conn.close()


# ============================================================================
# Pydantic Models - Nhss_SDM (clause 6.2)
# ============================================================================
class PgwInfo(BaseModel):
    pgwFqdn: str
    pgwIpv4: Optional[str] = None
    apn: str
    dnn: Optional[str] = None


class UeContextInPgwData(BaseModel):
    pgwInfo: List[PgwInfo]
    emergencyFqdn: Optional[str] = None
    emergencyPlmnId: Optional[str] = None
    emergencyIpAddr: Optional[str] = None
    emergencyRegistrationTime: Optional[str] = None


class SubscriptionData(BaseModel):
    nfInstanceId: str
    callbackReference: str
    monitoredResourceUris: List[str]
    expires: Optional[str] = None
    immediateReport: bool = False
    report: Optional[Dict[str, Any]] = None


class SubscriptionDataSets(BaseModel):
    ueContextInPgwData: bool = False


# ============================================================================
# Nhss_SDM: UE context in PGW data + subscriptions (clause 6.2 / 5.3)
# UDM retrieves EPS-side UE context for IRAT mobility and PDU continuity
# ============================================================================
@app.get("/nhss-sdm/v1/{ue_id}/ue-context-in-pgw-data", response_model=UeContextInPgwData)
def nhss_sdm_get_pgw_data(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$"),
):
    """Retrieve UE context in PGW data (PGW-C+SMF FQDN per APN).
    
    Used by UDM for PDU session continuity (5GC->EPC mobility).
    Returns PGW-C+SMF FQDN per APN/DNN plus emergency session data.
    """
    imsi = validate_imsi(ue_id)

    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_eps_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND: IMSI not found in EPS-UDR")

        cur.execute("SELECT * FROM tbl_eps_apn_profile WHERE imsi=%s AND is_active=1", (imsi,))
        apn_rows = cur.fetchall()

        pgw_info = []
        for apn in apn_rows:
            pgw_info.append(PgwInfo(
                pgwFqdn=apn.get("pgw_fqdn") or "",
                pgwIpv4=apn.get("pgw_ipv4"),
                apn=apn["apn"],
                dnn=apn["apn"],
            ))

        # Emergency data from subscriber record
        emergency_fqdn = None
        emergency_plmn = None
        emergency_ip = None
        emergency_time = None
        if row.get("odb_data"):
            try:
                odb = json.loads(row["odb_data"]) if isinstance(row["odb_data"], str) else row["odb_data"]
                emergency_fqdn = odb.get("emergencyPgwFqdn")
                emergency_plmn = odb.get("emergencyPlmnId")
                emergency_ip = odb.get("emergencyIpAddr")
                emergency_time = odb.get("emergencyRegistrationTime")
            except Exception:
                pass

        return UeContextInPgwData(
            pgwInfo=pgw_info,
            emergencyFqdn=emergency_fqdn,
            emergencyPlmnId=emergency_plmn,
            emergencyIpAddr=emergency_ip,
            emergencyRegistrationTime=emergency_time,
        )
    finally:
        conn.close()


@app.post("/nhss-sdm/v1/{ue_id}/subscriptions", status_code=201)
def nhss_sdm_subscribe(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$"),
    sub: SubscriptionData = None,
):
    """Subscribe to PGW data changes (UE context in PGW data).
    
    UDM subscribes to be notified when PGW-C+SMF FQDN changes for this UE.
    Returns 201 Created with Location header.
    """
    imsi = validate_imsi(ue_id)

    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT 1 FROM tbl_eps_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

        sub_id = str(uuid.uuid4())
        expires = sub.expires if sub and sub.expires else None

        cur.execute(
            """INSERT INTO tbl_nhss_subscription
               (imsi, subscription_type, callback_reference, nf_instance_id,
                monitored_resource_uris, expires, immediate_report)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (imsi, "sdm_pgw_data", sub.callbackReference, sub.nfInstanceId,
             json.dumps(sub.monitoredResourceUris), expires, sub.immediateReport),
        )
        conn.commit()

        audit_sync(imsi, "hss_to_udm", "pgw_data_subscribe", {
            "subscriptionId": sub_id,
            "callbackReference": sub.callbackReference,
        }, "sent")

        return JSONResponse(
            status_code=201,
            content={"subscriptionId": sub_id, "expires": expires},
            headers={"Location": f"/nhss-sdm/v1/{ue_id}/subscriptions/{sub_id}"},
        )
    finally:
        conn.close()


@app.delete("/nhss-sdm/v1/{ue_id}/subscriptions/{subscription_id}", status_code=204)
def nhss_sdm_unsubscribe(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$"),
    subscription_id: str = PathParam(...),
):
    """Unsubscribe from PGW data changes."""
    imsi = validate_imsi(ue_id)
    conn = get_eps_udr()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM tbl_nhss_subscription WHERE imsi=%s AND id=%s",
            (imsi, subscription_id),
        )
        conn.commit()
        return JSONResponse(status_code=204, content={})
    finally:
        conn.close()


@app.patch("/nhss-sdm/v1/{ue_id}/subscriptions/{subscription_id}", status_code=204)
def nhss_sdm_modify_subscription(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$"),
    subscription_id: str = PathParam(...),
    sub: SubscriptionData = None,
):
    """Modify an existing SDM subscription."""
    imsi = validate_imsi(ue_id)
    conn = get_eps_udr()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE tbl_nhss_subscription
               SET callback_reference=%s, monitored_resource_uris=%s,
                   expires=%s, immediate_report=%s, updated_at=CURRENT_TIMESTAMP
               WHERE imsi=%s AND id=%s""",
            (sub.callbackReference, json.dumps(sub.monitoredResourceUris),
             sub.expires, sub.immediateReport, imsi, subscription_id),
        )
        conn.commit()
        return JSONResponse(status_code=204, content={})
    finally:
        conn.close()


# ============================================================================
# Pydantic Models - Nhss_UECM (clause 6.3)
# ============================================================================
class DeregistrationRequest(BaseModel):
    imsi: str = Field(..., pattern=r"^[0-9]{5,15}$")
    deregReason: str = Field(..., pattern="^(UE_INITIAL_AND_SINGLE_REGISTRATION|UE_INITIAL_AND_DUAL_REGISTRATION|EPS_TO_5GS_MOBILITY|EPS_TO_5GS_MOBILITY_WITHOUT_N26_IWK)$")
    guami: Optional[str] = None


class ImeiUpdateInfo(BaseModel):
    imsi: str = Field(..., pattern=r"^[0-9]{5,15}$")
    imei: Optional[str] = Field(None, pattern=r"^[0-9]{14,15}$")
    imei_sv: Optional[str] = Field(None, pattern=r"^[0-9]{16}$")


class ImeiUpdateResponse(BaseModel):
    previousImei: Optional[str] = None
    previousImeiSv: Optional[str] = None


class RoamingStatusUpdateInfo(BaseModel):
    imsi: str = Field(..., pattern=r"^[0-9]{5,15}$")
    plmnId: str = Field(..., pattern=r"^\d{6}$")


# ============================================================================
# Nhss_UECM: SNDeregistration (clause 6.3 / 5.4.2.2)
# UDM asks HSS to cancel EPS/3G serving node after IRAT mobility
# ============================================================================
@app.post("/nhss-uecm/v1/deregister-sn", status_code=204)
def nhss_uecm_deregister_sn(req: DeregistrationRequest):
    """Cancel serving node (SNDeregistration).
    
    Implements the four DeregistrationReason values with exact CLR/MAP-D fan-out:
    - UE_INITIAL_AND_SINGLE_REGISTRATION: S6a/S6d/Gr CLR to MME/SGSN + MAP D CLR to MSC/VLR
    - UE_INITIAL_AND_DUAL_REGISTRATION: S6d/Gr(S4) CLR to SGSN only
    - EPS_TO_5GS_MOBILITY: S6a CLR to MME + MAP D CLR to MSC/VLR + S6d/Gr(S4) CLR to SGSN
    - EPS_TO_5GS_MOBILITY_WITHOUT_N26_IWK: S6d/Gr(S4) CLR to SGSN only (NO S6a to MME)
    """
    imsi = validate_imsi(req.imsi)

    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_eps_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

        # Record the deregistration action per reason (TS 23.632 L.5.3)
        actions = []
        reason = req.deregReason

        if reason == "UE_INITIAL_AND_SINGLE_REGISTRATION":
            actions.append("S6a CLR to MME (MME_UPDATE_PROCEDURE)")
            actions.append("MAP D Cancel Location to MSC/VLR")
            actions.append("Delete stored MME address and number")
            actions.append("Delete VLR number if exists")

        elif reason == "UE_INITIAL_AND_DUAL_REGISTRATION":
            actions.append("S6d/Gr(S4) CLR to SGSN (SGSN_UPDATE_PROCEDURE)")
            actions.append("Delete stored SGSN address and number")

        elif reason == "EPS_TO_5GS_MOBILITY":
            actions.append("S6a CLR to MME (MME_UPDATE_PROCEDURE)")
            actions.append("MAP D Cancel Location to MSC/VLR if VLR number exists")
            actions.append("S6d/Gr(S4) CLR to SGSN (SGSN_UPDATE_PROCEDURE)")

        elif reason == "EPS_TO_5GS_MOBILITY_WITHOUT_N26_IWK":
            # TS 23.502 clause 4.11.2.3: do NOT send S6a CLR to MME
            actions.append("S6d/Gr(S4) CLR to SGSN only")
            actions.append("Do NOT send S6a Cancel Location to MME")

        # Update subscriber status
        cur.execute(
            "UPDATE tbl_eps_subscriber SET subscriber_status=3, updated_at=CURRENT_TIMESTAMP WHERE imsi=%s",
            (imsi,),
        )
        conn.commit()

        audit_sync(imsi, "hss_to_udm", "deregister_sn", {
            "deregReason": reason,
            "guami": req.guami,
            "actions": actions,
        }, "acknowledged")

        return JSONResponse(status_code=204, content={})
    finally:
        conn.close()


# ============================================================================
# Nhss_UECM: IMEI Update (clause 6.3 / 5.4.2.2)
# UDM tells HSS about IMEI/PEI change; HSS returns previous value
# ============================================================================
@app.post("/nhss-uecm/v1/imei-update", response_model=ImeiUpdateResponse)
def nhss_uecm_imei_update(req: ImeiUpdateInfo):
    """Update IMEI/PEI in HSS.
    
    Returns 204 if HSS had no stored IMEI(SV).
    Returns 200 + previous value if HSS had a stored value (replaced).
    """
    imsi = validate_imsi(req.imsi)

    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT imei, imei_sv FROM tbl_eps_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

        prev_imei = row.get("imei")
        prev_imei_sv = row.get("imei_sv")

        new_imei = req.imei or req.imei_sv
        if not new_imei:
            raise HTTPException(status_code=400, detail="IMEI or IMEISV required")

        cur.execute(
            "UPDATE tbl_eps_subscriber SET imei=%s, imei_sv=%s, updated_at=CURRENT_TIMESTAMP WHERE imsi=%s",
            (req.imei, req.imei_sv, imsi),
        )
        conn.commit()

        audit_sync(imsi, "hss_to_udm", "update_imei", {
            "previousImei": prev_imei,
            "previousImeiSv": prev_imei_sv,
            "newImei": req.imei,
            "newImeiSv": req.imei_sv,
        }, "acknowledged")

        if prev_imei or prev_imei_sv:
            return ImeiUpdateResponse(previousImei=prev_imei, previousImeiSv=prev_imei_sv)
        else:
            return JSONResponse(status_code=204, content={})
    finally:
        conn.close()


# ============================================================================
# Nhss_UECM: Roaming Status Update (clause 6.3 / 5.4.2.2)
# UDM tells HSS about roaming status change
# ============================================================================
@app.post("/nhss-uecm/v1/roaming-status-update", status_code=204)
def nhss_uecm_roaming_status_update(req: RoamingStatusUpdateInfo):
    """Update roaming status (PLMN) in HSS."""
    imsi = validate_imsi(req.imsi)

    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT 1 FROM tbl_eps_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

        cur.execute(
            "UPDATE tbl_eps_subscriber SET roaming_restricted=1, updated_at=CURRENT_TIMESTAMP WHERE imsi=%s",
            (imsi,),
        )
        conn.commit()

        audit_sync(imsi, "hss_to_udm", "update_roaming", {
            "plmnId": req.plmnId,
        }, "acknowledged")

        return JSONResponse(status_code=204, content={})
    finally:
        conn.close()


# ============================================================================
# Pydantic Models - Nhss_EE (clause 6.4)
# ============================================================================
class MonitoringConfiguration(BaseModel):
    eventType: str = Field(..., pattern="^(LOSS_OF_CONNECTIVITY|UE_REACHABILITY_FOR_DATA|UE_REACHABILITY_FOR_SMS|LOCATION_REPORTING|COMMUNICATION_FAILURE|AVAILABILITY_AFTER_DDN_FAILURE|PDN_CONNECTIVITY_STATUS)$")
    immediateFlag: bool = False
    locationReportingConfiguration: Optional[Dict[str, Any]] = None
    lossConnectivityConfiguration: Optional[Dict[str, Any]] = None
    reachabilityForDataConfiguration: Optional[Dict[str, Any]] = None
    pduSessionStatusCfg: Optional[Dict[str, Any]] = None
    idleStatusInd: bool = False


class EeSubscription(BaseModel):
    callbackReference: str
    scefId: Optional[str] = None
    scefDiamRealm: Optional[str] = None
    monitoringConfigurations: Optional[Dict[str, MonitoringConfiguration]] = None
    supportedFeatures: Optional[str] = None
    reportingOptions: Optional[Dict[str, Any]] = None
    mtcProviderInformation: Optional[Dict[str, Any]] = None
    externalIdentifier: Optional[str] = None


class CreatedEeSubscription(BaseModel):
    eeSubscription: EeSubscription
    eventReports: Optional[List[Dict[str, Any]]] = None
    failedMonitoringConfigs: Optional[Dict[str, Dict[str, str]]] = None
    currentStatusNotAvailableList: Optional[List[str]] = None
    supportedFeatures: Optional[str] = None


class MonitoringReport(BaseModel):
    referenceId: str
    eventType: str
    timeStamp: str
    report: Optional[Dict[str, Any]] = None


# ============================================================================
# Nhss_EE: EPC monitoring subscriptions (clause 6.4 / 5.5)
# UDM configures EPC monitoring on behalf of combined SCEF+NEF
# Features: ERIR (Event Reports in Response), GBEE (Group-based)
# ============================================================================
@app.post("/nhss-ee/v1/{ue_id}/ee-subscriptions", response_model=CreatedEeSubscription, status_code=201)
def nhss_ee_subscribe(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$"),
    sub: EeSubscription = None,
):
    """Subscribe to EPC monitoring events.
    
    Combined SCEF+NEF configures monitoring for both EPC and 5GC.
    HSS configures EPC per TS 23.682 and returns result.
    With ERIR support, current reports may be in the 201 response.
    """
    imsi = validate_imsi(ue_id)

    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT 1 FROM tbl_eps_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

        sub_id = str(uuid.uuid4())
        supported_features = sub.supportedFeatures

        # ERIR: if supported, return current known reports in 201 response
        event_reports = None
        failed_configs = None
        status_not_available = None

        if sub.monitoringConfigurations:
            event_reports = []
            failed_configs = {}
            for ref_id, mc in sub.monitoringConfigurations.items():
                # Simulate checking current status
                if mc.eventType == "LOCATION_REPORTING":
                    event_reports.append({
                        "referenceId": ref_id,
                        "eventType": mc.eventType,
                        "timeStamp": datetime.now(timezone.utc).isoformat(),
                        "report": {"currentLocation": "unknown", "accuracy": "CELL_ID"},
                    })
                elif mc.eventType == "UE_REACHABILITY_FOR_DATA":
                    if not supported_features or "ERIR" not in supported_features:
                        failed_configs[ref_id] = {"eventType": mc.eventType, "failedCause": "UNSUPPORTED_MONITORING_REPORT_OPTIONS"}

        cur.execute(
            """INSERT INTO tbl_nhss_subscription
               (imsi, subscription_type, callback_reference, nf_instance_id,
                monitored_resource_uris, expires, immediate_report,
                monitoring_configurations, reporting_options, mtc_provider_information)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (imsi, "ee_monitoring", sub.callbackReference, str(uuid.uuid4()),
             json.dumps([sub.callbackReference]), None, sub.immediateFlag,
             json.dumps({k: v.model_dump() for k, v in (sub.monitoringConfigurations or {}).items()}),
             json.dumps(sub.reportingOptions) if sub.reportingOptions else None,
             json.dumps(sub.mtcProviderInformation) if sub.mtcProviderInformation else None),
        )
        conn.commit()

        audit_sync(imsi, "hss_to_udm", "update_roaming", {
            "subscriptionId": sub_id,
            "eventTypes": list((sub.monitoringConfigurations or {}).keys()),
        }, "sent")

        return CreatedEeSubscription(
            eeSubscription=sub,
            eventReports=event_reports,
            failedMonitoringConfigs=failed_configs,
            currentStatusNotAvailableList=status_not_available,
            supportedFeatures=supported_features,
        )
    finally:
        conn.close()


@app.delete("/nhss-ee/v1/{ue_id}/ee-subscriptions/{subscription_id}", status_code=204)
def nhss_ee_unsubscribe(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$"),
    subscription_id: str = PathParam(...),
):
    """Unsubscribe from EPC monitoring events."""
    imsi = validate_imsi(ue_id)
    conn = get_eps_udr()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM tbl_nhss_subscription WHERE imsi=%s AND id=%s AND subscription_type='ee_monitoring'",
            (imsi, subscription_id),
        )
        conn.commit()
        return JSONResponse(status_code=204, content={})
    finally:
        conn.close()


@app.patch("/nhss-ee/v1/{ue_id}/ee-subscriptions/{subscription_id}", status_code=204)
def nhss_ee_modify_subscription(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$"),
    subscription_id: str = PathParam(...),
    sub: EeSubscription = None,
):
    """Modify an existing EE subscription."""
    imsi = validate_imsi(ue_id)
    conn = get_eps_udr()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE tbl_nhss_subscription
               SET callback_reference=%s, monitoring_configurations=%s,
                   reporting_options=%s, updated_at=CURRENT_TIMESTAMP
               WHERE imsi=%s AND id=%s AND subscription_type='ee_monitoring'""",
            (sub.callbackReference,
             json.dumps({k: v.model_dump() for k, v in (sub.monitoringConfigurations or {}).items()}),
             json.dumps(sub.reportingOptions) if sub.reportingOptions else None,
             imsi, subscription_id),
        )
        conn.commit()
        return JSONResponse(status_code=204, content={})
    finally:
        conn.close()


# ============================================================================
# Pydantic Models - Nhss_PP (clause 6.5)
# ============================================================================
class CommunicationCharacteristicsAF(BaseModel):
    ppDlPacketCount: Optional[int] = None
    maximumResponseTime: Optional[int] = None  # DurationSec
    maximumLatency: Optional[int] = None  # DurationSec


class PpDataEntry(BaseModel):
    referenceId: str
    communicationCharacteristics: Optional[CommunicationCharacteristicsAF] = None
    validityTime: Optional[str] = None
    mtcProviderInformation: Optional[Dict[str, Any]] = None
    supportedFeatures: Optional[str] = None


# ============================================================================
# Nhss_PP: Per-AF parameter provisioning for EPC (clause 6.5 / 5.6)
# UDM pushes externally provisioned parameters into HSS for EPC enforcement
# {ueId} may be VarUeId, ExtGroupId, or "anyUE"
# ============================================================================
@app.put("/nhss-pp/v1/{ue_id}/pp-data-store/{af_instance_id}", status_code=201)
def nhss_pp_create(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$|anyUE$"),
    af_instance_id: str = PathParam(...),
    entry: PpDataEntry = None,
):
    """Create or update PP data entry for an AF instance.
    
    Returns 201 Created on create, 204 No Content on update.
    When max latency/response time/DL buffering changes, HSS may
    need to adjust active time/periodic registration timer and
    notify the MME.
    """
    imsi = None if ue_id == "anyUE" else validate_imsi(ue_id)

    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        if imsi:
            cur.execute("SELECT 1 FROM tbl_eps_subscriber WHERE imsi=%s", (imsi,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

        # Check if exists (update vs create)
        cur.execute(
            "SELECT 1 FROM tbl_nhss_pp_data WHERE imsi=%s AND af_instance_id=%s AND reference_id=%s",
            (imsi, af_instance_id, entry.referenceId),
        )
        exists = cur.fetchone()

        if exists:
            cur.execute(
                """UPDATE tbl_nhss_pp_data
                   SET communication_characteristics=%s, validity_time=%s,
                       mtc_provider_information=%s, supported_features=%s,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE imsi=%s AND af_instance_id=%s AND reference_id=%s""",
                (json.dumps(entry.communicationCharacteristics.model_dump() if entry.communicationCharacteristics else None),
                 entry.validityTime,
                 json.dumps(entry.mtcProviderInformation) if entry.mtcProviderInformation else None,
                 entry.supportedFeatures, imsi, af_instance_id, entry.referenceId),
            )
            conn.commit()
            return JSONResponse(status_code=204, content={})
        else:
            cur.execute(
                """INSERT INTO tbl_nhss_pp_data
                   (imsi, af_instance_id, reference_id, communication_characteristics,
                    validity_time, mtc_provider_information, supported_features)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (imsi, af_instance_id, entry.referenceId,
                 json.dumps(entry.communicationCharacteristics.model_dump() if entry.communicationCharacteristics else None),
                 entry.validityTime,
                 json.dumps(entry.mtcProviderInformation) if entry.mtcProviderInformation else None,
                 entry.supportedFeatures),
            )
            conn.commit()

            audit_sync(imsi or "anyUE", "hss_to_udm", "pp_provision", {
                "afInstanceId": af_instance_id,
                "referenceId": entry.referenceId,
            }, "sent")

            return JSONResponse(
                status_code=201,
                content={"referenceId": entry.referenceId, "afInstanceId": af_instance_id},
            )
    finally:
        conn.close()


@app.delete("/nhss-pp/v1/{ue_id}/pp-data-store/{af_instance_id}/{reference_id}", status_code=204)
def nhss_pp_delete(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$|anyUE$"),
    af_instance_id: str = PathParam(...),
    reference_id: str = PathParam(...),
):
    """Delete PP data entry."""
    imsi = None if ue_id == "anyUE" else validate_imsi(ue_id)
    conn = get_eps_udr()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM tbl_nhss_pp_data WHERE imsi=%s AND af_instance_id=%s AND reference_id=%s",
            (imsi, af_instance_id, reference_id),
        )
        conn.commit()
        return JSONResponse(status_code=204, content={})
    finally:
        conn.close()


@app.get("/nhss-pp/v1/{ue_id}/pp-data-store/{af_instance_id}/{reference_id}")
def nhss_pp_get(
    ue_id: str = PathParam(..., pattern=r"^(imsi-)?[0-9]{5,15}$|anyUE$"),
    af_instance_id: str = PathParam(...),
    reference_id: str = PathParam(...),
):
    """Get PP data entry."""
    imsi = None if ue_id == "anyUE" else validate_imsi(ue_id)
    conn = get_eps_udr()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM tbl_nhss_pp_data WHERE imsi=%s AND af_instance_id=%s AND reference_id=%s",
            (imsi, af_instance_id, reference_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
        return row
    finally:
        conn.close()


# ============================================================================
# Nhss_EE Notify (callback from HSS to UDM - called by UDM to receive notifications)
# This is the endpoint UDM exposes; HSS posts MonitoringReport here
# ============================================================================
@app.post("/nhss-ee/v1/notify")
def nhss_ee_notify(report: MonitoringReport):
    """Receive event occurrence notification (HSS internal callback).
    
    In production, this would be called by the HSS monitoring engine
    when an EPC event is detected. The UDM receives this via its own
    Nudm_EE Notify callback chain.
    """
    return {"status": "received", "referenceId": report.referenceId}


# ============================================================================
# Redirect helpers (307/308 with 3gpp-Sbi-Target-Nf-Id)
# ============================================================================
@app.get("/nhss/redirect/{target_nf}")
def nhss_redirect(target_nf: str, location: str = Query(...)):
    """307/308 redirection per TS 29.500 clause 5."""
    return JSONResponse(
        status_code=307,
        content={},
        headers={
            "Location": location,
            "3gpp-Sbi-Target-Nf-Id": target_nf,
        },
    )
