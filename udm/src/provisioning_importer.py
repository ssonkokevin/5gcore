"""Central SIM Provisioning Importer.

Provides a single entry point to upload SIM card personalization data
and project it to all network views:

  * 5G view (UDM):      tbl_5g_subscription in hssdb  -> Nudm_SDM/UEAU/UECM
  * 4G view (HSS):      tbl_eps_subscription in hssdb -> S6a/S6d (MME/SGSN)
  * 3G/2G view (HLR):   tbl_eps_subscription in hssdb -> Gr/C/D/B/E/F/G (MAP)
  * EPS-UDR (HSS front-end): tbl_eps_subscriber in eps_udr -> Nhss APIs

Per TS 23.632 (Part L): one canonical record in UDR, four rendered views.
The SIM is never pushed by itself; the operator imports per-card
personalization data (ICCID, IMSI, Ki, OPc, etc.) and the system renders
the appropriate subscription data per RAT.

Batch upload formats: CSV or JSON with one record per SIM card.
"""

import csv
import io
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

import mysql.connector
from pydantic import BaseModel

from udm.src.nhss_client import (
    sync_generate_av, sync_get_pgw_data, sync_deregister_sn,
    sync_update_imei, sync_update_roaming, sync_pp_create,
)

# ============================================================================
# DB configs
# ============================================================================
HSSDB_CONFIG = {
    "host": os.getenv("DB_HOST", "hssdb"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "hss"),
    "password": os.getenv("DB_PASSWORD", "hss123"),
    "database": os.getenv("DB_NAME", "hssdb"),
}

EPS_UDR_CONFIG = {
    "host": os.getenv("HSS_DB_HOST", "hssdb"),
    "port": int(os.getenv("HSS_DB_PORT", "3306")),
    "user": os.getenv("HSS_DB_USER", "hss"),
    "password": os.getenv("HSS_DB_PASSWORD", "hss123"),
    "database": os.getenv("EPS_UDR_DB_NAME", "eps_udr"),
}

OPERATOR_KEY = os.getenv("OPERATOR_KEY", "00" * 16)
AUTH_OPTION = os.getenv("AUTH_OPTION", "2")  # 1=HSS, 2=UDM, 3=split


def get_hssdb():
    return mysql.connector.connect(**HSSDB_CONFIG)


def get_eps_udr():
    return mysql.connector.connect(**EPS_UDR_CONFIG)


# ============================================================================
# SIM Personalization Data Model (what the vendor delivers)
# ============================================================================
class SimCardRecord(BaseModel):
    """One SIM card's personalization data from the vendor."""
    iccid: str
    imsi: str
    msisdn: Optional[str] = None
    ki: Optional[str] = None              # 4G/3G/2G root key (128-bit hex)
    k: Optional[str] = None               # 5G root key (256-bit hex / K4)
    op: Optional[str] = None              # OP (operator variant)
    opc: Optional[str] = None             # OPc (derived)
    sqn: int = 0
    amf: str = "8000"
    networkAccessMode: int = 2            # 0=GPRS,1=CS,2=Both,3=5G
    subscriberStatus: int = 0             # 0=Active
    roamingRestricted: bool = False
    apnProfiles: Optional[List[Dict]] = None
    nssai: Optional[List[Dict]] = None    # 5G S-NSSAI
    dnnConfigs: Optional[List[Dict]] = None
    supplementaryServices: Optional[List[Dict]] = None
    roamingProfiles: Optional[List[Dict]] = None
    camelProfiles: Optional[List[Dict]] = None
    imsSubscription: Optional[Dict] = None
    batchId: Optional[str] = None
    mvnoMcc: Optional[str] = None
    mvnoMnc: Optional[str] = None
    # 5G SA specific
    suciCalcInfo: Optional[Dict] = None
    n5gcAllowed: bool = False             # 5G NAS capability
    pniNpnAllowed: bool = False           # Private network
    # Auth ownership (per TS 23.632 L.4)
    authOption: Optional[int] = None      # Override global AUTH_OPTION


# ============================================================================
# Key derivation helpers
# ============================================================================
def derive_opc_if_needed(op: str, k_or_ki: str) -> Optional[str]:
    """Derive OPc = E_K(OP) xor OP (TS 35.206). Fails loudly without AES."""
    if not op or not k_or_ki:
        return None
    from corelib.milenage import derive_opc
    return derive_opc(bytes.fromhex(op), bytes.fromhex(k_or_ki)).hex().upper()


# ============================================================================
# Central provisioning: one SIM -> all views
# ============================================================================
def provision_sim_card(record: SimCardRecord, batch_id: Optional[str] = None) -> Dict[str, Any]:
    """Provision one SIM card across all views.

    Writes to:
      1. tbl_subscriber (canonical, hssdb)
      2. tbl_5g_subscription (UDM 5G view, if mode includes 5G)
      3. tbl_eps_subscription (HSS 4G view, if mode includes 4G/3G/2G)
      4. tbl_eps_apn_profile (APN/DNN per APN for PGW-C+SMF FQDN)
      5. tbl_eps_subscriber in eps_udr (HSS front-end for Nhss/S6a/Gr)
      6. tbl_eps_subscription_data in eps_udr
      7. IMS, supplementary, roaming, CAMEL projections
      8. Sync audit log for cross-unit tracking

    Returns dict with status per view and any errors.
    """
    result = {
        "imsi": record.imsi,
        "iccid": record.iccid,
        "status": "success",
        "views": {},
        "errors": [],
    }

    # Determine which views to write
    mode = record.networkAccessMode
    write_5g = mode in (3,)  # 5G SA
    write_eps = mode in (0, 1, 2)  # GPRS(3G), CS(2G), Both(2G+3G)
    write_all = mode == 2  # Both 2G+3G (EPS view covers both)

    # Determine auth option for this subscriber
    sub_auth_option = record.authOption if record.authOption is not None else int(AUTH_OPTION)

    conn_hssdb = get_hssdb()
    conn_eps = get_eps_udr()

    try:
        cur_h = conn_hssdb.cursor()
        cur_e = conn_eps.cursor()

        # --- 1. Canonical subscriber record (hssdb.tbl_subscriber) ---
        opc = record.opc
        if not opc and record.op and (record.k or record.ki):
            opc = derive_opc_if_needed(record.op.upper(), (record.k or record.ki).upper())

        # Per-authentication keys are never stored against the subscriber.
        keys_5g = {"k_asme": None, "k_seaf": None, "k_ausf": None}

        cur_h.execute(
            """INSERT INTO tbl_subscriber
               (imsi, msisdn, imei, imei_sv, k, ki, op, opc, sqn, amf,
                k_asme, k_seaf, k_ausf, kc, sres,
                network_access_mode, subscriber_status, roaming_restricted,
                regional_restriction, odb_data, trace_config,
                prose_enabled, redcap_allowed, ntn_allowed, eredcap_allowed,
                xr_allowed, aiml_allowed,
                batch_id, mvno_mcc, mvno_mnc)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                msisdn=VALUES(msisdn), k=VALUES(k), ki=VALUES(ki), op=VALUES(op), opc=VALUES(opc),
                sqn=VALUES(sqn), amf=VALUES(amf),
                k_asme=VALUES(k_asme), k_seaf=VALUES(k_seaf), k_ausf=VALUES(k_ausf),
                network_access_mode=VALUES(network_access_mode),
                subscriber_status=VALUES(subscriber_status),
                roaming_restricted=VALUES(roaming_restricted),
                batch_id=VALUES(batch_id), mvno_mcc=VALUES(mvno_mcc), mvno_mnc=VALUES(mvno_mnc),
                updated_at=CURRENT_TIMESTAMP""",
            (
                record.imsi, record.msisdn, None, None,
                record.k, record.ki, record.op, opc,
                record.sqn, record.amf,
                keys_5g["k_asme"], keys_5g["k_seaf"], keys_5g["k_ausf"],
                None, None,
                mode, record.subscriberStatus, record.roamingRestricted,
                json.dumps(record.regional_restriction if hasattr(record, 'regional_restriction') else {}),
                json.dumps(record.odb_data if hasattr(record, 'odb_data') else {}),
                None,
                False, False, False, False, False, False,
                batch_id or record.batchId, record.mvnoMcc, record.mvnoMnc,
            ),
        )
        conn_hssdb.commit()
        result["views"]["subscriber"] = "provisioned"

        # --- 2. 5G subscription view (UDM) ---
        if write_5g:
            cur_h.execute(
                """INSERT INTO tbl_5g_subscription
                   (imsi, supi, suci_calc_info, default_nssai, allowed_nssai,
                    ue_ambr_ul, ue_ambr_dl, rat_restrictions_5g, smf_selection,
                    gmlc_address, lcs_privacy_5g, sor_info, ue_id_mapping,
                    nssaa_info, vplmn_5g_data,
                    urllc_allowed, mmtc_allowed, v2x_allowed_5g,
                    redcap_allowed_5g, ntn_allowed_5g, pni_npn_allowed,
                    eredcap_allowed_5g, mbs_allowed, xr_allowed_5g,
                    aiml_allowed_5g, multicast_mbs_allowed,
                    reduced_cap_allowed, aiml_enhanced_allowed)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                    default_nssai=VALUES(default_nssai), allowed_nssai=VALUES(allowed_nssai),
                    ue_ambr_ul=VALUES(ue_ambr_ul), ue_ambr_dl=VALUES(ue_ambr_dl),
                    rat_restrictions_5g=VALUES(rat_restrictions_5g),
                    smf_selection=VALUES(smf_selection), updated_at=CURRENT_TIMESTAMP""",
                (
                    record.imsi, f"imsi-{record.imsi}",
                    json.dumps(record.suciCalcInfo) if record.suciCalcInfo else None,
                    json.dumps(record.nssai) if record.nssai else None,
                    json.dumps(record.nssai) if record.nssai else None,
                    1000000000, 1000000000,
                    json.dumps({"nr": True, "eutra": write_eps, "wlan": False}),
                    json.dumps({}),
                    None, None, None, None,
                    json.dumps({}), json.dumps({}),
                    False, False, False,
                    record.redcap_allowed if hasattr(record, 'redcap_allowed') else False,
                    record.ntn_allowed if hasattr(record, 'ntn_allowed') else False,
                    record.pniNpnAllowed,
                    False, False, False,
                    False, False,
                    False, False,
                ),
            )
            conn_hssdb.commit()
            result["views"]["fiveG"] = "provisioned"

        # --- 3. EPS subscription view (HSS/HLR) ---
        if write_eps:
            cur_h.execute(
                """INSERT INTO tbl_eps_subscription
                   (imsi, apn_config, default_apn, ue_ambr_ul, ue_ambr_dl,
                    rat_restrictions, msisdn_list, csg_subscription,
                    mme_subscription, hss_subscription, lcs_privacy,
                    vplmn_dynamic, nb_iot_allowed, emtc_allowed,
                    v2x_allowed, industrial_iot_allowed, redcap_allowed)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                    apn_config=VALUES(apn_config), default_apn=VALUES(default_apn),
                    ue_ambr_ul=VALUES(ue_ambr_ul), ue_ambr_dl=VALUES(ue_ambr_dl),
                    rat_restrictions=VALUES(rat_restrictions),
                    updated_at=CURRENT_TIMESTAMP""",
                (
                    record.imsi,
                    json.dumps(record.apnProfiles) if record.apnProfiles else None,
                    record.apnProfiles[0]["apn"] if record.apnProfiles else None,
                    100000000, 100000000,
                    json.dumps({"eutran": True, "utran": mode in (0, 2), "geran": mode in (1, 2)}),
                    json.dumps([record.msisdn] if record.msisdn else []),
                    None, None, None, None,
                    json.dumps({}), False, False, False, False, False,
                ),
            )
            conn_hssdb.commit()
            result["views"]["eps"] = "provisioned"

        # --- 4. EPS-UDR (HSS front-end for Nhss/S6a/Gr) ---
        cur_e.execute(
            """INSERT INTO tbl_eps_subscriber
               (imsi, msisdn, k, ki, op, opc, sqn, amf, k_asme,
                network_access_mode, subscriber_status, roaming_restricted,
                odb_data, source_system, last_synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'udm',%s)
               ON DUPLICATE KEY UPDATE
                msisdn=VALUES(msisdn), k=VALUES(k), ki=VALUES(ki),
                op=VALUES(op), opc=VALUES(opc), sqn=VALUES(sqn), amf=VALUES(amf),
                k_asme=VALUES(k_asme),
                network_access_mode=VALUES(network_access_mode),
                subscriber_status=VALUES(subscriber_status),
                roaming_restricted=VALUES(roaming_restricted),
                odb_data=VALUES(odb_data), last_synced_at=VALUES(last_synced_at),
                updated_at=CURRENT_TIMESTAMP""",
            (
                record.imsi, record.msisdn,
                record.k, record.ki, record.op, opc,
                record.sqn, record.amf, keys_5g["k_asme"],
                mode, record.subscriberStatus, record.roamingRestricted,
                json.dumps({}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn_eps.commit()

        cur_e.execute(
            """INSERT INTO tbl_eps_subscription_data
               (imsi, apn_config, default_apn, ue_ambr_ul, ue_ambr_dl,
                rat_restrictions, mme_subscription, hss_subscription)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                apn_config=VALUES(apn_config), default_apn=VALUES(default_apn),
                ue_ambr_ul=VALUES(ue_ambr_ul), ue_ambr_dl=VALUES(ue_ambr_dl),
                updated_at=CURRENT_TIMESTAMP""",
            (
                record.imsi,
                json.dumps(record.apnProfiles) if record.apnProfiles else None,
                record.apnProfiles[0]["apn"] if record.apnProfiles else None,
                100000000, 100000000,
                json.dumps({"eutran": True, "utran": mode in (0, 2), "geran": mode in (1, 2)}),
                None, None,
            ),
        )
        conn_eps.commit()
        result["views"]["epsUdr"] = "provisioned"

        # --- 5. APN/DNN profiles (PGW-C+SMF FQDN per APN for PDU continuity) ---
        if record.apnProfiles:
            for apn in record.apnProfiles:
                cur_h.execute(
                    """INSERT INTO tbl_apn_profile
                       (imsi, apn, apn_type, qci, arp_priority,
                        apn_ambr_ul, apn_ambr_dl, pdn_type,
                        pgw_fqdn, sgw_fqdn, dns_primary, dns_secondary,
                        is_default, is_active)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                        qci=VALUES(qci), arp_priority=VALUES(arp_priority),
                        pgw_fqdn=VALUES(pgw_fqdn), sgw_fqdn=VALUES(sgw_fqdn),
                        updated_at=CURRENT_TIMESTAMP""",
                    (
                        record.imsi, apn.get("apn", "internet"),
                        apn.get("apnType", "internet"),
                        apn.get("qci", 9), apn.get("arpPriority", 8),
                        apn.get("apnAmbrUl", 100000000), apn.get("apnAmbrDl", 100000000),
                        apn.get("pdnType", "ipv4v6"),
                        apn.get("pgwFqdn"), apn.get("sgwFqdn"),
                        apn.get("dnsPrimary", "8.8.8.8"), apn.get("dnsSecondary", "8.8.4.4"),
                        apn.get("isDefault", False), apn.get("isActive", True),
                    ),
                )
                # Also project to EPS-UDR APN table
                cur_e.execute(
                    """INSERT INTO tbl_eps_apn_profile
                       (imsi, apn, apn_type, qci, arp_priority,
                        apn_ambr_ul, apn_ambr_dl, pdn_type,
                        pgw_fqdn, sgw_fqdn, dns_primary, dns_secondary,
                        is_default, is_active)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                        qci=VALUES(qci), pgw_fqdn=VALUES(pgw_fqdn),
                        updated_at=CURRENT_TIMESTAMP""",
                    (
                        record.imsi, apn.get("apn", "internet"),
                        apn.get("apnType", "internet"),
                        apn.get("qci", 9), apn.get("arpPriority", 8),
                        apn.get("apnAmbrUl", 100000000), apn.get("apnAmbrDl", 100000000),
                        apn.get("pdnType", "ipv4v6"),
                        apn.get("pgwFqdn"), apn.get("sgwFqdn"),
                        apn.get("dnsPrimary", "8.8.8.8"), apn.get("dnsSecondary", "8.8.4.4"),
                        apn.get("isDefault", False), apn.get("isActive", True),
                    ),
                )
            conn_hssdb.commit()
            conn_eps.commit()
            result["views"]["apnProfiles"] = "provisioned"

        # --- 6. IMS subscription (Cx/Sh view) ---
        if record.imsSubscription:
            cur_h.execute(
                """INSERT INTO tbl_ims_subscription
                   (imsi, impu_list, impi, ims_domain, service_profile_id,
                    scscf_name, scscf_realm, auth_scheme)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                    impu_list=VALUES(impu_list), scscf_name=VALUES(scscf_name),
                    updated_at=CURRENT_TIMESTAMP""",
                (
                    record.imsi,
                    json.dumps(record.imsSubscription.get("impuList", [])),
                    record.imsSubscription.get("impi"),
                    record.imsSubscription.get("imsDomain"),
                    record.imsSubscription.get("serviceProfileId"),
                    record.imsSubscription.get("scscfName"),
                    record.imsSubscription.get("scscfRealm"),
                    record.imsSubscription.get("authScheme", "AKAv1-MD5"),
                ),
            )
            conn_hssdb.commit()
            result["views"]["ims"] = "provisioned"

        # --- 7. Supplementary services ---
        if record.supplementaryServices:
            for svc in record.supplementaryServices:
                cur_h.execute(
                    """INSERT INTO tbl_supplementary_service
                       (imsi, service_code, service_name, provision_status,
                        activation_code, deactivation_code, interrogation_code,
                        registration_code, erasure_code, forwarding_number,
                        forwarding_condition, no_reply_timer, clip_provisioned,
                        clir_provisioned, ussd_enabled, camel_phase)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                        provision_status=VALUES(provision_status),
                        updated_at=CURRENT_TIMESTAMP""",
                    (
                        record.imsi, svc.get("serviceCode"), svc.get("serviceName"),
                        svc.get("provisionStatus", "provisioned"),
                        svc.get("activationCode"), svc.get("deactivationCode"),
                        svc.get("interrogationCode"), svc.get("registrationCode"),
                        svc.get("erasureCode"), svc.get("forwardingNumber"),
                        svc.get("forwardingCondition", "unconditional"),
                        svc.get("noReplyTimer", 20),
                        svc.get("clipProvisioned", True),
                        svc.get("clirProvisioned", True),
                        svc.get("ussdEnabled", True),
                        svc.get("camelPhase", 3),
                    ),
                )
                cur_e.execute(
                    """INSERT INTO tbl_eps_supplementary_service
                       (imsi, service_code, service_name, provision_status,
                        activation_code, deactivation_code, forwarding_number,
                        forwarding_condition, clip_provisioned, clir_provisioned,
                        ussd_enabled, camel_phase)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                        provision_status=VALUES(provision_status),
                        updated_at=CURRENT_TIMESTAMP""",
                    (
                        record.imsi, svc.get("serviceCode"), svc.get("serviceName"),
                        svc.get("provisionStatus", "provisioned"),
                        svc.get("activationCode"), svc.get("deactivationCode"),
                        svc.get("forwardingNumber"),
                        svc.get("forwardingCondition", "unconditional"),
                        svc.get("clipProvisioned", True),
                        svc.get("clirProvisioned", True),
                        svc.get("ussdEnabled", True),
                        svc.get("camelPhase", 3),
                    ),
                )
            conn_hssdb.commit()
            conn_eps.commit()
            result["views"]["supplementaryServices"] = "provisioned"

        # --- 8. Roaming profiles ---
        if record.roamingProfiles:
            for rp in record.roamingProfiles:
                cur_h.execute(
                    """INSERT INTO tbl_roaming_profile
                       (imsi, visited_plmn, roaming_allowed, rat_allowed,
                        odb_roaming, odb_outgoing, odb_incoming, odb_premium)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                        roaming_allowed=VALUES(roaming_allowed),
                        updated_at=CURRENT_TIMESTAMP""",
                    (
                        record.imsi, rp.get("visitedPlmn", "00101"),
                        rp.get("roamingAllowed", True),
                        json.dumps(rp.get("ratAllowed", {"nr": True, "eutran": True, "utran": True, "geran": True})),
                        rp.get("odbRoaming", False), rp.get("odbOutgoing", False),
                        rp.get("odbIncoming", False), rp.get("odbPremium", False),
                    ),
                )
                cur_e.execute(
                    """INSERT INTO tbl_eps_roaming_profile
                       (imsi, visited_plmn, roaming_allowed, rat_allowed,
                        odb_roaming, odb_outgoing, odb_incoming, odb_premium)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                        roaming_allowed=VALUES(roaming_allowed),
                        updated_at=CURRENT_TIMESTAMP""",
                    (
                        record.imsi, rp.get("visitedPlmn", "00101"),
                        rp.get("roamingAllowed", True),
                        json.dumps(rp.get("ratAllowed", {"nr": True, "eutran": True, "utran": True, "geran": True})),
                        rp.get("odbRoaming", False), rp.get("odbOutgoing", False),
                        rp.get("odbIncoming", False), rp.get("odbPremium", False),
                    ),
                )
            conn_hssdb.commit()
            conn_eps.commit()
            result["views"]["roamingProfiles"] = "provisioned"

        # --- 9. Cross-unit sync: notify HSS via Nhss (if HSS owns auth) ---
        if sub_auth_option == 1 and record.k and opc:
            # Option 1: HSS computes vectors. UDM tells HSS via Nhss.
            # Generate an initial AV in HSS to establish SQN
            try:
                status, resp = sync_generate_av(record.imsi, "5G_AKA", "")
                result["views"]["nhssAuth"] = f"sync_status_{status}"
            except Exception as ex:
                result["errors"].append(f"Nhss auth sync: {str(ex)}")

        # Notify HSS of IMEI/PEI if present
        if record.msisdn:
            try:
                sync_update_imei(record.imsi, imei=None, imei_sv=None)
            except Exception:
                pass

        # --- 10. Sync audit log ---
        try:
            cur_h.execute(
                """INSERT INTO tbl_sync_audit
                   (imsi, direction, operation, payload, status)
                   VALUES (%s,'udm_to_hss','provision',%s,'acknowledged')""",
                (record.imsi, json.dumps({
                    "mode": mode,
                    "authOption": sub_auth_option,
                    "views": list(result["views"].keys()),
                })),
            )
            conn_hssdb.commit()
        except Exception:
            pass

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))
        try:
            conn_hssdb.rollback()
            conn_eps.rollback()
        except Exception:
            pass
    finally:
        conn_hssdb.close()
        conn_eps.close()

    return result


# ============================================================================
# Batch upload: CSV or JSON
# ============================================================================
def parse_batch_file(content: bytes, filename: str) -> List[SimCardRecord]:
    """Parse uploaded batch file (CSV or JSON) into SimCardRecord list."""
    records = []

    if filename.lower().endswith(".json"):
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict):
            data = [data]
        for item in data:
            records.append(SimCardRecord(**item))

    elif filename.lower().endswith(".csv"):
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            # Parse JSON fields
            def jf(key):
                val = row.get(key)
                if val:
                    try:
                        return json.loads(val)
                    except Exception:
                        return val
                return None

            records.append(SimCardRecord(
                iccid=row.get("iccid", ""),
                imsi=row.get("imsi", ""),
                msisdn=row.get("msisdn") or None,
                ki=row.get("ki") or None,
                k=row.get("k") or None,
                op=row.get("op") or None,
                opc=row.get("opc") or None,
                sqn=int(row.get("sqn", "0")),
                amf=row.get("amf", "8000"),
                networkAccessMode=int(row.get("networkAccessMode", "2")),
                subscriberStatus=int(row.get("subscriberStatus", "0")),
                roamingRestricted=row.get("roamingRestricted", "false").lower() == "true",
                apnProfiles=jf("apnProfiles"),
                nssai=jf("nssai"),
                dnnConfigs=jf("dnnConfigs"),
                supplementaryServices=jf("supplementaryServices"),
                roamingProfiles=jf("roamingProfiles"),
                camelProfiles=jf("camelProfiles"),
                imsSubscription=jf("imsSubscription"),
                batchId=row.get("batchId") or None,
                mvnoMcc=row.get("mvnoMcc") or None,
                mvnoMnc=row.get("mvnoMnc") or None,
                suciCalcInfo=jf("suciCalcInfo"),
                n5gcAllowed=row.get("n5gcAllowed", "false").lower() == "true",
                pniNpnAllowed=row.get("pniNpnAllowed", "false").lower() == "true",
            ))
    else:
        raise ValueError("Unsupported file format. Use .csv or .json")

    return records


def import_batch(records: List[SimCardRecord], batch_id: str) -> Dict[str, Any]:
    """Import a batch of SIM cards. Returns per-record results + summary."""
    results = []
    total = len(records)
    successful = 0
    failed = 0

    for rec in records:
        try:
            result = provision_sim_card(rec, batch_id)
            results.append(result)
            if result["status"] == "success":
                successful += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            results.append({
                "imsi": getattr(rec, 'imsi', 'unknown'),
                "status": "error",
                "views": {},
                "errors": [str(e)],
            })

    return {
        "batchId": batch_id,
        "status": "completed" if failed == 0 else ("partial" if successful > 0 else "failed"),
        "totalRecords": total,
        "successfulRecords": successful,
        "failedRecords": failed,
        "records": results,
    }


# ============================================================================
# Bidirectional sync: HSS -> UDM updates (called by HSS Nhss server)
# ============================================================================
def apply_hss_imei_update(imsi: str, imei: Optional[str], imei_sv: Optional[str]) -> Dict[str, Any]:
    """HSS notifies UDM of IMEI/PEI change (Nhss_UECM imei-update reverse).
    
    UDM updates tbl_subscriber and propagates to EPS-UDR.
    """
    result = {"imsi": imsi, "status": "success", "errors": []}

    conn_h = get_hssdb()
    conn_e = get_eps_udr()
    try:
        cur_h = conn_h.cursor()
        cur_e = conn_e.cursor()

        cur_h.execute(
            "UPDATE tbl_subscriber SET imei=%s, imei_sv=%s, updated_at=CURRENT_TIMESTAMP WHERE imsi=%s",
            (imei, imei_sv, imsi),
        )
        conn_h.commit()

        cur_e.execute(
            "UPDATE tbl_eps_subscriber SET imei=%s, imei_sv=%s, updated_at=CURRENT_TIMESTAMP WHERE imsi=%s",
            (imei, imei_sv, imsi),
        )
        conn_e.commit()

        result["views"] = {"subscriber": "updated", "epsUdr": "updated"}
    except Exception as e:
        result["status"] = "error"
        result["errors"] = [str(e)]
        try:
            conn_h.rollback()
            conn_e.rollback()
        except Exception:
            pass
    finally:
        conn_h.close()
        conn_e.close()

    return result


def apply_hss_roaming_update(imsi: str, plmn_id: str) -> Dict[str, Any]:
    """HSS notifies UDM of roaming status change."""
    result = {"imsi": imsi, "status": "success", "errors": []}

    conn_h = get_hssdb()
    try:
        cur_h = conn_h.cursor()
        cur_h.execute(
            "UPDATE tbl_subscriber SET roaming_restricted=1, updated_at=CURRENT_TIMESTAMP WHERE imsi=%s",
            (imsi,),
        )
        conn_h.commit()
        result["views"] = {"subscriber": "updated"}
    except Exception as e:
        result["status"] = "error"
        result["errors"] = [str(e)]
        try:
            conn_h.rollback()
        except Exception:
            pass
    finally:
        conn_h.close()

    return result
