#!/usr/bin/env python3
"""
SMF - Session Management Function
Implements TS 29.502 Nsmf_PDUSession (N11 interface)
PFCP Client (TS 29.244) for N4 interface
GTPv2-C Server (TS 29.274) for S5/S8 PGW-C interface
UE IP allocation, UPF selection, DHCPv4/v6, N10/N40/NRF clients
"""

import json
import logging
import os
import signal
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
import yaml

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("smf")

CONFIG_PATH = os.getenv("SMF_CONFIG", "/app/config/smf.yaml")
UPF_TOPOLOGY_PATH = os.getenv("SMF_UPF_TOPOLOGY", "/app/config/upf_topology.json")


class RequestType(Enum):
    INITIAL_REQUEST = "INITIAL_REQUEST"
    EXISTING_PDU_SESSION = "EXISTING_PDU_SESSION"
    EMERGENCY_REQUEST = "EMERGENCY_REQUEST"
    EXISTING_EMERGENCY_PDU_SESSION = "EXISTING_EMERGENCY_PDU_SESSION"


class PduSessionType(Enum):
    IPV4 = "IPv4"
    IPV6 = "IPv6"
    IPV4V6 = "IPv4v6"
    ETHERNET = "Ethernet"
    UNSTRUCTURED = "Unstructured"


class SscMode(Enum):
    SSC_MODE_1 = 1
    SSC_MODE_2 = 2
    SSC_MODE_3 = 3


class AccessType(Enum):
    ACCESS_3GPP = "3GPP_ACCESS"
    ACCESS_NON_3GPP = "NON_3GPP_ACCESS"


class RatType(Enum):
    NR = "NR"
    EUTRA = "EUTRA"
    WLAN = "WLAN"
    VIRTUAL = "VIRTUAL"
    NB_IOT = "NB-IoT"
    WIRELINE = "WIRELINE"
    WIRELINE_CABLE = "WIRELINE_CABLE"
    WIRELINE_BF = "WIRELINE_BF"
    LTE_M = "LTE-M"
    NR_U = "NR-U"


class UpCnxState(Enum):
    ACTIVATING = "ACTIVATING"
    ACTIVE = "ACTIVE"
    DEACTIVATING = "DEACTIVATING"
    INACTIVE = "INACTIVE"


class Cause(Enum):
    SUCCESS = "SUCCESS"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    DNN_NOT_SUPPORTED = "DNN_NOT_SUPPORTED"
    S_NSSAI_NOT_SUPPORTED = "S_NSSAI_NOT_SUPPORTED"
    PDU_SESSION_NOT_FOUND = "PDU_SESSION_NOT_FOUND"
    INSUFFICIENT_RESOURCES = "INSUFFICIENT_RESOURCES"
    UE_NOT_AUTHORIZED = "UE_NOT_AUTHORIZED"
    NO_NETWORK_SLICES_AVAILABLE = "NO_NETWORK_SLICES_AVAILABLE"
    UNSPECIFIED = "UNSPECIFIED"


@dataclass
class ARP:
    priority_level: int
    preempt_cap: str = "NOT_PREEMPT"
    preempt_vuln: str = "PREEMPTABLE"


@dataclass
class QosFlowProfile:
    five_qi: int
    arp: ARP
    priority_level: Optional[int] = None
    aver_window: Optional[int] = None
    max_data_burst_vol: Optional[int] = None
    gbr_ul: Optional[str] = None
    gbr_dl: Optional[str] = None
    maxbr_ul: Optional[str] = None
    maxbr_dl: Optional[str] = None
    reflective_qos: bool = False
    qnc: bool = False


@dataclass
class QosFlowItem:
    qfi: int
    qos_flow_profile: QosFlowProfile
    qos_flow_setup_item: Optional[Dict] = None


@dataclass
class TunnelInfo:
    ipv4_addr: Optional[str] = None
    ipv6_addr: Optional[str] = None
    teid: Optional[str] = None
    port_number: Optional[int] = None


@dataclass
class QosFlowTunnel:
    qfi: int
    ul_tunnel: TunnelInfo
    dl_tunnel: Optional[TunnelInfo] = None


@dataclass
class N2SmInfo:
    pdu_session_id: int
    qfi_list: List[int]
    qos_profiles: List[Dict]
    cn_tunnel_info: TunnelInfo
    s_nssai: Dict
    session_ambr: Dict[str, str]
    pdu_session_type: str
    up_security_enforcement: Optional[Dict] = None
    ue_integrity_protection_max_data_rate: Optional[Dict] = None
    rsn: Optional[int] = None
    pdu_session_pair_id: Optional[int] = None


@dataclass
class SmContext:
    sm_context_ref: str
    supi: str
    gpsi: Optional[str]
    pdu_session_id: int
    dnn: str
    s_nssai: Dict
    serving_nf_id: str
    guami: Dict
    request_type: RequestType
    access_type: AccessType
    rat_type: RatType
    ue_location: Optional[Dict]
    ue_time_zone: Optional[str]
    n1_sm_msg: Optional[str]
    sm_context_status_uri: str
    pcf_id: Optional[str]
    same_pcf_selection: bool = False
    pei: Optional[str] = None
    old_pdu_session_id: Optional[int] = None
    ladn_indication: bool = False
    ma_pdu_indication: bool = False
    priority_access: bool = False
    dnn_selection_mode: Optional[str] = None
    trace_requirements: Optional[Dict] = None
    
    # Session state
    pcf_smpolicy_id: Optional[str] = None
    upf_node_id: Optional[str] = None
    upf_ipv4: Optional[str] = None
    upf_n4_port: int = 8805
    upf_n3_ipv4: Optional[str] = None
    upf_n3_port: int = 2152
    cp_f_seid: int = 0
    up_f_seid: int = 0
    upf_teid_allocated: bool = False
    ue_ipv4: Optional[str] = None
    ue_ipv6_prefix: Optional[str] = None
    ue_ipv6_if_id: Optional[str] = None
    pdu_session_type: PduSessionType = PduSessionType.IPV4
    ssc_mode: SscMode = SscMode.SSC_MODE_1
    up_cnx_state: UpCnxState = UpCnxState.ACTIVATING
    qos_flows: List[QosFlowItem] = field(default_factory=list)
    n3_teid: Optional[str] = None
    n3_ipv4: Optional[str] = None
    ebi_list: List[int] = field(default_factory=list)
    eps_bearer_info: List[Dict] = field(default_factory=list)
    eps_interworking: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Charging
    charging_id: Optional[int] = None
    charging_characteristics: Optional[str] = None
    
    # Policy
    session_ambr: Dict[str, str] = field(default_factory=dict)
    default_qos: Optional[QosFlowProfile] = None
    pcc_rules: Dict = field(default_factory=dict)
    
    # PDRs/FARs/QERs/URRs
    pdrs: Dict = field(default_factory=dict)
    fars: Dict = field(default_factory=dict)
    qers: Dict = field(default_factory=dict)
    urrs: Dict = field(default_factory=dict)
    pdr_counter: int = 1
    far_counter: int = 1
    qer_counter: int = 1
    urr_counter: int = 1


class IPPoolManager:
    def __init__(self, pools: List[Dict]):
        self.pools = {}
        for pool in pools:
            self.pools[pool["name"]] = {
                "cidr": pool["cidr"],
                "gateway": pool.get("gateway"),
                "dns_primary": pool.get("dns_primary"),
                "dns_secondary": pool.get("dns_secondary"),
                "allocated": set(),
                "network": self._parse_cidr(pool["cidr"]),
            }
    
    def _parse_cidr(self, cidr: str) -> Tuple[int, int]:
        if ":" in cidr:
            # IPv6 - simplified
            return (0, 0)
        network_str, prefix = cidr.split("/")
        prefix = int(prefix)
        ip_parts = [int(x) for x in network_str.split(".")]
        ip_int = (ip_parts[0] << 24) | (ip_parts[1] << 16) | (ip_parts[2] << 8) | ip_parts[3]
        mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        network = ip_int & mask
        return (network, prefix)
    
    def allocate(self, pool_name: str, requested_ip: Optional[str] = None) -> Optional[str]:
        pool = self.pools.get(pool_name)
        if not pool:
            return None
        
        if requested_ip:
            if self._ip_in_pool(requested_ip, pool):
                if requested_ip not in pool["allocated"]:
                    pool["allocated"].add(requested_ip)
                    return requested_ip
            return None
        
        network, prefix = pool["network"]
        if prefix == 0:  # IPv6
            return "2001:db8::1"
        
        for i in range(1, (1 << (32 - prefix)) - 1):
            ip_int = network | i
            if ip_int in pool["allocated"]:
                continue
            ip_str = ".".join(str((ip_int >> (8 * j)) & 0xFF) for j in [3, 2, 1, 0])
            if ip_str == pool["gateway"]:
                continue
            pool["allocated"].add(ip_int)
            return ip_str
        return None
    
    def release(self, pool_name: str, ip: str):
        pool = self.pools.get(pool_name)
        if pool:
            try:
                ip_parts = [int(x) for x in ip.split(".")]
                ip_int = (ip_parts[0] << 24) | (ip_parts[1] << 16) | (ip_parts[2] << 8) | ip_parts[3]
                pool["allocated"].discard(ip_int)
            except:
                pass
    
    def _ip_in_pool(self, ip: str, pool: Dict) -> bool:
        try:
            ip_parts = [int(x) for x in ip.split(".")]
            ip_int = (ip_parts[0] << 24) | (ip_parts[1] << 16) | (ip_parts[2] << 8) | ip_parts[3]
            network, prefix = pool["network"]
            mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
            return (ip_int & mask) == network
        except:
            return False
    
    def get_pool_info(self, pool_name: str) -> Dict:
        pool = self.pools.get(pool_name)
        if not pool:
            return {}
        return {
            "cidr": pool["cidr"],
            "gateway": pool["gateway"],
            "dns_primary": pool.get("dns_primary"),
            "dns_secondary": pool.get("dns_secondary"),
            "allocated_count": len(pool["allocated"]),
        }


class UPFSelector:
    def __init__(self, topology_file: str):
        with open(topology_file, "r") as f:
            self.topology = json.load(f)
    
    def select_upf(self, dnn: str, s_nssai: Dict, ue_location: Optional[Dict] = None) -> Optional[Dict]:
        candidates = []
        for upf in self.topology.get("upfs", []):
            if dnn not in upf.get("dnn_list", []):
                continue
            if not self._snssai_matches(s_nssai, upf.get("snssai_list", [])):
                continue
            if ue_location and not self._tai_matches(ue_location, upf.get("tai_list", [])):
                continue
            candidates.append(upf)
        
        if not candidates:
            return None
        
        # Select by lowest load ratio
        best = min(candidates, key=lambda u: u.get("current_load", 0) / max(u.get("capacity", 1), 1))
        best["current_load"] = best.get("current_load", 0) + 1
        return best
    
    def _snssai_matches(self, requested: Dict, supported: List[Dict]) -> bool:
        if not requested:
            return True
        sst = requested.get("sst")
        sd = requested.get("sd")
        for snssai in supported:
            if snssai.get("sst") == sst:
                if sd is None or snssai.get("sd") == sd:
                    return True
        return False
    
    def _tai_matches(self, ue_location: Dict, tai_list: List[Dict]) -> bool:
        plmn_id = ue_location.get("plmn_id")
        tac = ue_location.get("tac")
        if not plmn_id or not tac:
            return True
        for tai in tai_list:
            if tai.get("plmn_id") == plmn_id and tai.get("tac") == tac:
                return True
        return False
    
    def release_upf(self, node_id: str):
        for upf in self.topology.get("upfs", []):
            if upf.get("node_id") == node_id:
                upf["current_load"] = max(0, upf.get("current_load", 1) - 1)
                break


class PFCPClient:
    def __init__(self, config: Dict):
        self.config = config
        self.sockets: Dict[str, socket.socket] = {}
        self.associations: Dict[str, Dict] = {}
        self.sequence_numbers: Dict[str, int] = {}
        self.lock = threading.Lock()
    
    def _get_socket(self, upf_ip: str, upf_port: int) -> socket.socket:
        key = f"{upf_ip}:{upf_port}"
        if key not in self.sockets:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            sock.bind(("0.0.0.0", 0))
            self.sockets[key] = sock
        return self.sockets[key]
    
    def _next_sequence(self, upf_ip: str) -> int:
        with self.lock:
            seq = self.sequence_numbers.get(upf_ip, 0) + 1
            self.sequence_numbers[upf_ip] = seq % 0xFFFFFF
            return seq
    
    def _build_header(self, msg_type: int, seid: int, sequence: int, flags: int = 0) -> bytes:
        version = 1
        header = struct.pack("!BBHQ3s", 
            (version << 5) | flags,
            msg_type,
            0,  # length placeholder
            seid,
            sequence.to_bytes(3, "big")
        )
        return header
    
    def _encode_ie(self, ie_type: int, data: bytes) -> bytes:
        return struct.pack("!HH", ie_type, len(data)) + data
    
    def _encode_fteid(self, fteid: Dict) -> bytes:
        # IE 21: F-TEID
        choose = fteid.get("choose", 0)
        v4 = 1 if fteid.get("ipv4") else 0
        v6 = 1 if fteid.get("ipv6") else 0
        interface = fteid.get("interface", 0)
        teid = fteid.get("teid", 0)
        
        data = struct.pack("!BBBBI", (choose << 7) | (v4 << 6) | (v6 << 5) | interface, 0, 0, 0, teid)
        if v4:
            ip_parts = [int(x) for x in fteid["ipv4"].split(".")]
            data += bytes(ip_parts)
        if v6:
            # Simplified IPv6 encoding
            data += bytes(16)
        return self._encode_ie(21, data)
    
    def _encode_pdi(self, pdi: Dict) -> bytes:
        # IE 2: PDI
        data = b""
        if "source_interface" in pdi:
            data += self._encode_ie(20, struct.pack("!B", pdi["source_interface"]))
        if "local_fteid" in pdi:
            data += self._encode_fteid(pdi["local_fteid"])
        if "ue_ipv4" in pdi:
            ip_parts = [int(x) for x in pdi["ue_ipv4"].split(".")]
            data += self._encode_ie(17, bytes(ip_parts))
        if "network_instance" in pdi:
            data += self._encode_ie(22, pdi["network_instance"].encode())
        if "sdf_filter" in pdi:
            # IE 23: SDF Filter - simplified
            filter_data = pdi["sdf_filter"].encode()
            data += self._encode_ie(23, struct.pack("!B", len(filter_data)) + filter_data)
        if "qfi" in pdi:
            data += self._encode_ie(124, struct.pack("!B", pdi["qfi"]))
        if "application_id" in pdi:
            data += self._encode_ie(24, pdi["application_id"].encode())
        return self._encode_ie(2, data)
    
    def _encode_far(self, far: Dict) -> bytes:
        # IE 3: FAR
        data = b""
        data += self._encode_ie(44, struct.pack("!B", far.get("apply_action", 2)))  # FORW
        if "forwarding_params" in far:
            fp = far["forwarding_params"]
            fp_data = b""
            if "destination_interface" in fp:
                fp_data += self._encode_ie(42, struct.pack("!B", fp["destination_interface"]))
            if "network_instance" in fp:
                fp_data += self._encode_ie(22, fp["network_instance"].encode())
            if "outer_header" in fp:
                fp_data += self._encode_fteid(fp["outer_header"])
            if "redirect_info" in fp:
                ri = fp["redirect_info"]
                ri_data = struct.pack("!B", ri.get("type", 0))
                if "addr" in ri:
                    ri_data += ri["addr"].encode()
                fp_data += self._encode_ie(38, ri_data)
            data += self._encode_ie(4, fp_data)
        return self._encode_ie(3, data)
    
    def _encode_qer(self, qer: Dict) -> bytes:
        # IE 7: QER
        data = b""
        data += self._encode_ie(25, struct.pack("!B", qer.get("gate_status", 2)))  # OPEN
        if "mbr" in qer:
            mbr = qer["mbr"]
            data += self._encode_ie(26, struct.pack("!QQ", int(mbr.get("ul", 0)), int(mbr.get("dl", 0))))
        if "gbr" in qer:
            gbr = qer["gbr"]
            data += self._encode_ie(27, struct.pack("!QQ", int(gbr.get("ul", 0)), int(gbr.get("dl", 0))))
        if "qfi" in qer:
            data += self._encode_ie(124, struct.pack("!B", qer["qfi"]))
        if "precedence" in qer:
            data += self._encode_ie(29, struct.pack("!B", qer["precedence"]))
        return self._encode_ie(7, data)
    
    def _encode_urr(self, urr: Dict) -> bytes:
        # IE 6: URR
        data = b""
        data += self._encode_ie(37, struct.pack("!B", urr.get("reporting_triggers", 0)))
        if "volume_threshold" in urr:
            data += self._encode_ie(31, struct.pack("!Q", int(urr["volume_threshold"])))
        if "time_threshold" in urr:
            data += self._encode_ie(32, struct.pack("!Q", int(urr["time_threshold"])))
        if "measurement_method" in urr:
            data += self._encode_ie(1, struct.pack("!B", urr["measurement_method"]))
        return self._encode_ie(6, data)
    
    def session_establishment(self, upf_ip: str, upf_port: int, sm_context: SmContext) -> Tuple[bool, Dict]:
        sock = self._get_socket(upf_ip, upf_port)
        sequence = self._next_sequence(upf_ip)
        
        cp_f_seid = sm_context.cp_f_seid or (int(time.time() * 1000) & 0xFFFFFFFFFFFF)
        sm_context.cp_f_seid = cp_f_seid
        
        # Build Session Establishment Request
        msg = bytearray()
        msg += self._encode_ie(56, struct.pack("!Q", cp_f_seid))  # Node ID
        msg += self._encode_ie(57, struct.pack("!Q", cp_f_seid))  # CP F-SEID
        
        # Create PDRs
        # UL PDR
        ul_pdi = {
            "source_interface": 0,  # Access
            "local_fteid": {"interface": 5, "choose": 1},  # UPF N3, choose TEID
            "ue_ipv4": sm_context.ue_ipv4,
            "network_instance": sm_context.dnn,
            "qfi": sm_context.qos_flows[0].qfi if sm_context.qos_flows else 9,
        }
        if sm_context.pcc_rules:
            for rule_id, rule in sm_context.pcc_rules.items():
                if rule.get("flowInfos"):
                    ul_pdi["sdf_filter"] = rule["flowInfos"][0].get("flowDescription", "")
                    break
        
        msg += self._encode_ie(1, self._encode_pdi(ul_pdi))  # Create PDR
        msg += self._encode_ie(108, struct.pack("!H", sm_context.pdr_counter))  # PDR ID
        msg += self._encode_ie(109, struct.pack("!H", sm_context.far_counter))  # FAR ID
        msg += self._encode_ie(109, struct.pack("!H", sm_context.qer_counter))  # QER ID
        if sm_context.urr_counter > 0:
            msg += self._encode_ie(109, struct.pack("!H", sm_context.urr_counter))  # URR ID
        sm_context.pdr_counter += 1
        
        # UL FAR
        ul_far = {
            "apply_action": 2,  # FORW
            "forwarding_params": {
                "destination_interface": 0,  # Access
                "network_instance": sm_context.dnn,
            }
        }
        msg += self._encode_ie(1, self._encode_far(ul_far))  # Create FAR
        msg += self._encode_ie(108, struct.pack("!H", sm_context.far_counter))
        sm_context.far_counter += 1
        
        # UL QER
        ul_qer = {
            "gate_status": 2,  # OPEN
            "mbr": {"ul": 0, "dl": 0},
            "qfi": sm_context.qos_flows[0].qfi if sm_context.qos_flows else 9,
            "precedence": 255,
        }
        if sm_context.session_ambr:
            ul_qer["mbr"] = {
                "ul": int(sm_context.session_ambr.get("uplink", 0)),
                "dl": int(sm_context.session_ambr.get("downlink", 0)),
            }
        msg += self._encode_ie(1, self._encode_qer(ul_qer))  # Create QER
        msg += self._encode_ie(109, struct.pack("!H", sm_context.qer_counter))
        sm_context.qer_counter += 1
        
        # DL PDR
        dl_pdi = {
            "source_interface": 1,  # Core
            "ue_ipv4": sm_context.ue_ipv4,
            "network_instance": sm_context.dnn,
            "qfi": sm_context.qos_flows[0].qfi if sm_context.qos_flows else 9,
        }
        if sm_context.pcc_rules:
            for rule_id, rule in sm_context.pcc_rules.items():
                if rule.get("flowInfos"):
                    dl_pdi["sdf_filter"] = rule["flowInfos"][0].get("flowDescription", "")
                    break
        
        msg += self._encode_ie(1, self._encode_pdi(dl_pdi))
        msg += self._encode_ie(108, struct.pack("!H", sm_context.pdr_counter))
        msg += self._encode_ie(109, struct.pack("!H", sm_context.far_counter))
        msg += self._encode_ie(109, struct.pack("!H", sm_context.qer_counter))
        if sm_context.urr_counter > 0:
            msg += self._encode_ie(109, struct.pack("!H", sm_context.urr_counter))
        sm_context.pdr_counter += 1
        
        # DL FAR
        dl_far = {
            "apply_action": 2,  # FORW
            "forwarding_params": {
                "destination_interface": 1,  # Core/N6
                "network_instance": sm_context.dnn,
            }
        }
        msg += self._encode_ie(1, self._encode_far(dl_far))
        msg += self._encode_ie(108, struct.pack("!H", sm_context.far_counter))
        sm_context.far_counter += 1
        
        # DL QER
        dl_qer = {
            "gate_status": 2,
            "qfi": sm_context.qos_flows[0].qfi if sm_context.qos_flows else 9,
            "precedence": 255,
        }
        msg += self._encode_ie(1, self._encode_qer(dl_qer))
        msg += self._encode_ie(109, struct.pack("!H", sm_context.qer_counter))
        sm_context.qer_counter += 1
        
        # URR for charging
        if sm_context.charging_id:
            urr = {
                "reporting_triggers": 0x1E,  # VOLQU|TIMQU|PERIO|L2C
                "volume_threshold": 1073741824,
                "time_threshold": 3600,
                "measurement_method": 3,  # Volume + Duration
            }
            msg += self._encode_ie(1, self._encode_urr(urr))
            msg += self._encode_ie(109, struct.pack("!H", sm_context.urr_counter))
            sm_context.urr_counter += 1
        
        # Finalize message
        msg_len = len(msg) + 16  # header is 16 bytes
        header = struct.pack("!BBHQ3s", 
            (1 << 5) | 0,  # version 1, no flags
            50,  # Session Establishment Request
            msg_len,
            cp_f_seid,
            sequence.to_bytes(3, "big")
        )
        full_msg = header + msg
        
        try:
            sock.sendto(full_msg, (upf_ip, upf_port))
            data, addr = sock.recvfrom(4096)
            
            # Parse response
            if len(data) >= 16:
                resp_msg_type = data[1]
                if resp_msg_type == 51:  # Session Establishment Response
                    # Parse UP F-SEID, created PDRs, etc.
                    sm_context.up_f_seid = int.from_bytes(data[8:16], "big")
                    log.info("PFCP Session established with UPF %s, UP F-SEID=%d", upf_ip, sm_context.up_f_seid)
                    return True, {"up_f_seid": sm_context.up_f_seid}
        except Exception as e:
            log.error("PFCP Session Establishment failed: %s", e)
        
        return False, {}
    
    def session_modification(self, upf_ip: str, upf_port: int, sm_context: SmContext, 
                             n3_teid: str, n3_ipv4: str) -> bool:
        sock = self._get_socket(upf_ip, upf_port)
        sequence = self._next_sequence(upf_ip)
        
        msg = bytearray()
        msg += self._encode_ie(57, struct.pack("!Q", sm_context.cp_f_seid))  # CP F-SEID
        
        # Update DL FAR with gNB F-TEID
        dl_far = {
            "apply_action": 2,
            "forwarding_params": {
                "destination_interface": 0,
                "network_instance": sm_context.dnn,
                "outer_header": {
                    "ipv4": n3_ipv4,
                    "teid": int(n3_teid, 16) if isinstance(n3_teid, str) and n3_teid.startswith("0x") else int(n3_teid),
                    "interface": 5,
                    "choose": 0,
                }
            }
        }
        msg += self._encode_ie(2, self._encode_far(dl_far))  # Update FAR
        msg += self._encode_ie(108, struct.pack("!H", 2))  # FAR ID for DL
        
        msg_len = len(msg) + 16
        header = struct.pack("!BBHQ3s", (1 << 5) | 0, 52, msg_len, sm_context.cp_f_seid, sequence.to_bytes(3, "big"))
        full_msg = header + msg
        
        try:
            sock.sendto(full_msg, (upf_ip, upf_port))
            data, addr = sock.recvfrom(4096)
            if len(data) >= 16 and data[1] == 53:
                log.info("PFCP Session Modification successful")
                return True
        except Exception as e:
            log.error("PFCP Session Modification failed: %s", e)
        return False
    
    def session_deletion(self, upf_ip: str, upf_port: int, sm_context: SmContext) -> bool:
        sock = self._get_socket(upf_ip, upf_port)
        sequence = self._next_sequence(upf_ip)
        
        msg = bytearray()
        msg += self._encode_ie(57, struct.pack("!Q", sm_context.cp_f_seid))
        
        msg_len = len(msg) + 16
        header = struct.pack("!BBHQ3s", (1 << 5) | 0, 54, msg_len, sm_context.cp_f_seid, sequence.to_bytes(3, "big"))
        full_msg = header + msg
        
        try:
            sock.sendto(full_msg, (upf_ip, upf_port))
            data, addr = sock.recvfrom(4096)
            if len(data) >= 16 and data[1] == 55:
                log.info("PFCP Session Deletion successful")
                return True
        except Exception as e:
            log.error("PFCP Session Deletion failed: %s", e)
        return False
    
    def association_setup(self, upf_ip: str, upf_port: int) -> bool:
        sock = self._get_socket(upf_ip, upf_port)
        sequence = self._next_sequence(upf_ip)
        
        msg = bytearray()
        msg += self._encode_ie(56, b"smf.example.com")  # Node ID
        msg += self._encode_ie(43, struct.pack("!Q", 0xFFFFFFFFFFFFFFFF))  # UP Function Features - all
        
        msg_len = len(msg) + 16
        header = struct.pack("!BBHQ3s", (1 << 5) | 0, 5, msg_len, 0, sequence.to_bytes(3, "big"))
        full_msg = header + msg
        
        try:
            sock.sendto(full_msg, (upf_ip, upf_port))
            data, addr = sock.recvfrom(4096)
            if len(data) >= 16 and data[1] == 6:
                log.info("PFCP Association established with UPF %s", upf_ip)
                self.associations[upf_ip] = {"established": True}
                return True
        except Exception as e:
            log.error("PFCP Association Setup failed: %s", e)
        return False


class GTPv2CServer:
    def __init__(self, config: Dict, smf_engine):
        self.config = config
        self.smf_engine = smf_engine
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", config.get("gtpc_port", 2123)))
        self.running = False
        self.sequence = 0
        self.teid_counter = 1
    
    def start(self):
        self.running = True
        threading.Thread(target=self._listen, daemon=True).start()
    
    def stop(self):
        self.running = False
        self.sock.close()
    
    def _listen(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                threading.Thread(target=self._handle_message, args=(data, addr), daemon=True).start()
            except OSError:
                break
    
    def _handle_message(self, data: bytes, addr: Tuple):
        if len(data) < 12:
            return
        
        version_flags = data[0]
        msg_type = data[1]
        msg_len = struct.unpack("!H", data[2:4])[0]
        teid = struct.unpack("!I", data[4:8])[0]
        seq = int.from_bytes(data[8:11], "big")
        
        # Parse IEs (simplified)
        ies = self._parse_ies(data[12:])
        
        if msg_type == 32:  # Create Session Request
            self._handle_create_session(ies, addr, seq)
        elif msg_type == 34:  # Modify Bearer Request
            self._handle_modify_bearer(ies, addr, seq)
        elif msg_type == 36:  # Delete Session Request
            self._handle_delete_session(ies, addr, seq)
        elif msg_type == 1:  # Echo Request
            self._send_echo_response(addr, seq, teid)
    
    def _parse_ies(self, data: bytes) -> Dict:
        ies = {}
        i = 0
        while i < len(data):
            if i + 4 > len(data):
                break
            ie_type = data[i]
            ie_len = struct.unpack("!H", data[i+1:i+3])[0]
            ie_instance = data[i+3]
            ie_data = data[i+4:i+4+ie_len]
            ies[ie_type] = {"instance": ie_instance, "data": ie_data, "len": ie_len}
            i += 4 + ie_len
        return ies
    
    def _handle_create_session(self, ies: Dict, addr: Tuple, seq: int):
        # Extract IMSI (IE 1), APN (IE 71), RAT Type (IE 22), ULI (IE 20), etc.
        imsi = self._decode_imsi(ies.get(1, {}).get("data", b""))
        apn = self._decode_apn(ies.get(71, {}).get("data", b""))
        rat_type = ies.get(22, {}).get("data", b"\x06")[0]  # Default EUTRA
        uli = self._decode_uli(ies.get(20, {}).get("data", b""))
        sender_fteid = self._decode_fteid(ies.get(87, {}).get("data", b""))
        apn_ambr = self._decode_ambr(ies.get(79, {}).get("data", b""))
        bearer_ctx = ies.get(93, {}).get("data", b"")
        
        # Create SM context for EPS
        # This would map to N7 CreateSMPolicy via PCF
        log.info("GTPv2-C Create Session Request: IMSI=%s APN=%s RAT=%d", imsi, apn, rat_type)
        
        # For now, send a basic Create Session Response
        self._send_create_session_response(addr, seq, sender_fteid.get("teid", 0), imsi, apn)
    
    def _handle_modify_bearer(self, ies: Dict, addr: Tuple, seq: int):
        log.info("GTPv2-C Modify Bearer Request")
        self._send_modify_bearer_response(addr, seq)
    
    def _handle_delete_session(self, ies: Dict, addr: Tuple, seq: int):
        log.info("GTPv2-C Delete Session Request")
        self._send_delete_session_response(addr, seq)
    
    def _decode_imsi(self, data: bytes) -> str:
        if not data:
            return ""
        # BCD encoding
        imsi = ""
        for b in data:
            imsi += str(b & 0xF)
            imsi += str((b >> 4) & 0xF)
        return imsi.rstrip("fF")
    
    def _decode_apn(self, data: bytes) -> str:
        if not data:
            return ""
        apn = ""
        i = 0
        while i < len(data):
            length = data[i]
            if length == 0:
                break
            apn += data[i+1:i+1+length].decode() + "."
            i += 1 + length
        return apn.rstrip(".")
    
    def _decode_uli(self, data: bytes) -> Dict:
        if len(data) < 2:
            return {}
        uli_type = data[0]
        result = {"type": uli_type}
        if uli_type == 0:  # CGI
            pass
        elif uli_type == 1:  # SAI
            pass
        elif uli_type == 2:  # RAI
            pass
        elif uli_type == 3:  # TAI
            if len(data) >= 7:
                plmn = data[1:4]
                tac = struct.unpack("!H", data[5:7])[0]
                result["plmn_id"] = self._decode_plmn(plmn)
                result["tac"] = tac
        elif uli_type == 4:  # ECGI
            pass
        return result
    
    def _decode_plmn(self, data: bytes) -> str:
        if len(data) != 3:
            return ""
        mcc = ((data[0] & 0xF) * 100) + ((data[0] >> 4) * 10) + (data[1] & 0xF)
        mnc = ((data[1] >> 4) * 100) + ((data[2] & 0xF) * 10) + (data[2] >> 4)
        return f"{mcc}{mnc:02d}"
    
    def _decode_fteid(self, data: bytes) -> Dict:
        if len(data) < 9:
            return {}
        v4 = (data[0] >> 6) & 1
        v6 = (data[0] >> 5) & 1
        interface = data[0] & 0x1F
        teid = struct.unpack("!I", data[1:5])[0]
        result = {"interface": interface, "teid": teid}
        if v4 and len(data) >= 9:
            ip = ".".join(str(b) for b in data[5:9])
            result["ipv4"] = ip
        return result
    
    def _decode_ambr(self, data: bytes) -> Dict:
        if len(data) < 8:
            return {}
        ul = struct.unpack("!I", data[:4])[0]
        dl = struct.unpack("!I", data[4:8])[0]
        return {"ul": ul, "dl": dl}
    
    def _send_create_session_response(self, addr: Tuple, seq: int, sender_teid: int, imsi: str, apn: str):
        # Build Create Session Response
        self.sequence = (self.sequence + 1) % 0xFFFFFF
        teid = self.teid_counter
        self.teid_counter += 1
        
        # Header
        msg = bytearray()
        msg.append(0x48)  # Version 2, P=0, T=1
        msg.append(33)  # Create Session Response
        msg.extend(struct.pack("!H", 0))  # Length placeholder
        msg.extend(struct.pack("!I", teid))
        msg.extend(self.sequence.to_bytes(3, "big"))
        
        # Cause IE (2)
        msg.append(2)
        msg.extend(struct.pack("!H", 2))
        msg.append(0)
        msg.extend(struct.pack("!H", 16))  # Request accepted
        
        # PGW S5/S8 F-TEID (87)
        msg.append(87)
        msg.extend(struct.pack("!H", 9))
        msg.append(0)
        msg.append(0xC5)  # V4=1, V6=0, Interface=5 (S5/S8)
        msg.extend(struct.pack("!I", teid))
        msg.extend(socket.inet_aton("10.0.0.30"))  # UPF IP
        
        # PGW S5/S8 IP (94) - optional
        
        # PAA (79) - PDN Address Allocation
        msg.append(79)
        msg.extend(struct.pack("!H", 6))
        msg.append(0)
        msg.append(0x01)  # IPv4
        msg.extend(socket.inet_aton("10.60.0.2"))  # UE IP
        
        # APN Restriction (101)
        msg.append(101)
        msg.extend(struct.pack("!H", 1))
        msg.append(0)
        msg.append(0)  # No restriction
        
        # Update length
        msg_len = len(msg) - 4
        msg[2:4] = struct.pack("!H", msg_len)
        
        self.sock.sendto(msg, addr)
    
    def _send_modify_bearer_response(self, addr: Tuple, seq: int):
        self.sequence = (self.sequence + 1) % 0xFFFFFF
        msg = bytearray()
        msg.append(0x48)
        msg.append(35)  # Modify Bearer Response
        msg.extend(struct.pack("!H", 2))
        msg.extend(struct.pack("!I", 0))
        msg.extend(self.sequence.to_bytes(3, "big"))
        msg.append(2)
        msg.extend(struct.pack("!H", 2))
        msg.append(0)
        msg.extend(struct.pack("!H", 16))
        msg[2:4] = struct.pack("!H", len(msg) - 4)
        self.sock.sendto(msg, addr)
    
    def _send_delete_session_response(self, addr: Tuple, seq: int):
        self.sequence = (self.sequence + 1) % 0xFFFFFF
        msg = bytearray()
        msg.append(0x48)
        msg.append(37)  # Delete Session Response
        msg.extend(struct.pack("!H", 2))
        msg.extend(struct.pack("!I", 0))
        msg.extend(self.sequence.to_bytes(3, "big"))
        msg.append(2)
        msg.extend(struct.pack("!H", 2))
        msg.append(0)
        msg.extend(struct.pack("!H", 16))
        msg[2:4] = struct.pack("!H", len(msg) - 4)
        self.sock.sendto(msg, addr)
    
    def _send_echo_response(self, addr: Tuple, seq: int, teid: int):
        self.sequence = (self.sequence + 1) % 0xFFFFFF
        msg = bytearray()
        msg.append(0x40)  # Version 2, T=0
        msg.append(2)  # Echo Response
        msg.extend(struct.pack("!H", 0))
        msg.extend(b"\x00\x00\x00\x00")
        msg.extend(self.sequence.to_bytes(3, "big"))
        msg[2:4] = struct.pack("!H", len(msg) - 4)
        self.sock.sendto(msg, addr)


class SMFEngine:
    def __init__(self, config: Dict):
        self.config = config
        self.sm_contexts: Dict[str, SmContext] = {}
        self.ip_pools = IPPoolManager(config.get("ip_pools", []))
        self.upf_selector = UPFSelector(config.get("upf", {}).get("topology_file", UPF_TOPOLOGY_PATH))
        self.pfcp_client = PFCPClient(config.get("n4", {}))
        self.gtpc_server = GTPv2CServer(config.get("gtpc", {}), self)
        self.context_lock = threading.Lock()
        self._register_with_nrf()
    
    def _register_with_nrf(self):
        nrf_endpoint = self.config.get("nrf", {}).get("endpoint", "http://nrf:8080")
        try:
            resp = requests.put(
                f"{nrf_endpoint}/nnrf-nfm/v1/nf-instances/smf-instance",
                json={
                    "nfInstanceId": "smf-instance",
                    "nfType": "SMF",
                    "nfStatus": "REGISTERED",
                    "smfInfo": {
                        "sNssaiSmfInfoList": [
                            {"sNssai": {"sst": 1, "sd": "010203"}, "dnnSmfInfoList": [{"dnn": "internet"}]},
                            {"sNssai": {"sst": 2, "sd": "040506"}, "dnnSmfInfoList": [{"dnn": "ims"}]},
                        ],
                        "taiList": [{"plmnId": "64108", "tac": 1}, {"plmnId": "64108", "tac": 2}],
                        "taiRangeList": [],
                        "pgwFqdn": "pgw.example.com",
                        "accessType": ["3GPP_ACCESS", "NON_3GPP_ACCESS"],
                        "priority": 10,
                    },
                    "ipv4Addresses": ["10.0.0.10"],
                    "fqdn": "smf.example.com",
                    "capacity": 100000,
                    "load": 0,
                    "loadTimeStamp": datetime.utcnow().isoformat() + "Z",
                },
                timeout=5,
            )
            if resp.status_code in (200, 201):
                log.info("Registered with NRF")
        except Exception as e:
            log.warning("Could not register with NRF: %s", e)
    
    def create_sm_context(self, data: Dict) -> Tuple[Dict, int, Dict]:
        supi = data.get("supi", "")
        pdu_session_id = data.get("pduSessionId", 0)
        dnn = data.get("dnn", "internet")
        s_nssai = data.get("sNssai", {"sst": 1})
        request_type = RequestType(data.get("requestType", "INITIAL_REQUEST"))
        access_type = AccessType(data.get("anType", "3GPP_ACCESS"))
        rat_type = RatType(data.get("ratType", "NR"))
        
        # Generate SM Context Ref
        sm_context_ref = str(uuid.uuid4())
        
        # Get subscription data from UDM
        subs_data = self._get_subscription_data(supi, dnn, s_nssai)
        
        # Create SM Context
        ctx = SmContext(
            sm_context_ref=sm_context_ref,
            supi=supi,
            gpsi=data.get("gpsi"),
            pdu_session_id=pdu_session_id,
            dnn=dnn,
            s_nssai=s_nssai,
            serving_nf_id=data.get("servingNfId", "amf-1"),
            guami=data.get("guami", {}),
            request_type=request_type,
            access_type=access_type,
            rat_type=rat_type,
            ue_location=data.get("userLocationInfo"),
            ue_time_zone=data.get("ueTimeZone"),
            n1_sm_msg=data.get("n1SmMsg"),
            sm_context_status_uri=data.get("smContextStatusUri", ""),
            pcf_id=data.get("pcfId"),
            same_pcf_selection=data.get("samePcfSelection", False),
            pei=data.get("pei"),
            old_pdu_session_id=data.get("oldPduSessionId"),
            ladn_indication=data.get("ladnIndication", False),
            ma_pdu_indication=data.get("maPduIndication", False),
            priority_access=data.get("priorityAccess", False),
            dnn_selection_mode=data.get("dnnSelectionMode"),
            trace_requirements=data.get("traceRequirements"),
        )
        
        # Apply subscription data
        if subs_data:
            ctx.session_ambr = subs_data.get("subsSessAmbr", {"uplink": "1000000000", "downlink": "1000000000"})
            default_qos = subs_data.get("subsDefQos", {})
            ctx.default_qos = QosFlowProfile(
                five_qi=default_qos.get("5qi", 9),
                arp=ARP(
                    priority_level=default_qos.get("arp", {}).get("priorityLevel", 8),
                    preempt_cap=default_qos.get("arp", {}).get("preemptCap", "NOT_PREEMPT"),
                    preempt_vuln=default_qos.get("arp", {}).get("preemptVuln", "PREEMPTABLE"),
                ),
                priority_level=default_qos.get("priorityLevel"),
                aver_window=default_qos.get("averWindow"),
                max_data_burst_vol=default_qos.get("maxDataBurstVol"),
            )
            ctx.charging_characteristics = subs_data.get("chargingCharacteristics", "1")
            ctx.pdu_session_type = PduSessionType(subs_data.get("allowedPduSessionTypes", ["IPv4"])[0])
            ctx.ssc_mode = SscMode(subs_data.get("allowedSscModes", [1])[0])
        
        # Select UPF
        upf = self.upf_selector.select_upf(dnn, s_nssai, ctx.ue_location)
        if not upf:
            return {"cause": "NO_UPF_AVAILABLE"}, 500, {}
        
        ctx.upf_node_id = upf.get("node_id")
        ctx.upf_ipv4 = upf.get("ipv4")
        ctx.upf_n4_port = upf.get("n4_port", 8805)
        ctx.upf_n3_ipv4 = upf.get("n3_ipv4")
        ctx.upf_n3_port = upf.get("n3_port", 2152)
        
        # Allocate UE IP
        dnn_config = self.config.get("dnn_configs", {}).get(dnn, {})
        ip_pools = dnn_config.get("ip_pools", ["default-ipv4", "default-ipv6"])
        ctx.ue_ipv4 = self.ip_pools.allocate(ip_pools[0])
        if not ctx.ue_ipv4:
            return {"cause": "IP_ADDRESS_UNAVAILABLE"}, 500, {}
        
        # Setup PFCP association
        if not self.pfcp_client.associations.get(ctx.upf_ipv4):
            self.pfcp_client.association_setup(ctx.upf_ipv4, ctx.upf_n4_port)
        
        # Establish PFCP session
        success, pfcp_resp = self.pfcp_client.session_establishment(ctx.upf_ipv4, ctx.upf_n4_port, ctx)
        if not success:
            self.ip_pools.release(ip_pools[0], ctx.ue_ipv4)
            self.upf_selector.release_upf(ctx.upf_node_id)
            return {"cause": "PFCP_SESSION_ESTABLISHMENT_FAILED"}, 500, {}
        
        # Create policy association with PCF
        pcf_resp = self._create_pcf_policy(ctx)
        if pcf_resp:
            ctx.pcf_smpolicy_id = pcf_resp.get("smPolicyId")
            ctx.pcc_rules = pcf_resp.get("pccRules", {})
            # Apply QoS from policy
            self._apply_policy_qos(ctx, pcf_resp)
        
        # Create QoS flows
        self._create_qos_flows(ctx)
        
        # Allocate EBI for EPS interworking
        if self.config.get("eps_interworking", {}).get("enabled"):
            ctx.ebi_list = list(range(5, 15))
        
        with self.context_lock:
            self.sm_contexts[sm_context_ref] = ctx
        
        # Build response
        response = {
            "cause": "SUCCESS",
            "smContextRef": sm_context_ref,
            "upCnxState": ctx.up_cnx_state.value,
            "n2SmInfo": self._build_n2_sm_info(ctx),
            "n2SmInfoType": "PDU_RES_SETUP",
            "selectedSmfId": "smf-instance",
        }
        
        headers = {"Location": f"/nsmf-pdusession/v1/sm-contexts/{sm_context_ref}"}
        return response, 201, headers
    
    def _get_subscription_data(self, supi: str, dnn: str, s_nssai: Dict) -> Optional[Dict]:
        udm_endpoint = self.config.get("udm", {}).get("endpoint", "http://udm:8080")
        try:
            resp = requests.get(
                f"{udm_endpoint}/nudm-sdm/v1/{supi}/sm-data",
                params={"dnn": dnn, "snssai": json.dumps(s_nssai)},
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.warning("Failed to get subscription data from UDM: %s", e)
        return None
    
    def _create_pcf_policy(self, ctx: SmContext) -> Optional[Dict]:
        pcf_endpoint = self.config.get("pcf", {}).get("endpoint", "http://pcf:7777")
        try:
            resp = requests.post(
                f"{pcf_endpoint}/npcf-smpolicycontrol/v1/sm-policies",
                json={
                    "supi": ctx.supi,
                    "gpsi": ctx.gpsi,
                    "pduSessionId": ctx.pdu_session_id,
                    "pduSessionType": ctx.pdu_session_type.value,
                    "dnn": ctx.dnn,
                    "sliceInfo": ctx.s_nssai,
                    "servingNetwork": ctx.serving_nf_id,
                    "userLocationInfo": ctx.ue_location,
                    "ueTimeZone": ctx.ue_time_zone,
                    "pei": ctx.pei,
                    "accessType": ctx.access_type.value,
                    "ratType": ctx.rat_type.value,
                    "ipv4Address": ctx.ue_ipv4,
                    "ipv6AddressPrefix": ctx.ue_ipv6_prefix,
                    "subsSessAmbr": ctx.session_ambr,
                    "subsDefQos": {
                        "5qi": ctx.default_qos.five_qi if ctx.default_qos else 9,
                        "arp": {
                            "priorityLevel": ctx.default_qos.arp.priority_level if ctx.default_qos else 8,
                            "preemptCap": ctx.default_qos.arp.preempt_cap if ctx.default_qos else "NOT_PREEMPT",
                            "preemptVuln": ctx.default_qos.arp.preempt_vuln if ctx.default_qos else "PREEMPTABLE",
                        },
                    } if ctx.default_qos else None,
                    "chargingCharacteristics": ctx.charging_characteristics,
                    "online": False,
                    "offline": True,
                    "notificationUri": f"http://smf:7777/npcf-smpolicycontrol/v1/sm-policies/{{smPolicyId}}/notify",
                    "suppFeat": self.config.get("supported_features", "ffff"),
                },
                timeout=10,
            )
            if resp.status_code in (200, 201):
                return resp.json()
        except Exception as e:
            log.warning("Failed to create PCF policy: %s", e)
        return None
    
    def _apply_policy_qos(self, ctx: SmContext, policy: Dict):
        qos_decs = policy.get("qosDecs", {})
        for qos_id, qos in qos_decs.items():
            if qos_id == "default-qos" or qos_id == "ims-qos":
                ctx.default_qos = QosFlowProfile(
                    five_qi=qos.get("5qi", 9),
                    arp=ARP(
                        priority_level=qos.get("arp", {}).get("priorityLevel", 8),
                        preempt_cap=qos.get("arp", {}).get("preemptCap", "NOT_PREEMPT"),
                        preempt_vuln=qos.get("arp", {}).get("preemptVuln", "PREEMPTABLE"),
                    ),
                    priority_level=qos.get("priorityLevel"),
                    aver_window=qos.get("averWindow"),
                    max_data_burst_vol=qos.get("maxDataBurstVol"),
                    gbr_ul=qos.get("gbrUl"),
                    gbr_dl=qos.get("gbrDl"),
                    maxbr_ul=qos.get("maxbrUl"),
                    maxbr_dl=qos.get("maxbrDl"),
                    qnc=qos.get("qnc", False),
                    reflective_qos=qos.get("reflectiveQos", False),
                )
                break
    
    def _create_qos_flows(self, ctx: SmContext):
        # Default QoS flow
        qfi = 9
        ctx.qos_flows = [QosFlowItem(
            qfi=qfi,
            qos_flow_profile=ctx.default_qos or QosFlowProfile(
                five_qi=9,
                arp=ARP(priority_level=8),
            )
        )]
        
        # Additional QoS flows from PCC rules
        for rule_id, rule in ctx.pcc_rules.items():
            if rule.get("refQosData"):
                for qos_ref in rule["refQosData"]:
                    # Would create additional QoS flow
                    pass
    
    def _build_n2_sm_info(self, ctx: SmContext) -> Dict:
        return {
            "pduSessionId": ctx.pdu_session_id,
            "qfiList": [qf.qfi for qf in ctx.qos_flows],
            "qosProfiles": [
                {
                    "5qi": qf.qos_flow_profile.five_qi,
                    "arp": {
                        "priorityLevel": qf.qos_flow_profile.arp.priority_level,
                        "preemptCap": qf.qos_flow_profile.arp.preempt_cap,
                        "preemptVuln": qf.qos_flow_profile.arp.preempt_vuln,
                    },
                    "gbrUl": qf.qos_flow_profile.gbr_ul,
                    "gbrDl": qf.qos_flow_profile.gbr_dl,
                    "maxbrUl": qf.qos_flow_profile.maxbr_ul,
                    "maxbrDl": qf.qos_flow_profile.maxbr_dl,
                }
                for qf in ctx.qos_flows
            ],
            "cnTunnelInfo": {
                "ipv4Addr": ctx.upf_n3_ipv4,
                "teid": ctx.n3_teid or "0",
            },
            "sNssai": ctx.s_nssai,
            "sessionAmbr": ctx.session_ambr,
            "pduSessionType": ctx.pdu_session_type.value,
            "upSecurityEnforcement": None,
        }
    
    def update_sm_context(self, sm_context_ref: str, data: Dict) -> Tuple[Dict, int]:
        with self.context_lock:
            ctx = self.sm_contexts.get(sm_context_ref)
        if not ctx:
            return {"cause": "CONTEXT_NOT_FOUND"}, 404
        
        # Handle N2 SM information (gNB F-TEID)
        n2_sm_info = data.get("n2SmInfo", {})
        if n2_sm_info:
            ctx.n3_teid = n2_sm_info.get("anTunnelInfo", {}).get("teid")
            ctx.n3_ipv4 = n2_sm_info.get("anTunnelInfo", {}).get("ipv4Addr")
            accepted_qfis = n2_sm_info.get("acceptedQfiList", [])
            rejected_qfis = n2_sm_info.get("rejectedQfiList", [])
            
            # Update PFCP with gNB F-TEID
            if ctx.n3_teid and ctx.n3_ipv4:
                self.pfcp_client.session_modification(
                    ctx.upf_ipv4, ctx.upf_n4_port, ctx, ctx.n3_teid, ctx.n3_ipv4
                )
            
            # Remove rejected QFIs
            for qfi in rejected_qfis:
                ctx.qos_flows = [qf for qf in ctx.qos_flows if qf.qfi != qfi]
        
        # Handle N1 SM message
        n1_sm_msg = data.get("n1SmMsg")
        if n1_sm_msg:
            pass  # Process N1 message
        
        # Handle release
        if data.get("release", False):
            return self.release_sm_context(sm_context_ref)
        
        return {"cause": "SUCCESS"}, 200
    
    def release_sm_context(self, sm_context_ref: str) -> Tuple[Dict, int]:
        with self.context_lock:
            ctx = self.sm_contexts.pop(sm_context_ref, None)
        if not ctx:
            return {"cause": "CONTEXT_NOT_FOUND"}, 404
        
        # Delete PFCP session
        self.pfcp_client.session_deletion(ctx.upf_ipv4, ctx.upf_n4_port, ctx)
        
        # Delete PCF policy
        if ctx.pcf_smpolicy_id:
            pcf_endpoint = self.config.get("pcf", {}).get("endpoint", "http://pcf:7777")
            try:
                requests.delete(
                    f"{pcf_endpoint}/npcf-smpolicycontrol/v1/sm-policies/{ctx.pcf_smpolicy_id}",
                    timeout=5,
                )
            except Exception as e:
                log.warning("Failed to delete PCF policy: %s", e)
        
        # Release IP
        dnn_config = self.config.get("dnn_configs", {}).get(ctx.dnn, {})
        ip_pools = dnn_config.get("ip_pools", ["default-ipv4"])
        if ctx.ue_ipv4:
            self.ip_pools.release(ip_pools[0], ctx.ue_ipv4)
        
        # Release UPF
        self.upf_selector.release_upf(ctx.upf_node_id)
        
        # Notify AMF
        if ctx.sm_context_status_uri:
            try:
                requests.post(ctx.sm_context_status_uri, json={
                    "smContextStatus": "RELEASED",
                    "smContextRef": sm_context_ref,
                }, timeout=5)
            except Exception as e:
                log.warning("Failed to notify AMF: %s", e)
        
        return {"cause": "SUCCESS"}, 200
    
    def get_sm_context(self, sm_context_ref: str) -> Optional[SmContext]:
        with self.context_lock:
            return self.sm_contexts.get(sm_context_ref)
    
    def notify_status(self, sm_context_ref: str, data: Dict) -> Tuple[Dict, int]:
        # AMF notifies SMF of context status change
        return {"cause": "SUCCESS"}, 200
    
    def send_mo_data(self, sm_context_ref: str, data: Dict) -> Tuple[Dict, int]:
        return {"cause": "SUCCESS"}, 200
    
    def create_pdu_session(self, data: Dict) -> Tuple[Dict, int]:
        # SMF-to-SMF (home-routed)
        return {"cause": "NOT_IMPLEMENTED"}, 501
    
    def update_pdu_session(self, data: Dict) -> Tuple[Dict, int]:
        return {"cause": "NOT_IMPLEMENTED"}, 501
    
    def release_pdu_session(self, data: Dict) -> Tuple[Dict, int]:
        return {"cause": "NOT_IMPLEMENTED"}, 501
    
    def retrieve_pdu_session(self, data: Dict) -> Tuple[Dict, int]:
        return {"cause": "NOT_IMPLEMENTED"}, 501
    
    def transfer_mo_data(self, data: Dict) -> Tuple[Dict, int]:
        return {"cause": "NOT_IMPLEMENTED"}, 501


class SMFHandler(BaseHTTPRequestHandler):
    engine: SMFEngine = None

    def _send(self, code: int, payload: Dict = None, headers: Dict = None):
        body = json.dumps(payload).encode("utf-8") if payload else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _parse_json_body(self) -> Dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length:
            return json.loads(self.rfile.read(content_length).decode("utf-8"))
        return {}

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self._send(200, {"status": "ok", "nf": "smf", "contexts": len(self.engine.sm_contexts)})
            return
        
        if self.path.startswith("/nsmf-pdusession/v1/sm-contexts"):
            parts = self.path.split("/")
            if len(parts) > 5 and parts[5]:
                sm_context_ref = parts[5]
                if "/retrieve" in self.path:
                    ctx = self.engine.get_sm_context(sm_context_ref)
                    if ctx:
                        self._send(200, {"context": "retrieved"})
                    else:
                        self._send(404, {"cause": "CONTEXT_NOT_FOUND"})
                else:
                    ctx = self.engine.get_sm_context(sm_context_ref)
                    if ctx:
                        self._send(200, {"context": "found"})
                    else:
                        self._send(404, {"cause": "CONTEXT_NOT_FOUND"})
            else:
                self._send(200, {"contexts": list(self.engine.sm_contexts.keys())})
            return
        
        self._send(404, {"cause": "NOT_FOUND"})

    def do_POST(self):
        if self.path == "/nsmf-pdusession/v1/sm-contexts":
            body = self._parse_json_body()
            response, code, headers = self.engine.create_sm_context(body)
            self._send(code, response, headers)
            return
        
        parts = self.path.split("/")
        if len(parts) >= 6 and parts[5]:
            sm_context_ref = parts[5]
            body = self._parse_json_body()
            
            if "/modify" in self.path or "/update" in self.path:
                response, code = self.engine.update_sm_context(sm_context_ref, body)
                self._send(code, response)
            elif "/release" in self.path:
                response, code = self.engine.release_sm_context(sm_context_ref)
                self._send(code, response)
            elif "/retrieve" in self.path:
                response, code = self.engine.get_sm_context(sm_context_ref), 200
                self._send(code, response or {"cause": "CONTEXT_NOT_FOUND"})
            elif "/send-mo-data" in self.path:
                response, code = self.engine.send_mo_data(sm_context_ref, body)
                self._send(code, response)
            elif "/status-notify" in self.path:
                response, code = self.engine.notify_status(sm_context_ref, body)
                self._send(code, response)
            else:
                self._send(404, {"cause": "NOT_FOUND"})
            return
        
        if self.path == "/nsmf-pdusession/v1/pdu-sessions":
            body = self._parse_json_body()
            response, code = self.engine.create_pdu_session(body)
            self._send(code, response)
            return
        
        if self.path.startswith("/nsmf-pdusession/v1/pdu-sessions/"):
            parts = self.path.split("/")
            if len(parts) >= 7 and parts[6]:
                pdu_session_ref = parts[6]
                body = self._parse_json_body()
                if "/modify" in self.path:
                    response, code = self.engine.update_pdu_session(body)
                elif "/release" in self.path:
                    response, code = self.engine.release_pdu_session(body)
                elif "/retrieve" in self.path:
                    response, code = self.engine.retrieve_pdu_session(body)
                elif "/transfer-mo-data" in self.path:
                    response, code = self.engine.transfer_mo_data(body)
                else:
                    response, code = {"cause": "NOT_FOUND"}, 404
                self._send(code, response)
            return
        
        self._send(404, {"cause": "NOT_FOUND"})

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


def main():
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    
    smf_config = config.get("smf", config)
    
    SMFHandler.engine = SMFEngine(smf_config)
    
    host = smf_config.get("host", "0.0.0.0")
    sbi_port = smf_config.get("sbi_port", 7777)
    
    log.info("Starting SMF on %s:%s", host, sbi_port)
    
    # Start GTPv2-C server
    SMFHandler.engine.gtpc_server.start()
    log.info("GTPv2-C server started on port %s", smf_config.get("gtpc_port", 2123))
    
    server = HTTPServer((host, sbi_port), SMFHandler)
    
    def shutdown(*_):
        log.info("Shutting down SMF")
        SMFHandler.engine.gtpc_server.stop()
        server.shutdown()
    
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    server.serve_forever()


if __name__ == "__main__":
    main()