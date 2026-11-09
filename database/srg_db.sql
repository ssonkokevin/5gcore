-- ============================================================================
-- srg_db.sql - STP/DRA Core Database Schema
-- Mirrors production schema from D:\core dpi\sql\srg_db.sql
-- Tables: tbl_dra_local, tbl_dra_peer, tbl_dra_peer_set, tbl_dra_route,
--         tbl_dra_translate, tbl_m3ua_link, tbl_m3ua_as, tbl_m3ua_asp,
--         tbl_stp_route, tbl_stp_translate, tbl_stp_trace
-- ============================================================================

CREATE DATABASE IF NOT EXISTS srg_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE srg_db;

-- -----------------------------------------------------
-- tbl_dra_local - Local DRA instance identity
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_local (
    id INT NOT NULL AUTO_INCREMENT,
    origin_host VARCHAR(255) NOT NULL,
    origin_realm VARCHAR(255) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    vendor_id INT NOT NULL DEFAULT 10415,
    port INT NOT NULL DEFAULT 3868,
    realm VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_origin_host (origin_host)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_peer - Known Diameter/SIGTRAN peers
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_peer (
    id INT NOT NULL AUTO_INCREMENT,
    peer_name VARCHAR(255) NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INT NOT NULL DEFAULT 3868,
    realm VARCHAR(255) NOT NULL,
    protocol ENUM('diameter','sigtran','sctp') NOT NULL DEFAULT 'diameter',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_peer_name (peer_name)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_peer_set - Peer groups for redundancy
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_peer_set (
    id INT NOT NULL AUTO_INCREMENT,
    set_name VARCHAR(255) NOT NULL,
    peer_name VARCHAR(255) NOT NULL,
    priority INT NOT NULL DEFAULT 1,
    route_mode ENUM('redundant','primary','backup') NOT NULL DEFAULT 'primary',
    FOREIGN KEY (peer_name) REFERENCES tbl_dra_peer(peer_name),
    PRIMARY KEY (id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_route - Diameter routing table
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_route (
    id INT NOT NULL AUTO_INCREMENT,
    destination_realm VARCHAR(255) NOT NULL,
    application_id BIGINT NOT NULL,
    command_code INT NOT NULL,
    peer_name VARCHAR(255) NOT NULL,
    action ENUM('route','proxy','translate','reject') NOT NULL DEFAULT 'route',
    FOREIGN KEY (peer_name) REFERENCES tbl_dra_peer(peer_name),
    PRIMARY KEY (id),
    UNIQUE KEY uk_dra_route (destination_realm, application_id, command_code)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_dra_translate - Diameter <-> M3UA translation rules
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_dra_translate (
    id INT NOT NULL AUTO_INCREMENT,
    direction ENUM('m3ua_to_diameter','diameter_to_m3ua') NOT NULL,
    si INT NOT NULL,
    ssn INT NOT NULL,
    application_id BIGINT,
    command_code INT,
    target_application BIGINT,
    target_si INT,
    target_ssn INT,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_m3ua_link - M3UA link configuration
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_m3ua_link (
    id INT NOT NULL AUTO_INCREMENT,
    link_name VARCHAR(255) NOT NULL,
    local_ip VARCHAR(45) NOT NULL,
    remote_ip VARCHAR(45) NOT NULL,
    local_port INT NOT NULL DEFAULT 2905,
    remote_port INT NOT NULL DEFAULT 2905,
    sctp_role ENUM('asp','sgp') NOT NULL DEFAULT 'asp',
    instance INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_m3ua_as - M3UA Application Server
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_m3ua_as (
    id INT NOT NULL AUTO_INCREMENT,
    as_name VARCHAR(255) NOT NULL,
    routing_context INT NOT NULL,
    traffic_mode ENUM('broadcast','override','loadshare','roundrobin') NOT NULL DEFAULT 'broadcast',
    PRIMARY KEY (id),
    UNIQUE KEY uk_as_name (as_name)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_m3ua_asp - M3UA Application Server Process
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_m3ua_asp (
    id INT NOT NULL AUTO_INCREMENT,
    asp_name VARCHAR(255) NOT NULL,
    as_name VARCHAR(255) NOT NULL,
    instance INT NOT NULL DEFAULT 0,
    FOREIGN KEY (as_name) REFERENCES tbl_m3ua_as(as_name),
    PRIMARY KEY (id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_stp_route - STP routing table (SIGTRAN)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_stp_route (
    id INT NOT NULL AUTO_INCREMENT,
    dpc VARCHAR(20) NOT NULL,
    opc VARCHAR(20) NOT NULL,
    si INT NOT NULL,
    ssn INT NOT NULL,
    route_mode ENUM('redundant','primary','backup') NOT NULL DEFAULT 'redundant',
    destination VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_stp_route (dpc, opc, si, ssn)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_stp_translate - STP translation rules
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_stp_translate (
    id INT NOT NULL AUTO_INCREMENT,
    direction ENUM('diameter_to_m3ua','m3ua_to_diameter') NOT NULL,
    application_id BIGINT,
    command_code INT,
    si INT NOT NULL,
    ssn INT NOT NULL,
    target_si INT,
    target_ssn INT,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- tbl_stp_trace - STP packet trace log
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS tbl_stp_trace (
    id INT NOT NULL AUTO_INCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dpc VARCHAR(20),
    opc VARCHAR(20),
    si INT,
    ssn INT,
    message_type VARCHAR(50),
    src_ip VARCHAR(45),
    dst_ip VARCHAR(45),
    payload_len INT,
    PRIMARY KEY (id),
    KEY idx_timestamp (timestamp)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- Seed data (mirrors ham_stp1_tbl_stp_route.sql patterns)
-- -----------------------------------------------------
INSERT IGNORE INTO tbl_dra_local (origin_host, origin_realm, product_name, vendor_id, port, realm)
VALUES ('dra.core.local', 'core.local', 'SRG-DRA', 10415, 3868, 'core.local');

INSERT IGNORE INTO tbl_dra_peer (peer_name, host, port, realm, protocol, is_active)
VALUES
    ('udm', 'udm', 3868, 'core.local', 'diameter', 1),
    ('scp', 'scp', 3868, 'core.local', 'diameter', 1),
    ('stp', 'stp', 2905, 'core.local', 'sigtran', 1);

INSERT IGNORE INTO tbl_dra_peer_set (set_name, peer_name, priority, route_mode)
VALUES
    ('core_peers', 'udm', 1, 'primary'),
    ('core_peers', 'scp', 2, 'backup'),
    ('core_peers', 'stp', 3, 'redundant');

INSERT IGNORE INTO tbl_dra_route (destination_realm, application_id, command_code, peer_name, action)
VALUES
    ('core.local', 16777216, 272, 'udm', 'route'),
    ('core.local', 16777216, 272, 'scp', 'proxy'),
    ('core.local', 16777216, 272, 'stp', 'translate');

INSERT IGNORE INTO tbl_dra_translate (direction, si, ssn, application_id, command_code, target_application, target_si, target_ssn)
VALUES
    ('m3ua_to_diameter', 3, 8, NULL, NULL, 16777216, NULL, NULL),
    ('diameter_to_m3ua', NULL, NULL, 16777216, 272, NULL, 3, 8);

INSERT IGNORE INTO tbl_m3ua_link (link_name, local_ip, remote_ip, local_port, remote_port, sctp_role, instance)
VALUES ('stp-link-0', '0.0.0.0', '0.0.0.0', 2905, 2905, 'asp', 0);

INSERT IGNORE INTO tbl_m3ua_as (as_name, routing_context, traffic_mode)
VALUES ('core-stp-as', 1, 'broadcast');

INSERT IGNORE INTO tbl_m3ua_asp (asp_name, as_name, instance)
VALUES ('core-stp-asp', 'core-stp-as', 0);

INSERT IGNORE INTO tbl_stp_route (dpc, opc, si, ssn, route_mode, destination)
VALUES
    ('0.0.0', '0.0.0', 3, 0, 'redundant', 'dra'),
    ('1.1.1', '2.2.2', 3, 8, 'redundant', 'udm'),
    ('1.1.1', '3.3.3', 3, 8, 'primary', 'udm'),
    ('2.2.2', '1.1.1', 3, 8, 'redundant', 'scp');

INSERT IGNORE INTO tbl_stp_translate (direction, application_id, command_code, si, ssn, target_si, target_ssn)
VALUES
    ('diameter_to_m3ua', 16777216, 272, 3, 8, 3, 8),
    ('m3ua_to_diameter', NULL, NULL, 3, 8, NULL, NULL);

-- -----------------------------------------------------
-- End of srg_db.sql
-- -----------------------------------------------------
