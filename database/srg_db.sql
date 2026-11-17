-- ============================================================================
-- srg_db.sql - STP/DRA Core Database Schema (Production-Grade)
-- Mirrors production schema from D:\core dpi\sql\srg_db.sql
-- Tables: tbl_dra_local, tbl_dra_peer, tbl_dra_peer_set, tbl_dra_route,
--         tbl_dra_translate, tbl_dra_trace, tbl_m3ua_global,
--         tbl_m3ua_link, tbl_m3ua_linkset, tbl_m3ua_local,
--         tbl_stp_route, tbl_stp_translate, tbl_stp_trace
-- ============================================================================

CREATE DATABASE IF NOT EXISTS srg_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE srg_db;

-- -----------------------------------------------------
-- tbl_dra_local - Local DRA instance identity (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_local (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(255) NOT NULL,
    name VARCHAR(32) NOT NULL,
    ip VARCHAR(32) NOT NULL,
    port SMALLINT NOT NULL DEFAULT 3868,
    protocol VARCHAR(32) NOT NULL,
    realm VARCHAR(256) NOT NULL,
    host VARCHAR(256) NOT NULL,
    vendor_id INT UNSIGNED NOT NULL DEFAULT 10415,
    application_ids VARCHAR(255) NOT NULL,
    product_name VARCHAR(32) NOT NULL,
    tls_flag TINYINT(1) NOT NULL DEFAULT 0,
    crt_file_name VARCHAR(255) NOT NULL DEFAULT '',
    key_file_name VARCHAR(255) NOT NULL DEFAULT '',
    PRIMARY KEY (id),
    UNIQUE KEY idx_tbl_dra_local_name (name)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_peer_set - Peer groups for redundancy/load-balance
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_peer_set (
    peerset_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(255) NOT NULL,
    name VARCHAR(32) NOT NULL,
    mode VARCHAR(32) NOT NULL DEFAULT 'balance',
    PRIMARY KEY (peerset_id),
    UNIQUE KEY idx_tbl_dra_peer_set_name (name)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_peer - Known Diameter/SIGTRAN peers (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_peer (
    peer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(255) NOT NULL,
    name VARCHAR(32) NOT NULL,
    local_id BIGINT UNSIGNED NOT NULL,
    peer_set_id BIGINT UNSIGNED NOT NULL,
    remote_ip VARCHAR(32) NOT NULL,
    remote_port INT UNSIGNED NOT NULL DEFAULT 3868,
    remote_host VARCHAR(256) NOT NULL,
    remote_realm VARCHAR(256) NOT NULL,
    remote_type VARCHAR(64) NOT NULL,
    protocol VARCHAR(256) NOT NULL DEFAULT 'sctp',
    priority TINYINT UNSIGNED NOT NULL DEFAULT 1,
    enable TINYINT(1) NOT NULL DEFAULT 1,
    application_ids VARCHAR(256) NOT NULL,
    vendor_id INT UNSIGNED NOT NULL DEFAULT 10415,
    product_name VARCHAR(32) NOT NULL,
    tls_flag TINYINT(1) NOT NULL DEFAULT 0,
    crt_file_name VARCHAR(256) NOT NULL DEFAULT '',
    key_file_name VARCHAR(256) NOT NULL DEFAULT '',
    loop_flag TINYINT(1) NOT NULL DEFAULT 0,
    watchdog_interval SMALLINT UNSIGNED NOT NULL DEFAULT 5,
    retransmit_timer SMALLINT UNSIGNED NOT NULL DEFAULT 10,
    max_retransmit SMALLINT UNSIGNED NOT NULL DEFAULT 3,
    PRIMARY KEY (peer_id),
    UNIQUE KEY idx_tbl_dra_peer_name (name),
    KEY fk_tbl_dra_peer_tbl_dra_local (local_id),
    KEY fk_tbl_dra_peer_tbl_dra_peer_set (peer_set_id),
    CONSTRAINT fk_tbl_dra_peer_tbl_dra_local FOREIGN KEY (local_id) REFERENCES tbl_dra_local (id),
    CONSTRAINT fk_tbl_dra_peer_tbl_dra_peer_set FOREIGN KEY (peer_set_id) REFERENCES tbl_dra_peer_set (peerset_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_route - Diameter routing table (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_route (
    route_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(255) NOT NULL,
    name VARCHAR(32) NOT NULL,
    origin_peer_set_id BIGINT UNSIGNED NOT NULL,
    dest_peer_set_id BIGINT UNSIGNED NOT NULL,
    imsi VARCHAR(64) DEFAULT NULL,
    impi VARCHAR(64) DEFAULT NULL,
    impu VARCHAR(64) DEFAULT NULL,
    ip_addr VARCHAR(64) DEFAULT NULL,
    msisdn VARCHAR(64) DEFAULT NULL,
    origin_host VARCHAR(256) DEFAULT NULL,
    application_id VARCHAR(255) DEFAULT NULL,
    origin_realm VARCHAR(256) DEFAULT NULL,
    destination_host VARCHAR(256) DEFAULT NULL,
    destination_realm VARCHAR(256) DEFAULT NULL,
    priority TINYINT UNSIGNED NOT NULL DEFAULT 1,
    origin_peer_set LONGTEXT,
    dest_peer_set LONGTEXT,
    PRIMARY KEY (route_id),
    UNIQUE KEY idx_tbl_dra_route_name (name),
    KEY fk_tbl_dra_route_tbl_dra_peer_set (origin_peer_set_id),
    KEY fk_tbl_dra_route_tbl_dra_peer_set2 (dest_peer_set_id),
    CONSTRAINT fk_tbl_dra_route_tbl_dra_peer_set FOREIGN KEY (origin_peer_set_id) REFERENCES tbl_dra_peer_set (peerset_id),
    CONSTRAINT fk_tbl_dra_route_tbl_dra_peer_set2 FOREIGN KEY (dest_peer_set_id) REFERENCES tbl_dra_peer_set (peerset_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_translate - Diameter AVP translation rules (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_translate (
    translate_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(255) NOT NULL,
    name VARCHAR(32) NOT NULL,
    origin_peer_set_name_id BIGINT UNSIGNED NOT NULL,
    dest_peer_set_name_id BIGINT UNSIGNED NOT NULL,
    avp_code INT UNSIGNED NOT NULL,
    avp_type VARCHAR(64) NOT NULL,
    avp_value VARCHAR(255) NOT NULL,
    command_code BIGINT UNSIGNED DEFAULT 0,
    application_ids VARCHAR(256) NOT NULL,
    set_session_id TINYINT(1) NOT NULL DEFAULT 0,
    origin_peer_set LONGTEXT,
    dest_peer_set LONGTEXT,
    PRIMARY KEY (translate_id),
    UNIQUE KEY idx_tbl_dra_translate_name (name),
    KEY fk_tbl_dra_translate_tbl_dra_peer_set (origin_peer_set_name_id),
    KEY fk_tbl_dra_translate_tbl_dra_peer_set2 (dest_peer_set_name_id),
    CONSTRAINT fk_tbl_dra_translate_tbl_dra_peer_set FOREIGN KEY (origin_peer_set_name_id) REFERENCES tbl_dra_peer_set (peerset_id),
    CONSTRAINT fk_tbl_dra_translate_tbl_dra_peer_set2 FOREIGN KEY (dest_peer_set_name_id) REFERENCES tbl_dra_peer_set (peerset_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_trace - DRA trace/logging
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_trace (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(255) NOT NULL,
    trace_id VARCHAR(255) NOT NULL,
    max_trace_time VARCHAR(1024) NOT NULL,
    create_time VARCHAR(1024) NOT NULL,
    operation VARCHAR(32) NOT NULL,
    ue_id_type VARCHAR(32) NOT NULL,
    ue_id VARCHAR(32) NOT NULL,
    plmn_mcc VARCHAR(32) NOT NULL,
    plmn_mnc VARCHAR(32) NOT NULL,
    interface VARCHAR(1024) NOT NULL,
    trace_depth VARCHAR(32) NOT NULL,
    trace_event VARCHAR(1024) NOT NULL,
    tce_info VARCHAR(1024) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY idx_tbl_dra_trace_trace_id (trace_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_m3ua_global - M3UA global configuration (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_m3ua_global (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(32) NOT NULL,
    name VARCHAR(32) NOT NULL,
    audit_interval INT UNSIGNED NOT NULL DEFAULT 30000,
    multiple_network_appearances CHAR(8) NOT NULL DEFAULT 'disabled',
    max_deactivate_attempts TINYINT UNSIGNED NOT NULL DEFAULT 3,
    fsm_timeout SMALLINT UNSIGNED NOT NULL DEFAULT 2000,
    tx_buffer_size INT UNSIGNED NOT NULL DEFAULT 102400,
    rx_buffer_size INT UNSIGNED NOT NULL DEFAULT 102400,
    max_ingress_streams SMALLINT UNSIGNED NOT NULL DEFAULT 16,
    num_egress_streams SMALLINT UNSIGNED NOT NULL DEFAULT 16,
    hb_interval INT UNSIGNED NOT NULL DEFAULT 30000,
    cong_onset_level1 TINYINT UNSIGNED NOT NULL DEFAULT 80,
    cong_abatement_level1 TINYINT UNSIGNED NOT NULL DEFAULT 70,
    cong_onset_level2 TINYINT UNSIGNED NOT NULL DEFAULT 90,
    cong_abatement_level2 TINYINT UNSIGNED NOT NULL DEFAULT 80,
    cong_onset_level3 TINYINT UNSIGNED NOT NULL DEFAULT 100,
    cong_abatement_level3 TINYINT UNSIGNED NOT NULL DEFAULT 90,
    cong_report_frequency TINYINT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    UNIQUE KEY idx_tbl_m3ua_global_instance_id (instance_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_m3ua_local - Local M3UA point codes (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_m3ua_local (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(32) NOT NULL,
    name VARCHAR(32) NOT NULL,
    local_point_code CHAR(11) NOT NULL,
    point_code_length TINYINT UNSIGNED NOT NULL DEFAULT 14,
    network_indicator CHAR(16) NOT NULL DEFAULT 'intl',
    PRIMARY KEY (id),
    UNIQUE KEY u_key (instance_id, name),
    UNIQUE KEY u_pc (instance_id, local_point_code)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_m3ua_linkset - M3UA linksets (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_m3ua_linkset (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(32) NOT NULL,
    name VARCHAR(32) NOT NULL,
    m3ua_local_name VARCHAR(32) NOT NULL,
    adjacent_point_code CHAR(11) NOT NULL,
    traffic_mode CHAR(11) NOT NULL DEFAULT 'loadshare',
    PRIMARY KEY (id),
    UNIQUE KEY u_key (instance_id, name),
    UNIQUE KEY u_pc (instance_id, adjacent_point_code)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_m3ua_link - M3UA link configuration (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_m3ua_link (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(32) NOT NULL,
    name VARCHAR(32) NOT NULL,
    m3ua_linkset_name VARCHAR(32) NOT NULL,
    local_ip_addr CHAR(32) NOT NULL,
    local_port SMALLINT UNSIGNED NOT NULL DEFAULT 2905,
    remote_ip_addr CHAR(32) NOT NULL,
    remote_port SMALLINT UNSIGNED NOT NULL DEFAULT 2905,
    link_type CHAR(32) NOT NULL DEFAULT 'sgp',
    compat_mode CHAR(32) NOT NULL DEFAULT 'standard',
    max_ingress_streams TINYINT UNSIGNED NOT NULL DEFAULT 16,
    num_egress_streams TINYINT UNSIGNED NOT NULL DEFAULT 16,
    association_creation CHAR(32) NOT NULL DEFAULT 'initiate',
    max_path_mtu INT UNSIGNED NOT NULL DEFAULT 1500,
    network_appearance INT UNSIGNED NOT NULL DEFAULT 0,
    link_status CHAR(32) NOT NULL DEFAULT 'activated',
    PRIMARY KEY (id),
    UNIQUE KEY u_key (instance_id, name),
    UNIQUE KEY u_ip (instance_id, local_ip_addr, local_port, remote_ip_addr, remote_port)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_stp_route - STP routing table (SIGTRAN) (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_stp_route (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(255) NOT NULL,
    name VARCHAR(32) NOT NULL,
    enable TINYINT UNSIGNED NOT NULL DEFAULT 1,
    priority TINYINT UNSIGNED NOT NULL DEFAULT 1,
    linkset_ingress VARCHAR(32) NOT NULL DEFAULT '',
    linkset_egress VARCHAR(32) NOT NULL DEFAULT '',
    calling_gt VARCHAR(32) NOT NULL DEFAULT '',
    called_gt VARCHAR(32) NOT NULL DEFAULT '',
    imsi TEXT NOT NULL,
    translate_group VARCHAR(32) NOT NULL DEFAULT '',
    route_mode VARCHAR(32) NOT NULL DEFAULT 'loadshare',
    called_identity INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY u_key (instance_id, name)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_stp_translate - STP GT/PC translation rules (matches production)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_stp_translate (
    tid INT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(32) NOT NULL,
    name VARCHAR(32) NOT NULL,
    spc_rule VARCHAR(32) NOT NULL DEFAULT 'ignore',
    spc VARCHAR(32) NOT NULL DEFAULT '',
    dpc VARCHAR(32) NOT NULL DEFAULT '',
    spc_ni VARCHAR(32) NOT NULL DEFAULT 'intl',
    calling_rule VARCHAR(32) NOT NULL DEFAULT 'ignore',
    called_rule VARCHAR(32) NOT NULL DEFAULT 'ignore',
    calling_origin VARCHAR(32) NOT NULL DEFAULT '',
    calling_dest VARCHAR(32) NOT NULL DEFAULT '',
    called_origin VARCHAR(32) NOT NULL DEFAULT '',
    called_dest VARCHAR(32) NOT NULL DEFAULT '',
    PRIMARY KEY (tid),
    UNIQUE KEY u_key (instance_id, name)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_stp_trace - STP packet trace log
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_stp_trace (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    instance_id VARCHAR(255) NOT NULL,
    trace_id VARCHAR(255) NOT NULL,
    operation VARCHAR(32) NOT NULL,
    ue_id_type VARCHAR(32) NOT NULL,
    ue_id VARCHAR(32) NOT NULL,
    plmn_id VARCHAR(32) NOT NULL,
    interface VARCHAR(1024) NOT NULL,
    trace_depth VARCHAR(32) NOT NULL,
    trace_event VARCHAR(1024) NOT NULL,
    tce_ip VARCHAR(128) NOT NULL,
    tce_port VARCHAR(32) NOT NULL,
    tce_name VARCHAR(32) NOT NULL,
    trace_time BIGINT NOT NULL,
    start_time BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uidx (instance_id, trace_id, ue_id),
    KEY idx_tbl_stp_trace_instance_id (instance_id)
) ENGINE=InnoDB;

-- ============================================================================
-- Seed Data (from production captures: srg_db.sql + ham_stp1_tbl_stp_route.sql)
-- ============================================================================

-- tbl_dra_local
INSERT IGNORE INTO tbl_dra_local (instance_id, name, ip, port, protocol, realm, host, vendor_id, application_ids, product_name, tls_flag, crt_file_name, key_file_name)
VALUES
    ('srg01', 'MME_TO_DRA_2', '102.134.143.11', 3001, 'sctp', 'mnc020.mcc641.3gppnetwork.org', 'dra01hss01.mnc020.mcc641.3gppnetwork.org', 10415, '16777251', 'dra', 0, '', ''),
    ('srg01', 'DRA_TO_HSS', '102.134.143.10', 3868, 'sctp', 'mnc020.mcc641.3gppnetwork.org', 'dra01.mnc020.mcc641.3gppnetwork.org', 10415, '16777251', 'dra', 0, '', ''),
    ('srg01', 'MME_TO_DRA_1', '102.134.143.10', 3001, 'sctp', 'mnc020.mcc641.3gppnetwork.org', 'dra01hss01.mnc020.mcc641.3gppnetwork.org', 10415, '16777251', 'dra', 0, '', ''),
    ('srg01', 'DRA_to_SMSC', '102.134.143.10', 13868, 'sctp', 'mnc020.mcc641.3gppnetwork.org', 'dra1.mnc020.mcc641.3gppnetwork.org', 10415, '16777251', 'dra', 0, '', '');

-- tbl_dra_peer_set
INSERT IGNORE INTO tbl_dra_peer_set (instance_id, name, mode)
VALUES
    ('srg01', 'DRA_TO_HSS_PEER', 'balance'),
    ('srg01', 'MME_TO_DRA', 'balance'),
    ('srg01', 'MME02_TO_DRA', 'balance'),
    ('srg01', 'MME03_TO_DRA', 'balance'),
    ('srg01', 'DRA_to_SMSC', 'balance');

-- tbl_dra_peer (matches production peers)
INSERT IGNORE INTO tbl_dra_peer (instance_id, name, local_id, peer_set_id, remote_ip, remote_port, remote_host, remote_realm, remote_type, protocol, priority, enable, application_ids, vendor_id, product_name, tls_flag, crt_file_name, key_file_name, loop_flag, watchdog_interval, retransmit_timer, max_retransmit)
VALUES
    ('srg01', 'HSS01', 3, 2, '10.1.12.10', 3868, 'hss01.mnc020.mcc641.3gppnetwork.org', 'mnc020.mcc641.3gppnetwork.org', 'server', 'sctp', 1, 1, '16777251', 10415, 'dra', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME01', 4, 3, '212.88.127.158', 3868, 'mme4.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'USN', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME02', 2, 3, '212.88.127.158', 3868, 'mme4.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'USN', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME03', 4, 3, '212.88.127.159', 3868, 'mme4.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'USN', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME04', 2, 3, '212.88.127.159', 3868, 'mme4.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'USN', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME011', 4, 4, '212.88.127.154', 3868, 'mme3.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'USN', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME012', 2, 4, '212.88.127.154', 3868, 'mme3.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'USN', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME013', 4, 4, '212.88.127.155', 3868, 'mme3.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'USN', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME014', 2, 4, '212.88.127.155', 3868, 'mme3.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'USN', 0, '', '', 0, 5, 10, 3),
    ('srg01', 'MME021', 4, 5, '212.88.127.43', 3868, 'mme6.epc.mnc010.mcc641.3gppnetwork.org', 'epc.mnc010.mcc641.3gppnetwork.org', 'client', 'sctp', 1, 1, '16777251', 10415, 'UNC', 0, '', '', 0, 5, 10, 3);

-- tbl_dra_route (matches production IMSI-based routing)
INSERT IGNORE INTO tbl_dra_route (instance_id, name, origin_peer_set_id, dest_peer_set_id, imsi, application_id, priority)
VALUES
    ('srg01', 'MME01_TO_HSS', 3, 2, '64120*', '16777251', 1),
    ('srg01', 'HSS_TO_MME01', 2, 3, '64120*', '16777251', 1),
    ('srg01', 'MME02_TO_HSS', 4, 2, '64120*', '16777251', 1),
    ('srg01', 'HSS_TO_MME02', 2, 4, '64120*', '16777251', 1),
    ('srg01', 'MME03_To_HSS', 5, 2, '64120*', '16777251', 1),
    ('srg01', 'HSS_To_MME03', 2, 5, '64120*', NULL, 1);

-- tbl_dra_translate (AVP 283=Origin-Realm, 293=Destination-Host)
INSERT IGNORE INTO tbl_dra_translate (instance_id, name, origin_peer_set_name_id, dest_peer_set_name_id, avp_code, avp_type, avp_value, command_code, application_ids, set_session_id)
VALUES
    ('srg01', 'tranlats_1', 3, 2, 283, 'UTF8String', 'mnc020.mcc641.3gppnetwork.org', 0, '16777251', 0),
    ('srg01', 'translate_2', 3, 2, 293, 'UTF8String', 'hss01.mnc020.mcc641.3gppnetwork.org', 0, '16777251', 0);

-- tbl_m3ua_global
INSERT IGNORE INTO tbl_m3ua_global (instance_id, name, audit_interval, multiple_network_appearances, max_deactivate_attempts, fsm_timeout, tx_buffer_size, rx_buffer_size, max_ingress_streams, num_egress_streams, hb_interval, cong_onset_level1, cong_abatement_level1, cong_onset_level2, cong_abatement_level2, cong_onset_level3, cong_abatement_level3, cong_report_frequency)
VALUES
    ('srg01', 'STP_GLOBAL', 30000, 'disabled', 3, 2000, 102400, 102400, 16, 16, 3000, 80, 70, 90, 80, 100, 90, 1);

-- tbl_m3ua_local
INSERT IGNORE INTO tbl_m3ua_local (instance_id, name, local_point_code, point_code_length, network_indicator)
VALUES
    ('srg01', 'LOCAL_PointCode', '3.14.4', 14, 'natl'),
    ('srg01', 'test', '3.14.1', 14, 'intl');

-- tbl_m3ua_linkset
INSERT IGNORE INTO tbl_m3ua_linkset (instance_id, name, m3ua_local_name, adjacent_point_code, traffic_mode)
VALUES
    ('srg01', 'MSC_TO_STP', 'LOCAL_PointCode', '0.185.1', 'loadshare'),
    ('srg01', 'STP_TO_HLR', 'LOCAL_PointCode', '3.15.0', 'loadshare'),
    ('srg01', 'MSC_TO_STP_2', 'LOCAL_PointCode', '0.183.1', 'loadshare'),
    ('srg01', 'STP_IWF', 'LOCAL_PointCode', '3.14.2', 'loadshare'),
    ('srg01', 'STP_SMSC', 'LOCAL_PointCode', '3.14.6', 'loadshare'),
    ('srg01', 'STP_To_USSD', 'LOCAL_PointCode', '3.15.2', 'loadshare'),
    ('srg01', 'Safari_USSD', 'LOCAL_PointCode', '0.186.1', 'loadshare');

-- tbl_m3ua_link (matches production multi-homed links)
INSERT IGNORE INTO tbl_m3ua_link (instance_id, name, m3ua_linkset_name, local_ip_addr, local_port, remote_ip_addr, remote_port, link_type, compat_mode, max_ingress_streams, num_egress_streams, association_creation, max_path_mtu, network_appearance, link_status)
VALUES
    ('srg01', 'MSC01_1', 'MSC_TO_STP', '102.134.143.10;102.134.143.11', 46000, '10.1.250.66;10.1.250.74', 2905, 'ipspSe', 'standard', 16, 16, 'initiate', 1500, 0, 'activated'),
    ('srg01', 'HLR01', 'STP_TO_HLR', '102.134.143.10', 46001, '10.1.12.10', 5001, 'ipspSe', 'standard', 16, 16, 'initiate', 1500, 0, 'activated'),
    ('srg01', 'MSC01', 'MSC_TO_STP_2', '102.134.143.10;102.134.143.11', 46001, '10.1.22.3;10.1.22.35', 2905, 'ipspSe', 'standard', 16, 16, 'initiate', 1500, 0, 'activated'),
    ('srg01', 'IWF01', 'STP_IWF', '102.134.143.10', 47000, '10.1.12.130', 47000, 'ipspSe', 'standard', 16, 16, 'initiate', 1500, 0, 'activated'),
    ('srg01', 'SMSC01', 'STP_SMSC', '102.134.143.10', 46002, '10.1.12.140', 47000, 'ipspSe', 'standard', 16, 16, 'initiate', 1500, 1, 'activated'),
    ('srg01', 'USSD01', 'STP_To_USSD', '102.134.143.10', 46099, '10.1.12.141', 48000, 'ipspSe', 'standard', 16, 16, 'initiate', 1500, 0, 'activated'),
    ('srg01', 'USSD1', 'Safari_USSD', '10.1.10.21', 46022, '10.1.10.80', 46022, 'ipspSe', 'standard', 16, 16, 'accept', 1500, 0, 'activated');

-- tbl_stp_route (258 routes from ham_stp1_tbl_stp_route.sql - key routes inserted)
INSERT IGNORE INTO tbl_stp_route (instance_id, name, enable, priority, linkset_ingress, linkset_egress, calling_gt, called_gt, imsi, translate_group, route_mode, called_identity)
VALUES
    ('srg01', 'routeFromKambcToHLR_Reg', 1, 1, 'MSC_TO_STP', 'STP_TO_HLR,STP_TO_HLR_2', '*', '256724000000', '', '', 'redundant', 0),
    ('srg01', 'routeFromMumbcToHLR_Reg', 1, 1, 'MSC_TO_STP_2', 'STP_TO_HLR,STP_TO_HLR_2', '*', '256724000000', '', '', 'redundant', 0),
    ('srg01', 'routeFromHLRToMsc', 1, 1, 'STP_TO_HLR', 'MSC_TO_STP,MSC_TO_STP_2', '*', '2567711010', '', '', 'redundant', 0),
    ('srg01', 'routeFromHLRToSgsn', 1, 1, 'STP_TO_HLR', 'MSC_TO_STP,MSC_TO_STP_2', '*', '25677110036', '', '', 'redundant', 0),
    ('srg01', 'routeFromSgsnToHLR_LUAck_1', 1, 1, 'MSC_TO_STP_2', 'STP_TO_HLR,STP_TO_HLR_2', '256771100362', '25672400001', '', '', 'redundant', 0),
    ('srg01', 'routeFromSgsnToHLR_LUAck_2', 1, 1, 'MSC_TO_STP_2', 'STP_TO_HLR,STP_TO_HLR_2', '256771100361', '25672400001', '', '', 'redundant', 0),
    ('srg01', 'routeFromSgsnToHLR_LUAck_3', 1, 1, 'MSC_TO_STP', 'STP_TO_HLR,STP_TO_HLR_2', '256771100362', '25672400001', '', '', 'redundant', 0),
    ('srg01', 'routeFromSgsnToHLR_LUAck_4', 1, 1, 'MSC_TO_STP', 'STP_TO_HLR,STP_TO_HLR_2', '256771100361', '25672400001', '', '', 'redundant', 0),
    ('srg01', 'routeFromKambcToIWF_C', 1, 1, 'MSC_TO_STP', 'STP_IWF,STP_IWF_2', '*', '256724000016', '', '', 'redundant', 0),
    ('srg01', 'routeFromMumbcToIWF_C', 1, 1, 'MSC_TO_STP_2', 'STP_IWF,STP_IWF_2', '*', '256724000016', '', '', 'redundant', 0),
    ('srg01', 'routeFromKambcToSMSC_SMSin', 1, 1, 'MSC_TO_STP', 'STP_SMSC,STP_SMSC_02', '*', '256724000010', '', '', 'redundant', 0),
    ('srg01', 'routeFromMumbcToSMSC_SMSin', 1, 1, 'MSC_TO_STP_2', 'STP_SMSC,STP_SMSC_02', '*', '256724000010', '', '', 'redundant', 0),
    ('srg01', 'routeFromSMSCToMsc_SMSOaAck', 1, 1, 'STP_SMSC', 'MSC_TO_STP,MSC_TO_STP_2', '256724000010', '2567711010', '', '', 'redundant', 0),
    ('srg01', 'routeFromSMSCToHLR_SRIreq', 1, 1, 'STP_SMSC', 'STP_TO_HLR,STP_TO_HLR_2', '256724000010', '256724', '', '', 'redundant', 0),
    ('srg01', 'routeFromHLRToSMSC_SRIAck', 1, 1, 'STP_TO_HLR', 'STP_SMSC,STP_SMSC_02', '256724000014', '256724000010', '', '', 'redundant', 0),
    ('srg01', 'routeFromIWFToMSC_iDPContinue', 1, 1, 'STP_IWF', 'MSC_TO_STP_2,MSC_TO_STP', '256724000016', '2567711010', '', '', 'redundant', 0),
    ('srg01', 'routeFromMSCToHLR_USSDString', 1, 1, 'MSC_TO_STP', 'STP_TO_HLR', '2567711010', '256724000014', '', '', 'redundant', 0),
    ('srg01', 'routeFromMumbcToHLR_USSDString', 1, 1, 'MSC_TO_STP_2', 'STP_TO_HLR', '25677110106', '256724000014', '', '', 'redundant', 0),
    ('srg01', 'routeFromMSCToHLR_voiceSRI', 1, 1, 'MSC_TO_STP_2', 'STP_TO_HLR', '25677110106', '256724005011', '', '', 'redundant', 0),
    ('srg01', 'routeFromHLRToUSSD_ussdString', 1, 1, 'STP_TO_HLR', 'Safari_USSD', '256724000014', '256724000020', '', '', 'redundant', 0),
    ('srg01', 'routeFromUssdToHLR_ssreq', 1, 1, 'Safari_USSD', 'STP_TO_HLR', '256724000020', '256724000014', '', '', 'redundant', 0);

-- tbl_stp_translate (GT translation rules)
INSERT IGNORE INTO tbl_stp_translate (instance_id, name, spc_rule, spc, dpc, spc_ni, calling_rule, called_rule, calling_origin, calling_dest, called_origin, called_dest)
VALUES
    ('srg01', 'trans_sgsn_1', 'changeNi', '1.1.1', '1.1.1', 'natlSpare', 'ignore', 'ignore', '256771100361', '256771100361', '256771100361', '256771101061'),
    ('srg01', 'trans_sgsn_2', 'ignore', '1.1.1', '2.2.2', 'intl', 'ignore', 'modPrefix', '256771101061', '256771101061', '256771100362', '256771101061'),
    ('srg01', 'trans_smsc_1', 'ignore', '1.1.1', '1.2.2', 'intl', 'ignore', 'replaceGT', '256724000018', '256724000014', '2567', '256771100057'),
    ('srg01', 'trans_smsc_2', 'ignore', '1.1.1', '2.2.2', 'intl', 'ignore', 'replaceGT', '', '', '256765', '256771101626');

-- -----------------------------------------------------
-- End of srg_db.sql
-- -----------------------------------------------------
