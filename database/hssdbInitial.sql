-- ============================================================================
-- hssdbInitial.sql - UDM/HSS/HLR Subscriber Database Schema
-- Tri-mode HLR/HSS/UDM (mirrored from protei-scp-platform/udm-build/hssdbInitial.sql)
-- Extended for 5G/4G/3G/2G with full key hierarchy, batch provisioning
-- Tables: tbl_subscriber, tbl_auth_vector, tbl_roaming, tbl_service_profile,
--         tbl_batch_upload, tbl_imsi_range
-- ============================================================================

CREATE DATABASE IF NOT EXISTS hssdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hssdb;

-- -----------------------------------------------------
-- tbl_subscriber - Core subscriber record (HLR/HSS/UDM)
-- Tri-mode: 5G (K, OP, SQN, AMF, K_ASME, K_SEAF, K_AUSF)
--           4G (Ki, OPc, SQN, AMF, K_ASME)
--           3G/2G (Ki, Kc, SRES, OPc)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_subscriber (
    imsi VARCHAR(15) NOT NULL,
    msisdn VARCHAR(15),
    imei VARCHAR(15),
    -- 5G/4G Root Keys
    k VARCHAR(32) COMMENT '5G root key (K4) - 256-bit hex',
    ki VARCHAR(32) COMMENT '4G/3G/2G root key (Ki) - 128-bit hex',
    -- OP/OPc
    op VARCHAR(32) COMMENT 'OP (Operator Variant Algorithm config) - 128-bit hex',
    opc VARCHAR(32) COMMENT 'OPc (derived OP) - 128-bit hex',
    -- Sequence & AMF
    sqn BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Sequence number for AKA',
    amf VARCHAR(8) DEFAULT '8000' COMMENT 'Authentication Management Field (hex)',
    -- Derived 5G Key Hierarchy
    k_asme VARCHAR(32) COMMENT 'K_ASME (Access Security Mgmt Entity Key)',
    k_seaf VARCHAR(32) COMMENT 'K_SEAF (Serving Entity Auth Field Key)',
    k_ausf VARCHAR(32) COMMENT 'K_AUSF (AUSF Key)',
    -- 2G/3G Cipher & Auth
    kc VARCHAR(32) COMMENT 'Kc (2G/3G Cipher Key) - 64-bit hex',
    sres VARCHAR(16) COMMENT 'SRES (2G/3G Auth Response) - 32-bit hex',
    -- Network Access
    network_access_mode INT NOT NULL DEFAULT 2 COMMENT '0=GPRS, 1=CS, 2=Both, 3=5G',
    subscriber_status INT NOT NULL DEFAULT 0 COMMENT '0=Active, 1=Barred, 2=Suspended',
    roaming_restricted TINYINT(1) NOT NULL DEFAULT 0,
    -- QoS
    ambr_ul VARCHAR(32) COMMENT 'UL AMBR (e.g., 100Mbps)',
    ambr_dl VARCHAR(32) COMMENT 'DL AMBR (e.g., 100Mbps)',
    -- Batch Provisioning
    batch_id VARCHAR(64) COMMENT 'Batch upload identifier',
    imsi_range_start VARCHAR(15) COMMENT 'For range allocations',
    imsi_range_end VARCHAR(15) COMMENT 'For range allocations',
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (imsi),
    UNIQUE KEY uk_msisdn (msisdn),
    KEY idx_batch_id (batch_id),
    KEY idx_imsi_range (imsi_range_start, imsi_range_end)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_auth_vector - Authentication vectors (pre-computed)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_auth_vector (
    imsi VARCHAR(15) NOT NULL,
    rand VARCHAR(32) COMMENT 'RAND (128-bit hex)',
    autn VARCHAR(32) COMMENT 'AUTN (128-bit hex)',
    res VARCHAR(16) COMMENT 'RES (64-bit hex)',
    xres VARCHAR(32) COMMENT 'XRES (extended RES for 5G)',
    ck VARCHAR(32) COMMENT 'CK (Cipher Key)',
    ik VARCHAR(32) COMMENT 'IK (Integrity Key)',
    k_asme VARCHAR(32) COMMENT 'K_ASME (5G)',
    k_seaf VARCHAR(32) COMMENT 'K_SEAF (5G)',
    k_ausf VARCHAR(32) COMMENT 'K_AUSF (5G)',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (imsi),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_roaming - Roaming restrictions per visited PLMN
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_roaming (
    imsi VARCHAR(15) NOT NULL,
    visited_plmn VARCHAR(6) NOT NULL COMMENT 'MCC+MNC (e.g., 310260)',
    roaming_allowed TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (imsi, visited_plmn),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_service_profile - Service control profile (SCP linkage)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_service_profile (
    imsi VARCHAR(15) NOT NULL,
    service_key VARCHAR(64),
    scp_trigger VARCHAR(64),
    camel_phase INT NOT NULL DEFAULT 1,
    PRIMARY KEY (imsi),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi) ON DELETE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_batch_upload - Batch upload tracking & audit
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_batch_upload (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(64) NOT NULL UNIQUE,
    filename VARCHAR(255),
    total_records INT UNSIGNED NOT NULL DEFAULT 0,
    successful_records INT UNSIGNED NOT NULL DEFAULT 0,
    failed_records INT UNSIGNED NOT NULL DEFAULT 0,
    status ENUM('pending','processing','completed','failed') NOT NULL DEFAULT 'pending',
    error_log JSON COMMENT 'Failed record details',
    created_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_batch_id (batch_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_imsi_range - IMSI range management for allocations
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_imsi_range (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    range_name VARCHAR(64) NOT NULL UNIQUE,
    mcc VARCHAR(3) NOT NULL,
    mnc VARCHAR(3) NOT NULL,
    msisdn_prefix VARCHAR(10),
    imsi_start VARCHAR(15) NOT NULL,
    imsi_end VARCHAR(15) NOT NULL,
    next_imsi VARCHAR(15) NOT NULL,
    allocated_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    total_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    status ENUM('available','exhausted','reserved') NOT NULL DEFAULT 'available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_range (mcc, mnc, imsi_start, imsi_end)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- Seed: example subscribers (5G/4G/3G/2G compatible)
-- -----------------------------------------------------
INSERT IGNORE INTO tbl_subscriber
    (imsi, msisdn, imei, k, ki, op, opc, sqn, amf, network_access_mode, subscriber_status, ambr_ul, ambr_dl)
VALUES
    -- 5G/4G/3G/2G full provisioned (OPc pre-derived from OP+K)
    ('208010123456789', '33061234567', '123456789012345',
     '00112233445566778899AABBCCDDEEFF',  -- K (5G)
     '00112233445566778899AABBCCDDEEFF',  -- Ki (4G/3G/2G)
     '63BFA50EE6523365FF14C1F45F88737D',  -- OP
     '00112233445566778899AABBCCDDEEFF',  -- OPc (example)
     0, '8000', 2, 0, '100Mbps', '100Mbps'),
    -- 5G-only (K only, OPc derived)
    ('208010123456790', '33061234568', '123456789012346',
     '112233445566778899AABBCCDDEEFF00',
     NULL, '63BFA50EE6523365FF14C1F45F88737D', NULL, 0, '8000', 3, 0, '1Gbps', '1Gbps'),
    -- 4G-only (Ki + OPc)
    ('208010123456791', '33061234569', '123456789012347',
     NULL, '2233445566778899AABBCCDDEEFF0011',
     NULL, '33445566778899AABBCCDDEEFF001122', 0, '8000', 2, 0, '100Mbps', '100Mbps');

-- -----------------------------------------------------
-- Seed: IMSI range for batch allocations (MCC=208, MNC=01)
-- -----------------------------------------------------
INSERT IGNORE INTO tbl_imsi_range
    (range_name, mcc, mnc, msisdn_prefix, imsi_start, imsi_end, next_imsi, total_count)
VALUES
    ('france-orange-5g', '208', '01', '3306', '208010100000000', '208010199999999', '208010100000000', 100000),
    ('france-orange-4g', '208', '01', '3307', '208010200000000', '208010299999999', '208010200000000', 100000);

-- -----------------------------------------------------
-- End of hssdbInitial.sql
-- -----------------------------------------------------
