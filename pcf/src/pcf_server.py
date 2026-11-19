#!/usr/bin/env python3
"""
PCF - Policy Control Function
Implements TS 29.512 Npcf_SMPolicyControl (N7 interface)
Full PCC rule decision engine with ADC, charging, QoS, traffic control, usage monitoring
"""

import json
import logging
import os
import signal
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
log = logging.getLogger("pcf")

CONFIG_PATH = os.getenv("PCF_CONFIG", "/app/config/pcf.yaml")
RULES_PATH = os.getenv("PCF_PCC_RULES", "/app/config/pcc_rules.json")
SESSION_RULES_PATH = os.getenv("PCF_SESSION_RULES", "/app/config/session_rules.json")
QOS_PROFILES_PATH = os.getenv("PCF_QOS_PROFILES", "/app/config/qos_profiles.json")
CHARGING_PROFILES_PATH = os.getenv("PCF_CHARGING_PROFILES", "/app/config/charging_profiles.json")
TRAFFIC_CONTROL_PATH = os.getenv("PCF_TRAFFIC_CONTROL", "/app/config/traffic_control_profiles.json")
USAGE_MONITORING_PATH = os.getenv("PCF_USAGE_MONITORING", "/app/config/usage_monitoring_profiles.json")
CONDITION_PROFILES_PATH = os.getenv("PCF_CONDITION_PROFILES", "/app/config/condition_profiles.json")
PREDEFINED_RULES_PATH = os.getenv("PCF_PREDEFINED_RULES", "/app/config/predefined_rules.json")


class FlowStatus(Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    ENABLED_UPLINK = "ENABLED_UPLINK"
    ENABLED_DOWNLINK = "ENABLED_DOWNLINK"


class MeteringMethod(Enum):
    VOLUME = "VOLUME"
    DURATION = "DURATION"
    VOLUME_DURATION = "VOLUME_DURATION"
    EVENT = "EVENT"


class SdfHandl(Enum):
    BLOCKING = "BLOCKING"
    NON_BLOCKING = "NON_BLOCKING"
    NO_CREDIT_CONTROL = "NO_CREDIT_CONTROL"


class PccRuleStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ReportingLevel(Enum):
    SERVICE_ID_LEVEL = "SERVICE_ID_LEVEL"
    RATING_GROUP_LEVEL = "RATING_GROUP_LEVEL"
    SPONSORED_CONNECTIVITY_LEVEL = "SPONSORED_CONNECTIVITY_LEVEL"


class PCRT(Enum):
    PLMN_CH = "PLMN_CH"
    AC_TY_CH = "AC_TY_CH"
    RAT_TY_CH = "RAT_TY_CH"
    LOC_CH = "LOC_CH"
    PRA_CH = "PRA_CH"
    OUT_OF_CREDIT = "OUT_OF_CREDIT"
    REALLO_CREDIT = "REALLO_CREDIT"
    UE_IP_CH = "UE_IP_CH"
    US_RE = "US_RE"
    APP_STA = "APP_STA"
    APP_STO = "APP_STO"
    AN_INFO = "AN_INFO"
    CREDIT_MGMT_SESS_FAIL = "CREDIT_MGMT_SESS_FAIL"
    UE_REACH = "UE_REACH"
    SE_AMBR_CH = "SE_AMBR_CH"
    DEF_QOS_CH = "DEF_QOS_CH"
    NO_CREDIT = "NO_CREDIT"
    RES_RELEASE = "RES_RELEASE"
    SUCC_RES_ALLO = "SUCC_RES_ALLO"
    QOS_NOTIF = "QOS_NOTIF"
    ACCESS_TYPE_CHANGE = "ACCESS_TYPE_CHANGE"


@dataclass
class ARP:
    priority_level: int
    preempt_cap: str = "NOT_PREEMPT"
    preempt_vuln: str = "PREEMPTABLE"


@dataclass
class QosData:
    qos_id: str
    five_qi: int
    maxbr_ul: str
    maxbr_dl: str
    gbr_ul: Optional[str] = None
    gbr_dl: Optional[str] = None
    arp: Optional[ARP] = None
    priority_level: Optional[int] = None
    aver_window: Optional[int] = None
    max_data_burst_vol: Optional[int] = None
    qnc: bool = False
    reflective_qos: bool = False
    sharing_key_dl: Optional[str] = None
    sharing_key_ul: Optional[str] = None


@dataclass
class ChargingData:
    chg_id: str
    metering_method: MeteringMethod
    offline: bool
    online: bool
    rating_group: int
    service_id: Optional[int] = None
    sponsor_id: Optional[str] = None
    app_svc_prov_id: Optional[str] = None
    af_charging_identifier: Optional[str] = None
    reporting_level: ReportingLevel = ReportingLevel.RATING_GROUP_LEVEL
    sdf_handl: SdfHandl = SdfHandl.NO_CREDIT_CONTROL


@dataclass
class RedirectInfo:
    redirect_enabled: bool
    redirect_address_type: str
    redirect_server_address: str


@dataclass
class TrafficControlData:
    tc_id: str
    flow_status: FlowStatus
    redirect_info: Optional[RedirectInfo] = None
    add_redirect_info: List[RedirectInfo] = field(default_factory=list)
    mute_notif: bool = False
    traffic_steering_pol_id_dl: Optional[str] = None
    traffic_steering_pol_id_ul: Optional[str] = None
    route_to_locs: List[str] = field(default_factory=list)
    max_allowed_up_lat: int = 0
    metadata: Optional[str] = None
    sim_conn_ind: bool = False
    sim_conn_term: bool = False
    up_path_chg_event: bool = False


@dataclass
class UsageMonitoringData:
    um_id: str
    volume_threshold: Optional[str] = None
    volume_threshold_uplink: Optional[str] = None
    volume_threshold_downlink: Optional[str] = None
    time_threshold: Optional[int] = None
    monitoring_time: Optional[int] = None
    next_vol_threshold: Optional[str] = None
    next_vol_threshold_uplink: Optional[str] = None
    next_vol_threshold_downlink: Optional[str] = None
    next_time_threshold: Optional[int] = None
    inactivity_time: Optional[int] = None
    ex_usage_pcc_rule_ids: List[str] = field(default_factory=list)


@dataclass
class ConditionData:
    cond_id: str
    activation_time: Optional[str] = None
    deactivation_time: Optional[str] = None
    access_type: List[str] = field(default_factory=list)
    rat_type: List[str] = field(default_factory=list)
    serving_nf_identity: Optional[str] = None


@dataclass
class FlowInformation:
    flow_description: str
    flow_direction: str
    flow_id: int
    packet_filter: Optional[Dict] = None


@dataclass
class PccRule:
    pcc_rule_id: str
    precedence: int
    flow_infos: List[FlowInformation] = field(default_factory=list)
    app_id: Optional[str] = None
    ref_qos_data: List[str] = field(default_factory=list)
    ref_chg_data: List[str] = field(default_factory=list)
    ref_tc_data: List[str] = field(default_factory=list)
    ref_um_data: List[str] = field(default_factory=list)
    ref_cond_data: List[str] = field(default_factory=list)
    ref_alt_qos_params: List[str] = field(default_factory=list)
    ref_qos_mon: Optional[str] = None
    af_sig_protocol: Optional[str] = None
    pcc_rule_status: PccRuleStatus = PccRuleStatus.ACTIVE


@dataclass
class SessionRule:
    sess_rule_id: str
    auth_sess_ambr: Dict[str, str]
    auth_def_qos: Dict
    pcc_rule_status: PccRuleStatus = PccRuleStatus.ACTIVE


@dataclass
class SmPolicyContextData:
    supi: str
    gpsi: Optional[str] = None
    pdu_session_id: int = 0
    pdu_session_type: Optional[str] = None
    dnn: Optional[str] = None
    slice_info: Optional[Dict] = None
    serving_network: Optional[str] = None
    user_location_info: Optional[Dict] = None
    ue_time_zone: Optional[str] = None
    pei: Optional[str] = None
    access_type: Optional[str] = None
    rat_type: Optional[str] = None
    ipv4_address: Optional[str] = None
    ipv6_address_prefix: Optional[str] = None
    subs_sess_ambr: Optional[Dict] = None
    subs_def_qos: Optional[Dict] = None
    charging_characteristics: Optional[str] = None
    online: bool = False
    offline: bool = False
    notification_uri: Optional[str] = None
    supp_feat: Optional[str] = None


@dataclass
class SmPolicyDecision:
    pcc_rules: Dict[str, PccRule] = field(default_factory=dict)
    sess_rules: Dict[str, SessionRule] = field(default_factory=dict)
    qos_decs: Dict[str, QosData] = field(default_factory=dict)
    chg_decs: Dict[str, ChargingData] = field(default_factory=dict)
    traff_cont_decs: Dict[str, TrafficControlData] = field(default_factory=dict)
    um_decs: Dict[str, UsageMonitoringData] = field(default_factory=dict)
    conds: Dict[str, ConditionData] = field(default_factory=dict)
    policy_ctrl_req_triggers: List[str] = field(default_factory=list)
    last_req_rule_data: List[str] = field(default_factory=list)
    last_req_usage_data: List[str] = field(default_factory=list)


@dataclass
class SmPolicyAssociation:
    sm_policy_id: str
    context: SmPolicyContextData
    decision: SmPolicyDecision
    created_at: datetime
    updated_at: datetime


class PCFEngine:
    def __init__(self, config: Dict):
        self.config = config
        self.associations: Dict[str, SmPolicyAssociation] = {}
        self.pcc_rules: Dict[str, PccRule] = {}
        self.session_rules: Dict[str, SessionRule] = {}
        self.qos_profiles: Dict[str, QosData] = {}
        self.charging_profiles: Dict[str, ChargingData] = {}
        self.traffic_control_profiles: Dict[str, TrafficControlData] = {}
        self.usage_monitoring_profiles: Dict[str, UsageMonitoringData] = {}
        self.condition_profiles: Dict[str, ConditionData] = {}
        self.predefined_rules: Dict[str, PccRule] = {}
        self._load_configs()
        self._register_with_nrf()

    def _load_configs(self):
        configs = [
            (RULES_PATH, "rules", self._load_pcc_rules),
            (SESSION_RULES_PATH, "sessionRules", self._load_session_rules),
            (QOS_PROFILES_PATH, "qosDecs", self._load_qos_profiles),
            (CHARGING_PROFILES_PATH, "chgDecs", self._load_charging_profiles),
            (TRAFFIC_CONTROL_PATH, "traffContDecs", self._load_traffic_control),
            (USAGE_MONITORING_PATH, "umDecs", self._load_usage_monitoring),
            (CONDITION_PROFILES_PATH, "conds", self._load_conditions),
            (PREDEFINED_RULES_PATH, "predefinedRules", self._load_predefined_rules),
        ]
        for path, key, loader in configs:
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    loader(data.get(key, data))
                log.info("Loaded %s from %s", key, path)
            except FileNotFoundError:
                log.warning("Config file not found: %s", path)

    def _load_pcc_rules(self, data: List[Dict]):
        for rule in data:
            flows = [FlowInformation(**f) for f in rule.get("flowInfos", [])]
            self.pcc_rules[rule["pccRuleId"]] = PccRule(
                pcc_rule_id=rule["pccRuleId"],
                precedence=rule.get("precedence", 255),
                flow_infos=flows,
                app_id=rule.get("appId"),
                ref_qos_data=rule.get("refQosData", []),
                ref_chg_data=rule.get("refChgData", []),
                ref_tc_data=rule.get("refTcData", []),
                ref_um_data=rule.get("refUmData", []),
                ref_cond_data=rule.get("refCondData", []),
                ref_alt_qos_params=rule.get("refAltQosParams", []),
                ref_qos_mon=rule.get("refQosMon"),
                af_sig_protocol=rule.get("afSigProtocol"),
                pcc_rule_status=PccRuleStatus(rule.get("pccRuleStatus", "ACTIVE")),
            )

    def _load_session_rules(self, data: List[Dict]):
        for rule in data:
            self.session_rules[rule["sessRuleId"]] = SessionRule(
                sess_rule_id=rule["sessRuleId"],
                auth_sess_ambr=rule.get("authSessAmbr", {}),
                auth_def_qos=rule.get("authDefQos", {}),
                pcc_rule_status=PccRuleStatus(rule.get("pccRuleStatus", "ACTIVE")),
            )

    def _load_qos_profiles(self, data: Dict):
        for qos_id, qos in data.items():
            arp = None
            if "arp" in qos:
                arp = ARP(
                    priority_level=qos["arp"].get("priorityLevel", 8),
                    preempt_cap=qos["arp"].get("preemptCap", "NOT_PREEMPT"),
                    preempt_vuln=qos["arp"].get("preemptVuln", "PREEMPTABLE"),
                )
            self.qos_profiles[qos_id] = QosData(
                qos_id=qos_id,
                five_qi=qos["5qi"],
                maxbr_ul=qos.get("maxbrUl", "0"),
                maxbr_dl=qos.get("maxbrDl", "0"),
                gbr_ul=qos.get("gbrUl"),
                gbr_dl=qos.get("gbrDl"),
                arp=arp,
                priority_level=qos.get("priorityLevel"),
                aver_window=qos.get("averWindow"),
                max_data_burst_vol=qos.get("maxDataBurstVol"),
                qnc=qos.get("qnc", False),
                reflective_qos=qos.get("reflectiveQos", False),
                sharing_key_dl=qos.get("sharingKeyDl"),
                sharing_key_ul=qos.get("sharingKeyUl"),
            )

    def _load_charging_profiles(self, data: Dict):
        for chg_id, chg in data.items():
            self.charging_profiles[chg_id] = ChargingData(
                chg_id=chg_id,
                metering_method=MeteringMethod(chg.get("meteringMethod", "VOLUME")),
                offline=chg.get("offline", False),
                online=chg.get("online", False),
                rating_group=chg.get("ratingGroup", 1),
                service_id=chg.get("serviceId"),
                sponsor_id=chg.get("sponsorId"),
                app_svc_prov_id=chg.get("appSvcProvId"),
                af_charging_identifier=chg.get("afChargingIdentifier"),
                reporting_level=ReportingLevel(chg.get("reportingLevel", "RATING_GROUP_LEVEL")),
                sdf_handl=SdfHandl(chg.get("sdfHandl", "NO_CREDIT_CONTROL")),
            )

    def _load_traffic_control(self, data: Dict):
        for tc_id, tc in data.items():
            redirect = None
            if tc.get("redirectInfo"):
                ri = tc["redirectInfo"]
                redirect = RedirectInfo(
                    redirect_enabled=ri.get("redirectEnabled", True),
                    redirect_address_type=ri.get("redirectAddressType", "IPV4_ADDR"),
                    redirect_server_address=ri.get("redirectServerAddress", ""),
                )
            add_redirect = []
            for ri in tc.get("addRedirectInfo", []):
                add_redirect.append(RedirectInfo(
                    redirect_enabled=ri.get("redirectEnabled", True),
                    redirect_address_type=ri.get("redirectAddressType", "IPV4_ADDR"),
                    redirect_server_address=ri.get("redirectServerAddress", ""),
                ))
            self.traffic_control_profiles[tc_id] = TrafficControlData(
                tc_id=tc_id,
                flow_status=FlowStatus(tc.get("flowStatus", "ENABLED")),
                redirect_info=redirect,
                add_redirect_info=add_redirect,
                mute_notif=tc.get("muteNotif", False),
                traffic_steering_pol_id_dl=tc.get("trafficSteeringPolIdDl"),
                traffic_steering_pol_id_ul=tc.get("trafficSteeringPolIdUl"),
                route_to_locs=tc.get("routeToLocs", []),
                max_allowed_up_lat=tc.get("maxAllowedUpLat", 0),
                metadata=tc.get("metadata"),
                sim_conn_ind=tc.get("simConnInd", False),
                sim_conn_term=tc.get("simConnTerm", False),
                up_path_chg_event=tc.get("upPathChgEvent", False),
            )

    def _load_usage_monitoring(self, data: Dict):
        for um_id, um in data.items():
            self.usage_monitoring_profiles[um_id] = UsageMonitoringData(
                um_id=um_id,
                volume_threshold=um.get("volumeThreshold"),
                volume_threshold_uplink=um.get("volumeThresholdUplink"),
                volume_threshold_downlink=um.get("volumeThresholdDownlink"),
                time_threshold=um.get("timeThreshold"),
                monitoring_time=um.get("monitoringTime"),
                next_vol_threshold=um.get("nextVolThreshold"),
                next_vol_threshold_uplink=um.get("nextVolThresholdUplink"),
                next_vol_threshold_downlink=um.get("nextVolThresholdDownlink"),
                next_time_threshold=um.get("nextTimeThreshold"),
                inactivity_time=um.get("inactivityTime"),
                ex_usage_pcc_rule_ids=um.get("exUsagePccRuleIds", []),
            )

    def _load_conditions(self, data: Dict):
        for cond_id, cond in data.items():
            self.condition_profiles[cond_id] = ConditionData(
                cond_id=cond_id,
                activation_time=cond.get("activationTime"),
                deactivation_time=cond.get("deactivationTime"),
                access_type=cond.get("accessType", []),
                rat_type=cond.get("ratType", []),
                serving_nf_identity=cond.get("servingNfIdentity"),
            )

    def _load_predefined_rules(self, data: List[Dict]):
        for rule in data:
            flows = [FlowInformation(**f) for f in rule.get("flowInfos", [])]
            self.predefined_rules[rule["pccRuleId"]] = PccRule(
                pcc_rule_id=rule["pccRuleId"],
                precedence=rule.get("precedence", 255),
                flow_infos=flows,
                app_id=rule.get("appId"),
                ref_qos_data=rule.get("refQosData", []),
                ref_chg_data=rule.get("refChgData", []),
                ref_tc_data=rule.get("refTcData", []),
                ref_um_data=rule.get("refUmData", []),
                ref_cond_data=rule.get("refCondData", []),
                ref_alt_qos_params=rule.get("refAltQosParams", []),
                ref_qos_mon=rule.get("refQosMon"),
                af_sig_protocol=rule.get("afSigProtocol"),
                pcc_rule_status=PccRuleStatus(rule.get("pccRuleStatus", "ACTIVE")),
            )

    def _register_with_nrf(self):
        nrf_endpoint = self.config.get("nrf", {}).get("endpoint", "http://nrf:8080")
        try:
            resp = requests.put(
                f"{nrf_endpoint}/nnrf-nfm/v1/nf-instances/pcf-instance",
                json={
                    "nfInstanceId": "pcf-instance",
                    "nfType": "PCF",
                    "nfStatus": "REGISTERED",
                    "pcfInfo": {
                        "dnaiList": ["internet"],
                        "supiRanges": [{"start": "641080000000000", "end": "641089999999999"}],
                        "rxDiamHost": "pcf.example.com",
                        "rxDiamRealm": "example.com",
                    },
                    "ipv4Addresses": ["10.0.0.10"],
                    "fqdn": "pcf.example.com",
                    "capacity": 10000,
                    "load": 0,
                    "loadTimeStamp": datetime.utcnow().isoformat() + "Z",
                },
                timeout=5,
            )
            if resp.status_code in (200, 201):
                log.info("Registered with NRF")
            else:
                log.warning("NRF registration failed: %s", resp.status_code)
        except Exception as e:
            log.warning("Could not register with NRF: %s", e)

    def create_policy(self, context: SmPolicyContextData) -> Tuple[SmPolicyDecision, str]:
        sm_policy_id = str(uuid.uuid4())
        
        decision = SmPolicyDecision()
        decision.policy_ctrl_req_triggers = self.config.get("policy_control_request_triggers", [])
        
        self._apply_session_rules(decision, context)
        self._apply_pcc_rules(decision, context)
        self._resolve_references(decision)
        
        assoc = SmPolicyAssociation(
            sm_policy_id=sm_policy_id,
            context=context,
            decision=decision,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.associations[sm_policy_id] = assoc
        log.info("Created policy association %s for SUPI=%s DNN=%s", sm_policy_id, context.supi, context.dnn)
        return decision, sm_policy_id

    def _apply_session_rules(self, decision: SmPolicyDecision, context: SmPolicyContextData):
        for rule in self.session_rules.values():
            if self._evaluate_conditions(rule, context):
                decision.sess_rules[rule.sess_rule_id] = rule

    def _apply_pcc_rules(self, decision: SmPolicyDecision, context: SmPolicyContextData):
        dnn = context.dnn or "internet"
        slice_sst = context.slice_info.get("sst") if context.slice_info else None
        
        for rule in self.pcc_rules.values():
            if self._should_apply_rule(rule, context):
                decision.pcc_rules[rule.pcc_rule_id] = rule
        
        for rule in self.predefined_rules.values():
            if self._should_apply_rule(rule, context):
                decision.pcc_rules[rule.pcc_rule_id] = rule

    def _should_apply_rule(self, rule: PccRule, context: SmPolicyContextData) -> bool:
        if rule.pcc_rule_status != PccRuleStatus.ACTIVE:
            return False
        if rule.ref_cond_data:
            for cond_id in rule.ref_cond_data:
                if cond_id in self.condition_profiles:
                    if not self._evaluate_condition(self.condition_profiles[cond_id], context):
                        return False
        return True

    def _evaluate_conditions(self, obj, context: SmPolicyContextData) -> bool:
        if hasattr(obj, 'ref_cond_data'):
            for cond_id in obj.ref_cond_data:
                if cond_id in self.condition_profiles:
                    if not self._evaluate_condition(self.condition_profiles[cond_id], context):
                        return False
        return True

    def _evaluate_condition(self, cond: ConditionData, context: SmPolicyContextData) -> bool:
        now = datetime.utcnow()
        if cond.activation_time:
            act_time = datetime.fromisoformat(cond.activation_time.replace("Z", "+00:00"))
            if now < act_time:
                return False
        if cond.deactivation_time:
            deact_time = datetime.fromisoformat(cond.deactivation_time.replace("Z", "+00:00"))
            if now > deact_time:
                return False
        if cond.access_type and context.access_type:
            if context.access_type not in cond.access_type:
                return False
        if cond.rat_type and context.rat_type:
            if context.rat_type not in cond.rat_type:
                return False
        if cond.serving_nf_identity and context.serving_network:
            if cond.serving_nf_identity.startswith("!"):
                if context.serving_network == cond.serving_nf_identity[1:]:
                    return False
            elif context.serving_network != cond.serving_nf_identity:
                return False
        return True

    def _resolve_references(self, decision: SmPolicyDecision):
        for rule in decision.pcc_rules.values():
            for qos_ref in rule.ref_qos_data:
                if qos_ref in self.qos_profiles and qos_ref not in decision.qos_decs:
                    decision.qos_decs[qos_ref] = self.qos_profiles[qos_ref]
            for chg_ref in rule.ref_chg_data:
                if chg_ref in self.charging_profiles and chg_ref not in decision.chg_decs:
                    decision.chg_decs[chg_ref] = self.charging_profiles[chg_ref]
            for tc_ref in rule.ref_tc_data:
                if tc_ref in self.traffic_control_profiles and tc_ref not in decision.traff_cont_decs:
                    decision.traff_cont_decs[tc_ref] = self.traffic_control_profiles[tc_ref]
            for um_ref in rule.ref_um_data:
                if um_ref in self.usage_monitoring_profiles and um_ref not in decision.um_decs:
                    decision.um_decs[um_ref] = self.usage_monitoring_profiles[um_ref]
            for cond_ref in rule.ref_cond_data:
                if cond_ref in self.condition_profiles and cond_ref not in decision.conds:
                    decision.conds[cond_ref] = self.condition_profiles[cond_ref]

    def get_policy(self, sm_policy_id: str) -> Optional[SmPolicyAssociation]:
        return self.associations.get(sm_policy_id)

    def update_policy(self, sm_policy_id: str, update_data: Dict) -> Optional[SmPolicyDecision]:
        assoc = self.associations.get(sm_policy_id)
        if not assoc:
            return None
        
        context = assoc.context
        if "supi" in update_data:
            context.supi = update_data["supi"]
        if "gpsi" in update_data:
            context.gpsi = update_data["gpsi"]
        if "pduSessionId" in update_data:
            context.pdu_session_id = update_data["pduSessionId"]
        if "ipv4Address" in update_data:
            context.ipv4_address = update_data["ipv4Address"]
        if "ipv6AddressPrefix" in update_data:
            context.ipv6_address_prefix = update_data["ipv6AddressPrefix"]
        if "userLocationInfo" in update_data:
            context.user_location_info = update_data["userLocationInfo"]
        if "accessType" in update_data:
            context.access_type = update_data["accessType"]
        if "ratType" in update_data:
            context.rat_type = update_data["ratType"]
        if "servingNetwork" in update_data:
            context.serving_network = update_data["servingNetwork"]
        if "ueTimeZone" in update_data:
            context.ue_time_zone = update_data["ueTimeZone"]
        if "chargingCharacteristics" in update_data:
            context.charging_characteristics = update_data["chargingCharacteristics"]
        if "online" in update_data:
            context.online = update_data["online"]
        if "offline" in update_data:
            context.offline = update_data["offline"]
        
        if "repPolicyCtrlReqTriggers" in update_data:
            for trigger in update_data["repPolicyCtrlReqTriggers"]:
                self._handle_trigger(assoc, trigger, update_data)
        
        decision = SmPolicyDecision()
        decision.policy_ctrl_req_triggers = self.config.get("policy_control_request_triggers", [])
        self._apply_session_rules(decision, context)
        self._apply_pcc_rules(decision, context)
        self._resolve_references(decision)
        
        assoc.decision = decision
        assoc.updated_at = datetime.utcnow()
        return decision

    def _handle_trigger(self, assoc: SmPolicyAssociation, trigger: str, data: Dict):
        log.info("Handling PCRT %s for policy %s", trigger, assoc.sm_policy_id)
        
        if trigger == PCRT.APP_STA.value:
            app_id = data.get("appDetectionInfos", [{}])[0].get("appId")
            if app_id:
                self._activate_app_rules(assoc, app_id)
        
        elif trigger == PCRT.APP_STO.value:
            app_id = data.get("appDetectionInfos", [{}])[0].get("appId")
            if app_id:
                self._deactivate_app_rules(assoc, app_id)
        
        elif trigger == PCRT.OUT_OF_CREDIT.value:
            self._handle_out_of_credit(assoc, data)
        
        elif trigger == PCRT.REALLO_CREDIT.value:
            self._handle_realloc_credit(assoc, data)
        
        elif trigger == PCRT.UE_IP_CH.value:
            if "ipv4Address" in data:
                assoc.context.ipv4_address = data["ipv4Address"]
            if "ipv6AddressPrefix" in data:
                assoc.context.ipv6_address_prefix = data["ipv6AddressPrefix"]
        
        elif trigger == PCRT.LOC_CH.value:
            if "userLocationInfo" in data:
                assoc.context.user_location_info = data["userLocationInfo"]
        
        elif trigger == PCRT.AC_TY_CH.value:
            if "accessType" in data:
                assoc.context.access_type = data["accessType"]
        
        elif trigger == PCRT.RAT_TY_CH.value:
            if "ratType" in data:
                assoc.context.rat_type = data["ratType"]

    def _activate_app_rules(self, assoc: SmPolicyAssociation, app_id: str):
        for rule in self.predefined_rules.values():
            if rule.app_id == app_id:
                assoc.decision.pcc_rules[rule.pcc_rule_id] = rule
        log.info("Activated rules for app %s", app_id)

    def _deactivate_app_rules(self, assoc: SmPolicyAssociation, app_id: str):
        to_remove = [rid for rid, rule in assoc.decision.pcc_rules.items() if rule.app_id == app_id]
        for rid in to_remove:
            del assoc.decision.pcc_rules[rid]
        log.info("Deactivated rules for app %s", app_id)

    def _handle_out_of_credit(self, assoc: SmPolicyAssociation, data: Dict):
        charging_key = data.get("chargingKey")
        if charging_key:
            for rule in assoc.decision.pcc_rules.values():
                if any(chg == charging_key for chg in rule.ref_chg_data):
                    for tc_ref in rule.ref_tc_data:
                        if tc_ref in self.traffic_control_profiles:
                            tc = self.traffic_control_profiles[tc_ref]
                            tc.flow_status = FlowStatus.DISABLED
                            if tc.redirect_info:
                                tc.redirect_info.redirect_enabled = True
        log.warning("Out of credit for policy %s", assoc.sm_policy_id)

    def _handle_realloc_credit(self, assoc: SmPolicyAssociation, data: Dict):
        charging_key = data.get("chargingKey")
        if charging_key:
            for rule in assoc.decision.pcc_rules.values():
                if any(chg == charging_key for chg in rule.ref_chg_data):
                    for tc_ref in rule.ref_tc_data:
                        if tc_ref in self.traffic_control_profiles:
                            tc = self.traffic_control_profiles[tc_ref]
                            tc.flow_status = FlowStatus.ENABLED
                            if tc.redirect_info:
                                tc.redirect_info.redirect_enabled = False
        log.info("Credit reallocated for policy %s", assoc.sm_policy_id)

    def delete_policy(self, sm_policy_id: str) -> bool:
        if sm_policy_id in self.associations:
            del self.associations[sm_policy_id]
            log.info("Deleted policy association %s", sm_policy_id)
            return True
        return False

    def notify_policy_update(self, sm_policy_id: str):
        assoc = self.associations.get(sm_policy_id)
        if not assoc or not assoc.context.notification_uri:
            return
        
        notification = {
            "smPolicyId": sm_policy_id,
            "policyDecision": self._decision_to_json(assoc.decision),
        }
        
        try:
            resp = requests.post(
                assoc.context.notification_uri,
                json=notification,
                timeout=5,
            )
            log.info("Policy update notification sent to %s: %s", assoc.context.notification_uri, resp.status_code)
        except Exception as e:
            log.warning("Failed to send policy notification: %s", e)

    def _decision_to_json(self, decision: SmPolicyDecision) -> Dict:
        return {
            "pccRules": {k: self._pcc_rule_to_json(v) for k, v in decision.pcc_rules.items()},
            "sessRules": {k: self._session_rule_to_json(v) for k, v in decision.sess_rules.items()},
            "qosDecs": {k: self._qos_data_to_json(v) for k, v in decision.qos_decs.items()},
            "chgDecs": {k: self._charging_data_to_json(v) for k, v in decision.chg_decs.items()},
            "traffContDecs": {k: self._traffic_control_to_json(v) for k, v in decision.traff_cont_decs.items()},
            "umDecs": {k: self._usage_monitoring_to_json(v) for k, v in decision.um_decs.items()},
            "conds": {k: self._condition_to_json(v) for k, v in decision.conds.items()},
            "policyCtrlReqTriggers": decision.policy_ctrl_req_triggers,
            "lastReqRuleData": decision.last_req_rule_data,
            "lastReqUsageData": decision.last_req_usage_data,
        }

    def _pcc_rule_to_json(self, rule: PccRule) -> Dict:
        return {
            "pccRuleId": rule.pcc_rule_id,
            "precedence": rule.precedence,
            "flowInfos": [{"flowDescription": f.flow_description, "flowDirection": f.flow_direction, "flowId": f.flow_id} for f in rule.flow_infos],
            "appId": rule.app_id,
            "refQosData": rule.ref_qos_data,
            "refChgData": rule.ref_chg_data,
            "refTcData": rule.ref_tc_data,
            "refUmData": rule.ref_um_data,
            "refCondData": rule.ref_cond_data,
            "refAltQosParams": rule.ref_alt_qos_params,
            "refQosMon": rule.ref_qos_mon,
            "afSigProtocol": rule.af_sig_protocol,
            "pccRuleStatus": rule.pcc_rule_status.value,
        }

    def _session_rule_to_json(self, rule: SessionRule) -> Dict:
        return {
            "sessRuleId": rule.sess_rule_id,
            "authSessAmbr": rule.auth_sess_ambr,
            "authDefQos": rule.auth_def_qos,
            "pccRuleStatus": rule.pcc_rule_status.value,
        }

    def _qos_data_to_json(self, qos: QosData) -> Dict:
        return {
            "qosId": qos.qos_id,
            "5qi": qos.five_qi,
            "maxbrUl": qos.maxbr_ul,
            "maxbrDl": qos.maxbr_dl,
            "gbrUl": qos.gbr_ul,
            "gbrDl": qos.gbr_dl,
            "arp": {
                "priorityLevel": qos.arp.priority_level,
                "preemptCap": qos.arp.preempt_cap,
                "preemptVuln": qos.arp.preempt_vuln,
            } if qos.arp else None,
            "priorityLevel": qos.priority_level,
            "averWindow": qos.aver_window,
            "maxDataBurstVol": qos.max_data_burst_vol,
            "qnc": qos.qnc,
            "reflectiveQos": qos.reflective_qos,
            "sharingKeyDl": qos.sharing_key_dl,
            "sharingKeyUl": qos.sharing_key_ul,
        }

    def _charging_data_to_json(self, chg: ChargingData) -> Dict:
        return {
            "chgId": chg.chg_id,
            "meteringMethod": chg.metering_method.value,
            "offline": chg.offline,
            "online": chg.online,
            "ratingGroup": chg.rating_group,
            "serviceId": chg.service_id,
            "sponsorId": chg.sponsor_id,
            "appSvcProvId": chg.app_svc_prov_id,
            "afChargingIdentifier": chg.af_charging_identifier,
            "reportingLevel": chg.reporting_level.value,
            "sdfHandl": chg.sdf_handl.value,
        }

    def _traffic_control_to_json(self, tc: TrafficControlData) -> Dict:
        return {
            "tcId": tc.tc_id,
            "flowStatus": tc.flow_status.value,
            "redirectInfo": {
                "redirectEnabled": tc.redirect_info.redirect_enabled,
                "redirectAddressType": tc.redirect_info.redirect_address_type,
                "redirectServerAddress": tc.redirect_info.redirect_server_address,
            } if tc.redirect_info else None,
            "addRedirectInfo": [
                {
                    "redirectEnabled": r.redirect_enabled,
                    "redirectAddressType": r.redirect_address_type,
                    "redirectServerAddress": r.redirect_server_address,
                }
                for r in tc.add_redirect_info
            ],
            "muteNotif": tc.mute_notif,
            "trafficSteeringPolIdDl": tc.traffic_steering_pol_id_dl,
            "trafficSteeringPolIdUl": tc.traffic_steering_pol_id_ul,
            "routeToLocs": tc.route_to_locs,
            "maxAllowedUpLat": tc.max_allowed_up_lat,
            "metadata": tc.metadata,
            "simConnInd": tc.sim_conn_ind,
            "simConnTerm": tc.sim_conn_term,
            "upPathChgEvent": tc.up_path_chg_event,
        }

    def _usage_monitoring_to_json(self, um: UsageMonitoringData) -> Dict:
        return {
            "umId": um.um_id,
            "volumeThreshold": um.volume_threshold,
            "volumeThresholdUplink": um.volume_threshold_uplink,
            "volumeThresholdDownlink": um.volume_threshold_downlink,
            "timeThreshold": um.time_threshold,
            "monitoringTime": um.monitoring_time,
            "nextVolThreshold": um.next_vol_threshold,
            "nextVolThresholdUplink": um.next_vol_threshold_uplink,
            "nextVolThresholdDownlink": um.next_vol_threshold_downlink,
            "nextTimeThreshold": um.next_time_threshold,
            "inactivityTime": um.inactivity_time,
            "exUsagePccRuleIds": um.ex_usage_pcc_rule_ids,
        }

    def _condition_to_json(self, cond: ConditionData) -> Dict:
        return {
            "condId": cond.cond_id,
            "activationTime": cond.activation_time,
            "deactivationTime": cond.deactivation_time,
            "accessType": cond.access_type,
            "ratType": cond.rat_type,
            "servingNfIdentity": cond.serving_nf_identity,
        }


class PCFHandler(BaseHTTPRequestHandler):
    engine: PCFEngine = None

    def _send(self, code: int, payload: Dict = None):
        body = json.dumps(payload).encode("utf-8") if payload else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
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
            self._send(200, {"status": "ok", "nf": "pcf", "associations": len(self.engine.associations)})
            return
        
        if self.path.startswith("/npcf-smpolicycontrol/v1/sm-policies"):
            parts = self.path.split("/")
            if len(parts) > 5 and parts[5]:
                sm_policy_id = parts[5]
                assoc = self.engine.get_policy(sm_policy_id)
                if assoc:
                    self._send(200, self.engine._decision_to_json(assoc.decision))
                else:
                    self._send(404, {"cause": "SM_POLICY_NOT_FOUND"})
            else:
                policies = [self.engine._decision_to_json(a.decision) for a in self.engine.associations.values()]
                self._send(200, {"policies": policies})
            return
        
        self._send(404, {"cause": "NOT_FOUND"})

    def do_POST(self):
        if self.path == "/npcf-smpolicycontrol/v1/sm-policies":
            body = self._parse_json_body()
            context = SmPolicyContextData(
                supi=body.get("supi", ""),
                gpsi=body.get("gpsi"),
                pdu_session_id=body.get("pduSessionId", 0),
                pdu_session_type=body.get("pduSessionType"),
                dnn=body.get("dnn"),
                slice_info=body.get("sliceInfo"),
                serving_network=body.get("servingNetwork"),
                user_location_info=body.get("userLocationInfo"),
                ue_time_zone=body.get("ueTimeZone"),
                pei=body.get("pei"),
                access_type=body.get("accessType"),
                rat_type=body.get("ratType"),
                ipv4_address=body.get("ipv4Address"),
                ipv6_address_prefix=body.get("ipv6AddressPrefix"),
                subs_sess_ambr=body.get("subsSessAmbr"),
                subs_def_qos=body.get("subsDefQos"),
                charging_characteristics=body.get("chargingCharacteristics"),
                online=body.get("online", False),
                offline=body.get("offline", False),
                notification_uri=body.get("notificationUri"),
                supp_feat=body.get("suppFeat"),
            )
            decision, sm_policy_id = self.engine.create_policy(context)
            self.send_response(201)
            self.send_header("Location", f"/npcf-smpolicycontrol/v1/sm-policies/{sm_policy_id}")
            self.send_header("Content-Type", "application/json")
            body_json = json.dumps(self.engine._decision_to_json(decision)).encode("utf-8")
            self.send_header("Content-Length", str(len(body_json)))
            self.end_headers()
            self.wfile.write(body_json)
            return
        
        parts = self.path.split("/")
        if len(parts) >= 6 and parts[5] and parts[6] == "update":
            sm_policy_id = parts[5]
            body = self._parse_json_body()
            decision = self.engine.update_policy(sm_policy_id, body)
            if decision:
                self._send(200, self.engine._decision_to_json(decision))
            else:
                self._send(404, {"cause": "SM_POLICY_NOT_FOUND"})
            return
        
        if len(parts) >= 6 and parts[5] and parts[6] == "delete":
            sm_policy_id = parts[5]
            if self.engine.delete_policy(sm_policy_id):
                self._send(204)
            else:
                self._send(404, {"cause": "SM_POLICY_NOT_FOUND"})
            return
        
        self._send(404, {"cause": "NOT_FOUND"})

    def do_DELETE(self):
        if self.path.startswith("/npcf-smpolicycontrol/v1/sm-policies/"):
            parts = self.path.split("/")
            if len(parts) >= 6 and parts[5]:
                sm_policy_id = parts[5]
                if self.engine.delete_policy(sm_policy_id):
                    self._send(204)
                else:
                    self._send(404, {"cause": "SM_POLICY_NOT_FOUND"})
            return
        self._send(404, {"cause": "NOT_FOUND"})

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


def main():
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    
    PCFHandler.engine = PCFEngine(config)
    
    host = config.get("host", "0.0.0.0")
    port = config.get("port", 7777)
    
    log.info("Starting PCF on %s:%s", host, port)
    log.info("PCC rules loaded: %d", len(PCFHandler.engine.pcc_rules))
    log.info("QoS profiles: %d", len(PCFHandler.engine.qos_profiles))
    log.info("Charging profiles: %d", len(PCFHandler.engine.charging_profiles))
    log.info("Traffic control profiles: %d", len(PCFHandler.engine.traffic_control_profiles))
    log.info("Usage monitoring profiles: %d", len(PCFHandler.engine.usage_monitoring_profiles))
    log.info("Condition profiles: %d", len(PCFHandler.engine.condition_profiles))
    log.info("Predefined rules: %d", len(PCFHandler.engine.predefined_rules))
    
    server = HTTPServer((host, port), PCFHandler)
    
    def shutdown(*_):
        log.info("Shutting down PCF")
        server.shutdown()
    
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    server.serve_forever()


if __name__ == "__main__":
    main()