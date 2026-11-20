// API Types for 5G Core OAM Dashboard

// Common
export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface ApiError {
  detail: string
  code?: string
}

// Subscriber Types
export interface Subscriber {
  imsi: string
  msisdn?: string
  imei?: string
  imei_sv?: string
  k?: string
  ki?: string
  op?: string
  opc?: string
  sqn: number
  amf: string
  k_asme?: string
  k_seaf?: string
  k_ausf?: string
  kc?: string
  sres?: string
  network_access_mode: number
  subscriber_status: number
  roaming_restricted: boolean
  regional_restriction?: Record<string, any>
  odb_data?: Record<string, any>
  trace_config?: Record<string, any>
  prose_enabled: boolean
  redcap_allowed: boolean
  ntn_allowed: boolean
  eredcap_allowed: boolean
  xr_allowed: boolean
  aiml_allowed: boolean
  ambr_ul: number
  ambr_dl: number
  batch_id?: string
  imsi_range_start?: string
  imsi_range_end?: string
  mvno_mcc?: string
  mvno_mnc?: string
  created_at: string
  updated_at: string
}

export interface SubscriberCreate {
  imsi: string
  msisdn?: string
  imei?: string
  imei_sv?: string
  k?: string
  ki?: string
  op?: string
  opc?: string
  sqn?: number
  amf?: string
  k_asme?: string
  k_seaf?: string
  k_ausf?: string
  kc?: string
  sres?: string
  network_access_mode?: number
  subscriber_status?: number
  roaming_restricted?: boolean
  regional_restriction?: Record<string, any>
  odb_data?: Record<string, any>
  trace_config?: Record<string, any>
  prose_enabled?: boolean
  redcap_allowed?: boolean
  ntn_allowed?: boolean
  eredcap_allowed?: boolean
  xr_allowed?: boolean
  aiml_allowed?: boolean
  ambr_ul?: number
  ambr_dl?: number
  batch_id?: string
  imsi_range_start?: string
  imsi_range_end?: string
  mvno_mcc?: string
  mvno_mnc?: string
}

export interface SubscriberUpdate {
  msisdn?: string
  imei?: string
  imei_sv?: string
  k?: string
  ki?: string
  op?: string
  opc?: string
  sqn?: number
  amf?: string
  k_asme?: string
  k_seaf?: string
  k_ausf?: string
  kc?: string
  sres?: string
  network_access_mode?: number
  subscriber_status?: number
  roaming_restricted?: boolean
  regional_restriction?: Record<string, any>
  odb_data?: Record<string, any>
  trace_config?: Record<string, any>
  prose_enabled?: boolean
  redcap_allowed?: boolean
  ntn_allowed?: boolean
  eredcap_allowed?: boolean
  xr_allowed?: boolean
  aiml_allowed?: boolean
  ambr_ul?: number
  ambr_dl?: number
  batch_id?: string
}

// Full Profile
export interface FullProfile {
  subscriber: Subscriber
  eps?: EPSSubscription
  fiveg?: FiveGSubscription
  ims?: IMSSubscription
  apn_profiles: APNProfile[]
  supplementary_services: SupplementaryService[]
  roaming_profiles: RoamingProfile[]
  camel_profiles: CamelServiceProfile[]
}

// Subscription Types
export interface EPSSubscription {
  imsi: string
  apn_config?: Record<string, any>
  default_apn?: string
  ue_ambr_ul: number
  ue_ambr_dl: number
  rat_restrictions?: Record<string, any>
  msisdn_list?: Record<string, any>
  csg_subscription?: Record<string, any>
  mme_subscription?: Record<string, any>
  hss_subscription?: Record<string, any>
  lcs_privacy?: Record<string, any>
  vplmn_dynamic?: Record<string, any>
  nb_iot_allowed: boolean
  emtc_allowed: boolean
  v2x_allowed: boolean
  industrial_iot_allowed: boolean
  redcap_allowed: boolean
  created_at: string
  updated_at: string
}

export interface FiveGSubscription {
  imsi: string
  supi?: string
  suci_calc_info?: Record<string, any>
  default_nssai?: Record<string, any>
  allowed_nssai?: Record<string, any>
  ue_ambr_ul: number
  ue_ambr_dl: number
  rat_restrictions_5g?: Record<string, any>
  smf_selection?: Record<string, any>
  gmlc_address?: string
  lcs_privacy_5g?: Record<string, any>
  sor_info?: Record<string, any>
  ue_id_mapping?: Record<string, any>
  nssaa_info?: Record<string, any>
  vplmn_5g_data?: Record<string, any>
  urllc_allowed: boolean
  mmtc_allowed: boolean
  v2x_allowed_5g: boolean
  redcap_allowed_5g: boolean
  ntn_allowed_5g: boolean
  pni_npn_allowed: boolean
  eredcap_allowed_5g: boolean
  mbs_allowed: boolean
  xr_allowed_5g: boolean
  aiml_allowed_5g: boolean
  multicast_mbs_allowed: boolean
  reduced_cap_allowed: boolean
  aiml_enhanced_allowed: boolean
  created_at: string
  updated_at: string
}

export interface IMSSubscription {
  imsi: string
  impu_list?: Record<string, any>
  impi?: string
  ims_domain?: string
  service_profile_id?: string
  scscf_name?: string
  scscf_realm?: string
  reg_status: string
  reg_expires: number
  contact_list?: Record<string, any>
  auth_scheme: string
  wildcarded_impu: boolean
  mtsi_allowed: boolean
  rcs_allowed: boolean
  nr_multicast_allowed: boolean
  emtsi_allowed: boolean
  created_at: string
  updated_at: string
}

// Profile Types
export interface APNProfile {
  id: number
  imsi: string
  apn: string
  apn_type: string
  qci: number
  arp_priority: number
  arp_preempt_cap: boolean
  arp_preempt_vuln: boolean
  apn_ambr_ul: number
  apn_ambr_dl: number
  ue_ambr_ul: number
  ue_ambr_dl: number
  pcc_rule_name?: string
  pcc_rule_version: number
  pdn_type: string
  ipv4_addr_alloc: string
  ipv6_prefix_len: number
  static_ipv4?: string
  static_ipv6?: string
  dns_primary: string
  dns_secondary: string
  pgw_fqdn?: string
  pgw_ipv4?: string
  pgw_ipv6?: string
  sgw_fqdn?: string
  sgw_ipv4?: string
  charging_id: number
  charging_gateway?: string
  is_emergency: boolean
  dnn_selection_mode: string
  mvno_reseller_id?: string
  urllc_qos: boolean
  redcap_qos: boolean
  mbs_qos: boolean
  is_default: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SupplementaryService {
  id: number
  imsi: string
  service_code: string
  service_name?: string
  provision_status: string
  activation_code?: string
  deactivation_code?: string
  interrogation_code?: string
  registration_code?: string
  erasure_code?: string
  forwarding_number?: string
  forwarding_condition: string
  no_reply_timer: number
  override_category: string
  max_simultaneous_calls: number
  clip_provisioned: boolean
  clir_provisioned: boolean
  clir_option: string
  ussd_enabled: boolean
  ussd_string_length: number
  camel_phase: number
  camel_tdp_list?: Record<string, any>
  mmtel_allowed: boolean
  rcs_allowed: boolean
  created_at: string
  updated_at: string
}

export interface RoamingProfile {
  id: number
  imsi: string
  visited_plmn: string
  roaming_allowed: boolean
  rat_allowed?: Record<string, any>
  odb_roaming: boolean
  odb_outgoing: boolean
  odb_incoming: boolean
  odb_premium: boolean
  ho_restriction?: Record<string, any>
  charging_profile_id?: string
  v_mme_fqdn?: string
  v_mme_ipv4?: string
  v_sgsn_fqdn?: string
  v_sgsn_ipv4?: string
  v_pgw_fqdn?: string
  v_pgw_ipv4?: string
  v_amf_fqdn?: string
  v_amf_ipv4?: string
  v_smf_fqdn?: string
  v2x_roaming: boolean
  redcap_roaming: boolean
  ntn_roaming: boolean
  created_at: string
  updated_at: string
}

export interface CamelServiceProfile {
  id: number
  imsi: string
  service_key: number
  tdp_list?: Record<string, any>
  gsm_scf_address: string
  default_call_handling: string
  csi_psi?: Record<string, any>
  csi_csi?: Record<string, any>
  csi_ssi?: Record<string, any>
  csi_msi?: Record<string, any>
  csi_lsi?: Record<string, any>
  csi_v2x?: Record<string, any>
  csi_redcap?: Record<string, any>
  created_at: string
  updated_at: string
}

// Auth Vector
export interface AuthVector {
  imsi: string
  rand_5g?: string
  autn_5g?: string
  xres_5g?: string
  k_ausf?: string
  k_seaf?: string
  k_amf?: string
  rand_4g?: string
  autn_4g?: string
  xres_4g?: string
  ck_4g?: string
  ik_4g?: string
  k_asme_4g?: string
  rand_3g?: string
  autn_3g?: string
  xres_3g?: string
  ck_3g?: string
  ik_3g?: string
  rand_2g?: string
  sres_2g?: string
  kc_2g?: string
  rand_redcap?: string
  generated_at: string
  expires_at?: string
  algorithm: string
  opc_used?: string
  sqn_used?: number
}

export interface AuthVectorGenerateRequest {
  rand?: string
  algorithm?: string
  count?: number
}

export interface AuthVectorResponse {
  vectors: AuthVector[]
}

// Batch Upload
export interface BatchUpload {
  id: number
  batch_id: string
  filename?: string
  total_records: number
  successful_records: number
  failed_records: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error_log?: Record<string, any>
  created_by?: string
  created_at: string
  completed_at?: string
}

export interface BatchUploadRequest {
  file: File
  batch_id?: string
  auto_derive?: boolean
  default_ki?: string
  default_op?: string
  default_k?: string
  default_network_access_mode?: number
  default_subscriber_status?: number
}

// IMSI Range
export interface IMSIRange {
  id: number
  range_name: string
  mcc: string
  mnc: string
  msisdn_prefix?: string
  imsi_start: string
  imsi_end: string
  next_imsi: string
  allocated_count: number
  total_count: number
  status: 'available' | 'exhausted' | 'reserved'
  mvno_id?: string
  default_k?: string
  default_ki?: string
  default_op?: string
  default_opc?: string
  default_algorithm: string
  created_at: string
}

export interface IMSIRangeCreate {
  range_name: string
  mcc: string
  mnc: string
  msisdn_prefix?: string
  imsi_start: string
  imsi_end: string
  default_k?: string
  default_ki?: string
  default_op?: string
  default_opc?: string
  default_algorithm?: string
  mvno_id?: string
}

export interface IMSIAllocateRequest {
  range_name: string
  count: number
}

export interface IMSIAllocateResponse {
  allocated_imsis: string[]
  count: number
}

// USSD Route
export interface USSDRoute {
  id: number
  ussd_string: string
  destination_type: string
  destination_address?: string
  gsm_scf_address?: string
  service_key: number
  default_response?: string
  timeout_sec: number
  mvno_mcc?: string
  mvno_mnc?: string
  fiveg_ussd_allowed: boolean
  is_active: boolean
  priority: number
  created_at: string
  updated_at: string
}

// Network Node
export interface NetworkNode {
  id: number
  node_name: string
  node_type: string
  fqdn?: string
  ipv4?: string
  ipv6?: string
  diameter_host?: string
  diameter_realm?: string
  diameter_port: number
  sctp_port: number
  point_code?: string
  global_title?: string
  gt_translation_type: number
  gt_numbering_plan: number
  gt_nature_of_address: number
  plmn_id?: string
  supported_interfaces?: Record<string, any>
  is_active: boolean
  health_check_url?: string
  created_at: string
  updated_at: string
}

export interface NetworkNodeCreate {
  node_name: string
  node_type: string
  fqdn?: string
  ipv4?: string
  ipv6?: string
  diameter_host?: string
  diameter_realm?: string
  diameter_port?: number
  sctp_port?: number
  point_code?: string
  global_title?: string
  gt_translation_type?: number
  gt_numbering_plan?: number
  gt_nature_of_address?: number
  plmn_id?: string
  supported_interfaces?: Record<string, any>
  is_active?: boolean
  health_check_url?: string
}

// Reference Data
export interface MCCMNC {
  id: number
  mcc: string
  mnc: string
  country_name?: string
  network_name?: string
  network_type: 'MNO' | 'MVNO' | 'Test'
  parent_mcc?: string
  parent_mnc?: string
  is_active: boolean
  created_at: string
}

export interface PLMNProfile {
  id: number
  plmn_id: string
  plmn_name?: string
  eps_supported: boolean
  fiveg_supported: boolean
  redcap_supported: boolean
  ntn_supported: boolean
  fiveg_advanced_supported: boolean
  hplmn_allowed: boolean
  vplmn_allowed: boolean
  diameter_realm?: string
  tac_range_start: number
  tac_range_end: number
  created_at: string
}

// DRA Types
export interface DRALocal {
  id: number
  instance_id: string
  name: string
  ip: string
  port: number
  protocol: string
  realm: string
  host: string
  vendor_id: number
  application_ids: string
  product_name: string
  tls_flag: boolean
  crt_file_name: string
  key_file_name: string
}

export interface DRAPeerSet {
  peerset_id: number
  instance_id: string
  name: string
  mode: string
}

export interface DRAPeer {
  peer_id: number
  instance_id: string
  name: string
  local: number
  local_name: string
  peer_set: number
  peer_set_name: string
  remote_ip: string
  remote_port: number
  remote_host: string
  remote_realm: string
  remote_type: string
  protocol: string
  priority: number
  enable: boolean
  application_ids: string
  vendor_id: number
  product_name: string
  tls_flag: boolean
  crt_file_name: string
  key_file_name: string
  loop_flag: boolean
  watchdog_interval: number
  retransmit_timer: number
  max_retransmit: number
}

export interface DRARoute {
  route_id: number
  instance_id: string
  name: string
  origin_peer_set: number
  origin_peer_set_name: string
  dest_peer_set: number
  dest_peer_set_name: string
  imsi?: string
  impi?: string
  impu?: string
  ip_addr?: string
  msisdn?: string
  origin_host?: string
  application_id?: string
  origin_realm?: string
  destination_host?: string
  destination_realm?: string
  priority: number
}

export interface DRATranslate {
  translate_id: number
  instance_id: string
  name: string
  origin_peer_set: number
  origin_peer_set_name: string
  dest_peer_set: number
  dest_peer_set_name: string
  avp_code: number
  avp_type: string
  avp_value: string
  command_code: number
  application_ids: string
  set_session_id: boolean
}

// STP Types
export interface M3UAGlobal {
  id: number
  instance_id: string
  name: string
  audit_interval: number
  multiple_network_appearances: string
  max_deactivate_attempts: number
  fsm_timeout: number
  tx_buffer_size: number
  rx_buffer_size: number
  max_ingress_streams: number
  num_egress_streams: number
  hb_interval: number
  cong_onset_level1: number
  cong_abatement_level1: number
  cong_onset_level2: number
  cong_abatement_level2: number
  cong_onset_level3: number
  cong_abatement_level3: number
  cong_report_frequency: number
}

export interface M3UALocal {
  id: number
  instance_id: string
  name: string
  local_point_code: string
  point_code_length: number
  network_indicator: string
}

export interface M3UALinkset {
  id: number
  instance_id: string
  name: string
  m3ua_local: string
  adjacent_point_code: string
  traffic_mode: string
}

export interface M3UALink {
  id: number
  instance_id: string
  name: string
  linkset_name: string
  local_ip_addr: string
  local_port: number
  remote_ip_addr: string
  remote_port: number
  link_type: string
  compat_mode: string
  max_ingress_streams: number
  num_egress_streams: number
  association_creation: string
  max_path_mtu: number
  network_appearance: number
  link_status: string
}

export interface STPRoute {
  id: number
  instance_id: string
  name: string
  enable: number
  priority: number
  linkset_ingress: string
  linkset_egress: string
  calling_gt: string
  called_gt: string
  imsi: string
  translate_group: string
  route_mode: string
  called_identity: number
}

export interface STPTranslate {
  tid: number
  instance_id: string
  name: string
  spc_rule: string
  spc: string
  dpc: string
  spc_ni: string
  calling_rule: string
  called_rule: string
  calling_origin: string
  calling_dest: string
  called_origin: string
  called_dest: string
}

// UECM
export interface UECMRegistration {
  id: number
  imsi: string
  access_type: '3GPP' | 'non-3GPP'
  registration_data?: Record<string, any>
  registered_at: string
  updated_at: string
}

// KPI Types
export interface KPIData {
  active_ues: number
  pdu_sessions: number
  throughput_ul_mbps: number
  throughput_dl_mbps: number
  auth_success_rate: number
  registration_success_rate: number
  handover_success_rate: number
  latency_ms: number
}

export interface KPITimeSeries {
  timestamp: string
  active_ues: number
  pdu_sessions: number
  throughput_ul_mbps: number
  throughput_dl_mbps: number
  auth_success_rate: number
  registration_success_rate: number
  handover_success_rate: number
  latency_ms: number
}