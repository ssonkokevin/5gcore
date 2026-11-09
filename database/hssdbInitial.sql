-- ============================================================================
-- hssdbInitial.sql - UDM/HSS/HLR Subscriber Database Schema
-- Tri-mode HLR/HSS/UDM (mirrored from protei-scp-platform/udm-build/hssdbInitial.sql)
-- Tables: tbl_subscriber, tbl_auth_vector, tbl_roaming, tbl_service_profile
-- ============================================================================

CREATE DATABASE IF NOT EXISTS hssdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hssdb;

-- -----------------------------------------------------
-- tbl_subscriber - Core subscriber record (HLR/HSS/UDM)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_subscriber (
    imsi VARCHAR(15) NOT NULL,
    msisdn VARCHAR(15),
    imei VARCHAR(15),
    authentication_key VARCHAR(32),   -- Ki
    opc VARCHAR(32),                  -- OPC
    network_access_mode INT NOT NULL DEFAULT 0,
    subscriber_status INT NOT NULL DEFAULT 0,
    roaming_restricted TINYINT(1) NOT NULL DEFAULT 0,
    ambr_ul VARCHAR(32),
    ambr_dl VARCHAR(32),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (imsi),
    UNIQUE KEY uk_msisdn (msisdn)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_auth_vector - Authentication vectors
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_auth_vector (
    imsi VARCHAR(15) NOT NULL,
    rand VARCHAR(32),
    autn VARCHAR(32),
    res VARCHAR(16),
    ck VARCHAR(32),
    ik VARCHAR(32),
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (imsi),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_roaming - Roaming restrictions
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_roaming (
    imsi VARCHAR(15) NOT NULL,
    visited_plmn VARCHAR(6),
    roaming_allowed TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (imsi),
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi)
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
    FOREIGN KEY (imsi) REFERENCES tbl_subscriber(imsi)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- Seed: example subscriber
-- -----------------------------------------------------
INSERT IGNORE INTO tbl_subscriber
    (imsi, msisdn, imei, authentication_key, opc, network_access_mode, subscriber_status, roaming_restricted, ambr_ul, ambr_dl)
VALUES
    ('208010123456789', '33061234567', '123456789012345', '00112233445566778899AABBCCDDEEFF', '00112233445566778899AABBCCDDEEFF', 0, 0, 0, '100Mbps', '100Mbps');

-- -----------------------------------------------------
-- End of hssdbInitial.sql
-- -----------------------------------------------------
