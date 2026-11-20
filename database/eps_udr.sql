-- ============================================================================
-- eps_udr.sql - EPS-UDR Schema for HSS/HLR Projection (TS 23.008, 29.272, 29.002)
-- Mirrors 5G UDM subscriber data into EPS/CS view for HSS and HLR front ends.
-- When a SIM is provisioned centrally, the canonical subscriber record is
-- projected here so S6a/S6d (MME/SGSN) and Gr/C/D/B/E/F/G (MAP) interfaces
-- can serve 4G/3G/2G attach, location update, and authentication.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS eps_udr CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE eps_udr;

-- ============================================================================
-- EPS SUBSCRIBER (Canonical record mirrored from tbl_subscriber in hssdb)
-- HSS/HLR front end reads this for S6a/S6d ULR/ULA and Gr SendAuthenticationInfo
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_subscriber (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    msisdn VARCHAR(15),
    imei VARCHAR(15),
    imei_sv VARCHAR(16),
    -- Root Keys (TS 33.102/33.401/33.501)
    k VARCHAR(32) COMMENT '5G Root Key (K4) - 256-bit hex',
    ki VARCHAR(32) COMMENT '4G/3G/2G Root Key (Ki) - 128-bit hex',
    op VARCHAR(32) COMMENT 'OP (Operator Variant) - 128-bit hex',
    opc VARCHAR(32) COMMENT 'OPc (Derived) - 128-bit hex',
    sqn BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'SQN for AKA (48-bit) - authoritative copy',
    amf VARCHAR(8) DEFAULT '8000' COMMENT 'Auth Management Field',
    k_asme VARCHAR(32) COMMENT 'K_ASME (EPS AKA)',
    -- Network Access Mode (TS 23.008)
    -- 0=GPRS(3G only), 1=CS(2G only), 2=Both(2G+3G), 3=5G
    network_access_mode TINYINT UNSIGNED NOT NULL DEFAULT 2,
    subscriber_status TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0=Active,1=Barred,2=Suspended,3=Detached',
    roaming_restricted TINYINT(1) DEFAULT 0,
    odb_data JSON COMMENT 'Operator Determined Barring',
    -- Source tracking: which system owns this record
    source_system ENUM('udm','hss','hlr','import') DEFAULT 'udm',
    last_synced_at TIMESTAMP NULL COMMENT 'Last time this record was synced from UDM',
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_msisdn (msisdn),
    KEY idx_status (subscriber_status),
    KEY idx_source (source_system)
) ENGINE=InnoDB COMMENT='EPS Subscriber canonical record (HSS/HLR view of UDR)';

-- ============================================================================
-- EPS SUBSCRIPTION DATA (S6a/S6d view for MME/SGSN attach)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_subscription_data (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    apn_config JSON COMMENT 'Array of APN profiles with QCI, ARP, AMBR, PGW-C+SMF FQDN',
    default_apn VARCHAR(100),
    ue_ambr_ul BIGINT UNSIGNED DEFAULT 100000000,
    ue_ambr_dl BIGINT UNSIGNED DEFAULT 100000000,
    rat_restrictions JSON COMMENT 'E-UTRAN, UTRAN, GERAN allowed per TS 23.401',
    msisdn_list JSON,
    csg_subscription JSON,
    mme_subscription JSON COMMENT 'MME group/set/host for S11/S6a',
    hss_subscription JSON COMMENT 'HSS host/realm for S6a',
    lcs_privacy JSON COMMENT 'LCS privacy exceptions (SLh/SLg)',
    vplmn_dynamic JSON COMMENT 'Per-VPLMN: MME, SGSN, PGW addresses',
    nb_iot_allowed TINYINT(1) DEFAULT 0,
    emtc_allowed TINYINT(1) DEFAULT 0,
    v2x_allowed TINYINT(1) DEFAULT 0,
    industrial_iot_allowed TINYINT(1) DEFAULT 0,
    redcap_allowed TINYINT(1) DEFAULT 0,
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='EPS Subscription Data per TS 29.272 (S6a/S6d view)';

-- ============================================================================
-- APN/DNN PROFILE (EPS view - PGW-C+SMF FQDN per APN for PDU continuity)
-- Used by Nhss_SDM ue-context-in-pgw-data and PDU session continuity
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_apn_profile (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    apn VARCHAR(100) NOT NULL COMMENT 'APN name (NI + OI)',
    apn_type ENUM('internet','ims','emergency','mms','enterprise','m2m','mbs','fmc') DEFAULT 'internet',
    qci TINYINT UNSIGNED DEFAULT 9,
    arp_priority TINYINT UNSIGNED DEFAULT 8,
    arp_preempt_cap TINYINT(1) DEFAULT 0,
    arp_preempt_vuln TINYINT(1) DEFAULT 0,
    apn_ambr_ul BIGINT UNSIGNED DEFAULT 100000000,
    apn_ambr_dl BIGINT UNSIGNED DEFAULT 100000000,
    pdn_type ENUM('ipv4','ipv6','ipv4v6','non-ip') DEFAULT 'ipv4v6',
    ipv4_addr_alloc ENUM('dynamic','static','dhcp') DEFAULT 'dynamic',
    ipv6_prefix_len TINYINT UNSIGNED DEFAULT 64,
    static_ipv4 VARCHAR(45), static_ipv6 VARCHAR(45),
    dns_primary VARCHAR(45) DEFAULT '8.8.8.8',
    dns_secondary VARCHAR(45) DEFAULT '8.8.4.4',
    pgw_fqdn VARCHAR(255) COMMENT 'PGW-C FQDN for S5/S8/S2b (PDU continuity)',
    pgw_ipv4 VARCHAR(45),
    sgw_fqdn VARCHAR(255),
    sgw_ipv4 VARCHAR(45),
    charging_id INT UNSIGNED DEFAULT 0,
    charging_gateway VARCHAR(255),
    is_emergency TINYINT(1) DEFAULT 0,
    dnn_selection_mode ENUM('UE-provided','Network-provided','Verified') DEFAULT 'Verified',
    is_default TINYINT(1) DEFAULT 0,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_apn (imsi, apn),
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='APN Profile EPS view (PGW-C+SMF FQDN per APN)';

-- ============================================================================
-- IMS SUBSCRIPTION (Cx/Sh view for IMS CSCF/AS)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_ims_subscription (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    impu_list JSON COMMENT 'Array of SIP URIs/TEL URIs',
    impi VARCHAR(255),
    ims_domain VARCHAR(255),
    service_profile_id VARCHAR(64),
    scscf_name VARCHAR(255),
    scscf_realm VARCHAR(255),
    reg_status ENUM('registered','unregistered') DEFAULT 'unregistered',
    reg_expires BIGINT UNSIGNED DEFAULT 0,
    contact_list JSON,
    auth_scheme ENUM('AKAv1-MD5','AKAv2-SHA-256') DEFAULT 'AKAv1-MD5',
    wildcarded_impu TINYINT(1) DEFAULT 0,
    mtsi_allowed TINYINT(1) DEFAULT 0,
    rcs_allowed TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='IMS Subscription EPS view (Cx/Sh interface)';

-- ============================================================================
-- SUPPLEMENTARY SERVICES (MAP C/D/B/E/F/G view for HLR)
-- CS supplementary services: CF, CW, CLIP, CLIR, MPTY, USSD, BoIC, BaIC, CAMEL
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_supplementary_service (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    service_code VARCHAR(20) NOT NULL,
    service_name VARCHAR(100),
    provision_status ENUM('not_provisioned','provisioned','active','deactivated') DEFAULT 'not_provisioned',
    activation_code VARCHAR(32),
    deactivation_code VARCHAR(32),
    interrogation_code VARCHAR(32),
    registration_code VARCHAR(32),
    erasure_code VARCHAR(32),
    forwarding_number VARCHAR(20),
    forwarding_condition ENUM('unconditional','busy','no_reply','not_reachable','all') DEFAULT 'unconditional',
    no_reply_timer TINYINT UNSIGNED DEFAULT 20,
    override_category ENUM('none','operator','subscriber') DEFAULT 'none',
    max_simultaneous_calls SMALLINT UNSIGNED DEFAULT 0,
    clip_provisioned TINYINT(1) DEFAULT 1,
    clir_provisioned TINYINT(1) DEFAULT 1,
    clir_option ENUM('presentation_allowed','presentation_restricted','network_default') DEFAULT 'network_default',
    ussd_enabled TINYINT(1) DEFAULT 1,
    ussd_string_length SMALLINT UNSIGNED DEFAULT 160,
    camel_phase TINYINT UNSIGNED DEFAULT 3,
    camel_tdp_list JSON COMMENT 'Trigger Detection Points (CAMEL)',
    mmtel_allowed TINYINT(1) DEFAULT 0,
    rcs_allowed TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_service (imsi, service_code),
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Supplementary Services EPS/HLR view (MAP C/D/B/E/F/G)';

-- ============================================================================
-- ROAMING PROFILE (Per-VPLMN for HSS/HLR)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_roaming_profile (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    visited_plmn CHAR(6) NOT NULL,
    roaming_allowed TINYINT(1) DEFAULT 1,
    rat_allowed JSON COMMENT 'Per-RAT: NR, E-UTRA, UTRAN, GERAN',
    odb_roaming TINYINT(1) DEFAULT 0,
    odb_outgoing TINYINT(1) DEFAULT 0,
    odb_incoming TINYINT(1) DEFAULT 0,
    odb_premium TINYINT(1) DEFAULT 0,
    ho_restriction JSON,
    charging_profile_id VARCHAR(64),
    v_mme_fqdn VARCHAR(255), v_mme_ipv4 VARCHAR(45),
    v_sgsn_fqdn VARCHAR(255), v_sgsn_ipv4 VARCHAR(45),
    v_pgw_fqdn VARCHAR(255), v_pgw_ipv4 VARCHAR(45),
    v_amf_fqdn VARCHAR(255), v_amf_ipv4 VARCHAR(45),
    v_smf_fqdn VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_vplmn (imsi, visited_plmn),
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Roaming Profile EPS/HLR view per VPLMN';

-- ============================================================================
-- SMS / MWD (Message Waiting Data for MT-SMS routing)
-- HSS tracks SMS-GMSC/IWMSC subscription and MWD state
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_sms_mwd (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    smsc_address VARCHAR(20) COMMENT 'SMSC address for message waiting',
    mw_data TINYINT(1) DEFAULT 0 COMMENT 'Message Waiting Data flag',
    memory_capacity_exceeded TINYINT(1) DEFAULT 0,
    sms_over_ip_allowed TINYINT(1) DEFAULT 0,
    ip_sm_gw_address VARCHAR(255) COMMENT 'IP-SM-GW for SMSoIP',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='SMS Message Waiting Data (HSS/HLR view)';

-- ============================================================================
-- AUTHENTICATION VECTORS (EPS/CS view)
-- HSS/HLR stores generated vectors for S6a AIA and Gr SendAuthenticationInfo
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_eps_auth_vector (
    imsi VARCHAR(15) NOT NULL PRIMARY KEY,
    -- 4G EPS AKA (S6a AIR/AIA)
    rand_4g VARCHAR(32),
    autn_4g VARCHAR(32),
    xres_4g VARCHAR(16),
    ck_4g VARCHAR(32),
    ik_4g VARCHAR(32),
    k_asme_4g VARCHAR(32),
    -- 3G UMTS AKA (Gr SendAuthenticationInfo)
    rand_3g VARCHAR(32),
    autn_3g VARCHAR(32),
    xres_3g VARCHAR(16),
    ck_3g VARCHAR(32),
    ik_3g VARCHAR(32),
    -- 2G GSM (D interface)
    rand_2g VARCHAR(32),
    sres_2g VARCHAR(8),
    kc_2g VARCHAR(16),
    -- 5G AKA (Nhss_UEAU generate-av reverse direction)
    rand_5g VARCHAR(32),
    autn_5g VARCHAR(32),
    xres_star_5g VARCHAR(32),
    k_ausf_5g VARCHAR(32),
    -- Metadata
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL DEFAULT NULL,
    algorithm VARCHAR(32) DEFAULT 'milenage',
    opc_used VARCHAR(32),
    sqn_used BIGINT UNSIGNED,
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Auth Vectors EPS/HLR view (S6a/Gr/D interfaces)';

-- ============================================================================
-- NHSS SUBSCRIPTIONS (Nhss_SDM and Nhss_EE subscriptions from UDM)
-- HSS tracks UDM subscriptions to EPS data changes
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_nhss_subscription (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    subscription_type ENUM('sdm_pgw_data','ee_monitoring') NOT NULL,
    callback_reference VARCHAR(512) COMMENT 'UDM callback URL for notifications',
    nf_instance_id VARCHAR(64),
    monitored_resource_uris JSON,
    expires TIMESTAMP NULL,
    immediate_report TINYINT(1) DEFAULT 0,
    monitoring_configurations JSON,
    reporting_options JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_imsi_type (imsi, subscription_type),
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Nhss subscriptions from UDM (SDM + EE)';

-- ============================================================================
-- NHSS PP DATA (External parameter provisioning for EPC)
-- Nhss_PP create/update/delete/get per AF instance
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_nhss_pp_data (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    af_instance_id VARCHAR(64) NOT NULL,
    reference_id VARCHAR(64) NOT NULL,
    communication_characteristics JSON COMMENT '{ppDlPacketCount, maximumResponseTime, maximumLatency}',
    validity_time TIMESTAMP NULL,
    mtc_provider_information JSON,
    supported_features VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_imsi_af_ref (imsi, af_instance_id, reference_id),
    KEY idx_imsi (imsi),
    FOREIGN KEY (imsi) REFERENCES tbl_eps_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Nhss_PP data per AF instance (EPC parameter provisioning)';

-- ============================================================================
-- SYNC AUDIT LOG (Bidirectional sync trail between UDM and HSS)
-- Records every cross-unit communication for debugging and reconciliation
-- ============================================================================

CREATE TABLE IF NOT EXISTS tbl_sync_audit (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    imsi VARCHAR(15) NOT NULL,
    direction ENUM('udm_to_hss','hss_to_udm') NOT NULL,
    operation ENUM('provision','update_imei','update_roaming','deregister_sn','pgw_data_subscribe','pp_provision','auth_vector_request') NOT NULL,
    payload JSON COMMENT 'Full payload sent/received',
    status ENUM('sent','acknowledged','failed','retry') DEFAULT 'sent',
    retry_count INT UNSIGNED DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP NULL,
    KEY idx_imsi_direction (imsi, direction),
    KEY idx_status (status),
    KEY idx_created (created_at)
) ENGINE=InnoDB COMMENT='Bidirectional sync audit log (UDM <-> HSS)';

-- ============================================================================
-- SEED DATA: MCC/MNC for Uganda (MCC 641) and test PLMNs
-- ============================================================================

-- No seed subscriber data - provisioned via central import API

-- ============================================================================
-- End of eps_udr.sql
-- ============================================================================
