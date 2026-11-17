#!/usr/bin/env python3
"""
CAMEL State Machine (TS 23.078, TS 29.078, TS 29.002)

Implements:
- CAMEL Phases 1-4
- OCSI (Originating CAMEL Subscription Information) triggers
- TCSI (Terminating CAMEL Subscription Information) triggers
- CAP operations: InitialDP, Connect, Continue, ReleaseCall, ApplyCharging, etc.
- gsmSCF interaction for call control decisions
- TDP (Trigger Detection Points): Collected Info, Analysed Info, Route Select Failure, etc.
- CSI (CAMEL Subscription Info) for PS, CS, SS, Mobility, LCS domains
"""

import asyncio
import logging
import os
import secrets
import json
import mysql.connector
from typing import Optional, Dict, List, Tuple, Any
from enum import IntEnum

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger("camel-engine")

# ============================================================================
# CAMEL Constants (TS 23.078, TS 29.078)
# ============================================================================

# CAMEL Phases
CAMEL_PHASE_1 = 1
CAMEL_PHASE_2 = 2
CAMEL_PHASE_3 = 3
CAMEL_PHASE_4 = 4

# Trigger Detection Points (TDP) - TS 23.078
TDP_COLLECTED_INFO = 1       # Collected Info
TDP_ANALYSED_INFO = 2        # Analysed Info
TDP_ROUTE_SELECT_FAILURE = 3 # Route Select Failure
TDP_BUSY = 4                 # Busy
TDP_NO_ANSWER = 5            # No Answer
TDP_ANSWER = 6               # Answer
TDP_DISCONNECT = 7           # Disconnect
TDP_MID_CALL = 8             # Mid Call
TDP_RELEASE = 9              # Release
TDP_REQUEST_REPORT_BCSM_EVENT = 10
TDP_OTHER_PARTY_BUSY = 11
TDP_OTHER_PARTY_NO_ANSWER = 12
TDP_OTHER_PARTY_ANSWER = 13
TDP_DP_CONNECT = 14
TDP_DP_DISCONNECT_LEG = 15
TDP_DP_MID_CALL = 16
TDP_DP_DISCONNECT = 17
TDP_DP_RELEASE = 18
TDP_DP_REQUEST_REPORT_BCSM_EVENT = 19
TDP_DP_OTHER_PARTY_BUSY = 20
TDP_DP_OTHER_PARTY_NO_ANSWER = 21
TDP_DP_OTHER_PARTY_ANSWER = 22

# CAP Operation Codes (TS 29.078)
CAP_OP_INITIAL_DP = 1
CAP_OP_CONNECT = 2
CAP_OP_CONTINUE = 3
CAP_OP_RELEASE_CALL = 4
CAP_OP_APPLY_CHARGING = 5
CAP_OP_APPLY_CHARGING_REPORT = 6
CAP_OP_EVENT_REPORT_BCSM = 7
CAP_OP_REQUEST_REPORT_BCSM_EVENT = 8
CAP_OP_PLAY_ANNOUNCEMENT = 9
CAP_OP_SEND_CHARGING_INFO = 10
CAP_OP_DP = 11
CAP_OP_DISCONNECT_FWD_CONNECTION = 12
CAP_OP_CONNECT_TO_RESOURCE = 13
CAP_OP_CONTINUE_WITH_ARGUMENT = 14
CAP_OP_FORWARD_CALLING_INFO = 15
CAP_OP_REQUEST_REPORT_BCSM_EVENT_2 = 16

# Call Control Results
CC_CONTINUE = 0
CC_RELEASE_CALL = 1
CC_ROUTE_TO_SCF = 2
CC_APPLY_CHARGING = 3

# Call Leg Types
LEG_ORIGINATING = "originating"
LEG_TERMINATING = "terminating"

# ============================================================================
# CAMEL Configuration
# ============================================================================

class CamelConfig:
    def __init__(self):
        self.smf_host = os.getenv("CAMEL_SMF_HOST", "smf.core.local")
        self.smf_port = int(os.getenv("CAMEL_SMF_PORT", "7778"))
        self.gsm_scf_address = os.getenv("CAMEL_GSM_SCF_ADDRESS", "scf.core.local")
        self.default_phase = int(os.getenv("CAMEL_DEFAULT_PHASE", "3"))
        self.db_config = {
            "host": os.getenv("DB_HOST", "hssdb"),
            "port": int(os.getenv("DB_PORT", "3306")),
            "user": os.getenv("DB_USER", "hss"),
            "password": os.getenv("DB_PASSWORD", "hss123"),
            "database": os.getenv("DB_NAME", "hssdb"),
        }


camel_config = CamelConfig()


def get_db():
    return mysql.connector.connect(**camel_config.db_config)


# ============================================================================
# CAMEL State Machine
# ============================================================================

class CamelState(IntEnum):
    IDLE = 0
    INITIAL_DP_RECEIVED = 1
    WAITING_SCF_RESPONSE = 2
    PLAYING_ANNOUNCEMENT = 3
    WAITING_DIGITS = 4
    CONNECTING = 5
    ACTIVE = 6
    RELEASING = 7
    TERMINATED = 8


class CamelLeg:
    """Represents a call leg in the CAMEL state machine."""
    
    def __init__(self, leg_id: str, imsi: str, msisdn: str, leg_type: str):
        self.leg_id = leg_id
        self.imsi = imsi
        self.msisdn = msisdn
        self.leg_type = leg_type  # originating or terminating
        self.state = CamelState.IDLE
        self.camel_phase = 3
        self.service_key = 0
        self.tdp_list = []
        self.current_tdp = None
        self.gsm_scf_address = ""
        self.call_control_result = CC_CONTINUE
        self.digits_collected = ""
        self.announcement_id = None
        self.charging_applied = False
        self.metadata = {}
        self.created_at = None
    
    def to_dict(self) -> Dict:
        return {
            "leg_id": self.leg_id,
            "imsi": self.imsi,
            "msisdn": self.msisdn,
            "leg_type": self.leg_type,
            "state": self.state.name,
            "camel_phase": self.camel_phase,
            "service_key": self.service_key,
            "tdp_list": self.tdp_list,
            "current_tdp": self.current_tdp,
            "gsm_scf_address": self.gsm_scf_address,
            "call_control_result": self.call_control_result,
            "digits_collected": self.digits_collected,
            "announcement_id": self.announcement_id,
            "charging_applied": self.charging_applied,
        }


class CamelEngine:
    """CAMEL state machine engine."""
    
    def __init__(self):
        self.legs: Dict[str, CamelLeg] = {}
        self.redis = None
    
    def get_redis(self):
        import redis
        return redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", "change-me"),
            decode_responses=True,
        )
    
    def load_camel_profile(self, imsi: str) -> Optional[Dict]:
        """Load CAMEL service profile for subscriber."""
        conn = get_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM tbl_camel_service_profile WHERE imsi=%s", (imsi,))
            rows = cur.fetchall()
            return rows
        finally:
            conn.close()
    
    def get_subscriber(self, imsi: str) -> Optional[Dict]:
        conn = get_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM tbl_subscriber WHERE imsi=%s", (imsi,))
            return cur.fetchone()
        finally:
            conn.close()
    
    def create_leg(self, leg_id: str, imsi: str, msisdn: str, leg_type: str) -> CamelLeg:
        """Create a new call leg."""
        leg = CamelLeg(leg_id, imsi, msisdn, leg_type)
        
        # Load CAMEL profile
        profiles = self.load_camel_profile(imsi)
        if profiles:
            profile = profiles[0]  # Use first profile
            leg.camel_phase = profile.get("camel_phase", 3)
            leg.service_key = profile.get("service_key", 0)
            leg.gsm_scf_address = profile.get("gsm_scf_address", "")
            if profile.get("tdp_list"):
                try:
                    leg.tdp_list = json.loads(profile["tdp_list"])
                except:
                    leg.tdp_list = []
            leg.metadata = {
                "csi_psi": profile.get("csi_psi"),
                "csi_csi": profile.get("csi_csi"),
                "csi_ssi": profile.get("csi_ssi"),
                "csi_msi": profile.get("csi_msi"),
                "csi_lsi": profile.get("csi_lsi"),
                "csi_v2x": profile.get("csi_v2x"),
                "csi_redcap": profile.get("csi_redcap"),
            }
        
        self.legs[leg_id] = leg
        
        # Persist to Redis
        r = self.get_redis()
        r.set(f"camel:leg:{leg_id}", json.dumps(leg.to_dict()))
        
        return leg
    
    def get_leg(self, leg_id: str) -> Optional[CamelLeg]:
        """Get call leg by ID."""
        if leg_id in self.legs:
            return self.legs[leg_id]
        
        # Try Redis
        r = self.get_redis()
        data = r.get(f"camel:leg:{leg_id}")
        if data:
            d = json.loads(data)
            leg = CamelLeg(d["leg_id"], d["imsi"], d["msisdn"], d["leg_type"])
            leg.state = CamelState[d["state"]]
            leg.camel_phase = d["camel_phase"]
            leg.service_key = d["service_key"]
            leg.tdp_list = d["tdp_list"]
            leg.current_tdp = d["current_tdp"]
            leg.gsm_scf_address = d["gsm_scf_address"]
            leg.call_control_result = d["call_control_result"]
            leg.digits_collected = d["digits_collected"]
            leg.announcement_id = d["announcement_id"]
            leg.charging_applied = d["charging_applied"]
            self.legs[leg_id] = leg
            return leg
        
        return None
    
    def save_leg(self, leg: CamelLeg):
        """Persist leg state to Redis."""
        r = self.get_redis()
        r.set(f"camel:leg:{leg.leg_id}", json.dumps(leg.to_dict()))
    
    def process_initial_dp(self, leg_id: str, imsi: str, msisdn: str, 
                          called_party: str, calling_party: str,
                          service_key: int, tdp: int,
                          leg_type: str = LEG_ORIGINATING) -> Dict:
        """Process InitialDP trigger from MSC/SGSN."""
        leg = self.get_leg(leg_id)
        if not leg:
            leg = self.create_leg(leg_id, imsi, msisdn, leg_type)
        
        leg.state = CamelState.INITIAL_DP_RECEIVED
        leg.current_tdp = tdp
        leg.service_key = service_key
        
        logger.info(f"CAMEL InitialDP: leg={leg_id} imsi={imsi} tdp={tdp} phase={leg.camel_phase}")
        
        # Check if this TDP is in the subscriber's TDP list
        tdp_matched = False
        for t in leg.tdp_list:
            if t.get("tdp") == tdp or t.get("tdp") == f"tdp_{tdp}":
                tdp_matched = True
                break
        
        if not tdp_matched and leg.camel_phase >= 1:
            # Default: continue call without SCF intervention
            leg.state = CamelState.ACTIVE
            self.save_leg(leg)
            return {
                "result": CC_CONTINUE,
                "action": "continue_call",
                "leg_id": leg_id,
            }
        
        # Query gsmSCF for call control decision
        scf_decision = self.query_gsm_scf(leg, tdp, called_party, calling_party)
        
        if scf_decision["action"] == "continue":
            leg.state = CamelState.ACTIVE
            leg.call_control_result = CC_CONTINUE
            self.save_leg(leg)
            return {
                "result": CC_CONTINUE,
                "action": "continue_call",
                "leg_id": leg_id,
            }
        elif scf_decision["action"] == "release":
            leg.state = CamelState.RELEASING
            leg.call_control_result = CC_RELEASE_CALL
            self.save_leg(leg)
            return {
                "result": CC_RELEASE_CALL,
                "action": "release_call",
                "leg_id": leg_id,
            }
        elif scf_decision["action"] == "route_to_scf":
            leg.state = CamelState.WAITING_SCF_RESPONSE
            leg.call_control_result = CC_ROUTE_TO_SCF
            self.save_leg(leg)
            return {
                "result": CC_ROUTE_TO_SCF,
                "action": "route_to_scf",
                "leg_id": leg_id,
                "gsm_scf_address": leg.gsm_scf_address,
            }
        elif scf_decision["action"] == "play_announcement":
            leg.state = CamelState.PLAYING_ANNOUNCEMENT
            leg.announcement_id = scf_decision.get("announcement_id")
            self.save_leg(leg)
            return {
                "result": CC_CONTINUE,
                "action": "play_announcement",
                "leg_id": leg_id,
                "announcement_id": leg.announcement_id,
            }
        elif scf_decision["action"] == "collect_digits":
            leg.state = CamelState.WAITING_DIGITS
            self.save_leg(leg)
            return {
                "result": CC_CONTINUE,
                "action": "collect_digits",
                "leg_id": leg_id,
            }
        
        # Default: continue
        leg.state = CamelState.ACTIVE
        self.save_leg(leg)
        return {
            "result": CC_CONTINUE,
            "action": "continue_call",
            "leg_id": leg_id,
        }
    
    def query_gsm_scf(self, leg: CamelLeg, tdp: int, called_party: str, calling_party: str) -> Dict:
        """Query gsmSCF for call control decision."""
        # In production, this would send a CAP message to the gsmSCF
        # For now, return a default decision based on TDP
        
        decision = {"action": "continue"}
        
        # Check OCSI/TCSI triggers from profile
        csi = leg.metadata.get("csi_csi") if leg.leg_type == LEG_ORIGINATING else leg.metadata.get("csi_psi")
        
        if csi:
            try:
                csi_data = json.loads(csi) if isinstance(csi, str) else csi
                triggers = csi_data.get("triggers", [])
                for trigger in triggers:
                    if trigger.get("tdp") == tdp:
                        action = trigger.get("action", "continue")
                        decision["action"] = action
                        if action == "route_to_scf":
                            decision["gsm_scf_address"] = leg.gsm_scf_address or camel_config.gsm_scf_address
                        if action == "play_announcement":
                            decision["announcement_id"] = trigger.get("announcement_id", 1)
                        break
            except:
                pass
        
        return decision
    
    def process_event_report(self, leg_id: str, event_type: str, event_info: Dict) -> Dict:
        """Process Event Report BSM from MSC/SGSN."""
        leg = self.get_leg(leg_id)
        if not leg:
            return {"result": CC_CONTINUE, "action": "continue_call"}
        
        logger.info(f"CAMEL Event Report: leg={leg_id} event={event_type}")
        
        # Map event to TDP
        tdp_map = {
            "collected_info": TDP_COLLECTED_INFO,
            "analysed_info": TDP_ANALYSED_INFO,
            "route_select_failure": TDP_ROUTE_SELECT_FAILURE,
            "busy": TDP_BUSY,
            "no_answer": TDP_NO_ANSWER,
            "answer": TDP_ANSWER,
            "disconnect": TDP_DISCONNECT,
            "mid_call": TDP_MID_CALL,
            "release": TDP_RELEASE,
        }
        
        tdp = tdp_map.get(event_type, 0)
        leg.current_tdp = tdp
        
        # Query gsmSCF for event handling
        scf_decision = self.query_gsm_scf(leg, tdp, event_info.get("called_party", ""), event_info.get("calling_party", ""))
        
        if scf_decision["action"] == "continue":
            leg.state = CamelState.ACTIVE
        elif scf_decision["action"] == "release":
            leg.state = CamelState.RELEASING
        elif scf_decision["action"] == "play_announcement":
            leg.state = CamelState.PLAYING_ANNOUNCEMENT
            leg.announcement_id = scf_decision.get("announcement_id")
        
        self.save_leg(leg)
        
        return {
            "result": leg.call_control_result,
            "action": scf_decision["action"],
            "leg_id": leg_id,
        }
    
    def process_connect(self, leg_id: str) -> Dict:
        """Process Connect trigger."""
        leg = self.get_leg(leg_id)
        if not leg:
            return {"result": CC_CONTINUE, "action": "continue_call"}
        
        leg.state = CamelState.ACTIVE
        self.save_leg(leg)
        
        return {
            "result": CC_CONTINUE,
            "action": "continue_call",
            "leg_id": leg_id,
        }
    
    def process_release(self, leg_id: str) -> Dict:
        """Process Release trigger."""
        leg = self.get_leg(leg_id)
        if not leg:
            return {"result": CC_CONTINUE, "action": "continue_call"}
        
        leg.state = CamelState.TERMINATED
        self.save_leg(leg)
        
        return {
            "result": CC_CONTINUE,
            "action": "call_terminated",
            "leg_id": leg_id,
        }
    
    def get_leg_status(self, leg_id: str) -> Optional[Dict]:
        """Get current leg status."""
        leg = self.get_leg(leg_id)
        if not leg:
            return None
        return leg.to_dict()


# Global CAMEL engine instance
camel_engine = CamelEngine()


# ============================================================================
# CAMEL CAP Operations over MAP/TCAP
# ============================================================================

def encode_cap_initial_dp(leg_id: str, imsi: str, msisdn: str,
                         called_party: str, calling_party: str,
                         service_key: int, tdp: int) -> bytes:
    """Encode CAP InitialDP operation."""
    # CAP Invoke Component
    invoke = bytes([0x02, 0x01, leg_id.encode()[:1] and len(leg_id.encode()) or 1])  # Simplified
    invoke += leg_id.encode()
    
    # Operation code
    op_code = bytes([0x02, 0x01, CAP_OP_INITIAL_DP])
    
    # Parameters (simplified BER encoding)
    params = b""
    params += bytes([0x04, len(imsi)]) + imsi.encode()  # IMSI
    params += bytes([0x04, len(msisdn)]) + msisdn.encode()  # MSISDN
    params += bytes([0x04, len(called_party)]) + called_party.encode()  # Called party
    params += bytes([0x04, len(calling_party)]) + calling_party.encode()  # Calling party
    params += bytes([0x02, 0x01, service_key & 0xFF])  # Service key
    params += bytes([0x02, 0x01, tdp])  # TDP
    
    # Wrap in sequence
    param_seq = bytes([0x30, len(params)]) + params
    
    # Component
    component = bytes([0x62])  # Return result tag (simplified - using invoke)
    component += bytes([len(invoke) + len(op_code) + len(param_seq)])
    component += invoke + op_code + param_seq
    
    # TCAP wrapper
    tcap = bytes([TCAP_MSG_TYPE_QUERY])
    tcap += bytes([len(component)])
    tcap += component
    
    outer = bytes([0x60])
    outer += bytes([len(tcap)])
    outer += tcap
    
    return outer


def decode_cap_initial_dp(data: bytes) -> Dict:
    """Decode CAP InitialDP from TCAP message."""
    # Simplified decoder
    return {
        "imsi": "",
        "msisdn": "",
        "called_party": "",
        "calling_party": "",
        "service_key": 0,
        "tdp": 0,
    }


# ============================================================================
# CAMEL over MAP/SCCP Integration
# ============================================================================

def handle_camel_initial_dp(imsi: str, msisdn: str, called_party: str,
                           calling_party: str, service_key: int, tdp: int,
                           leg_type: str = LEG_ORIGINATING) -> Dict:
    """Handle CAP InitialDP from MSC/SGSN via MAP/SCCP."""
    leg_id = f"camel-{secrets.token_hex(8)}"
    return camel_engine.process_initial_dp(
        leg_id, imsi, msisdn, called_party, calling_party,
        service_key, tdp, leg_type
    )


def handle_camel_event_report(leg_id: str, event_type: str, event_info: Dict) -> Dict:
    """Handle Event Report BSM from MSC/SGSN."""
    return camel_engine.process_event_report(leg_id, event_type, event_info)


def handle_camel_connect(leg_id: str) -> Dict:
    """Handle Connect trigger."""
    return camel_engine.process_connect(leg_id)


def handle_camel_release(leg_id: str) -> Dict:
    """Handle Release trigger."""
    return camel_engine.process_release(leg_id)


def get_camel_leg_status(leg_id: str) -> Optional[Dict]:
    """Get CAMEL leg status."""
    return camel_engine.get_leg_status(leg_id)


# ============================================================================
# CAMEL Phase Capabilities
# ============================================================================

CAMEL_PHASE_CAPABILITIES = {
    CAMEL_PHASE_1: {
        "tdps": [TDP_COLLECTED_INFO, TDP_ANALYSED_INFO, TDP_ROUTE_SELECT_FAILURE, TDP_BUSY, TDP_NO_ANSWER, TDP_ANSWER, TDP_DISCONNECT, TDP_RELEASE],
        "operations": [CAP_OP_INITIAL_DP, CAP_OP_CONNECT, CAP_OP_CONTINUE, CAP_OP_RELEASE_CALL, CAP_OP_APPLY_CHARGING],
        "features": ["basic_call_control", "charging"],
    },
    CAMEL_PHASE_2: {
        "tdps": [TDP_COLLECTED_INFO, TDP_ANALYSED_INFO, TDP_ROUTE_SELECT_FAILURE, TDP_BUSY, TDP_NO_ANSWER, TDP_ANSWER, TDP_DISCONNECT, TDP_RELEASE, TDP_MID_CALL, TDP_REQUEST_REPORT_BCSM_EVENT],
        "operations": [CAP_OP_INITIAL_DP, CAP_OP_CONNECT, CAP_OP_CONTINUE, CAP_OP_RELEASE_CALL, CAP_OP_APPLY_CHARGING, CAP_OP_APPLY_CHARGING_REPORT, CAP_OP_EVENT_REPORT_BCSM, CAP_OP_REQUEST_REPORT_BCSM_EVENT, CAP_OP_PLAY_ANNOUNCEMENT],
        "features": ["basic_call_control", "charging", "announcement", "mid_call"],
    },
    CAMEL_PHASE_3: {
        "tdps": [TDP_COLLECTED_INFO, TDP_ANALYSED_INFO, TDP_ROUTE_SELECT_FAILURE, TDP_BUSY, TDP_NO_ANSWER, TDP_ANSWER, TDP_DISCONNECT, TDP_RELEASE, TDP_MID_CALL, TDP_REQUEST_REPORT_BCSM_EVENT, TDP_OTHER_PARTY_BUSY, TDP_OTHER_PARTY_NO_ANSWER, TDP_OTHER_PARTY_ANSWER, TDP_DP_CONNECT, TDP_DP_DISCONNECT_LEG, TDP_DP_MID_CALL, TDP_DP_DISCONNECT, TDP_DP_RELEASE, TDP_DP_REQUEST_REPORT_BCSM_EVENT, TDP_DP_OTHER_PARTY_BUSY, TDP_DP_OTHER_PARTY_NO_ANSWER, TDP_DP_OTHER_PARTY_ANSWER],
        "operations": [CAP_OP_INITIAL_DP, CAP_OP_CONNECT, CAP_OP_CONTINUE, CAP_OP_RELEASE_CALL, CAP_OP_APPLY_CHARGING, CAP_OP_APPLY_CHARGING_REPORT, CAP_OP_EVENT_REPORT_BCSM, CAP_OP_REQUEST_REPORT_BCSM_EVENT, CAP_OP_PLAY_ANNOUNCEMENT, CAP_OP_SEND_CHARGING_INFO, CAP_OP_DP, CAP_OP_DISCONNECT_FWD_CONNECTION, CAP_OP_CONNECT_TO_RESOURCE, CAP_OP_CONTINUE_WITH_ARGUMENT, CAP_OP_FORWARD_CALLING_INFO],
        "features": ["full_call_control", "charging", "announcement", "mid_call", "other_party_events", "dp_triggers", "resource_connection"],
    },
    CAMEL_PHASE_4: {
        "tdps": [TDP_COLLECTED_INFO, TDP_ANALYSED_INFO, TDP_ROUTE_SELECT_FAILURE, TDP_BUSY, TDP_NO_ANSWER, TDP_ANSWER, TDP_DISCONNECT, TDP_RELEASE, TDP_MID_CALL, TDP_REQUEST_REPORT_BCSM_EVENT, TDP_OTHER_PARTY_BUSY, TDP_OTHER_PARTY_NO_ANSWER, TDP_OTHER_PARTY_ANSWER, TDP_DP_CONNECT, TDP_DP_DISCONNECT_LEG, TDP_DP_MID_CALL, TDP_DP_DISCONNECT, TDP_DP_RELEASE, TDP_DP_REQUEST_REPORT_BCSM_EVENT, TDP_DP_OTHER_PARTY_BUSY, TDP_DP_OTHER_PARTY_NO_ANSWER, TDP_DP_OTHER_PARTY_ANSWER],
        "operations": [CAP_OP_INITIAL_DP, CAP_OP_CONNECT, CAP_OP_CONTINUE, CAP_OP_RELEASE_CALL, CAP_OP_APPLY_CHARGING, CAP_OP_APPLY_CHARGING_REPORT, CAP_OP_EVENT_REPORT_BCSM, CAP_OP_REQUEST_REPORT_BCSM_EVENT, CAP_OP_PLAY_ANNOUNCEMENT, CAP_OP_SEND_CHARGING_INFO, CAP_OP_DP, CAP_OP_DISCONNECT_FWD_CONNECTION, CAP_OP_CONNECT_TO_RESOURCE, CAP_OP_CONTINUE_WITH_ARGUMENT, CAP_OP_FORWARD_CALLING_INFO],
        "features": ["full_call_control", "charging", "announcement", "mid_call", "other_party_events", "dp_triggers", "resource_connection", "gprs_support", "ip_sm_gw_support"],
    },
}


def get_camel_capabilities(phase: int) -> Dict:
    """Get CAMEL phase capabilities."""
    return CAMEL_PHASE_CAPABILITIES.get(phase, CAMEL_PHASE_CAPABILITIES[CAMEL_PHASE_3])