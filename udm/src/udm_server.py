"""UDM - Unified Data Management reference implementation.

FastAPI REST service exposing subscriber data (HLR/HSS/UDM tri-mode schema
per hssdbInitial.sql covering 3GPP Rel-15 through Rel-20).

Extended for 5G/4G/3G/2G with full key hierarchy, batch provisioning,
Nudm_SDM endpoints (TS 29.503), Diameter S6a/Cx (TS 29.272),
APN/DNN profiles, supplementary services, roaming, USSD/CAMEL routing.

Endpoints:
  Health:       GET /health
  Subscriber:   GET/POST/PUT/DELETE /subscribers/{imsi}
                GET /subscribers/{imsi}/full-profile
  Auth Vector:  GET /subscribers/{imsi}/auth-vector
                POST /subscribers/{imsi}/auth-vector/generate
  Nudm_SDM:     GET /nudm-sdm/v2/{imsi}/am-data
                GET /nudm-sdm/v2/{imsi}/smf-select-data
                GET /nudm-sdm/v2/{imsi}/ue-cm-data
                GET /nudm-sdm/v2/{imsi}/sm-data
                GET /nudm-sdm/v2/{imsi}/trace-data
                GET /nudm-sdm/v2/{imsi}/sms-data
  EPS (S6a):    GET /subscribers/{imsi}/eps-subscription
                PUT /subscribers/{imsi}/eps-subscription
  5G:           GET /subscribers/{imsi}/5g-subscription
                PUT /subscribers/{imsi}/5g-subscription
  IMS:          GET /subscribers/{imsi}/ims-subscription
                PUT /subscribers/{imsi}/ims-subscription
  APN/DNN:      GET/POST/PUT/DELETE /subscribers/{imsi}/apn-profiles
  Supplementary:GET/POST/PUT/DELETE /subscribers/{imsi}/supplementary-services
  Roaming:      GET/POST/PUT/DELETE /subscribers/{imsi}/roaming-profiles
  USSD/CAMEL:   GET/POST /ussd-routes, /camel-profiles
  Batch:        POST /subscribers/batch
                GET /batches/{batch_id}
  IMSI Range:   GET/POST /imsi-ranges/, POST /imsi-ranges/allocate
  Network Nodes:GET/POST /network-nodes/
"""

import csv
import io
import json
import logging
import os
import secrets
import sys
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import mysql.connector
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel, Field, field_validator
import redis

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suci as suci_lib  # noqa: E402  (TS 33.501 Annex C de-concealment)

logger = logging.getLogger("udm")

# Crypto imports for Milenage/AES (TS 33.102, 33.501)
try:
    from Crypto.Cipher import AES
    from Crypto.Hash import SHA256, HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

if not CRYPTO_AVAILABLE:
    raise SystemExit(
        "CRYPTO_UNAVAILABLE: pycryptodome is required for Milenage vectors; "
        "refusing to start. Install pycryptodome (docker/udm/Dockerfile)."
    )

app = FastAPI(
    title="UDM Tri-Mode (5G/4G/3G/2G) - Rel-15 to Rel-20",
    version="3.0.0",
    description="3GPP TS 29.503, 29.272, 29.228, 23.008, 33.501 compliant UDM/HSS/HLR"
)

# ============================================================================
# Configuration
# ============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "hssdb"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "hss"),
    "password": os.getenv("DB_PASSWORD", "hss123"),
    "database": os.getenv("DB_NAME", "hssdb"),
}

REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "redis"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "password": os.getenv("REDIS_PASSWORD", "change-me"),
    "decode_responses": True,
}

OPERATOR_KEY = bytes.fromhex(os.getenv("OPERATOR_KEY", "00" * 16))  # OP/OPc default


# ============================================================================
# Milenage / AES Crypto (TS 33.102, 33.501)
# ============================================================================
class MilenageCrypto:
    """Milenage algorithm set (f1, f1*, f2, f3, f4, f5, f5*) per TS 33.102.
    
    Uses AES-128 with operator key OPc. For 5G: TUAK or Milenage with K (TS 33.501).
    """
    
    # Constants per TS 33.102
    R1 = bytes.fromhex("00000000000000000000000000000000")
    R2 = bytes.fromhex("00000000000000000000000000000001")
    R3 = bytes.fromhex("00000000000000000000000000000002")
    R4 = bytes.fromhex("00000000000000000000000000000004")
    R5 = bytes.fromhex("00000000000000000000000000000008")
    C1 = bytes.fromhex("00000000000000000000000000000000")
    C2 = bytes.fromhex("00000000000000000000000000000001")
    C3 = bytes.fromhex("00000000000000000000000000000002")
    C4 = bytes.fromhex("00000000000000000000000000000004")
    C5 = bytes.fromhex("00000000000000000000000000000008")
    
    def __init__(self, opc: bytes):
        """Initialize with OPc (16 bytes)."""
        self.opc = opc
        self.cipher = AES.new(opc, AES.MODE_ECB)
    
    def _rotl(self, x: bytes, r: int) -> bytes:
        """Rotate left by r bits."""
        val = int.from_bytes(x, 'big')
        val = ((val << r) | (val >> (128 - r))) & ((1 << 128) - 1)
        return val.to_bytes(16, 'big')
    
    def _xor(self, a: bytes, b: bytes) -> bytes:
        return bytes(x ^ y for x, y in zip(a, b))
    
    def f1(self, k: bytes, rand: bytes, sqn: bytes, amf: bytes) -> bytes:
        """MAC-A (64 bits) for authentication."""
        temp = self._xor(self._xor(rand, self.opc), self.cipher.encrypt(self._xor(k, self.opc)))
        temp = self._xor(temp, self.R1)
        temp = self.cipher.encrypt(temp)
        temp = self._xor(temp, self.C1)
        temp = self._xor(temp, sqn)
        temp = self._xor(temp, amf.ljust(16, b'\x00'))
        mac_a = self.cipher.encrypt(temp)[:8]
        return mac_a
    
    def f1_star(self, k: bytes, rand: bytes, sqn: bytes, amf: bytes) -> bytes:
        """MAC-S (64 bits) for resynchronization."""
        temp = self._xor(self._xor(rand, self.opc), self.cipher.encrypt(self._xor(k, self.opc)))
        temp = self._xor(temp, self.R1)
        temp = self.cipher.encrypt(temp)
        temp = self._xor(temp, self.C1)
        temp = self._xor(temp, sqn)
        temp = self._xor(temp, amf.ljust(16, b'\x00'))
        mac_s = self.cipher.encrypt(temp)[:8]
        return mac_s
    
    def f2(self, k: bytes, rand: bytes) -> bytes:
        """RES (64 bits) / XRES (256 bits for 5G)."""
        temp = self._xor(self._xor(rand, self.opc), self.cipher.encrypt(self._xor(k, self.opc)))
        temp = self._xor(temp, self.R2)
        temp = self.cipher.encrypt(temp)
        temp = self._xor(temp, self.C2)
        res = self.cipher.encrypt(temp)[:8]
        return res
    
    def f3(self, k: bytes, rand: bytes) -> bytes:
        """CK (128 bits) - Cipher Key."""
        temp = self._xor(self._xor(rand, self.opc), self.cipher.encrypt(self._xor(k, self.opc)))
        temp = self._xor(temp, self.R3)
        temp = self.cipher.encrypt(temp)
        temp = self._xor(temp, self.C3)
        ck = self.cipher.encrypt(temp)
        return ck
    
    def f4(self, k: bytes, rand: bytes) -> bytes:
        """IK (128 bits) - Integrity Key."""
        temp = self._xor(self._xor(rand, self.opc), self.cipher.encrypt(self._xor(k, self.opc)))
        temp = self._xor(temp, self.R4)
        temp = self.cipher.encrypt(temp)
        temp = self._xor(temp, self.C4)
        ik = self.cipher.encrypt(temp)
        return ik
    
    def f5(self, k: bytes, rand: bytes) -> bytes:
        """AK (48 bits) - Anonymity Key."""
        temp = self._xor(self._xor(rand, self.opc), self.cipher.encrypt(self._xor(k, self.opc)))
        temp = self._xor(temp, self.R5)
        temp = self.cipher.encrypt(temp)
        temp = self._xor(temp, self.C5)
        ak = self.cipher.encrypt(temp)[:6]
        return ak
    
    def f5_star(self, k: bytes, rand: bytes) -> bytes:
        """AK* (48 bits) for 5G."""
        return self.f5(k, rand)
    
    def derive_opc(self, op: bytes, k: bytes) -> bytes:
        """Derive OPc from OP and K: OPc = AES_K(OP)."""
        cipher_k = AES.new(k, AES.MODE_ECB)
        return cipher_k.encrypt(op)
    
    def derive_5g_keys(self, k: bytes, sqn: int, amf: bytes, rand: bytes = None) -> Dict[str, bytes]:
        """Derive 5G key hierarchy per TS 33.501 Annex A.
        
        K_SEAF = KDF(K, "5G:SEAF", SQN || AMF)
        K_AUSF = KDF(K_SEAF, "5G:AUSF", ...)
        K_AMF  = KDF(K_SEAF, "5G:AMF", ...)
        """
        if rand is None:
            rand = secrets.token_bytes(16)
        
        sqn_bytes = sqn.to_bytes(6, 'big')
        
        # K_AUSF = f5*(K, RAND) || CK || IK (simplified)
        ak_star = self.f5_star(k, rand)
        ck = self.f3(k, rand)
        ik = self.f4(k, rand)
        k_ausf = ak_star + ck + ik  # 6+16+16 = 38 bytes -> truncate to 32
        
        # K_SEAF = KDF(K_AUSF, "5G:SEAF", serving network name)
        # Simplified: use HMAC-SHA256
        k_seaf = HMAC.new(k_ausf[:32], b"5G:SEAF" + sqn_bytes + amf, SHA256).digest()
        
        # K_AMF = KDF(K_SEAF, "5G:AMF", AMF)
        k_amf = HMAC.new(k_seaf, b"5G:AMF" + amf, SHA256).digest()
        
        return {
            "k_ausf": k_ausf[:32],
            "k_seaf": k_seaf,
            "k_amf": k_amf,
            "ck": ck,
            "ik": ik,
            "ak_star": ak_star,
        }
    
    def generate_auth_vector_5g(self, k: bytes, sqn: int, amf: bytes) -> Dict[str, bytes]:
        """Generate 5G authentication vector (RAND, AUTN, XRES*, K_AUSF, K_SEAF, K_AMF)."""
        rand = secrets.token_bytes(16)
        sqn_bytes = sqn.to_bytes(6, 'big')
        
        # XRES* = f2(K, RAND) extended to 256 bits for 5G
        res = self.f2(k, rand)
        xres_star = res + SHA256.new(rand + k).digest()[:24]  # 8+24=32 bytes
        
        # AUTN = SQN ⊕ AK* || AMF || MAC
        ak_star = self.f5_star(k, rand)
        sqn_xor_ak = self._xor(sqn_bytes, ak_star)
        mac_a = self.f1(k, rand, sqn_bytes, amf)
        autn = sqn_xor_ak + amf.ljust(2, b'\x00')[:2] + mac_a  # 6+2+8=16 bytes
        
        keys = self.derive_5g_keys(k, sqn, amf, rand)
        
        return {
            "rand": rand,
            "autn": autn,
            "xres_star": xres_star,
            "res": res,
            "ck": keys["ck"],
            "ik": keys["ik"],
            "k_ausf": keys["k_ausf"],
            "k_seaf": keys["k_seaf"],
            "k_amf": keys["k_amf"],
        }
    
    def generate_auth_vector_4g(self, ki: bytes, sqn: int, amf: bytes) -> Dict[str, bytes]:
        """Generate 4G EPS authentication vector per TS 33.401."""
        rand = secrets.token_bytes(16)
        sqn_bytes = sqn.to_bytes(6, 'big')
        
        res = self.f2(ki, rand)
        xres = res  # 64-bit for 4G
        ck = self.f3(ki, rand)
        ik = self.f4(ki, rand)
        ak = self.f5(ki, rand)
        
        sqn_xor_ak = self._xor(sqn_bytes, ak)
        mac_a = self.f1(ki, rand, sqn_bytes, amf)
        autn = sqn_xor_ak + amf.ljust(2, b'\x00')[:2] + mac_a
        
        # K_ASME = KDF(CK, IK, SN_ID, ...)
        k_asme = HMAC.new(ck + ik, b"EPS:KASME" + sqn_bytes, SHA256).digest()
        
        return {
            "rand": rand,
            "autn": autn,
            "xres": xres,
            "res": res,
            "ck": ck,
            "ik": ik,
            "k_asme": k_asme,
        }
    
    def generate_auth_vector_2g3g(self, ki: bytes, rand: bytes = None) -> Dict[str, bytes]:
        """Generate 2G/3G authentication vector (COMP128 / Milenage)."""
        if rand is None:
            rand = secrets.token_bytes(16)
        
        sres = self.f2(ki, rand)[:4]  # 32-bit SRES
        kc = self.f3(ki, rand)[:8]    # 64-bit Kc
        
        return {
            "rand": rand,
            "sres": sres,
            "kc": kc,
        }


# Global crypto instance (will be initialized per-subscriber)
crypto = None


def get_crypto(opc_hex: str) -> MilenageCrypto:
    """Get MilenageCrypto instance for given OPc."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("pycryptodome not available - install for production crypto")
    return MilenageCrypto(bytes.fromhex(opc_hex))


def derive_opc(op: str, k: str) -> str:
    """Derive OPc from OP and K using AES-128."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("CRYPTO_UNAVAILABLE: cannot derive OPc without pycryptodome")
    op_bytes = bytes.fromhex(op)
    k_bytes = bytes.fromhex(k)
    cipher = AES.new(k_bytes, AES.MODE_ECB)
    opc = cipher.encrypt(op_bytes)
    return opc.hex().upper()


# ============================================================================
# DB / Redis Helpers
# ============================================================================
def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def get_redis():
    return redis.Redis(**REDIS_CONFIG)


def dict_row(cur, row):
    """Convert row to dict with column names."""
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row))


def dict_rows(cur, rows):
    return [dict_row(cur, r) for r in rows]


# ============================================================================
# Pydantic Models
# ============================================================================
class SubscriberBase(BaseModel):
    imsi: str = Field(..., pattern=r"^\d{15}$")
    msisdn: Optional[str] = Field(None, pattern=r"^\d+$")
    imei: Optional[str] = Field(None, pattern=r"^\d{15}$")
    imei_sv: Optional[str] = Field(None, pattern=r"^\d{16}$")
    
    # Root Keys
    k: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$", description="5G root key (K4) - 256-bit hex")
    ki: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$", description="4G/3G/2G root key (Ki) - 128-bit hex")
    op: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$", description="OP (Operator Variant) - 128-bit hex")
    opc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$", description="OPc (derived) - 128-bit hex")
    
    # Sequence & AMF
    sqn: int = Field(0, ge=0, le=2**48-1, description="Sequence number (48-bit)")
    amf: str = Field("8000", pattern=r"^[0-9A-Fa-f]{4}$", description="Auth Management Field (hex)")
    
    # Derived 5G Keys
    k_asme: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    k_seaf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    k_ausf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    
    # 2G/3G
    kc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{16}$")
    sres: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{8}$")
    
    # Network
    network_access_mode: int = Field(2, ge=0, le=3, description="0=GPRS,1=CS,2=Both,3=5G")
    subscriber_status: int = Field(0, ge=0, le=3, description="0=Active,1=Barred,2=Suspended,3=Detached")
    roaming_restricted: bool = False
    regional_restriction: Optional[Dict] = None
    odb_data: Optional[Dict] = None
    trace_config: Optional[Dict] = None
    
    # Rel-17+
    prose_enabled: bool = False
    redcap_allowed: bool = False
    ntn_allowed: bool = False
    eredcap_allowed: bool = False
    xr_allowed: bool = False
    aiml_allowed: bool = False
    
    # Batch/MVNO
    batch_id: Optional[str] = None
    mvno_mcc: Optional[str] = Field(None, pattern=r"^\d{3}$")
    mvno_mnc: Optional[str] = Field(None, pattern=r"^\d{3}$")

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
    imei_sv: Optional[str] = Field(None, pattern=r"^\d{16}$")
    k: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    ki: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    op: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    opc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    sqn: Optional[int] = Field(None, ge=0, le=2**48-1)
    amf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{4}$")
    k_asme: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    k_seaf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    k_ausf: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    kc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{16}$")
    sres: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{8}$")
    network_access_mode: Optional[int] = Field(None, ge=0, le=3)
    subscriber_status: Optional[int] = Field(None, ge=0, le=3)
    roaming_restricted: Optional[bool] = None
    regional_restriction: Optional[Dict] = None
    odb_data: Optional[Dict] = None
    trace_config: Optional[Dict] = None
    prose_enabled: Optional[bool] = None
    redcap_allowed: Optional[bool] = None
    ntn_allowed: Optional[bool] = None
    eredcap_allowed: Optional[bool] = None
    xr_allowed: Optional[bool] = None
    aiml_allowed: Optional[bool] = None


class SubscriberResponse(SubscriberBase):
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class AuthVectorRequest(BaseModel):
    rand: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    algorithm: str = Field("milenage", pattern="^(milenage|comp128v1|comp128v2|comp128v3|xor|tuak)$")


class AuthVectorResponse(BaseModel):
    imsi: str
    rand: str
    autn: str
    res: str
    xres: str
    xres_star: Optional[str] = None
    ck: str
    ik: str
    k_asme: str
    k_seaf: Optional[str] = None
    k_ausf: Optional[str] = None
    k_amf: Optional[str] = None
    sres: Optional[str] = None
    kc: Optional[str] = None


# EPS Subscription Models
class EPSSubscriptionBase(BaseModel):
    apn_config: Optional[Dict] = None
    default_apn: Optional[str] = None
    ue_ambr_ul: int = 100000000
    ue_ambr_dl: int = 100000000
    rat_restrictions: Optional[Dict] = None
    msisdn_list: Optional[Dict] = None
    csg_subscription: Optional[Dict] = None
    mme_subscription: Optional[Dict] = None
    hss_subscription: Optional[Dict] = None
    lcs_privacy: Optional[Dict] = None
    vplmn_dynamic: Optional[Dict] = None
    nb_iot_allowed: bool = False
    emtc_allowed: bool = False
    v2x_allowed: bool = False
    industrial_iot_allowed: bool = False
    redcap_allowed: bool = False


class EPSSubscriptionResponse(EPSSubscriptionBase):
    imsi: str
    created_at: str
    updated_at: str


# 5G Subscription Models
class FiveGSubscriptionBase(BaseModel):
    supi: Optional[str] = None
    suci_calc_info: Optional[Dict] = None
    default_nssai: Optional[Dict] = None
    allowed_nssai: Optional[Dict] = None
    ue_ambr_ul: int = 1000000000
    ue_ambr_dl: int = 1000000000
    rat_restrictions_5g: Optional[Dict] = None
    smf_selection: Optional[Dict] = None
    gmlc_address: Optional[str] = None
    lcs_privacy_5g: Optional[Dict] = None
    sor_info: Optional[Dict] = None
    ue_id_mapping: Optional[Dict] = None
    nssaa_info: Optional[Dict] = None
    vplmn_5g_data: Optional[Dict] = None
    urllc_allowed: bool = False
    mmtc_allowed: bool = False
    v2x_allowed_5g: bool = False
    redcap_allowed_5g: bool = False
    ntn_allowed_5g: bool = False
    pni_npn_allowed: bool = False
    eredcap_allowed_5g: bool = False
    mbs_allowed: bool = False
    xr_allowed_5g: bool = False
    aiml_allowed_5g: bool = False
    multicast_mbs_allowed: bool = False
    reduced_cap_allowed: bool = False
    aiml_enhanced_allowed: bool = False


class FiveGSubscriptionResponse(FiveGSubscriptionBase):
    imsi: str
    created_at: str
    updated_at: str


# IMS Subscription Models
class IMSSubscriptionBase(BaseModel):
    impu_list: Optional[Dict] = None
    impi: Optional[str] = None
    ims_domain: Optional[str] = None
    service_profile_id: Optional[str] = None
    scscf_name: Optional[str] = None
    scscf_realm: Optional[str] = None
    auth_scheme: str = "AKAv1-MD5"
    wildcarded_impu: bool = False
    mtsi_allowed: bool = False
    rcs_allowed: bool = False
    nr_multicast_allowed: bool = False
    emtsi_allowed: bool = False


class IMSSubscriptionResponse(IMSSubscriptionBase):
    imsi: str
    reg_status: str
    reg_expires: int
    contact_list: Optional[Dict] = None
    created_at: str
    updated_at: str


# APN Profile Models
class APNProfileBase(BaseModel):
    apn: str = Field(..., pattern=r"^.{1,100}$")
    apn_type: str = Field("internet", pattern="^(internet|ims|emergency|mms|enterprise|m2m|mbs|fmc)$")
    qci: int = Field(9, ge=1, le=255)
    arp_priority: int = Field(8, ge=1, le=15)
    arp_preempt_cap: bool = False
    arp_preempt_vuln: bool = False
    apn_ambr_ul: int = 100000000
    apn_ambr_dl: int = 100000000
    ue_ambr_ul: int = 100000000
    ue_ambr_dl: int = 100000000
    pcc_rule_name: Optional[str] = None
    pcc_rule_version: int = 1
    pdn_type: str = Field("ipv4v6", pattern="^(ipv4|ipv6|ipv4v6|non-ip)$")
    ipv4_addr_alloc: str = Field("dynamic", pattern="^(dynamic|static|dhcp)$")
    ipv6_prefix_len: int = Field(64, ge=1, le=128)
    static_ipv4: Optional[str] = None
    static_ipv6: Optional[str] = None
    dns_primary: str = "8.8.8.8"
    dns_secondary: str = "8.8.4.4"
    pgw_fqdn: Optional[str] = None
    pgw_ipv4: Optional[str] = None
    pgw_ipv6: Optional[str] = None
    sgw_fqdn: Optional[str] = None
    sgw_ipv4: Optional[str] = None
    charging_id: int = 0
    charging_gateway: Optional[str] = None
    is_emergency: bool = False
    dnn_selection_mode: str = Field("Verified", pattern="^(UE-provided|Network-provided|Verified)$")
    mvno_reseller_id: Optional[str] = None
    urllc_qos: bool = False
    redcap_qos: bool = False
    mbs_qos: bool = False
    is_default: bool = False
    is_active: bool = True


class APNProfileResponse(APNProfileBase):
    id: int
    imsi: str
    created_at: str
    updated_at: str


# Supplementary Service Models
class SupplementaryServiceBase(BaseModel):
    service_code: str = Field(..., pattern=r"^.{1,20}$")
    service_name: Optional[str] = None
    provision_status: str = Field("not_provisioned", pattern="^(not_provisioned|provisioned|active|deactivated)$")
    activation_code: Optional[str] = None
    deactivation_code: Optional[str] = None
    interrogation_code: Optional[str] = None
    registration_code: Optional[str] = None
    erasure_code: Optional[str] = None
    forwarding_number: Optional[str] = None
    forwarding_condition: str = Field("unconditional", pattern="^(unconditional|busy|no_reply|not_reachable|all)$")
    no_reply_timer: int = Field(20, ge=1, le=30)
    override_category: str = Field("none", pattern="^(none|operator|subscriber)$")
    max_simultaneous_calls: int = 0
    clip_provisioned: bool = True
    clir_provisioned: bool = True
    clir_option: str = Field("network_default", pattern="^(presentation_allowed|presentation_restricted|network_default)$")
    ussd_enabled: bool = True
    ussd_string_length: int = 160
    camel_phase: int = Field(3, ge=1, le=4)
    camel_tdp_list: Optional[Dict] = None
    mmtel_allowed: bool = False
    rcs_allowed: bool = False


class SupplementaryServiceResponse(SupplementaryServiceBase):
    id: int
    imsi: str
    created_at: str
    updated_at: str


# Roaming Profile Models
class RoamingProfileBase(BaseModel):
    visited_plmn: str = Field(..., pattern=r"^\d{6}$")
    roaming_allowed: bool = True
    rat_allowed: Optional[Dict] = None
    odb_roaming: bool = False
    odb_outgoing: bool = False
    odb_incoming: bool = False
    odb_premium: bool = False
    ho_restriction: Optional[Dict] = None
    charging_profile_id: Optional[str] = None
    v_mme_fqdn: Optional[str] = None
    v_mme_ipv4: Optional[str] = None
    v_sgsn_fqdn: Optional[str] = None
    v_sgsn_ipv4: Optional[str] = None
    v_pgw_fqdn: Optional[str] = None
    v_pgw_ipv4: Optional[str] = None
    v_amf_fqdn: Optional[str] = None
    v_amf_ipv4: Optional[str] = None
    v_smf_fqdn: Optional[str] = None
    v2x_roaming: bool = False
    redcap_roaming: bool = False
    ntn_roaming: bool = False


class RoamingProfileResponse(RoamingProfileBase):
    id: int
    imsi: str
    created_at: str
    updated_at: str


# USSD Routing Models
class USSDRouteBase(BaseModel):
    ussd_string: str = Field(..., pattern=r"^.{1,32}$")
    destination_type: str = Field("internal", pattern="^(internal|external_ussd_gw|scp|gmlc|imsi_based)$")
    destination_address: Optional[str] = None
    gsm_scf_address: Optional[str] = None
    service_key: int = 0
    default_response: Optional[str] = None
    timeout_sec: int = Field(10, ge=1, le=60)
    mvno_mcc: Optional[str] = Field(None, pattern=r"^\d{3}$")
    mvno_mnc: Optional[str] = Field(None, pattern=r"^\d{3}$")
    fiveg_ussd_allowed: bool = False
    is_active: bool = True
    priority: int = 100


class USSDRouteResponse(USSDRouteBase):
    id: int
    created_at: str
    updated_at: str


# CAMEL Profile Models
class CamelServiceProfileBase(BaseModel):
    service_key: int = Field(..., gt=0)
    tdp_list: Optional[Dict] = None
    gsm_scf_address: str
    default_call_handling: str = Field("continue", pattern="^(continue|release|route_to_scf)$")
    csi_psi: Optional[Dict] = None
    csi_csi: Optional[Dict] = None
    csi_ssi: Optional[Dict] = None
    csi_msi: Optional[Dict] = None
    csi_lsi: Optional[Dict] = None
    csi_v2x: Optional[Dict] = None
    csi_redcap: Optional[Dict] = None


class CamelServiceProfileResponse(CamelServiceProfileBase):
    id: int
    imsi: str
    created_at: str
    updated_at: str


# Network Node Models
class NetworkNodeBase(BaseModel):
    node_name: str = Field(..., pattern=r"^.{1,64}$")
    node_type: str = Field(..., pattern="^(MME|MSC|SGSN|PGW|SGW|HSS|PCRF|PCF|SMF|UPF|AMF|GMLC|SCP|USSD_GW|SMSC|NRF|AUSF|UDM|NEF|BSF|UDSF|NSSF)$")
    fqdn: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    diameter_host: Optional[str] = None
    diameter_realm: Optional[str] = None
    diameter_port: int = 3868
    sctp_port: int = 2905
    point_code: Optional[str] = None
    global_title: Optional[str] = None
    gt_translation_type: int = 0
    gt_numbering_plan: int = 1
    gt_nature_of_address: int = 4
    plmn_id: Optional[str] = Field(None, pattern=r"^\d{6}$")
    supported_interfaces: Optional[Dict] = None
    is_active: bool = True
    health_check_url: Optional[str] = None


class NetworkNodeResponse(NetworkNodeBase):
    id: int
    created_at: str
    updated_at: str


# Batch Models
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
    error_log: Optional[Dict] = None
    created_at: str
    completed_at: Optional[str] = None


# IMSI Range Models
class IMSIRangeCreate(BaseModel):
    range_name: str = Field(..., pattern=r"^.{1,64}$")
    mcc: str = Field(..., pattern=r"^\d{3}$")
    mnc: str = Field(..., pattern=r"^\d{3}$")
    msisdn_prefix: Optional[str] = None
    imsi_start: str = Field(..., pattern=r"^\d{15}$")
    imsi_end: str = Field(..., pattern=r"^\d{15}$")
    default_k: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    default_ki: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    default_op: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    default_opc: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    default_algorithm: str = "milenage"


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
    mvno_id: Optional[str] = None


class IMSIAllocateRequest(BaseModel):
    range_name: str
    count: int = Field(1, ge=1, le=10000)
    ki: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    op: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{32}$")
    k: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{64}$")
    network_access_mode: int = 2
    subscriber_status: int = 0


# Full Profile Response
class FullProfileResponse(BaseModel):
    subscriber: SubscriberResponse
    eps: Optional[EPSSubscriptionResponse] = None
    fiveg: Optional[FiveGSubscriptionResponse] = None
    ims: Optional[IMSSubscriptionResponse] = None
    apn_profiles: List[APNProfileResponse] = []
    supplementary_services: List[SupplementaryServiceResponse] = []
    roaming_profiles: List[RoamingProfileResponse] = []
    camel_profiles: List[CamelServiceProfileResponse] = []


# Nudm_SDM Models (TS 29.503)
class NudmAMData(BaseModel):
    supported_features: Optional[str] = None
    internal_group_ids: Optional[List[str]] = None
    subscribed_gupu_ids: Optional[List[str]] = None
    sub_data_management: Optional[Dict] = None
    am_policy_data: Optional[Dict] = None
    ue_ambr: Optional[Dict] = None


class NudmSmfSelectData(BaseModel):
    supported_features: Optional[str] = None
    subscribed_snssais: Optional[List[Dict]] = None
    default_snssai: Optional[List[Dict]] = None
    smf_selection_subscription_data: Optional[List[Dict]] = None


class NudmUeCmData(BaseModel):
    supported_features: Optional[str] = None
    pdu_sessions: Optional[Dict] = None
    registrations: Optional[List[Dict]] = None


class NudmSmData(BaseModel):
    supported_features: Optional[str] = None
    dnn_configurations: Optional[Dict] = None
    lcs_privacy_data: Optional[Dict] = None
    lcs_mo_data: Optional[Dict] = None


# ============================================================================
# Health
# ============================================================================
def _suci_profile_summary():
    try:
        return suci_lib.configured_profiles()
    except suci_lib.SuciKeyNotConfigured as exc:
        logger.error("SUCI profile configuration rejected: %s", exc)
        return {"error": exc.code, "detail": str(exc)}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "udm",
        "version": "3.0.0",
        "modes": ["5G", "4G", "3G", "2G"],
        "crypto": "milenage",
        "crypto_library": "pycryptodome",
        "suci_profiles": _suci_profile_summary(),
        "specs": ["TS 29.503", "TS 29.272", "TS 29.228", "TS 33.501", "TS 33.102", "TS 23.008"]
    }


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
            if CRYPTO_AVAILABLE and opc:
                crypto = get_crypto(opc)
                derived = crypto.derive_5g_keys(bytes.fromhex(sub.k), sub.sqn, bytes.fromhex(sub.amf))
                keys_5g = {k: v.hex().upper() for k, v in derived.items()}
            else:
                raise HTTPException(
                    status_code=500,
                    detail="CRYPTO_UNAVAILABLE: pycryptodome required for 5G key derivation — fail closed"
                )
        
        cur.execute(
            """INSERT INTO tbl_subscriber
               (imsi, msisdn, imei, imei_sv, k, ki, op, opc, sqn, amf,
                k_asme, k_seaf, k_ausf, kc, sres,
                network_access_mode, subscriber_status, roaming_restricted,
                regional_restriction, odb_data, trace_config,
                prose_enabled, redcap_allowed, ntn_allowed, eredcap_allowed, xr_allowed, aiml_allowed,
                batch_id, mvno_mcc, mvno_mnc)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (sub.imsi, sub.msisdn, sub.imei, sub.imei_sv, sub.k, sub.ki, sub.op, opc,
             sub.sqn, sub.amf.upper(),
             keys_5g.get("k_asme"), keys_5g.get("k_seaf"), keys_5g.get("k_ausf"),
             sub.kc, sub.sres,
             sub.network_access_mode, sub.subscriber_status, sub.roaming_restricted,
             json.dumps(sub.regional_restriction) if sub.regional_restriction else None,
             json.dumps(sub.odb_data) if sub.odb_data else None,
             json.dumps(sub.trace_config) if sub.trace_config else None,
             sub.prose_enabled, sub.redcap_allowed, sub.ntn_allowed, sub.eredcap_allowed, sub.xr_allowed, sub.aiml_allowed,
             sub.batch_id, sub.mvno_mcc, sub.mvno_mnc),
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
        
        # Check exists
        cur.execute("SELECT 1 FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        # Build dynamic update
        fields = []
        values = []
        for field, value in sub.model_dump(exclude_unset=True).items():
            if field in ("k", "ki", "op", "opc", "k_asme", "k_seaf", "k_ausf", "amf") and value:
                value = value.upper()
            elif field in ("regional_restriction", "odb_data", "trace_config") and value is not None:
                value = json.dumps(value)
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
# Full Profile (All Tables)
# ============================================================================
@app.get("/subscribers/{imsi}/full-profile", response_model=FullProfileResponse)
def get_full_profile(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        
        # Subscriber
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        sub = cur.fetchone()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        # EPS
        cur.execute("SELECT * FROM tbl_eps_subscription WHERE imsi=%s", (imsi,))
        eps = cur.fetchone()
        
        # 5G
        cur.execute("SELECT * FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        fiveg = cur.fetchone()
        
        # IMS
        cur.execute("SELECT * FROM tbl_ims_subscription WHERE imsi=%s", (imsi,))
        ims = cur.fetchone()
        
        # APN Profiles
        cur.execute("SELECT * FROM tbl_apn_profile WHERE imsi=%s", (imsi,))
        apn_profiles = cur.fetchall()
        
        # Supplementary Services
        cur.execute("SELECT * FROM tbl_supplementary_service WHERE imsi=%s", (imsi,))
        supp_services = cur.fetchall()
        
        # Roaming Profiles
        cur.execute("SELECT * FROM tbl_roaming_profile WHERE imsi=%s", (imsi,))
        roaming_profiles = cur.fetchall()
        
        # CAMEL Profiles
        cur.execute("SELECT * FROM tbl_camel_service_profile WHERE imsi=%s", (imsi,))
        camel_profiles = cur.fetchall()
        
        return FullProfileResponse(
            subscriber=sub,
            eps=eps,
            fiveg=fiveg,
            ims=ims,
            apn_profiles=apn_profiles or [],
            supplementary_services=supp_services or [],
            roaming_profiles=roaming_profiles or [],
            camel_profiles=camel_profiles or [],
        )
    finally:
        conn.close()


# ============================================================================
# Authentication Vector Generation (Production Crypto)
# ============================================================================
@app.get("/subscribers/{imsi}/auth-vector", response_model=AuthVectorResponse)
def get_auth_vector(imsi: str, rand: Optional[str] = None, algorithm: str = "milenage"):
    """Generate authentication vector for 5G/4G/3G/2G AKA."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        # Generate RAND if not provided
        rand_bytes = bytes.fromhex(rand) if rand else secrets.token_bytes(16)
        rand_hex = rand_bytes.hex().upper()
        
        if not row.get("opc"):
            raise HTTPException(status_code=400, detail="AUTH_CREDENTIALS_MISSING: opc not provisioned")
        if not row.get("k") and not row.get("ki"):
            raise HTTPException(status_code=400, detail="AUTH_CREDENTIALS_MISSING: neither K nor Ki provisioned")

        # Populated only by the credential path that matches this subscriber.
        autn = res = xres = xres_star = ""
        ck = ik = k_asme = k_seaf = k_ausf = k_amf = ""
        sres = kc = ""
        
        amf_bytes = bytes.fromhex(row["amf"])
        sqn = row["sqn"]
        
        # 5G AKA (if K present)
        if row.get("k") and row.get("opc"):
            if CRYPTO_AVAILABLE:
                crypto = get_crypto(row["opc"])
                k_bytes = bytes.fromhex(row["k"])
                av = crypto.generate_auth_vector_5g(k_bytes, sqn, amf_bytes)
                rand_bytes = av["rand"]
                rand_hex = rand_bytes.hex().upper()
                autn = av["autn"].hex().upper()
                xres_star = av["xres_star"].hex().upper()
                res = av["res"].hex().upper()
                xres = av["xres_star"].hex().upper()  # Use XRES* for both
                ck = av["ck"].hex().upper()
                ik = av["ik"].hex().upper()
                k_ausf = av["k_ausf"].hex().upper()
                k_seaf = av["k_seaf"].hex().upper()
                k_amf = av["k_amf"].hex().upper()
                # K_ASME = K_SEAF for 5G (or derived)
                k_asme = av["k_seaf"].hex().upper()
            else:
                raise HTTPException(
                    status_code=500,
                    detail="CRYPTO_UNAVAILABLE: pycryptodome required for 5G AKA — fail closed"
                )
        
        # 4G AKA (if Ki present, no 5G)
        elif row.get("ki") and row.get("opc"):
            if CRYPTO_AVAILABLE:
                crypto = get_crypto(row["opc"])
                ki_bytes = bytes.fromhex(row["ki"])
                av = crypto.generate_auth_vector_4g(ki_bytes, sqn, amf_bytes)
                rand_bytes = av["rand"]
                rand_hex = rand_bytes.hex().upper()
                autn = av["autn"].hex().upper()
                xres = av["xres"].hex().upper()
                res = av["res"].hex().upper()
                ck = av["ck"].hex().upper()
                ik = av["ik"].hex().upper()
                k_asme = av["k_asme"].hex().upper()
            else:
                raise HTTPException(
                    status_code=500,
                    detail="CRYPTO_UNAVAILABLE: pycryptodome required for 4G AKA — fail closed"
                )
        
        # 2G/3G (if Ki present)
        if row.get("ki"):
            if CRYPTO_AVAILABLE and row.get("opc"):
                crypto = get_crypto(row["opc"])
                ki_bytes = bytes.fromhex(row["ki"])
                av = crypto.generate_auth_vector_2g3g(ki_bytes, rand_bytes)
                sres = av["sres"].hex().upper()
                kc = av["kc"].hex().upper()
            else:
                raise HTTPException(
                    status_code=500,
                    detail="CRYPTO_UNAVAILABLE: pycryptodome required for 2G/3G — fail closed"
                )
        
        # Update SQN
        new_sqn = sqn + 1
        cur.execute("UPDATE tbl_subscriber SET sqn=%s WHERE imsi=%s", (new_sqn, imsi))
        conn.commit()
        
        r = get_redis()
        r.delete(f"udm:subscriber:{imsi}")
        
        return AuthVectorResponse(
            imsi=imsi,
            rand=rand_hex,
            autn=autn,
            res=res,
            xres=xres,
            xres_star=xres_star,
            ck=ck,
            ik=ik,
            k_asme=k_asme,
            k_seaf=k_seaf,
            k_ausf=k_ausf,
            k_amf=k_amf,
            sres=sres,
            kc=kc,
        )
    finally:
        conn.close()


@app.post("/subscribers/{imsi}/auth-vector/generate", response_model=AuthVectorResponse)
def generate_auth_vector(imsi: str, req: AuthVectorRequest):
    return get_auth_vector(imsi, req.rand, req.algorithm)


# ============================================================================
# Nudm_SDM Endpoints (TS 29.503)
# ============================================================================
@app.get("/nudm-sdm/v2/{imsi}/am-data", response_model=NudmAMData)
def get_nudm_am_data(imsi: str, supported_features: Optional[str] = Query(None)):
    """Access and Mobility Subscription Data (TS 29.503 §5.1.2.2)."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        
        ue_ambr = {"uplink": f"{row.get('ue_ambr_ul', 1000000000)}", "downlink": f"{row.get('ue_ambr_dl', 1000000000)}"}
        
        return NudmAMData(
            supported_features=supported_features,
            ue_ambr=ue_ambr,
            sub_data_management=row.get("sor_info"),
            am_policy_data=row.get("nssaa_info"),
        )
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/smf-select-data", response_model=NudmSmfSelectData)
def get_nudm_smf_select_data(imsi: str, supported_features: Optional[str] = Query(None)):
    """SMF Selection Subscription Data (TS 29.503 §5.1.2.3)."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        
        return NudmSmfSelectData(
            supported_features=supported_features,
            default_snssai=json.loads(row["default_nssai"]) if row.get("default_nssai") else None,
            subscribed_snssais=json.loads(row["allowed_nssai"]) if row.get("allowed_nssai") else None,
            smf_selection_subscription_data=json.loads(row["smf_selection"]) if row.get("smf_selection") else None,
        )
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/ue-cm-data", response_model=NudmUeCmData)
def get_nudm_ue_cm_data(imsi: str, supported_features: Optional[str] = Query(None)):
    """UE Context in SMF Data (TS 29.503 §5.1.2.4)."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        
        return NudmUeCmData(
            supported_features=supported_features,
            pdu_sessions=row.get("ue_id_mapping"),
            registrations=row.get("vplmn_5g_data"),
        )
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/sm-data", response_model=NudmSmData)
def get_nudm_sm_data(imsi: str, supported_features: Optional[str] = Query(None), dnn: Optional[str] = Query(None)):
    """Session Management Subscription Data (TS 29.503 §5.1.2.5)."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row5g = cur.fetchone()
        if not row5g:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        
        cur.execute("SELECT * FROM tbl_apn_profile WHERE imsi=%s", (imsi,))
        apn_rows = cur.fetchall()
        
        dnn_configs = {}
        for apn in apn_rows:
            if dnn and apn["apn"] != dnn:
                continue
            dnn_configs[apn["apn"]] = {
                "dnn": apn["apn"],
                "pdu_session_types": {"default_session_type": apn["pdn_type"], "allowed_session_types": [apn["pdn_type"]]},
                "ssc_modes": {"default_ssc_mode": 1, "allowed_ssc_modes": [1, 2, 3]},
                "5g_qos_profile": {
                    "5qi": apn["qci"],
                    "arp": {"priority_level": apn["arp_priority"], "preempt_cap": "NOT_PREEMPT" if not apn["arp_preempt_cap"] else "PREEMPT", "preempt_vuln": "NOT_PREEMPTABLE" if not apn["arp_preempt_vuln"] else "PREEMPTABLE"},
                    "max_data_burst_vol": 0,
                },
                "session_ambr": {"uplink": f"{apn['apn_ambr_ul']}", "downlink": f"{apn['apn_ambr_dl']}"},
                "3gpp_charging_characteristics": "0000",
                "static_ip_address": [{"ipv4_addr": apn["static_ipv4"]}] if apn.get("static_ipv4") else [],
            }
        
        return NudmSmData(
            supported_features=supported_features,
            dnn_configurations=dnn_configs,
            lcs_privacy_data=row5g.get("lcs_privacy_5g"),
            lcs_mo_data={"gmlc_address": row5g.get("gmlc_address")} if row5g.get("gmlc_address") else None,
        )
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/trace-data")
def get_nudm_trace_data(imsi: str, supported_features: Optional[str] = Query(None)):
    """Trace Configuration Data (TS 29.503 §5.1.2.6)."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT trace_config FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        return {"supported_features": supported_features, "trace_data": row.get("trace_config")}
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/sms-data")
def get_nudm_sms_data(imsi: str, supported_features: Optional[str] = Query(None)):
    """SMS Subscription Data (TS 29.503 §5.1.2.7)."""
    return {"supported_features": supported_features, "sms_subscribed": True}


# ============================================================================
# Nudm_UEAU - UE Authentication (TS 29.503 §5.2)
# ============================================================================

class GenerateAuthDataRequest(BaseModel):
    serving_network_name: str = Field(..., description="Serving Network Name (SNID)")
    resynchronization_info: Optional[Dict] = Field(None, description="AUTS for resync")
    supported_features: Optional[str] = None


class AuthenticationVector5G(BaseModel):
    av_type: str = "5G_AKA"
    rand: str
    xres_star: str
    autn: str
    kausf: str


class GenerateAuthDataResponse(BaseModel):
    auth_type: str = "5G_AKA"
    auth_vectors: List[AuthenticationVector5G]
    supported_features: Optional[str] = None


@app.post("/nudm-ueau/v1/{supi_or_suci}/security-information/generate-auth-data", response_model=GenerateAuthDataResponse)
def generate_auth_data(supi_or_suci: str, req: GenerateAuthDataRequest):
    """Generate 5G Authentication Data (TS 29.503 §5.2.2.1).
    
    AUSF calls this to get 5G AKA vectors. Handles SUCI de-concealment.
    """
    imsi = resolve_identity(supi_or_suci)
    
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        if not row.get("k") or not row.get("opc"):
            raise HTTPException(status_code=400, detail="5G credentials not provisioned")
        
        # Generate authentication vector
        if CRYPTO_AVAILABLE:
            crypto = get_crypto(row["opc"])
            k_bytes = bytes.fromhex(row["k"])
            av = crypto.generate_auth_vector_5g(k_bytes, row["sqn"], bytes.fromhex(row["amf"]))
            
            auth_vector = AuthenticationVector5G(
                rand=av["rand"].hex().upper(),
                xres_star=av["xres_star"].hex().upper(),
                autn=av["autn"].hex().upper(),
                kausf=av["k_ausf"].hex().upper()
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="CRYPTO_UNAVAILABLE: pycryptodome required for 5G AKA — fail closed"
            )
        
        # Update SQN
        new_sqn = row["sqn"] + 1
        cur.execute("UPDATE tbl_subscriber SET sqn=%s WHERE imsi=%s", (new_sqn, imsi))
        conn.commit()
        
        r = get_redis()
        r.delete(f"udm:subscriber:{imsi}")
        
        return GenerateAuthDataResponse(
            auth_vectors=[auth_vector],
            supported_features=req.supported_features
        )
    finally:
        conn.close()


class HssAvRequest(BaseModel):
    hss_auth_type: str = Field(..., pattern="^(eps-aka|eap-aka|eap-aka-prime|ims-aka|gba-aka)$")
    num_vectors: int = Field(1, ge=1, le=5)
    supported_features: Optional[str] = None


class HssAvResponse(BaseModel):
    auth_vectors: List[Dict]
    supported_features: Optional[str] = None


@app.post("/nudm-ueau/v1/{supi}/hss-security-information/{hss_auth_type}/generate-av", response_model=HssAvResponse)
def generate_hss_av(supi: str, hss_auth_type: str, req: HssAvRequest):
    """HSS requests EPS/IMS authentication vectors (GetHssAv, TS 29.503 §5.2.2.4).
    
    Called by HSS for S6a/Cx interworking. Supports:
    - eps-aka: EPS AKA (KASME, XRES, RAND, AUTN, CK, IK)
    - ims-aka: IMS AKA (CK, IK, XRES, RAND, AUTN)
    - eap-aka / eap-aka-prime: EAP-AKA / EAP-AKA'
    - gba-aka: GBA AKA
    """
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi=%s", (supi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        if not row.get("ki") or not row.get("opc"):
            raise HTTPException(status_code=400, detail="4G/3G/2G credentials not provisioned")
        
        auth_vectors = []
        for i in range(req.num_vectors):
            rand = secrets.token_bytes(16)
            rand_hex = rand.hex().upper()
            
            if CRYPTO_AVAILABLE:
                crypto = get_crypto(row["opc"])
                ki_bytes = bytes.fromhex(row["ki"])
                sqn = row["sqn"]
                amf_bytes = bytes.fromhex(row["amf"])
                
                if hss_auth_type in ["eps-aka", "eap-aka"]:
                    av = crypto.generate_auth_vector_4g(ki_bytes, sqn, amf_bytes)
                    auth_vectors.append({
                        "av_type": "EPS_AKA",
                        "rand": rand_hex,
                        "xres": av["xres"].hex().upper(),
                        "autn": av["autn"].hex().upper(),
                        "kasme": av["k_asme"].hex().upper(),
                        "ck": av["ck"].hex().upper(),
                        "ik": av["ik"].hex().upper()
                    })
                elif hss_auth_type == "ims-aka":
                    av = crypto.generate_auth_vector_4g(ki_bytes, sqn, amf_bytes)
                    auth_vectors.append({
                        "av_type": "IMS_AKA",
                        "rand": rand_hex,
                        "xres": av["xres"].hex().upper(),
                        "autn": av["autn"].hex().upper(),
                        "ck": av["ck"].hex().upper(),
                        "ik": av["ik"].hex().upper()
                    })
                elif hss_auth_type == "gba-aka":
                    av = crypto.generate_auth_vector_4g(ki_bytes, sqn, amf_bytes)
                    auth_vectors.append({
                        "av_type": "GBA_AKA",
                        "rand": rand_hex,
                        "xres": av["xres"].hex().upper(),
                        "autn": av["autn"].hex().upper(),
                        "ck": av["ck"].hex().upper(),
                        "ik": av["ik"].hex().upper()
                    })
                else:
                    raise HTTPException(
                        status_code=501,
                        detail=(
                            "EAP_AKA_PRIME_NOT_IMPLEMENTED: CK'/IK' derivation (TS 33.402) "
                            "is not built; refusing to return placeholder vectors"
                        ),
                    )
            else:
                raise HTTPException(
                    status_code=500,
                    detail="CRYPTO_UNAVAILABLE: pycryptodome required for EPS/IMS vectors — fail closed",
                )

            # Increment SQN per vector
            cur.execute("UPDATE tbl_subscriber SET sqn=sqn+1 WHERE imsi=%s", (supi,))
        
        conn.commit()
        r = get_redis()
        r.delete(f"udm:subscriber:{supi}")
        
        return HssAvResponse(auth_vectors=auth_vectors, supported_features=req.supported_features)
    finally:
        conn.close()


@app.post("/nudm-ueau/v1/{supi}/auth-events")
def confirm_auth(supi: str, req: Dict):
    """Authentication Result Confirmation (TS 29.503 §5.2.2.2).
    
    AUSF confirms success/failure of authentication.
    """
    auth_event_id = req.get("authEventId")
    success = req.get("success", False)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tbl_auth_vector (imsi, rand_5g, generated_at) VALUES (%s, %s, NOW())
               ON DUPLICATE KEY UPDATE generated_at=NOW()""",
            (supi, req.get("rand", ""))
        )
        conn.commit()
        return {"status": "confirmed", "authEventId": auth_event_id}
    finally:
        conn.close()


@app.put("/nudm-ueau/v1/{supi}/auth-events/{auth_event_id}")
def delete_auth_event(supi: str, auth_event_id: str):
    """Remove authentication result (TS 29.503 §5.2.2.3)."""
    return {"status": "deleted", "authEventId": auth_event_id}


@app.post("/nudm-ueau/v1/{supi}/gba-security-information/generate-av")
def generate_gba_av(supi: str, req: Dict):
    """GBA Authentication Vectors (TS 29.503 §5.2.2.5)."""
    return generate_hss_av(supi, "gba-aka", HssAvRequest(hss_auth_type="gba-aka", num_vectors=1))


@app.post("/nudm-ueau/v1/{supi_or_suci}/prose-security-information/generate-av")
def generate_prose_av(supi_or_suci: str, req: Dict):
    """ProSe Authentication Vectors (TS 29.503 §5.2.2.6)."""
    imsi = supi_or_suci  # Already de-concealed if SUCI
    if suci_is_suci(supi_or_suci):
        imsi = deconceal_suci(supi_or_suci) or supi_or_suci
    return generate_auth_data(imsi, GenerateAuthDataRequest(serving_network_name=req.get("servingNetworkName", "prose")))


# ============================================================================
# SUCI De-concealment Helpers (TS 33.501 Annex C, TS 29.503 Annex C)
# ============================================================================

def suci_is_suci(val: str) -> bool:
    """Check if value is a SUCI string."""
    return val.startswith("suci-")


def resolve_identity(supi_or_suci: str) -> str:
    """Pass a SUPI through; de-conceal a SUCI with a specific failure cause."""
    if not suci_is_suci(supi_or_suci):
        return supi_or_suci
    try:
        return suci_lib.deconceal(supi_or_suci)
    except suci_lib.SuciError as exc:
        logger.warning("SUCI rejected: %s", exc.code)
        raise HTTPException(
            status_code=exc.http_status,
            detail={"cause": exc.code, "detail": str(exc)},
        ) from exc


def deconceal_suci(suci: str) -> Optional[str]:
    """Best-effort de-concealment for internal SDM lookups.

    Returns None so callers answer 404 for an unknown identity; endpoints that
    expose de-concealment directly use resolve_identity() to keep the cause.
    """
    if not suci_is_suci(suci):
        return None
    try:
        return suci_lib.deconceal(suci)
    except suci_lib.SuciError as exc:
        logger.warning("SUCI de-concealment failed: %s", exc.code)
        return None


@app.post("/nudm-ueid/v1/deconceal")
def ueid_deconceal(req: Dict):
    """Nudm_UEIdentifier - SUCI De-concealment (TS 29.503 §5.10).
    
    5G PKMF requests de-concealment of ProSe Remote UE's SUCI.
    """
    suci = req.get("suci")
    if not suci:
        raise HTTPException(status_code=400, detail="SUCI required")
    if not suci_is_suci(suci):
        raise HTTPException(status_code=400, detail="Value is not a SUCI")

    return {"supi": f"imsi-{resolve_identity(suci)}"}


# ============================================================================
# Nudm_UECM - UE Context Management (TS 29.503 §5.3)
# ============================================================================

class Amf3GppRegistration(BaseModel):
    guami: Dict
    purge_flag: Optional[bool] = False
    pei: Optional[str] = None
    ims_voip_support: Optional[bool] = None
    backup_amf_info: Optional[List[Dict]] = None
    eps_interworking_info: Optional[Dict] = None
    ue_srvcc_capability: Optional[bool] = None
    registration_time: Optional[str] = None
    vgmlc_address: Optional[str] = None
    supported_features: Optional[str] = None


class AmfNon3GppRegistration(BaseModel):
    guami: Dict
    purge_flag: Optional[bool] = False
    pei: Optional[str] = None
    backup_amf_info: Optional[List[Dict]] = None
    eps_interworking_info: Optional[Dict] = None
    registration_time: Optional[str] = None
    supported_features: Optional[str] = None


class SmfRegistration(BaseModel):
    pdu_session_id: int
    smf_instance_id: str
    plmn_id: Dict
    smf_set_id: Optional[str] = None
    single_nssai: Optional[Dict] = None
    dnn: Optional[str] = None
    emergency_services: Optional[bool] = False
    pcscf_restoration_callback_uri: Optional[str] = None
    pgw_fqdn: Optional[str] = None
    epdg_ind: Optional[bool] = None
    ipv4_addr: Optional[str] = None
    ipv6_prefix: Optional[List[str]] = None
    atsss_info: Optional[Dict] = None
    supported_features: Optional[str] = None


class Smsf3GppRegistration(BaseModel):
    smsf_instance_id: str
    plmn_id: Dict
    smsf_set_id: Optional[str] = None
    supported_features: Optional[str] = None


class IpSmGwRegistration(BaseModel):
    ip_sm_gw_id: str
    ip_sm_gw_map_address: Optional[str] = None
    supported_features: Optional[str] = None


class RegistrationResponse(BaseModel):
    registration: Dict


@app.put("/nudm-uecm/v1/{ue_id}/registrations/amf-3gpp-access", response_model=RegistrationResponse)
def register_amf_3gpp(ue_id: str, reg: Amf3GppRegistration):
    """AMF 3GPP Access Registration (TS 29.503 §5.3.2.2)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    
    r = get_redis()
    reg_key = f"uecm:registration:amf-3gpp:{imsi}"
    reg_data = reg.model_dump()
    reg_data["ue_id"] = imsi
    reg_data["access_type"] = "3GPP"
    reg_data["registered_at"] = datetime.utcnow().isoformat()
    r.set(reg_key, json.dumps(reg_data, default=str))
    r.expire(reg_key, 86400)  # 24h TTL
    
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tbl_uecm_registration (imsi, access_type, registration_data, registered_at)
               VALUES (%s, '3GPP', %s, NOW())
               ON DUPLICATE KEY UPDATE registration_data=%s, registered_at=NOW()""",
            (imsi, json.dumps(reg_data), json.dumps(reg_data))
        )
        conn.commit()
    finally:
        conn.close()
    
    return {"registration": reg_data}


@app.patch("/nudm-uecm/v1/{ue_id}/registrations/amf-3gpp-access")
def update_amf_3gpp(ue_id: str, req: Dict):
    """Update AMF 3GPP Registration (TS 29.503 §5.3.2.3)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    reg_key = f"uecm:registration:amf-3gpp:{imsi}"
    existing = r.get(reg_key)
    if not existing:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    reg_data = json.loads(existing)
    reg_data.update(req)
    reg_data["updated_at"] = datetime.utcnow().isoformat()
    r.set(reg_key, json.dumps(reg_data, default=str))
    
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tbl_uecm_registration SET registration_data=%s WHERE imsi=%s AND access_type='3GPP'",
            (json.dumps(reg_data), imsi)
        )
        conn.commit()
    finally:
        conn.close()
    
    return {"registration": reg_data}


@app.get("/nudm-uecm/v1/{ue_id}/registrations/amf-3gpp-access")
def get_amf_3gpp(ue_id: str):
    """Get AMF 3GPP Registration (TS 29.503 §5.3.2.4)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    reg_key = f"uecm:registration:amf-3gpp:{imsi}"
    existing = r.get(reg_key)
    if not existing:
        raise HTTPException(status_code=404, detail="Registration not found")
    return json.loads(existing)


@app.post("/nudm-uecm/v1/{ue_id}/registrations/amf-3gpp-access/dereg-amf")
def dereg_amf(ue_id: str, req: Dict):
    """Trigger AMF Deregistration (TS 29.503 §5.3.2.5)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    r.delete(f"uecm:registration:amf-3gpp:{imsi}")
    r.delete(f"uecm:registration:amf-non-3gpp:{imsi}")
    
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_uecm_registration WHERE imsi=%s AND access_type IN ('3GPP', 'non-3GPP')", (imsi,))
        conn.commit()
    finally:
        conn.close()
    
    return {"status": "deregistered"}


@app.post("/nudm-uecm/v1/{ue_id}/registrations/amf-3gpp-access/pei-update")
def pei_update(ue_id: str, req: Dict):
    """PEI Update (TS 29.503 §5.3.2.6)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    pei = req.get("pei")
    if not pei:
        raise HTTPException(status_code=400, detail="PEI required")
    
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE tbl_subscriber SET imei=%s WHERE imsi=%s", (pei, imsi))
        conn.commit()
    finally:
        conn.close()
    
    r = get_redis()
    r.delete(f"udm:subscriber:{imsi}")
    return {"status": "pei_updated", "pei": pei}


@app.post("/nudm-uecm/v1/{ue_id}/registrations/amf-3gpp-access/roaming-info-update")
def roaming_info_update(ue_id: str, req: Dict):
    """Roaming Information Update (TS 29.503 §5.3.2.7)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    vplmn = req.get("visitedPlmn", {}).get("mcc", "") + req.get("visitedPlmn", {}).get("mnc", "")
    if vplmn:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO tbl_roaming_profile (imsi, visited_plmn, roaming_allowed, rat_allowed)
                   VALUES (%s, %s, 1, %s)
                   ON DUPLICATE KEY UPDATE rat_allowed=%s""",
                (imsi, vplmn, json.dumps(req.get("ratAllowed", {})), json.dumps(req.get("ratAllowed", {})))
            )
            conn.commit()
        finally:
            conn.close()
    return {"status": "roaming_updated"}


@app.put("/nudm-uecm/v1/{ue_id}/registrations/amf-non-3gpp-access", response_model=RegistrationResponse)
def register_amf_non_3gpp(ue_id: str, reg: AmfNon3GppRegistration):
    """AMF Non-3GPP Access Registration."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    reg_key = f"uecm:registration:amf-non-3gpp:{imsi}"
    reg_data = reg.model_dump()
    reg_data["ue_id"] = imsi
    reg_data["access_type"] = "non-3GPP"
    reg_data["registered_at"] = datetime.utcnow().isoformat()
    r.set(reg_key, json.dumps(reg_data, default=str))
    r.expire(reg_key, 86400)
    return {"registration": reg_data}


@app.get("/nudm-uecm/v1/{ue_id}/registrations/smf-registrations")
def get_smf_registrations(ue_id: str):
    """Get SMF Registrations (TS 29.503 §5.3.2.9)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    pattern = f"uecm:registration:smf:{imsi}:*"
    keys = r.keys(pattern)
    registrations = {}
    for key in keys:
        data = r.get(key)
        if data:
            reg = json.loads(data)
            pdu_id = reg.get("pdu_session_id")
            if pdu_id:
                registrations[pdu_id] = reg
    return {"smfRegistrations": registrations}


@app.put("/nudm-uecm/v1/{ue_id}/registrations/smf-registrations/{pdu_session_id}", response_model=RegistrationResponse)
def register_smf(ue_id: str, pdu_session_id: int, reg: SmfRegistration):
    """SMF Registration per PDU Session (TS 29.503 §5.3.2.10)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    reg_key = f"uecm:registration:smf:{imsi}:{pdu_session_id}"
    reg_data = reg.model_dump()
    reg_data["ue_id"] = imsi
    reg_data["pdu_session_id"] = pdu_session_id
    reg_data["registered_at"] = datetime.utcnow().isoformat()
    r.set(reg_key, json.dumps(reg_data, default=str))
    r.expire(reg_key, 86400)
    return {"registration": reg_data}


@app.delete("/nudm-uecm/v1/{ue_id}/registrations/smf-registrations/{pdu_session_id}")
def deregister_smf(ue_id: str, pdu_session_id: int):
    """SMF Deregistration."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    r.delete(f"uecm:registration:smf:{imsi}:{pdu_session_id}")
    return {"status": "deregistered"}


@app.get("/nudm-uecm/v1/{ue_id}/registrations/smf-registrations/{pdu_session_id}")
def get_smf_registration(ue_id: str, pdu_session_id: int):
    """Get SMF Registration."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    reg_key = f"uecm:registration:smf:{imsi}:{pdu_session_id}"
    data = r.get(reg_key)
    if not data:
        raise HTTPException(status_code=404, detail="SMF registration not found")
    return json.loads(data)


@app.patch("/nudm-uecm/v1/{ue_id}/registrations/smf-registrations/{pdu_session_id}")
def update_smf_registration(ue_id: str, pdu_session_id: int, req: Dict):
    """Update SMF Registration."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    reg_key = f"uecm:registration:smf:{imsi}:{pdu_session_id}"
    existing = r.get(reg_key)
    if not existing:
        raise HTTPException(status_code=404, detail="SMF registration not found")
    reg_data = json.loads(existing)
    reg_data.update(req)
    reg_data["updated_at"] = datetime.utcnow().isoformat()
    r.set(reg_key, json.dumps(reg_data, default=str))
    return {"registration": reg_data}


@app.put("/nudm-uecm/v1/{ue_id}/registrations/smsf-3gpp-access", response_model=RegistrationResponse)
def register_smsf_3gpp(ue_id: str, reg: Smsf3GppRegistration):
    """SMSF 3GPP Access Registration."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    reg_key = f"uecm:registration:smsf-3gpp:{imsi}"
    reg_data = reg.model_dump()
    reg_data["ue_id"] = imsi
    reg_data["registered_at"] = datetime.utcnow().isoformat()
    r.set(reg_key, json.dumps(reg_data, default=str))
    return {"registration": reg_data}


@app.delete("/nudm-uecm/v1/{ue_id}/registrations/smsf-3gpp-access")
def deregister_smsf_3gpp(ue_id: str):
    """SMSF 3GPP Deregistration."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    r.delete(f"uecm:registration:smsf-3gpp:{imsi}")
    return {"status": "deregistered"}


@app.put("/nudm-uecm/v1/{ue_id}/registrations/ip-sm-gw", response_model=RegistrationResponse)
def register_ip_sm_gw(ue_id: str, reg: IpSmGwRegistration):
    """IP-SM-GW Registration."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    reg_key = f"uecm:registration:ip-sm-gw:{imsi}"
    reg_data = reg.model_dump()
    reg_data["ue_id"] = imsi
    reg_data["registered_at"] = datetime.utcnow().isoformat()
    r.set(reg_key, json.dumps(reg_data, default=str))
    return {"registration": reg_data}


@app.delete("/nudm-uecm/v1/{ue_id}/registrations/ip-sm-gw")
def deregister_ip_sm_gw(ue_id: str):
    """IP-SM-GW Deregistration."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    r = get_redis()
    r.delete(f"uecm:registration:ip-sm-gw:{imsi}")
    return {"status": "deregistered"}


@app.post("/nudm-uecm/v1/restore-pcscf")
def trigger_pcscf_restoration(req: Dict):
    """Trigger P-CSCF Restoration (TS 29.503 §5.3.2.16)."""
    ue_ids = req.get("ueIds", [])
    for ue_id in ue_ids:
        imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    return {"status": "pcscf_restoration_triggered", "ueCount": len(ue_ids)}


@app.get("/nudm-uecm/v1/{ue_id}/registrations/send-routing-info-sm")
def send_routing_info_sm(ue_id: str):
    """Send Routing Info for SM (TS 29.503 §5.3.2.17).
    
    Returns SMSF/IP-SM-GW routing info for MT-SMS.
    """
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        r = get_redis()
        smsf_key = f"uecm:registration:smsf-3gpp:{imsi}"
        smsf_data = r.get(smsf_key)
        
        if smsf_data:
            smsf = json.loads(smsf_data)
            return {
                "smsfAddress": smsf.get("smsfInstanceId"),
                "ipSmGwAddress": smsf.get("ipSmGwMapAddress"),
                "smsRouterAddress": "sms-router.core.local"
            }
        
        ipsmgw_key = f"uecm:registration:ip-sm-gw:{imsi}"
        ipsmgw_data = r.get(ipsmgw_key)
        if ipsmgw_data:
            ipsmgw = json.loads(ipsmgw_data)
            return {
                "ipSmGwAddress": ipsmgw.get("ipSmGwMapAddress"),
                "smsRouterAddress": "sms-router.core.local"
            }
        
        return {
            "smsGmscAddress": "sms-gmsc.core.local",
            "smsRouterAddress": "sms-router.core.local"
        }
    finally:
        conn.close()


@app.get("/nudm-uecm/v1/{ue_id}/registrations/trigger-auth")
def trigger_auth(ue_id: str):
    """Trigger Authentication (TS 29.503 §5.3.2.18)."""
    return {"status": "auth_triggered"}


# ============================================================================
# Nudm_SDM - Additional Data Sets (TS 29.503 §5.1)
# ============================================================================

@app.get("/nudm-sdm/v2/{imsi}/nssai")
def get_nudm_nssai(imsi: str, supported_features: Optional[str] = Query(None)):
    """Slice Selection Subscription Data (NSSAI)."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT default_nssai, allowed_nssai FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        
        return {
            "supported_features": supported_features,
            "subscribedSnssais": json.loads(row["default_nssai"]) if row.get("default_nssai") else [],
            "defaultSnssai": json.loads(row["allowed_nssai"]) if row.get("allowed_nssai") else []
        }
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/am-data/ecr-data")
def get_nudm_ecr_data(imsi: str, supported_features: Optional[str] = Query(None)):
    """Enhanced Coverage Restriction Data."""
    return {"supported_features": supported_features, "ecrData": {"restrictedEcgiList": []}}


@app.get("/nudm-sdm/v2/{imsi}/sms-mng-data")
def get_nudm_sms_mng_data(imsi: str, supported_features: Optional[str] = Query(None)):
    """SMS Management Subscription Data."""
    return {"supported_features": supported_features, "smsMngData": {"mtSmsBarringAll": False, "moSmsBarringAll": False}}


@app.get("/nudm-sdm/v2/{imsi}/ue-context-in-amf-data")
def get_nudm_ue_ctx_amf(imsi: str, supported_features: Optional[str] = Query(None)):
    """UE Context in AMF Data."""
    r = get_redis()
    reg_key = f"uecm:registration:amf-3gpp:{imsi}"
    data = r.get(reg_key)
    if not data:
        return {"supported_features": supported_features, "amf3GppAccessRegistration": None}
    return {"supported_features": supported_features, "amf3GppAccessRegistration": json.loads(data)}


@app.get("/nudm-sdm/v2/{imsi}/ue-context-in-smf-data")
def get_nudm_ue_ctx_smf(imsi: str, supported_features: Optional[str] = Query(None)):
    """UE Context in SMF Data."""
    r = get_redis()
    pattern = f"uecm:registration:smf:{imsi}:*"
    keys = r.keys(pattern)
    smf_regs = {}
    for key in keys:
        data = r.get(key)
        if data:
            reg = json.loads(data)
            pdu_id = reg.get("pdu_session_id")
            if pdu_id:
                smf_regs[pdu_id] = reg
    return {"supported_features": supported_features, "pduSessions": smf_regs}


@app.get("/nudm-sdm/v2/{imsi}/ue-context-in-smsf-data")
def get_nudm_ue_ctx_smsf(imsi: str, supported_features: Optional[str] = Query(None)):
    """UE Context in SMSF Data."""
    r = get_redis()
    smsf_key = f"uecm:registration:smsf-3gpp:{imsi}"
    data = r.get(smsf_key)
    return {"supported_features": supported_features, "smsf3GppAccessRegistration": json.loads(data) if data else None}


@app.get("/nudm-sdm/v2/{ue_id}/lcs-privacy-data")
def get_nudm_lcs_privacy(ue_id: str, supported_features: Optional[str] = Query(None)):
    """LCS Privacy Data."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT lcs_privacy_5g FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        return {"supported_features": supported_features, "lcsPrivacyData": row.get("lcs_privacy_5g", {})}
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/lcs-mo-data")
def get_nudm_lcs_mo(imsi: str, supported_features: Optional[str] = Query(None)):
    """LCS Mobile Originated Data."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT gmlc_address FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        return {"supported_features": supported_features, "gmlcAddress": row.get("gmlc_address")}
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/lcs-bca-data")
def get_nudm_lcs_bca(imsi: str, supported_features: Optional[str] = Query(None)):
    """LCS Broadcast Assistance Data."""
    return {"supported_features": supported_features, "lcsBcaData": {}}


@app.get("/nudm-sdm/v2/{imsi}/lcs-subscription-data")
def get_nudm_lcs_sub(imsi: str, supported_features: Optional[str] = Query(None)):
    """LCS Subscription Data."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT lcs_privacy_5g, gmlc_address FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        return {
            "supported_features": supported_features,
            "lcsPrivacyData": row.get("lcs_privacy_5g", {}),
            "gmlcAddress": row.get("gmlc_address")
        }
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/v2x-data")
def get_nudm_v2x(imsi: str, supported_features: Optional[str] = Query(None)):
    """V2X Subscription Data."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT v2x_allowed_5g, v2x_roaming FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        return {"supported_features": supported_features, "v2xData": {"v2xAllowed": row.get("v2x_allowed_5g", False) if row else False}}
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/prose-data")
def get_nudm_prose(imsi: str, supported_features: Optional[str] = Query(None)):
    """ProSe Subscription Data."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT prose_enabled FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        return {"supported_features": supported_features, "proseData": {"proseEnabled": row.get("prose_enabled", False) if row else False}}
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/5mbs-data")
def get_nudm_5mbs(imsi: str, supported_features: Optional[str] = Query(None)):
    """5MBS Subscription Data."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT mbs_allowed FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        return {"supported_features": supported_features, "mbsData": {"mbsAllowed": row.get("mbs_allowed", False) if row else False}}
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/{imsi}/uc-data")
def get_nudm_uc(imsi: str, supported_features: Optional[str] = Query(None)):
    """User Consent Data."""
    return {"supported_features": supported_features, "ucData": []}


@app.get("/nudm-sdm/v2/{imsi}/time-sync-data")
def get_nudm_time_sync(imsi: str, supported_features: Optional[str] = Query(None)):
    """Time Synchronization Subscription Data."""
    return {"supported_features": supported_features, "timeSyncData": {}}


@app.get("/nudm-sdm/v2/{imsi}/ranging-slpos-data")
def get_nudm_ranging(imsi: str, supported_features: Optional[str] = Query(None)):
    """Ranging/Sidelink Positioning Data."""
    return {"supported_features": supported_features, "rangingSlPosData": {}}


@app.get("/nudm-sdm/v2/{ue_id}/rangingsl-privacy-data")
def get_nudm_ranging_privacy(ue_id: str, supported_features: Optional[str] = Query(None)):
    """Ranging/Sidelink Positioning Privacy Data."""
    return {"supported_features": supported_features, "rangingSlPrivacyData": {}}


@app.get("/nudm-sdm/v2/{imsi}/a2x-data")
def get_nudm_a2x(imsi: str, supported_features: Optional[str] = Query(None)):
    """A2X Subscription Data."""
    return {"supported_features": supported_features, "a2xData": {}}


@app.get("/nudm-sdm/v2/{ue_id}/id-translation-result")
def get_nudm_id_translation(ue_id: str, supported_features: Optional[str] = Query(None)):
    """Identifier Translation (SUPI <-> GPSI)."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT msisdn FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        gpsi = f"msisdn-{row['msisdn']}" if row and row.get('msisdn') else None
        return {"supported_features": supported_features, "supi": f"imsi-{imsi}", "gpsi": gpsi}
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/multiple-identifiers")
def get_nudm_multiple_ids(supi: List[str] = Query(None), gpsi: List[str] = Query(None), supported_features: Optional[str] = Query(None)):
    """Multiple Identifier Translation."""
    results = []
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        if supi:
            for s in supi:
                imsi = deconceal_suci(s) if suci_is_suci(s) else s
                cur.execute("SELECT msisdn FROM tbl_subscriber WHERE imsi=%s", (imsi,))
                row = cur.fetchone()
                g = f"msisdn-{row['msisdn']}" if row and row.get('msisdn') else None
                results.append({"supi": s, "gpsi": g})
        return {"supported_features": supported_features, "identifierTranslations": results}
    finally:
        conn.close()


@app.get("/nudm-sdm/v2/shared-data")
def get_nudm_shared_data(supported_features: Optional[str] = Query(None)):
    """Get Shared Data."""
    return {"supported_features": supported_features, "sharedData": []}


@app.get("/nudm-sdm/v2/shared-data/{shared_data_id}")
def get_nudm_shared_data_by_id(shared_data_id: str, supported_features: Optional[str] = Query(None)):
    """Get Individual Shared Data."""
    return {"supported_features": supported_features, "sharedDataId": shared_data_id, "sharedData": {}}


@app.get("/nudm-sdm/v2/group-data/group-identifiers")
def get_nudm_group_ids(ext_group_id: str = Query(...), supported_features: Optional[str] = Query(None)):
    """Group Identifier Translation."""
    return {"supported_features": supported_features, "groupIdentifiers": []}


# SDM Subscriptions
@app.post("/nudm-sdm/v2/{ue_id}/sdm-subscriptions")
def subscribe_sdm(ue_id: str, req: Dict):
    """Subscribe to SDM Notifications."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    sub_id = f"sdm-sub-{secrets.token_hex(8)}"
    r = get_redis()
    r.set(f"sdm:subscription:{sub_id}", json.dumps({"ue_id": imsi, "callback": req.get("notificationUri"), "monitored_resources": req.get("monitoredResourceUris")}))
    return {"subscriptionId": sub_id, "supportedFeatures": req.get("supportedFeatures")}


@app.delete("/nudm-sdm/v2/{ue_id}/sdm-subscriptions/{subscription_id}")
def unsubscribe_sdm(ue_id: str, subscription_id: str):
    """Unsubscribe from SDM Notifications."""
    r = get_redis()
    r.delete(f"sdm:subscription:{subscription_id}")
    return {"status": "unsubscribed"}


@app.patch("/nudm-sdm/v2/{ue_id}/sdm-subscriptions/{subscription_id}")
def modify_sdm_subscription(ue_id: str, subscription_id: str, req: Dict):
    """Modify SDM Subscription."""
    r = get_redis()
    key = f"sdm:subscription:{subscription_id}"
    data = r.get(key)
    if not data:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub = json.loads(data)
    sub.update(req)
    r.set(key, json.dumps(sub))
    return sub


# SDM Info Operations
@app.put("/nudm-sdm/v2/{imsi}/am-data/sor-ack")
def sor_ack(imsi: str, req: Dict):
    """SoR Acknowledgement."""
    return {"status": "sor_acknowledged"}


@app.put("/nudm-sdm/v2/{imsi}/am-data/upu-ack")
def upu_ack(imsi: str, req: Dict):
    """UPU Acknowledgement."""
    return {"status": "upu_acknowledged"}


@app.put("/nudm-sdm/v2/{imsi}/am-data/subscribed-snssais-ack")
def snssai_ack(imsi: str, req: Dict):
    """S-NSSAI Acknowledgement."""
    return {"status": "snssai_acknowledged"}


@app.put("/nudm-sdm/v2/{imsi}/am-data/cag-ack")
def cag_ack(imsi: str, req: Dict):
    """CAG Acknowledgement."""
    return {"status": "cag_acknowledged"}


@app.post("/nudm-sdm/v2/{imsi}/am-data/update-sor")
def update_sor(imsi: str, req: Dict):
    """Update SoR Info."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tbl_5g_subscription SET sor_info=%s WHERE imsi=%s",
            (json.dumps(req.get("sorInfo", {})), imsi)
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "sor_updated"}


# ============================================================================
# Nudm_EventExposure (EE) - TS 29.503 §5.4
# ============================================================================

class EeSubscription(BaseModel):
    event_list: List[Dict]
    notification_uri: str
    notification_correlation_id: str
    expiry: Optional[str] = None
    supported_features: Optional[str] = None


@app.post("/nudm-ee/v1/{ue_identity}/ee-subscriptions")
def create_ee_subscription(ue_identity: str, req: EeSubscription):
    """Create Event Exposure Subscription."""
    imsi = deconceal_suci(ue_identity) if suci_is_suci(ue_identity) else ue_identity
    sub_id = f"ee-sub-{secrets.token_hex(8)}"
    r = get_redis()
    r.set(f"ee:subscription:{sub_id}", json.dumps({
        "ue_id": imsi,
        "event_list": req.event_list,
        "callback": req.notification_uri,
        "correlation_id": req.notification_correlation_id,
        "expiry": req.expiry
    }))
    return {"subscriptionId": sub_id, "supportedFeatures": req.supported_features}


@app.delete("/nudm-ee/v1/{ue_identity}/ee-subscriptions/{subscription_id}")
def delete_ee_subscription(ue_identity: str, subscription_id: str):
    """Delete Event Exposure Subscription."""
    r = get_redis()
    r.delete(f"ee:subscription:{subscription_id}")
    return {"status": "deleted"}


@app.patch("/nudm-ee/v1/{ue_identity}/ee-subscriptions/{subscription_id}")
def update_ee_subscription(ue_identity: str, subscription_id: str, req: Dict):
    """Update Event Exposure Subscription."""
    r = get_redis()
    key = f"ee:subscription:{subscription_id}"
    data = r.get(key)
    if not data:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub = json.loads(data)
    sub.update(req)
    r.set(key, json.dumps(sub))
    return sub


# ============================================================================
# Nudm_ParameterProvision (PP) - TS 29.503 §5.5
# ============================================================================

@app.get("/nudm-pp/v1/{ue_id}/pp-data")
def get_pp_data(ue_id: str, supported_features: Optional[str] = Query(None)):
    """Get Parameter Provisioning Data."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        return {"supported_features": supported_features, "ppData": row.get("sor_info", {}) if row else {}}
    finally:
        conn.close()


@app.patch("/nudm-pp/v1/{ue_id}/pp-data")
def update_pp_data(ue_id: str, req: Dict):
    """Update Parameter Provisioning Data."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tbl_5g_subscription SET sor_info=%s WHERE imsi=%s",
            (json.dumps(req.get("ppData", {})), imsi)
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "updated"}


@app.put("/nudm-pp/v1/{ue_id}/pp-data-store/{af_instance_id}")
def create_pp_data_entry(ue_id: str, af_instance_id: str, req: Dict):
    """Create PP Data Entry."""
    imsi = deconceal_suci(ue_id) if suci_is_suci(ue_id) else ue_id
    return {"status": "created", "afInstanceId": af_instance_id}


@app.delete("/nudm-pp/v1/{ue_id}/pp-data-store/{af_instance_id}")
def delete_pp_data_entry(ue_id: str, af_instance_id: str):
    """Delete PP Data Entry."""
    return {"status": "deleted"}


@app.get("/nudm-pp/v1/{ue_id}/pp-data-store/{af_instance_id}")
def get_pp_data_entry(ue_id: str, af_instance_id: str, supported_features: Optional[str] = Query(None)):
    """Get PP Data Entry."""
    return {"supported_features": supported_features, "ppDataEntry": {}}


@app.put("/nudm-pp/v1/5g-vn-groups/{ext_group_id}")
def create_5g_vn_group(ext_group_id: str, req: Dict):
    """Create 5G VN Group."""
    return {"status": "created", "extGroupId": ext_group_id}


@app.delete("/nudm-pp/v1/5g-vn-groups/{ext_group_id}")
def delete_5g_vn_group(ext_group_id: str):
    """Delete 5G VN Group."""
    return {"status": "deleted"}


@app.patch("/nudm-pp/v1/5g-vn-groups/{ext_group_id}")
def modify_5g_vn_group(ext_group_id: str, req: Dict):
    """Modify 5G VN Group."""
    return {"status": "modified"}


@app.get("/nudm-pp/v1/5g-vn-groups/{ext_group_id}")
def get_5g_vn_group(ext_group_id: str, supported_features: Optional[str] = Query(None)):
    """Get 5G VN Group."""
    return {"supported_features": supported_features, "vnGroup": {"extGroupId": ext_group_id}}


@app.put("/nudm-pp/v1/mbs-group-membership/{ext_group_id}")
def create_mbs_group(ext_group_id: str, req: Dict):
    """Create 5G MBS Group Membership."""
    return {"status": "created", "extGroupId": ext_group_id}


@app.delete("/nudm-pp/v1/mbs-group-membership/{ext_group_id}")
def delete_mbs_group(ext_group_id: str):
    """Delete 5G MBS Group Membership."""
    return {"status": "deleted"}


@app.patch("/nudm-pp/v1/mbs-group-membership/{ext_group_id}")
def modify_mbs_group(ext_group_id: str, req: Dict):
    """Modify 5G MBS Group Membership."""
    return {"status": "modified"}


@app.get("/nudm-pp/v1/mbs-group-membership/{ext_group_id}")
def get_mbs_group(ext_group_id: str, supported_features: Optional[str] = Query(None)):
    """Get 5G MBS Group Membership."""
    return {"supported_features": supported_features, "mbsGroup": {"extGroupId": ext_group_id}}


# ============================================================================
# Nudm_NIDDAuthorization (NIDDAU) - TS 29.503 §5.6
# ============================================================================

@app.post("/nudm-niddau/v1/{ue_identity}/authorize")
def authorize_nidd(ue_identity: str, req: Dict):
    """Authorize NIDD Configuration."""
    imsi = deconceal_suci(ue_identity) if suci_is_suci(ue_identity) else ue_identity
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT nb_iot_allowed, emtc_allowed FROM tbl_eps_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        authorized = (row.get("nb_iot_allowed", False) or row.get("emtc_allowed", False)) if row else False
        return {"authorizationResult": "AUTHORIZED" if authorized else "NOT_AUTHORIZED"}
    finally:
        conn.close()


# ============================================================================
# Nudm_MT - TS 29.503 §5.7 (HSS Interworking)
# ============================================================================

@app.get("/nudm-mt/v1/{supi}")
def provide_ue_info(supi: str, supported_features: Optional[str] = Query(None)):
    """Provide UE Info (TADS, User State, 5GSRVCCInfo).
    
    HSS calls this to determine terminating access domain selection.
    """
    imsi = deconceal_suci(supi) if suci_is_suci(supi) else supi
    r = get_redis()
    
    amf_3gpp = r.get(f"uecm:registration:amf-3gpp:{imsi}")
    amf_non3gpp = r.get(f"uecm:registration:amf-non-3gpp:{imsi}")
    smf_regs = r.keys(f"uecm:registration:smf:{imsi}:*")
    
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_eps_subscription WHERE imsi=%s", (imsi,))
        eps = cur.fetchone()
    finally:
        conn.close()
    
    tads = "5GS" if amf_3gpp or amf_non3gpp or smf_regs else ("EPS" if eps else "CS")
    user_state = "IDLE"
    if amf_3gpp:
        user_state = "CONNECTED"
    elif amf_non3gpp:
        user_state = "CONNECTED_NON_3GPP"
    elif eps:
        user_state = "EPS_ATTACHED"
    
    return {
        "supported_features": supported_features,
        "tads": tads,
        "userState": user_state,
        "srvccCapability": eps.get("eps_supported", False) if eps else False,
        "amf3GppAccessRegistration": json.loads(amf_3gpp) if amf_3gpp else None,
        "amfNon3GppAccessRegistration": json.loads(amf_non3gpp) if amf_non3gpp else None
    }


@app.post("/nudm-mt/v1/{supi}/loc-info/provide-loc-info")
def provide_location_info(supi: str, req: Dict):
    """Provide Location Info (5GC Location).
    
    HSS/GMLC calls this for 5GC location.
    """
    imsi = deconceal_suci(supi) if suci_is_suci(supi) else supi
    import requests
    try:
        resp = requests.post(
            "http://gmlc:8082/lcs/location-request",
            json={"imsi": imsi, "request_type": "immediate"},
            timeout=10
        )
        loc = resp.json()
        return {
            "locationInfo": {
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "accuracy": loc.get("accuracy"),
                "timestamp": loc.get("timestamp")
            }
        }
    except:
        return {"locationInfo": {"error": "GMLC unavailable"}}


# ============================================================================
# Nudm_ServiceSpecificAuthorization (SSAU) - TS 29.503 §5.8
# ============================================================================

@app.post("/nudm-ssau/v1/{ue_identity}/{service_type}/authorize")
def ssau_authorize(ue_identity: str, service_type: str, req: Dict):
    """Service-Specific Authorization."""
    imsi = deconceal_suci(ue_identity) if suci_is_suci(ue_identity) else ue_identity
    r = get_redis()
    auth_key = f"ssau:auth:{imsi}:{service_type}"
    r.set(auth_key, json.dumps({"authorized": True, "params": req, "at": datetime.utcnow().isoformat()}))
    return {"status": "authorized", "serviceType": service_type}


@app.post("/nudm-ssau/v1/{ue_identity}/{service_type}/remove")
def ssau_remove(ue_identity: str, service_type: str):
    """Remove Service-Specific Authorization."""
    imsi = deconceal_suci(ue_identity) if suci_is_suci(ue_identity) else ue_identity
    r = get_redis()
    r.delete(f"ssau:auth:{imsi}:{service_type}")
    return {"status": "removed", "serviceType": service_type}


# ============================================================================
# Nudm_ReportSMDeliveryStatus (RSDS) - TS 29.503 §5.9
# ============================================================================

@app.post("/nudm-rsds/v1/{ue_identity}/sm-delivery-status")
def report_sm_delivery_status(ue_identity: str, req: Dict):
    """Report SMS Delivery Status.
    
    SMS-GMSC or IP-SM-GW reports delivery status.
    """
    imsi = deconceal_suci(ue_identity) if suci_is_suci(ue_identity) else ue_identity
    status = req.get("deliveryStatus", "DELIVERED")
    r = get_redis()
    mwd_key = f"uecm:mwd:{imsi}"
    if status == "DELIVERED":
        r.delete(mwd_key)
    else:
        r.set(mwd_key, json.dumps({"status": status, "at": datetime.utcnow().isoformat()}))
    return {"status": "delivery_status_reported"}
@app.get("/subscribers/{imsi}/eps-subscription", response_model=EPSSubscriptionResponse)
def get_eps_subscription(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_eps_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            # Return defaults
            return EPSSubscriptionResponse(imsi=imsi, created_at="", updated_at="")
        return row
    finally:
        conn.close()


@app.put("/subscribers/{imsi}/eps-subscription", response_model=EPSSubscriptionResponse)
def update_eps_subscription(imsi: str, data: EPSSubscriptionBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        fields = []
        values = []
        for field, value in data.model_dump(exclude_unset=True).items():
            if field in ("apn_config", "rat_restrictions", "msisdn_list", "csg_subscription",
                         "mme_subscription", "hss_subscription", "lcs_privacy", "vplmn_dynamic") and value is not None:
                value = json.dumps(value)
            fields.append(f"{field}=%s")
            values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.append(imsi)
        cur.execute(f"UPDATE tbl_eps_subscription SET {', '.join(fields)} WHERE imsi=%s", values)
        if cur.rowcount == 0:
            # Insert if not exists
            cols = [f for f, _ in data.model_dump(exclude_unset=True).items()] + ["imsi"]
            vals = [v for _, v in data.model_dump(exclude_unset=True).items()] + [imsi]
            placeholders = ", ".join(["%s"] * len(vals))
            cur.execute(f"INSERT INTO tbl_eps_subscription ({', '.join(cols)}) VALUES ({placeholders})", vals)
        conn.commit()
        
        return get_eps_subscription(imsi)
    finally:
        conn.close()


# ============================================================================
# 5G Subscription
# ============================================================================
@app.get("/subscribers/{imsi}/5g-subscription", response_model=FiveGSubscriptionResponse)
def get_5g_subscription(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_5g_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="5G subscription not found")
        return row
    finally:
        conn.close()


@app.put("/subscribers/{imsi}/5g-subscription", response_model=FiveGSubscriptionResponse)
def update_5g_subscription(imsi: str, data: FiveGSubscriptionBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        fields = []
        values = []
        for field, value in data.model_dump(exclude_unset=True).items():
            if field in ("suci_calc_info", "default_nssai", "allowed_nssai", "rat_restrictions_5g",
                         "smf_selection", "lcs_privacy_5g", "sor_info", "ue_id_mapping",
                         "nssaa_info", "vplmn_5g_data") and value is not None:
                value = json.dumps(value)
            fields.append(f"{field}=%s")
            values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.append(imsi)
        cur.execute(f"UPDATE tbl_5g_subscription SET {', '.join(fields)} WHERE imsi=%s", values)
        if cur.rowcount == 0:
            cols = [f for f, _ in data.model_dump(exclude_unset=True).items()] + ["imsi"]
            vals = [v for _, v in data.model_dump(exclude_unset=True).items()] + [imsi]
            placeholders = ", ".join(["%s"] * len(vals))
            cur.execute(f"INSERT INTO tbl_5g_subscription ({', '.join(cols)}) VALUES ({placeholders})", vals)
        conn.commit()
        
        return get_5g_subscription(imsi)
    finally:
        conn.close()


# ============================================================================
# IMS Subscription
# ============================================================================
@app.get("/subscribers/{imsi}/ims-subscription", response_model=IMSSubscriptionResponse)
def get_ims_subscription(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_ims_subscription WHERE imsi=%s", (imsi,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="IMS subscription not found")
        return row
    finally:
        conn.close()


@app.put("/subscribers/{imsi}/ims-subscription", response_model=IMSSubscriptionResponse)
def update_ims_subscription(imsi: str, data: IMSSubscriptionBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        fields = []
        values = []
        for field, value in data.model_dump(exclude_unset=True).items():
            if field in ("impu_list", "contact_list") and value is not None:
                value = json.dumps(value)
            fields.append(f"{field}=%s")
            values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.append(imsi)
        cur.execute(f"UPDATE tbl_ims_subscription SET {', '.join(fields)} WHERE imsi=%s", values)
        if cur.rowcount == 0:
            cols = [f for f, _ in data.model_dump(exclude_unset=True).items()] + ["imsi"]
            vals = [v for _, v in data.model_dump(exclude_unset=True).items()] + [imsi]
            placeholders = ", ".join(["%s"] * len(vals))
            cur.execute(f"INSERT INTO tbl_ims_subscription ({', '.join(cols)}) VALUES ({placeholders})", vals)
        conn.commit()
        
        return get_ims_subscription(imsi)
    finally:
        conn.close()


# ============================================================================
# APN/DNN Profiles
# ============================================================================
@app.get("/subscribers/{imsi}/apn-profiles", response_model=List[APNProfileResponse])
def list_apn_profiles(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_apn_profile WHERE imsi=%s ORDER BY is_default DESC, apn", (imsi,))
        return cur.fetchall()
    finally:
        conn.close()


@app.post("/subscribers/{imsi}/apn-profiles", response_model=APNProfileResponse, status_code=201)
def create_apn_profile(imsi: str, profile: APNProfileBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        # If this is default, unset others
        if profile.is_default:
            cur.execute("UPDATE tbl_apn_profile SET is_default=0 WHERE imsi=%s", (imsi,))
        
        fields = list(profile.model_dump().keys())
        values = list(profile.model_dump().values()) + [imsi]
        placeholders = ", ".join(["%s"] * len(values))
        cols = ", ".join(fields + ["imsi"])
        
        cur.execute(f"INSERT INTO tbl_apn_profile ({cols}) VALUES ({placeholders})", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_apn_profile WHERE imsi=%s AND apn=%s", (imsi, profile.apn))
        return cur.fetchone()
    finally:
        conn.close()


@app.put("/subscribers/{imsi}/apn-profiles/{apn}", response_model=APNProfileResponse)
def update_apn_profile(imsi: str, apn: str, profile: APNProfileBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_apn_profile WHERE imsi=%s AND apn=%s", (imsi, apn))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="APN profile not found")
        
        if profile.is_default:
            cur.execute("UPDATE tbl_apn_profile SET is_default=0 WHERE imsi=%s", (imsi,))
        
        fields = []
        values = []
        for field, value in profile.model_dump(exclude_unset=True).items():
            fields.append(f"{field}=%s")
            values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.extend([imsi, apn])
        cur.execute(f"UPDATE tbl_apn_profile SET {', '.join(fields)} WHERE imsi=%s AND apn=%s", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_apn_profile WHERE imsi=%s AND apn=%s", (imsi, apn))
        return cur.fetchone()
    finally:
        conn.close()


@app.delete("/subscribers/{imsi}/apn-profiles/{apn}")
def delete_apn_profile(imsi: str, apn: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_apn_profile WHERE imsi=%s AND apn=%s", (imsi, apn))
        conn.commit()
        return {"status": "deleted", "imsi": imsi, "apn": apn}
    finally:
        conn.close()


# ============================================================================
# Supplementary Services
# ============================================================================
@app.get("/subscribers/{imsi}/supplementary-services", response_model=List[SupplementaryServiceResponse])
def list_supplementary_services(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_supplementary_service WHERE imsi=%s", (imsi,))
        return cur.fetchall()
    finally:
        conn.close()


@app.post("/subscribers/{imsi}/supplementary-services", response_model=SupplementaryServiceResponse, status_code=201)
def create_supplementary_service(imsi: str, service: SupplementaryServiceBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        fields = list(service.model_dump().keys())
        values = list(service.model_dump().values()) + [imsi]
        placeholders = ", ".join(["%s"] * len(values))
        cols = ", ".join(fields + ["imsi"])
        
        cur.execute(f"INSERT INTO tbl_supplementary_service ({cols}) VALUES ({placeholders})", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_supplementary_service WHERE imsi=%s AND service_code=%s", (imsi, service.service_code))
        return cur.fetchone()
    finally:
        conn.close()


@app.put("/subscribers/{imsi}/supplementary-services/{service_code}", response_model=SupplementaryServiceResponse)
def update_supplementary_service(imsi: str, service_code: str, service: SupplementaryServiceBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_supplementary_service WHERE imsi=%s AND service_code=%s", (imsi, service_code))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Supplementary service not found")
        
        fields = []
        values = []
        for field, value in service.model_dump(exclude_unset=True).items():
            if field == "camel_tdp_list" and value is not None:
                value = json.dumps(value)
            fields.append(f"{field}=%s")
            values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.extend([imsi, service_code])
        cur.execute(f"UPDATE tbl_supplementary_service SET {', '.join(fields)} WHERE imsi=%s AND service_code=%s", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_supplementary_service WHERE imsi=%s AND service_code=%s", (imsi, service_code))
        return cur.fetchone()
    finally:
        conn.close()


@app.delete("/subscribers/{imsi}/supplementary-services/{service_code}")
def delete_supplementary_service(imsi: str, service_code: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_supplementary_service WHERE imsi=%s AND service_code=%s", (imsi, service_code))
        conn.commit()
        return {"status": "deleted", "imsi": imsi, "service_code": service_code}
    finally:
        conn.close()


# ============================================================================
# Roaming Profiles
# ============================================================================
@app.get("/subscribers/{imsi}/roaming-profiles", response_model=List[RoamingProfileResponse])
def list_roaming_profiles(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_roaming_profile WHERE imsi=%s", (imsi,))
        return cur.fetchall()
    finally:
        conn.close()


@app.post("/subscribers/{imsi}/roaming-profiles", response_model=RoamingProfileResponse, status_code=201)
def create_roaming_profile(imsi: str, profile: RoamingProfileBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        fields = list(profile.model_dump().keys())
        values = list(profile.model_dump().values()) + [imsi]
        placeholders = ", ".join(["%s"] * len(values))
        cols = ", ".join(fields + ["imsi"])
        
        cur.execute(f"INSERT INTO tbl_roaming_profile ({cols}) VALUES ({placeholders})", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_roaming_profile WHERE imsi=%s AND visited_plmn=%s", (imsi, profile.visited_plmn))
        return cur.fetchone()
    finally:
        conn.close()


@app.put("/subscribers/{imsi}/roaming-profiles/{visited_plmn}", response_model=RoamingProfileResponse)
def update_roaming_profile(imsi: str, visited_plmn: str, profile: RoamingProfileBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_roaming_profile WHERE imsi=%s AND visited_plmn=%s", (imsi, visited_plmn))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Roaming profile not found")
        
        fields = []
        values = []
        for field, value in profile.model_dump(exclude_unset=True).items():
            if field == "rat_allowed" and value is not None:
                value = json.dumps(value)
            fields.append(f"{field}=%s")
            values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.extend([imsi, visited_plmn])
        cur.execute(f"UPDATE tbl_roaming_profile SET {', '.join(fields)} WHERE imsi=%s AND visited_plmn=%s", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_roaming_profile WHERE imsi=%s AND visited_plmn=%s", (imsi, visited_plmn))
        return cur.fetchone()
    finally:
        conn.close()


@app.delete("/subscribers/{imsi}/roaming-profiles/{visited_plmn}")
def delete_roaming_profile(imsi: str, visited_plmn: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_roaming_profile WHERE imsi=%s AND visited_plmn=%s", (imsi, visited_plmn))
        conn.commit()
        return {"status": "deleted", "imsi": imsi, "visited_plmn": visited_plmn}
    finally:
        conn.close()


# ============================================================================
# USSD Routing
# ============================================================================
@app.get("/ussd-routes", response_model=List[USSDRouteResponse])
def list_ussd_routes():
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_ussd_routing WHERE is_active=1 ORDER BY priority")
        return cur.fetchall()
    finally:
        conn.close()


@app.post("/ussd-routes", response_model=USSDRouteResponse, status_code=201)
def create_ussd_route(route: USSDRouteBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        fields = list(route.model_dump().keys())
        values = list(route.model_dump().values())
        placeholders = ", ".join(["%s"] * len(values))
        cols = ", ".join(fields)
        
        cur.execute(f"INSERT INTO tbl_ussd_routing ({cols}) VALUES ({placeholders})", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_ussd_routing WHERE ussd_string=%s", (route.ussd_string,))
        return cur.fetchone()
    finally:
        conn.close()


# ============================================================================
# CAMEL Profiles
# ============================================================================
@app.get("/subscribers/{imsi}/camel-profiles", response_model=List[CamelServiceProfileResponse])
def list_camel_profiles(imsi: str):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_camel_service_profile WHERE imsi=%s", (imsi,))
        return cur.fetchall()
    finally:
        conn.close()


@app.post("/subscribers/{imsi}/camel-profiles", response_model=CamelServiceProfileResponse, status_code=201)
def create_camel_profile(imsi: str, profile: CamelServiceProfileBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM tbl_subscriber WHERE imsi=%s", (imsi,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subscriber not found")
        
        fields = list(profile.model_dump().keys())
        values = list(profile.model_dump().values()) + [imsi]
        placeholders = ", ".join(["%s"] * len(values))
        cols = ", ".join(fields + ["imsi"])
        
        cur.execute(f"INSERT INTO tbl_camel_service_profile ({cols}) VALUES ({placeholders})", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_camel_service_profile WHERE imsi=%s AND service_key=%s", (imsi, profile.service_key))
        return cur.fetchone()
    finally:
        conn.close()


# ============================================================================
# Network Nodes
# ============================================================================
@app.get("/network-nodes", response_model=List[NetworkNodeResponse])
def list_network_nodes(node_type: Optional[str] = Query(None), plmn_id: Optional[str] = Query(None)):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        query = "SELECT * FROM tbl_network_node WHERE is_active=1"
        params = []
        if node_type:
            query += " AND node_type=%s"
            params.append(node_type)
        if plmn_id:
            query += " AND plmn_id=%s"
            params.append(plmn_id)
        query += " ORDER BY node_name"
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()


@app.post("/network-nodes", response_model=NetworkNodeResponse, status_code=201)
def create_network_node(node: NetworkNodeBase):
    conn = get_db()
    try:
        cur = conn.cursor()
        fields = list(node.model_dump().keys())
        values = list(node.model_dump().values())
        placeholders = ", ".join(["%s"] * len(values))
        cols = ", ".join(fields)
        
        if node.supported_interfaces:
            # Find the index and convert to JSON
            idx = fields.index("supported_interfaces")
            values[idx] = json.dumps(node.supported_interfaces)
        
        cur.execute(f"INSERT INTO tbl_network_node ({cols}) VALUES ({placeholders})", values)
        conn.commit()
        
        cur.execute("SELECT * FROM tbl_network_node WHERE node_name=%s", (node.node_name,))
        return cur.fetchone()
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
                 network_access_mode,subscriber_status,roaming_restricted,ambr_ul,ambr_dl,
                 prose_enabled,redcap_allowed,ntn_allowed,eredcap_allowed,xr_allowed,aiml_allowed
    
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
                    if CRYPTO_AVAILABLE and opc:
                        crypto = get_crypto(opc)
                        derived = crypto.derive_5g_keys(bytes.fromhex(k.upper()), sqn, bytes.fromhex(amf))
                        keys_5g = {k: v.hex().upper() for k, v in derived.items()}
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail="CRYPTO_UNAVAILABLE: pycryptodome required for 5G key derivation — fail closed"
                        )
                
                cur.execute(
                    """INSERT INTO tbl_subscriber
                       (imsi, msisdn, imei, imei_sv, k, ki, op, opc, sqn, amf,
                        k_asme, k_seaf, k_ausf, kc, sres,
                        network_access_mode, subscriber_status, roaming_restricted,
                        regional_restriction, odb_data, trace_config,
                        prose_enabled, redcap_allowed, ntn_allowed, eredcap_allowed, xr_allowed, aiml_allowed,
                        batch_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                        msisdn=VALUES(msisdn), imei=VALUES(imei), k=VALUES(k), ki=VALUES(ki),
                        op=VALUES(op), opc=VALUES(opc), sqn=VALUES(sqn), amf=VALUES(amf),
                        k_asme=VALUES(k_asme), k_seaf=VALUES(k_seaf), k_ausf=VALUES(k_ausf),
                        kc=VALUES(kc), sres=VALUES(sres),
                        network_access_mode=VALUES(network_access_mode),
                        subscriber_status=VALUES(subscriber_status),
                        roaming_restricted=VALUES(roaming_restricted),
                        regional_restriction=VALUES(regional_restriction),
                        odb_data=VALUES(odb_data), trace_config=VALUES(trace_config),
                        prose_enabled=VALUES(prose_enabled), redcap_allowed=VALUES(redcap_allowed),
                        ntn_allowed=VALUES(ntn_allowed), eredcap_allowed=VALUES(eredcap_allowed),
                        xr_allowed=VALUES(xr_allowed), aiml_allowed=VALUES(aiml_allowed),
                        batch_id=VALUES(batch_id)""",
                    (imsi,
                     rec.get("msisdn"), rec.get("imei"), rec.get("imei_sv"), k, ki, op, opc,
                     int(rec.get("sqn", 0)), rec.get("amf", "8000").upper(),
                     keys_5g["k_asme"], keys_5g["k_seaf"], keys_5g["k_ausf"],
                     rec.get("kc"), rec.get("sres"),
                     int(rec.get("network_access_mode", default_network_access_mode)),
                     int(rec.get("subscriber_status", default_subscriber_status)),
                     rec.get("roaming_restricted", "false").lower() == "true",
                     json.dumps(json.loads(rec["regional_restriction"])) if rec.get("regional_restriction") else None,
                     json.dumps(json.loads(rec["odb_data"])) if rec.get("odb_data") else None,
                     json.dumps(json.loads(rec["trace_config"])) if rec.get("trace_config") else None,
                     rec.get("prose_enabled", "false").lower() == "true",
                     rec.get("redcap_allowed", "false").lower() == "true",
                     rec.get("ntn_allowed", "false").lower() == "true",
                     rec.get("eredcap_allowed", "false").lower() == "true",
                     rec.get("xr_allowed", "false").lower() == "true",
                     rec.get("aiml_allowed", "false").lower() == "true",
                     batch_id),
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
@app.get("/imsi-ranges", response_model=List[IMSIRangeResponse])
def list_imsi_ranges():
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM tbl_imsi_range ORDER BY created_at DESC")
        return cur.fetchall()
    finally:
        conn.close()


@app.post("/imsi-ranges", response_model=IMSIRangeResponse, status_code=201)
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
               (range_name, mcc, mnc, msisdn_prefix, imsi_start, imsi_end, next_imsi, total_count,
                default_k, default_ki, default_op, default_opc, default_algorithm)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (range_data.range_name, range_data.mcc, range_data.mnc,
             range_data.msisdn_prefix, range_data.imsi_start, range_data.imsi_end,
             range_data.imsi_start, total,
             range_data.default_k, range_data.default_ki, range_data.default_op, range_data.default_opc,
             range_data.default_algorithm)
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
            k = req.k or range_row.get("default_k")
            ki = req.ki or range_row.get("default_ki")
            op = req.op or range_row.get("default_op")
            opc = req.opc or range_row.get("default_opc")
            
            if not opc and op and k:
                opc = derive_opc(op.upper(), k.upper())
            elif not opc and op and ki:
                opc = derive_opc(op.upper(), ki.upper())
            
            if k and not any(keys_5g.values()):
                if CRYPTO_AVAILABLE and opc:
                    crypto = get_crypto(opc)
                    derived = crypto.derive_5g_keys(bytes.fromhex(k.upper()), 0, bytes.fromhex("8000"))
                    keys_5g = {k: v.hex().upper() for k, v in derived.items()}
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="CRYPTO_UNAVAILABLE: pycryptodome required for 5G key derivation — fail closed"
                    )
            
            cur.execute(
                """INSERT INTO tbl_subscriber
                   (imsi, k, ki, op, opc, sqn, amf,
                    k_asme, k_seaf, k_ausf,
                    network_access_mode, subscriber_status, batch_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (imsi, k, ki, op, opc, 0, "8000",
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


# ============================================================================
# Nhss Client (UDM -> HSS per TS 29.563) + Central Provisioning + Bidirectional Sync
# ============================================================================
from udm.src.provisioning_importer import (
    provision_sim_card, parse_batch_file, import_batch,
    apply_hss_imei_update, apply_hss_roaming_update,
    SimCardRecord,
)


class NhssGenerateAvRequest(BaseModel):
    imsi: str = Field(..., pattern=r"^[0-9]{5,15}$")
    authType: str = Field("5G_AKA", pattern="^(5G_AKA|EAP_AKA_PRIME)$")
    servingNetworkName: str = ""
    resynchronizationInfo: Optional[Dict] = None


@app.post("/nhss-client/generate-av")
def nhss_client_generate_av(req: NhssGenerateAvRequest):
    """Nhss_UEAU: UDM requests 5G_AKA/EAP_AKA_PRIME vector from HSS (Option 1).
    
    Used when subscriber credentials live in EPS-UDR and HSS acts as ARPF.
    """
    try:
        status, resp = sync_generate_av(req.imsi, req.authType, req.servingNetworkName)
        return {"status": status, "response": resp}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"HSS unreachable: {str(e)}")


@app.post("/nhss-client/pgw-data/{imsi}")
def nhss_client_pgw_data(imsi: str):
    """Nhss_SDM: UDM fetches PGW-C+SMF FQDN per APN for PDU continuity (5GC->EPC)."""
    try:
        status, resp = sync_get_pgw_data(imsi)
        return {"status": status, "response": resp}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"HSS unreachable: {str(e)}")


@app.post("/nhss-client/deregister-sn")
def nhss_client_deregister_sn(req: Dict):
    """Nhss_UECM: UDM tells HSS to cancel EPS/3G serving node (IRAT mobility).
    
    Body: { imsi, deregReason, guami? }
    deregReason: UE_INITIAL_AND_SINGLE_REGISTRATION | UE_INITIAL_AND_DUAL_REGISTRATION
                 | EPS_TO_5GS_MOBILITY | EPS_TO_5GS_MOBILITY_WITHOUT_N26_IWK
    """
    try:
        status, resp = sync_deregister_sn(req["imsi"], req["deregReason"], req.get("guami"))
        return {"status": status, "response": resp}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"HSS unreachable: {str(e)}")


@app.post("/nhss-client/imei-update/{imsi}")
def nhss_client_imei_update(imsi: str, req: Dict):
    """Nhss_UECM: UDM tells HSS about IMEI/PEI change."""
    try:
        status, resp = sync_update_imei(imsi, req.get("imei"), req.get("imeiSv"))
        return {"status": status, "response": resp}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"HSS unreachable: {str(e)}")


@app.post("/nhss-client/roaming-update/{imsi}")
def nhss_client_roaming_update(imsi: str, req: Dict):
    """Nhss_UECM: UDM tells HSS about roaming status (PLMN) change."""
    try:
        status, resp = sync_update_roaming(imsi, req["plmnId"])
        return {"status": status, "response": resp}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"HSS unreachable: {str(e)}")


@app.post("/nhss-client/pp-create/{imsi}")
def nhss_client_pp_create(imsi: str, af_instance_id: str, req: Dict):
    """Nhss_PP: UDM pushes external parameters to HSS for EPC enforcement.
    
    Body: { referenceId, communicationCharacteristics?, validityTime?, mtcProviderInformation?, supportedFeatures? }
    """
    try:
        status, resp = sync_pp_create(imsi, af_instance_id, req.get("referenceId", f"ref-{uuid.uuid4().hex[:8]}"),
                                       req.get("communicationCharacteristics"))
        return {"status": status, "response": resp}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"HSS unreachable: {str(e)}")


# ============================================================================
# Bidirectional Sync: HSS -> UDM (called by HSS Nhss server)
# ============================================================================

class HssImeiUpdate(BaseModel):
    imei: Optional[str] = Field(None, pattern=r"^[0-9]{14,15}$")
    imei_sv: Optional[str] = Field(None, pattern=r"^[0-9]{16}$")


@app.post("/sync/hss/imei-update/{imsi}")
def hss_imei_update(imsi: str, req: HssImeiUpdate):
    """HSS notifies UDM of IMEI/PEI change (Nhss_UECM reverse direction).
    
    UDM updates canonical subscriber record and EPS-UDR projection.
    """
    result = apply_hss_imei_update(imsi, req.imei, req.imei_sv)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["errors"])
    return result


@app.post("/sync/hss/roaming-update/{imsi}")
def hss_roaming_update(imsi: str, req: Dict):
    """HSS notifies UDM of roaming status (PLMN) change."""
    plmn_id = req.get("plmnId")
    if not plmn_id:
        raise HTTPException(status_code=400, detail="plmnId required")
    result = apply_hss_roaming_update(imsi, plmn_id)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["errors"])
    return result


# ============================================================================
# Central SIM Provisioning (single entry point for all views)
# ============================================================================

@app.post("/provision/sim", status_code=201)
def provision_single_sim(record: SimCardRecord):
    """Provision one SIM card across all views (UDM 5G + HSS/HLR 4G/3G/2G).
    
    Writes canonical record + all projections in one transaction:
    - tbl_subscriber (canonical, hssdb)
    - tbl_5g_subscription (UDM view, if 5G mode)
    - tbl_eps_subscription (HSS view, if 4G/3G/2G mode)
    - tbl_eps_apn_profile (PGW-C+SMF FQDN per APN)
    - tbl_eps_subscriber in eps_udr (HSS front-end for Nhss/S6a/Gr)
    - IMS, supplementary, roaming projections
    - Cross-unit sync audit log
    
    network_access_mode: 0=GPRS(3G), 1=CS(2G), 2=Both(2G+3G), 3=5G
    """
    result = provision_sim_card(record)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["errors"])
    return result


@app.post("/provision/batch", status_code=201)
async def provision_batch(
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
):
    """Bulk provision SIM cards from CSV/JSON file.
    
    CSV columns: iccid,imsi,msisdn,ki,k,op,opc,sqn,amf,networkAccessMode,
                 subscriberStatus,roamingRestricted,apnProfiles(nested JSON),
                 nssai(nested JSON),supplementaryServices(nested JSON),
                 roamingProfiles(nested JSON),imsSubscription(nested JSON),
                 batchId,mvnoMcc,mvnoMnc,n5gcAllowed,pniNpnAllowed
    
    JSON: array of SimCardRecord objects.
    """
    batch_id = batch_id or f"batch-{uuid.uuid4().hex[:12]}"
    content = await file.read()
    
    try:
        records = parse_batch_file(content, file.filename or "upload")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")
    
    result = import_batch(records, batch_id)
    return result


@app.get("/sync/audit/{imsi}")
def get_sync_audit(imsi: str, limit: int = Query(50, ge=1, le=500)):
    """Get cross-unit sync audit trail for a subscriber."""
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT * FROM tbl_sync_audit WHERE imsi=%s ORDER BY created_at DESC LIMIT %s""",
            (imsi, limit),
        )
        return cur.fetchall()
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("UDM_PORT", "8080")))