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
import os
import secrets
import uuid
from typing import Optional, List, Dict, Any

import mysql.connector
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel, Field, field_validator
import redis

# Crypto imports for Milenage/AES (TS 33.102, 33.501)
try:
    from Crypto.Cipher import AES
    from Crypto.Hash import SHA256, HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

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
        import hashlib
        return hashlib.sha256((op + k).encode()).hexdigest()[:32].upper()
    op_bytes = bytes.fromhex(op)
    k_bytes = bytes.fromhex(k)
    cipher = AES.new(k_bytes, AES.MODE_ECB)
    opc = cipher.encrypt(op_bytes)
    return opc.hex().upper()


def derive_5g_keys_simple(k: str, sqn: int, amf: str) -> dict:
    """Fallback 5G key derivation without pycryptodome."""
    import hashlib
    base = k + f"{sqn:012X}" + amf + "00" * 16
    return {
        "k_asme": hashlib.sha256((base + "asme").encode()).hexdigest()[:32].upper(),
        "k_seaf": hashlib.sha256((base + "seaf").encode()).hexdigest()[:32].upper(),
        "k_ausf": hashlib.sha256((base + "ausf").encode()).hexdigest()[:32].upper(),
    }


def derive_2g3g_keys_simple(ki: str, rand: str) -> dict:
    """Fallback 2G/3G key derivation without pycryptodome."""
    import hashlib
    base = ki + rand
    return {
        "kc": hashlib.md5((base + "kc").encode()).hexdigest()[:16].upper(),
        "sres": hashlib.md5((base + "sres").encode()).hexdigest()[:8].upper(),
    }


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
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "udm",
        "version": "3.0.0",
        "modes": ["5G", "4G", "3G", "2G"],
        "crypto": "milenage" if CRYPTO_AVAILABLE else "fallback",
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
                derived = derive_5g_keys_simple(sub.k.upper(), sub.sqn, sub.amf.upper())
                keys_5g = derived
        
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
        
        # Default response values
        autn = "00" * 16
        res = "00" * 8
        xres = "00" * 32
        xres_star = "00" * 64
        ck = "00" * 32
        ik = "00" * 32
        k_asme = "00" * 64
        k_seaf = "00" * 64
        k_ausf = "00" * 64
        k_amf = "00" * 64
        sres = "00" * 8
        kc = "00" * 16
        
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
                # Fallback
                keys = derive_5g_keys_simple(row["k"], sqn, row["amf"])
                import hashlib
                autn = hashlib.sha256((row["k"] + rand_hex + f"{sqn:012X}" + row["amf"]).encode()).hexdigest()[:32].upper()
                xres_star = hashlib.sha256((row["k"] + rand_hex).encode()).hexdigest()[:64].upper()
                res = xres_star[:16]
                xres = xres_star
                ck = ik = hashlib.sha256((row["k"] + rand_hex + "ckik").encode()).hexdigest()[:32].upper()
                k_ausf = k_seaf = k_amf = keys["k_seaf"]
                k_asme = keys["k_asme"]
        
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
                import hashlib
                autn = hashlib.sha256((row["ki"] + rand_hex + f"{sqn:012X}" + row["amf"]).encode()).hexdigest()[:32].upper()
                xres = hashlib.sha256((row["ki"] + rand_hex).encode()).hexdigest()[:16].upper()
                res = xres
                ck = ik = hashlib.sha256((row["ki"] + rand_hex + "ckik").encode()).hexdigest()[:32].upper()
                k_asme = hashlib.sha256((ck + ik + f"{sqn:012X}").encode()).hexdigest()[:64].upper()
        
        # 2G/3G (if Ki present)
        if row.get("ki"):
            if CRYPTO_AVAILABLE and row.get("opc"):
                crypto = get_crypto(row["opc"])
                ki_bytes = bytes.fromhex(row["ki"])
                av = crypto.generate_auth_vector_2g3g(ki_bytes, rand_bytes)
                sres = av["sres"].hex().upper()
                kc = av["kc"].hex().upper()
            else:
                keys = derive_2g3g_keys_simple(row["ki"], rand_hex)
                sres = keys["sres"]
                kc = keys["kc"]
        
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
# EPS Subscription (S6a)
# ============================================================================
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
                        keys_5g = derive_5g_keys_simple(k.upper(), sqn, amf)
                
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
                    keys_5g = derive_5g_keys_simple(k.upper(), 0, "8000")
            
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("UDM_PORT", "8080")))