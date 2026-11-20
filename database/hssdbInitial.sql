-- ============================================================================
-- hssdbInitial.sql - UDM/HSS/HLR Subscriber Database Schema
-- 3GPP TS 23.008, 29.503, 29.504, 29.272, 29.002, 33.501, 23.501/502/503
-- TS 29.228/229 (IMS), TS 23.011/018/078 (Supplementary), TS 23.060/401 (APN)
-- Release: 3GPP Rel-15 through Rel-20 (R20) features included
-- ============================================================================

CREATE DATABASE IF NOT EXISTS hssdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hssdb;

-- ============================================================================
-- REFERENCE TABLES (MCC/MNC/PLMN Management for MVNO hosting)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_mcc_mnc (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    mcc CHAR(3) NOT NULL,
    mnc CHAR(3) NOT NULL,
    country_name VARCHAR(100),
    network_name VARCHAR(100),
    network_type ENUM('MNO','MVNO','Test') DEFAULT 'MNO',
    parent_mcc CHAR(3), parent_mnc CHAR(3),  -- For MVNO hosting
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_mcc_mnc (mcc, mnc)
) ENGINE=InnoDB COMMENT='MCC/MNC Registry per TS 23.003 (Rel-15+)';

CREATE TABLE IF NOT EXISTS tbl_plmn_profile (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    plmn_id CHAR(6) NOT NULL COMMENT 'MCC+MNC',
    plmn_name VARCHAR(100),
    -- EPS/5G Capabilities
    eps_supported TINYINT(1) DEFAULT 1,
    fiveg_supported TINYINT(1) DEFAULT 1,
    -- Rel-17 NR RedCap
    redcap_supported TINYINT(1) DEFAULT 0,
    -- Rel-18 NR-NTN
    ntn_supported TINYINT(1) DEFAULT 0,
    -- Rel-19 5G-Advanced
    fiveg_advanced_supported TINYINT(1) DEFAULT 0,
    -- Roaming
    hplmn_allowed TINYINT(1) DEFAULT 1,
    vplmn_allowed TINYINT(1) DEFAULT 1,
    -- Diameter Realm for S6a/Nudm
    diameter_realm VARCHAR(255) COMMENT 'e.g., mnc001.mcc310.3gppnetwork.org',
    -- Network identifiers
    tac_range_start INT UNSIGNED DEFAULT 1,
    tac_range_end INT UNSIGNED DEFAULT 65535,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_plmn (plmn_id)
) ENGINE=InnoDB COMMENT='PLMN Profile per TS 23.003/23.501 (Rel-15 to Rel-20)';

-- ============================================================================
-- CORE SUBSCRIBER (TS 23.008 Organization of Subscriber Data)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_subscriber (
    imsi VARCHAR(15) NOT NULL,
    msisdn VARCHAR(15),
    imei VARCHAR(15),
    imei_sv VARCHAR(16),
    -- Root Keys (TS 33.102/33.501)
    k VARCHAR(32) COMMENT '5G Root Key (K4) - 256-bit hex',
    ki VARCHAR(32) COMMENT '4G/3G/2G Root Key (Ki) - 128-bit hex',
    -- OP/OPc (TS 33.102)
    op VARCHAR(32) COMMENT 'OP (Operator Variant) - 128-bit hex',
    opc VARCHAR(32) COMMENT 'OPc (Derived) - 128-bit hex',
    -- Sequence & AMF
    sqn BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'SQN for AKA (48-bit)',
    sqn_heuristic TINYINT(1) DEFAULT 1 COMMENT 'SQN check heuristic',
    amf VARCHAR(8) DEFAULT '8000' COMMENT 'Authentication Management Field',
    -- Derived 5G Keys (TS 33.501 Annex A)
    k_asme VARCHAR(32) COMMENT 'K_ASME',
    k_seaf VARCHAR(32) COMMENT 'K_SEAF',
    k_ausf VARCHAR(32) COMMENT 'K_AUSF',
    -- 2G/3G Cipher (TS 33.102)
    kc VARCHAR(16) COMMENT 'Kc (64-bit hex)',
    sres VARCHAR(8) COMMENT 'SRES (32-bit hex)',
    -- Network Access (TS 23.008)
    network_access_mode TINYINT UNSIGNED NOT NULL DEFAULT 2 COMMENT '0=GPRS,1=CS,2=Both,3=5G',
    subscriber_status TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0=Active,1=Barred,2=Suspended,3=Detached',
    roaming_restricted TINYINT(1) DEFAULT 0,
    -- Regional Restrictions (TS 23.060)
    regional_restriction JSON COMMENT 'Allowed/forbidden area codes',
    -- Operator Determined Barring (TS 29.272/29.503)
    odb_data JSON COMMENT 'ODB: roaming, outgoing, incoming, etc.',
    -- Trace/MDT (TS 32.422/423)
    trace_config JSON COMMENT 'Trace reference, depth, events',
    -- Batch/MVNO
    batch_id VARCHAR(64),
    imsi_range_start VARCHAR(15), imsi_range_end VARCHAR(15),
    mvno_mcc CHAR(3), mvno_mnc CHAR(3) COMMENT 'For MVNO hosting',
    -- Rel-17: 5G ProSe, RedCap
    prose_enabled TINYINT(1) DEFAULT 0,
    redcap_allowed TINYINT(1) DEFAULT 0,
    -- Rel-18: NR-NTN, eRedCap
    ntn_allowed TINYINT(1) DEFAULT 0,
    eredcap_allowed TINYINT(1) DEFAULT 0,
    -- Rel-19: 5G-Advanced MIMO, XR
    xr_allowed TINYINT(1) DEFAULT 0,
    -- Rel-20: AI/ML, reduced capability
    aiml_allowed TINYINT(1) DEFAULT 0,
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (imsi),
    UNIQUE KEY uk_msisdn (msisdn),
    KEY idx_batch (batch_id),
    KEY idx_mvno (mvno_mcc, mvno_mnc),
    KEY idx_status (subscriber_status)
) ENGINE=InnoDB COMMENT='Core Subscriber per TS 23.008 (Rel-15 to Rel-20)';

-- ============================================================================
-- EPS SUBSCRIPTION DATA (TS 29.272 S6a, TS 23.401)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_subscription (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    -- APN Configuration (per TS 23.060/23.401)
    apn_config JSON COMMENT 'Array of APN profiles with QCI, ARP, AMBR, PGW',
    -- Default APN
    default_apn VARCHAR(100),
    -- UE AMBR (TS 23.401)
    ue_ambr_ul BIGINT UNSIGNED DEFAULT 100000000 COMMENT 'bps',
    ue_ambr_dl BIGINT UNSIGNED DEFAULT 100000000,
    -- RAT Restrictions (TS 23.401)
    rat_restrictions JSON COMMENT 'E-UTRAN, UTRAN, GERAN allowed',
    -- MSISDN List (TS 23.008)
    msisdn_list JSON COMMENT 'Additional MSISDNs',
    -- CSG Subscription (TS 29.272)
    csg_subscription JSON COMMENT 'CSG IDs allowed',
    -- MME Subscription (TS 29.272)
    mme_subscription JSON COMMENT 'MME group/set/host for S11',
    -- HSS Subscription (TS 29.272)
    hss_subscription JSON COMMENT 'HSS host/realm for S6a',
    -- LCS Privacy (TS 23.271)
    lcs_privacy JSON COMMENT 'LCS privacy exceptions',
    -- VPLMN Dynamic Data
    vplmn_dynamic JSON COMMENT 'Per-VPLMN: MME, SGSN, PGW addresses',
    -- Rel-15: NB-IoT, eMTC
    nb_iot_allowed TINYINT(1) DEFAULT 0,
    emtc_allowed TINYINT(1) DEFAULT 0,
    -- Rel-16: V2X, Industrial IoT
    v2x_allowed TINYINT(1) DEFAULT 0,
    industrial_iot_allowed TINYINT(1) DEFAULT 0,
    -- Rel-17: RedCap
    redcap_allowed TINYINT(1) DEFAULT 0,
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='EPS Subscription Data per TS 29.272 (Rel-15 to Rel-20)';

-- ============================================================================
-- 5G SUBSCRIPTION DATA (TS 29.503 Nudm_SDM, TS 23.501)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_5g_subscription (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    -- SUPI/SUCI (TS 23.003/33.501)
    supi VARCHAR(20) COMMENT 'Subscription Permanent Identifier',
    suci_calc_info JSON COMMENT 'SUCI calculation: profile, home network PK',
    -- S-NSSAI (TS 23.501)
    default_nssai JSON COMMENT 'Default S-NSSAI list [{"sst":1,"sd":"000001"}]',
    allowed_nssai JSON COMMENT 'Allowed S-NSSAI per PLMN',
    -- UE AMBR (TS 23.501)
    ue_ambr_ul BIGINT UNSIGNED DEFAULT 1000000000,
    ue_ambr_dl BIGINT UNSIGNED DEFAULT 1000000000,
    -- 5G Access Type (TS 23.501)
    rat_restrictions_5g JSON COMMENT 'NR, E-UTRA, WLAN allowed',
    -- SMF Selection (TS 23.501)
    smf_selection JSON COMMENT 'DNN->SMF FQDN mapping',
    -- LCS (TS 23.271)
    gmlc_address VARCHAR(255) COMMENT 'GMLC FQDN/IP for SLh',
    lcs_privacy_5g JSON COMMENT '5G LCS privacy',
    -- Sor/Steering (TS 23.501)
    sor_info JSON COMMENT 'Steering of Roaming info',
    ue_id_mapping JSON COMMENT '5G-GUTI, PEI mapping',
    -- Network Slicing
    nssaa_info JSON COMMENT 'NSSAA per slice',
    -- VPLMN Data
    vplmn_5g_data JSON COMMENT 'Per-VPLMN: AMF, SMF addresses',
    -- Rel-16: URLLC, mMTC, V2X
    urllc_allowed TINYINT(1) DEFAULT 0,
    mmtc_allowed TINYINT(1) DEFAULT 0,
    v2x_allowed_5g TINYINT(1) DEFAULT 0,
    -- Rel-17: RedCap, NR-NTN, PNI-NPN
    redcap_allowed_5g TINYINT(1) DEFAULT 0,
    ntn_allowed_5g TINYINT(1) DEFAULT 0,
    pni_npn_allowed TINYINT(1) DEFAULT 0,
    -- Rel-18: eRedCap, MBS, XR
    eredcap_allowed_5g TINYINT(1) DEFAULT 0,
    mbs_allowed TINYINT(1) DEFAULT 0,
    xr_allowed_5g TINYINT(1) DEFAULT 0,
    -- Rel-19: 5G-Advanced
    aiml_allowed_5g TINYINT(1) DEFAULT 0,
    multicast_mbs_allowed TINYINT(1) DEFAULT 0,
    -- Rel-20: Reduced capability, AI/ML
    reduced_cap_allowed TINYINT(1) DEFAULT 0,
    aiml_enhanced_allowed TINYINT(1) DEFAULT 0,
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='5G Subscription Data per TS 29.503 (Rel-15 to Rel-20)';

-- ============================================================================
-- IMS SUBSCRIPTION PROFILE (TS 29.228/229, IR.92)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_ims_subscription (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    -- IMPU (Public User Identity)
    impu_list JSON COMMENT 'Array of SIP URIs/TEL URIs',
    -- IMPI (Private User Identity)
    impi VARCHAR(255) COMMENT 'SIP URI format',
    -- IMS Domain
    ims_domain VARCHAR(255) COMMENT 'e.g., ims.mnc001.mcc310.3gppnetwork.org',
    -- Service Profile (TS 29.229)
    service_profile_id VARCHAR(64) COMMENT 'Initial Filter Criteria (iFC)',
    -- CSCF Assignment
    scscf_name VARCHAR(255) COMMENT 'Assigned S-CSCF',
    scscf_realm VARCHAR(255),
    -- Registration
    reg_status ENUM('registered','unregistered') DEFAULT 'unregistered',
    reg_expires BIGINT UNSIGNED DEFAULT 0,
    contact_list JSON COMMENT 'Registered contacts',
    -- Authorization
    auth_scheme ENUM('AKAv1-MD5','AKAv2-SHA-256') DEFAULT 'AKAv1-MD5',
    -- Wildcarded IMPU
    wildcarded_impu TINYINT(1) DEFAULT 0,
    -- Rel-16: MTSI, RCS
    mtsi_allowed TINYINT(1) DEFAULT 0,
    rcs_allowed TINYINT(1) DEFAULT 0,
    -- Rel-17: NR-Multicast
    nr_multicast_allowed TINYINT(1) DEFAULT 0,
    -- Rel-18: eMTSI
    emtsi_allowed TINYINT(1) DEFAULT 0,
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='IMS Subscription per TS 29.228/229 (Rel-15 to Rel-20)';

-- ============================================================================
-- APN/DNN PROFILE PER SUBSCRIBER (TS 23.060, 23.401, 23.501)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_apn_profile (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    apn VARCHAR(100) NOT NULL COMMENT 'DNN/APN name (NI + OI)',
    apn_type ENUM('internet','ims','emergency','mms','enterprise','m2m','mbs','fmc') DEFAULT 'internet',
    -- QoS (TS 23.501/23.401)
    qci TINYINT UNSIGNED DEFAULT 9 COMMENT '5QI/QCI',
    arp_priority TINYINT UNSIGNED DEFAULT 8,
    arp_preempt_cap TINYINT(1) DEFAULT 0,
    arp_preempt_vuln TINYINT(1) DEFAULT 0,
    -- AMBR
    apn_ambr_ul BIGINT UNSIGNED DEFAULT 100000000,
    apn_ambr_dl BIGINT UNSIGNED DEFAULT 100000000,
    ue_ambr_ul BIGINT UNSIGNED DEFAULT 100000000,
    ue_ambr_dl BIGINT UNSIGNED DEFAULT 100000000,
    -- PCC (TS 29.512/513)
    pcc_rule_name VARCHAR(64),
    pcc_rule_version INT UNSIGNED DEFAULT 1,
    -- IP Allocation (TS 23.060)
    pdn_type ENUM('ipv4','ipv6','ipv4v6','non-ip') DEFAULT 'ipv4v6',
    ipv4_addr_alloc ENUM('dynamic','static','dhcp') DEFAULT 'dynamic',
    ipv6_prefix_len TINYINT UNSIGNED DEFAULT 64,
    static_ipv4 VARCHAR(45), static_ipv6 VARCHAR(45),
    -- DNS
    dns_primary VARCHAR(45) DEFAULT '8.8.8.8',
    dns_secondary VARCHAR(45) DEFAULT '8.8.4.4',
    -- PGW/SGW (TS 23.401)
    pgw_fqdn VARCHAR(255), pgw_ipv4 VARCHAR(45), pgw_ipv6 VARCHAR(45),
    sgw_fqdn VARCHAR(255), sgw_ipv4 VARCHAR(45),
    -- Charging (TS 32.298)
    charging_id INT UNSIGNED DEFAULT 0,
    charging_gateway VARCHAR(255),
    -- Emergency APN (TS 23.401)
    is_emergency TINYINT(1) DEFAULT 0,
    -- DNN Selection (TS 23.501)
    dnn_selection_mode ENUM('UE-provided','Network-provided','Verified') DEFAULT 'Verified',
    -- MVNO
    mvno_reseller_id VARCHAR(64),
    -- Rel-16: URLLC QoS
    urllc_qos TINYINT(1) DEFAULT 0,
    -- Rel-17: RedCap, MBS
    redcap_qos TINYINT(1) DEFAULT 0,
    mbs_qos TINYINT(1) DEFAULT 0,
    -- Status
    is_default TINYINT(1) DEFAULT 0,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_apn (imsi, apn),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='APN/DNN Profile per TS 23.060/23.401/23.501 (Rel-15 to Rel-20)';

-- ============================================================================
-- SUPPLEMENTARY SERVICES (TS 23.011, 23.018, 29.002, 29.272)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_supplementary_service (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    service_code VARCHAR(20) NOT NULL COMMENT 'CF, CW, CLIP, CLIR, MPTY, USSD, BoIC, BaIC, etc.',
    service_name VARCHAR(100),
    -- Provisioning (TS 23.011)
    provision_status ENUM('not_provisioned','provisioned','active','deactivated') DEFAULT 'not_provisioned',
    activation_code VARCHAR(32),
    deactivation_code VARCHAR(32),
    interrogation_code VARCHAR(32),
    registration_code VARCHAR(32),
    erasure_code VARCHAR(32),
    -- Registration Data (TS 23.018)
    forwarding_number VARCHAR(20),
    forwarding_condition ENUM('unconditional','busy','no_reply','not_reachable','all') DEFAULT 'unconditional',
    no_reply_timer TINYINT UNSIGNED DEFAULT 20 COMMENT 'Seconds',
    -- Override/Restrictions
    override_category ENUM('none','operator','subscriber') DEFAULT 'none',
    max_simultaneous_calls SMALLINT UNSIGNED DEFAULT 0 COMMENT 'For MPTY',
    -- CLIP/CLIR (TS 23.081/082)
    clip_provisioned TINYINT(1) DEFAULT 1,
    clir_provisioned TINYINT(1) DEFAULT 1,
    clir_option ENUM('presentation_allowed','presentation_restricted','network_default') DEFAULT 'network_default',
    -- USSD (TS 23.090/29.002)
    ussd_enabled TINYINT(1) DEFAULT 1,
    ussd_string_length SMALLINT UNSIGNED DEFAULT 160,
    -- CAMEL (TS 23.078/29.078)
    camel_phase TINYINT UNSIGNED DEFAULT 3,
    camel_tdp_list JSON COMMENT 'Trigger Detection Points',
    -- Rel-16: MMTel
    mmtel_allowed TINYINT(1) DEFAULT 0,
    -- Rel-17: RCS
    rcs_allowed TINYINT(1) DEFAULT 0,
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_service (imsi, service_code),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Supplementary Services per TS 23.011/018/078 (Rel-15 to Rel-20)';

-- ============================================================================
-- ROAMING & OPERATOR POLICIES (TS 23.060, 29.272, 29.503)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_roaming_profile (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    visited_plmn CHAR(6) NOT NULL COMMENT 'MCC+MNC of VPLMN',
    -- Access
    roaming_allowed TINYINT(1) DEFAULT 1,
    rat_allowed JSON COMMENT 'Per-RAT: NR, E-UTRA, UTRAN, GERAN',
    -- Restrictions (TS 23.060 ODB)
    odb_roaming TINYINT(1) DEFAULT 0,
    odb_outgoing TINYINT(1) DEFAULT 0,
    odb_incoming TINYINT(1) DEFAULT 0,
    odb_premium TINYINT(1) DEFAULT 0,
    -- Handover
    ho_restriction JSON COMMENT 'Forbidden TAs/cells',
    -- Charging
    charging_profile_id VARCHAR(64),
    -- VPLMN-specific network elements
    v_mme_fqdn VARCHAR(255), v_mme_ipv4 VARCHAR(45),
    v_sgsn_fqdn VARCHAR(255), v_sgsn_ipv4 VARCHAR(45),
    v_pgw_fqdn VARCHAR(255), v_pgw_ipv4 VARCHAR(45),
    -- 5G
    v_amf_fqdn VARCHAR(255), v_amf_ipv4 VARCHAR(45),
    v_smf_fqdn VARCHAR(255),
    -- Rel-16: V2X roaming
    v2x_roaming TINYINT(1) DEFAULT 0,
    -- Rel-17: RedCap roaming
    redcap_roaming TINYINT(1) DEFAULT 0,
    -- Rel-18: NTN roaming
    ntn_roaming TINYINT(1) DEFAULT 0,
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_vplmn (imsi, visited_plmn),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Per-VPLMN Roaming Profile per TS 23.060/29.272/29.503 (Rel-15 to Rel-20)';

-- ============================================================================
-- USSD / CAMEL / MAP ROUTING (TS 29.002, 23.090, 23.078)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_ussd_routing (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ussd_string VARCHAR(32) NOT NULL COMMENT 'e.g., *123#, *100*1#',
    -- Routing (MAP/CAMEL)
    destination_type ENUM('internal','external_ussd_gw','scp','gmlc','imsi_based') DEFAULT 'internal',
    destination_address VARCHAR(255) COMMENT 'IP/FQDN/GT of USSD GW or SCP',
    -- MAP Parameters (TS 29.002)
    gsm_scf_address VARCHAR(255) COMMENT 'gprsSCFAddress for CAMEL',
    service_key INT UNSIGNED DEFAULT 0 COMMENT 'CAMEL Service Key',
    -- Default Handling
    default_response VARCHAR(255) COMMENT 'USSD response if no match',
    timeout_sec TINYINT UNSIGNED DEFAULT 10,
    -- MVNO
    mvno_mcc CHAR(3), mvno_mnc CHAR(3),
    -- Rel-17: USSD over 5G
    fiveg_ussd_allowed TINYINT(1) DEFAULT 0,
    -- Status
    is_active TINYINT(1) DEFAULT 1,
    priority SMALLINT UNSIGNED DEFAULT 100,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ussd_string (ussd_string)
) ENGINE=InnoDB COMMENT='USSD/CAMEL Routing per TS 29.002/23.090/23.078 (Rel-15 to Rel-20)';

CREATE TABLE IF NOT EXISTS tbl_camel_service_profile (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    service_key INT UNSIGNED NOT NULL COMMENT 'CAMEL Service Key (1-2^32-1)',
    -- TDP (Trigger Detection Points) per TS 23.078
    tdp_list JSON COMMENT 'Array of TDP: {"tdp": "collectedInfo", "criteria": {...}}',
    -- gsmSCF Address
    gsm_scf_address VARCHAR(255) NOT NULL COMMENT 'GT of gsmSCF',
    -- Default Handling
    default_call_handling ENUM('continue','release','route_to_scf') DEFAULT 'continue',
    -- CSI (CAMEL Subscription Info) per TS 29.078
    csi_psi JSON COMMENT 'CAMEL Subscription Info for PS',
    csi_csi JSON COMMENT 'CAMEL Subscription Info for CS',
    csi_ssi JSON COMMENT 'CAMEL Subscription Info for SS',
    csi_msi JSON COMMENT 'CAMEL Subscription Info for Mobility',
    csi_lsi JSON COMMENT 'CAMEL Subscription Info for LCS',
    -- Rel-16: V2X CSI
    csi_v2x JSON COMMENT 'CAMEL Subscription Info for V2X',
    -- Rel-17: RedCap CSI
    csi_redcap JSON COMMENT 'CAMEL Subscription Info for RedCap',
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_sk (imsi, service_key),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='CAMEL Service Profile per TS 23.078/29.078 (Rel-15 to Rel-20)';

-- ============================================================================
-- AUTHENTICATION VECTORS (TS 33.102, 33.501, 29.272)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_auth_vector (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    -- 5G (TS 33.501)
    rand_5g VARCHAR(32) COMMENT 'RAND (128-bit)',
    autn_5g VARCHAR(32) COMMENT 'AUTN (128-bit) = SQN⊕AK || AMF || MAC',
    xres_5g VARCHAR(32) COMMENT 'XRES* (256-bit for 5G)',
    k_ausf VARCHAR(32) COMMENT 'K_AUSF',
    k_seaf VARCHAR(32) COMMENT 'K_SEAF',
    k_amf VARCHAR(32) COMMENT 'K_AMF (derived in AUSF)',
    -- 4G (TS 33.401)
    rand_4g VARCHAR(32) COMMENT 'RAND (128-bit)',
    autn_4g VARCHAR(32) COMMENT 'AUTN (128-bit)',
    xres_4g VARCHAR(16) COMMENT 'XRES (64-bit)',
    ck_4g VARCHAR(32) COMMENT 'CK (128-bit)',
    ik_4g VARCHAR(32) COMMENT 'IK (128-bit)',
    k_asme_4g VARCHAR(32) COMMENT 'K_ASME',
    -- 3G (TS 33.102)
    rand_3g VARCHAR(32),
    autn_3g VARCHAR(32),
    xres_3g VARCHAR(16),
    ck_3g VARCHAR(32),
    ik_3g VARCHAR(32),
    -- 2G (TS 33.102)
    rand_2g VARCHAR(32),
    sres_2g VARCHAR(8) COMMENT 'SRES (32-bit)',
    kc_2g VARCHAR(16) COMMENT 'Kc (64-bit)',
    -- Rel-17: RedCap auth
    rand_redcap VARCHAR(32),
    -- Metadata
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL DEFAULT NULL,
    algorithm VARCHAR(32) DEFAULT 'milenage' COMMENT 'milenage, comp128v1-3, xor, TUAK',
    opc_used VARCHAR(32) COMMENT 'OPc used for this vector',
    sqn_used BIGINT UNSIGNED COMMENT 'SQN at generation',
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Auth Vectors per TS 33.102/33.501 (Rel-15 to Rel-20)';

-- ============================================================================
-- NETWORK INTERFACE / NODE MANAGEMENT (for MME/MSC/PGW/GMLC integration)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_network_node (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    node_name VARCHAR(64) NOT NULL UNIQUE,
    node_type ENUM('MME','MSC','SGSN','PGW','SGW','HSS','PCRF','PCF','SMF','UPF','AMF','GMLC','SCP','USSD_GW','SMSC','NRF','AUSF','UDM','NEF','BSF','UDSF','NSSF') NOT NULL,
    -- Identity
    fqdn VARCHAR(255),
    ipv4 VARCHAR(45), ipv6 VARCHAR(45),
    -- Diameter (TS 29.272)
    diameter_host VARCHAR(255),
    diameter_realm VARCHAR(255),
    diameter_port INT DEFAULT 3868,
    -- SCTP/M3UA (TS 29.002)
    sctp_port INT DEFAULT 2905,
    point_code VARCHAR(11) COMMENT 'ITU/ANSI PC',
    -- GT (MAP)
    global_title VARCHAR(20),
    gt_translation_type TINYINT UNSIGNED DEFAULT 0,
    gt_numbering_plan TINYINT UNSIGNED DEFAULT 1,
    gt_nature_of_address TINYINT UNSIGNED DEFAULT 4,
    -- PLMN
    plmn_id CHAR(6) COMMENT 'MCC+MNC this node serves',
    -- Capabilities
    supported_interfaces JSON COMMENT 'S6a, S11, S13, N4, N7, SLh, etc.',
    -- Status
    is_active TINYINT(1) DEFAULT 1,
    health_check_url VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_type_plmn (node_type, plmn_id)
) ENGINE=InnoDB COMMENT='Network Node Registry for Interworking (Rel-15 to Rel-20)';

-- ============================================================================
-- BATCH & IMSI RANGE MANAGEMENT
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_batch_upload (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(64) NOT NULL UNIQUE,
    filename VARCHAR(255),
    total_records INT UNSIGNED DEFAULT 0,
    successful_records INT UNSIGNED DEFAULT 0,
    failed_records INT UNSIGNED DEFAULT 0,
    status ENUM('pending','processing','completed','failed') DEFAULT 'pending',
    error_log JSON,
    created_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_batch_id (batch_id)
) ENGINE=InnoDB COMMENT='Batch Upload Audit';

CREATE TABLE IF NOT EXISTS tbl_imsi_range (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    range_name VARCHAR(64) NOT NULL UNIQUE,
    mcc CHAR(3) NOT NULL,
    mnc CHAR(3) NOT NULL,
    msisdn_prefix VARCHAR(10),
    imsi_start VARCHAR(15) NOT NULL,
    imsi_end VARCHAR(15) NOT NULL,
    next_imsi VARCHAR(15) NOT NULL,
    allocated_count BIGINT UNSIGNED DEFAULT 0,
    total_count BIGINT UNSIGNED DEFAULT 0,
    status ENUM('available','exhausted','reserved') DEFAULT 'available',
    -- MVNO
    mvno_id VARCHAR(64) COMMENT 'MVNO identifier if hosting',
    -- Key defaults for range
    default_k VARCHAR(32), default_ki VARCHAR(32),
    default_op VARCHAR(32), default_opc VARCHAR(32),
    default_algorithm VARCHAR(32) DEFAULT 'milenage',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_range (mcc, mnc, imsi_start, imsi_end)
) ENGINE=InnoDB COMMENT='IMSI Range Management for MVNO';

-- ============================================================================
-- SEED DATA: MCC/MNC (Example: France Orange, MVNO hosting)
-- ============================================================================

INSERT IGNORE INTO tbl_mcc_mnc (mcc, mnc, country_name, network_name, network_type, parent_mcc, parent_mnc, is_active)
VALUES 
    ('208', '01', 'France', 'Orange France', 'MNO', NULL, NULL, 1),
    ('208', '10', 'France', 'SFR', 'MNO', NULL, NULL, 1),
    ('208', '15', 'France', 'Free Mobile', 'MNO', NULL, NULL, 1),
    ('208', '20', 'France', 'Bouygues Telecom', 'MNO', NULL, NULL, 1),
    ('001', '01', 'Test', 'Test PLMN 1', 'Test', NULL, NULL, 1),
    ('001', '02', 'Test', 'Test PLMN 2', 'Test', NULL, NULL, 1);

INSERT IGNORE INTO tbl_plmn_profile (plmn_id, plmn_name, eps_supported, fiveg_supported, redcap_supported, ntn_supported, fiveg_advanced_supported, hplmn_allowed, vplmn_allowed, diameter_realm)
VALUES 
    ('20801', 'Orange France', 1, 1, 1, 1, 1, 1, 1, 'mnc01.mcc208.3gppnetwork.org'),
    ('20810', 'SFR', 1, 1, 1, 1, 1, 1, 1, 'mnc10.mcc208.3gppnetwork.org'),
    ('00101', 'Test PLMN 1', 1, 1, 1, 1, 1, 1, 1, 'mnc01.mcc001.3gppnetwork.org');

-- ============================================================================
-- SEED: Network Nodes (Example integration points)
-- ============================================================================

INSERT IGNORE INTO tbl_network_node (node_name, node_type, fqdn, ipv4, diameter_host, diameter_realm, diameter_port, sctp_port, point_code, plmn_id, supported_interfaces)
VALUES
    ('mme-01', 'MME', 'mme-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.10', 'mme-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 2905, '3.14.1', '20801', '["S6a","S11","S13","S10","Sv"]'),
    ('hss-01', 'HSS', 'hss-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.20', 'hss-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 2905, '3.14.2', '20801', '["Cx","S6a","Sh","Ro"]'),
    ('pgw-01', 'PGW', 'pgw-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.30', 'pgw-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 0, '', '20801', '["Gx","Gy","S5","S8"]'),
    ('gmlc-01', 'GMLC', 'gmlc-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.40', 'gmlc-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 2905, '3.14.3', '20801', '["SLh","SLg","MAP"]'),
    ('scp-01', 'SCP', 'scp-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.50', 'scp-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 2905, '3.14.4', '20801', '["CAP","INAP","MAP"]'),
    ('ussd-gw-01', 'USSD_GW', 'ussd-gw-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.60', 'ussd-gw-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 2905, '3.14.5', '20801', '["MAP-USSD"]'),
    ('amf-01', 'AMF', 'amf-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.70', 'amf-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 2905, '3.14.6', '20801', '["N1","N2","N8","N11","N12"]'),
    ('smf-01', 'SMF', 'smf-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.80', 'smf-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 0, '', '20801', '["N4","N7","N10","N11","N16"]'),
    ('upf-01', 'UPF', 'upf-01.mnc01.mcc208.3gppnetwork.org', '10.1.10.90', 'upf-01.mnc01.mcc208.3gppnetwork.org', 'mnc01.mcc208.3gppnetwork.org', 3868, 0, '', '20801', '["N3","N4","N6","N9"]');

-- ============================================================================
-- UE CONTEXT MANAGEMENT (TS 29.503 Nudm_UECM)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_uecm_registration (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    access_type ENUM('3GPP', 'non-3GPP') NOT NULL,
    registration_data JSON,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_access (imsi, access_type),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='UECM Registrations per TS 29.503 (Rel-15 to Rel-20)';

-- ============================================================================
-- End of hssdbInitial.sql
-- ============================================================================
