-- ============================================================================
-- Location services - core-side schema (tenant aware)
--
-- Owner: the E-SMLC, the LMF and the MME LCS function. The GMLC has its own
-- database in its own repository; this schema holds only what the positioning
-- engines and the MME need. Cell coordinates are duplicated here as a
-- positioning subset of the GMLC's authoritative cell database (D8); the
-- import format is identical.
--
-- Target: MariaDB 10.x / InnoDB / utf8mb4. Every table carries tenant_id
-- (D11). Scripts in this directory are ordered and idempotent.
-- ============================================================================

SET NAMES utf8mb4;

-- ----------------------------------------------------------------------------
-- Schema bookkeeping
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tbl_lcs_schema_version (
    script      VARCHAR(64) NOT NULL,
    applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(255) NOT NULL,
    PRIMARY KEY (script)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Location schema scripts applied, in order';

CREATE TABLE IF NOT EXISTS tbl_location_tenant (
    tenant_id   BIGINT UNSIGNED NOT NULL,
    name        VARCHAR(128) NOT NULL,
    active      TINYINT(1) NOT NULL DEFAULT 1,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Tenants. Hamiltel is tenant 1.';

INSERT IGNORE INTO tbl_location_tenant (tenant_id, name) VALUES (1, 'Hamiltel');

-- ----------------------------------------------------------------------------
-- Positioning cells and transmission/reception points
--
-- Only the fields an engine needs to place a measurement. Cell identity is the
-- canonical string defined in database/location/README.md.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tbl_lcs_cell (
    tenant_id         BIGINT UNSIGNED NOT NULL DEFAULT 1,
    rat               ENUM('GSM','UMTS','LTE','NR') NOT NULL,
    cell_identity     VARCHAR(32) NOT NULL COMMENT 'canonical mcc-mnc-<area>-<cell>',
    plmn_mcc          CHAR(3) NOT NULL,
    plmn_mnc          CHAR(3) NOT NULL,
    area_code         VARCHAR(16) NULL COMMENT 'LAC or TAC or NR-TAC, decimal',
    cell_code         VARCHAR(16) NOT NULL COMMENT 'CI / ECI / NCI, decimal',
    site_name         VARCHAR(128) NULL,
    latitude          DECIMAL(9,7) NULL,
    longitude         DECIMAL(10,7) NULL,
    antenna_height_m  DECIMAL(6,1) NULL,
    azimuth_deg       SMALLINT UNSIGNED NULL COMMENT '0-359, true north',
    beamwidth_deg     SMALLINT UNSIGNED NULL,
    radius_m          INT UNSIGNED NULL COMMENT 'coverage radius when no polygon',
    coverage_polygon  JSON NULL COMMENT '[[lat,lon],...] when known',
    pci               SMALLINT UNSIGNED NULL,
    arfcn             INT NULL COMMENT 'ARFCN / EARFCN / NR-ARFCN',
    prs_config        JSON NULL COMMENT 'PRS/TRS parameters for OTDOA/RTT',
    timing_advance    JSON NULL COMMENT 'TA step, unit and resolution parameters',
    cell_type         ENUM('MACRO','MICRO','INDOOR','UNKNOWN') NOT NULL DEFAULT 'UNKNOWN',
    data_source       VARCHAR(64) NULL COMMENT 'who supplied the geometry',
    data_quality      TINYINT UNSIGNED NULL COMMENT '0-100, see README',
    last_verified     DATE NULL,
    valid_from        TIMESTAMP NULL,
    valid_to          TIMESTAMP NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, rat, cell_identity),
    KEY idx_lcs_cell_area (tenant_id, rat, area_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Cell/TRP geometry for positioning; subset of the GMLC cell database';

-- ----------------------------------------------------------------------------
-- Positioning sessions
--
-- One row per MT-LR handled by an engine. The state column is the engine's
-- own view; the GMLC keeps its request state separately and correlates by
-- its own reference. A row is closed exactly once: DELIVERED, ABORTED,
-- TIMEOUT or FAILED.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tbl_lcs_session (
    tenant_id             BIGINT UNSIGNED NOT NULL DEFAULT 1,
    session_id            CHAR(36) NOT NULL COMMENT 'UUID assigned by the engine',
    engine                ENUM('E_SMLC','LMF','SMLC') NOT NULL,
    rat                   ENUM('GSM','UMTS','LTE','NR') NOT NULL,
    serving_node          VARCHAR(64) NOT NULL COMMENT 'MME/AMF identity that owns the session',
    external_ref          VARCHAR(64) NULL COMMENT 'MME/AMF correlation id (LCS-AP or SBI)',
    ue_imsi               VARCHAR(15) NOT NULL,
    ue_imei               VARCHAR(16) NULL,
    state                 ENUM('CREATED','CAPABILITY','ASSISTANCE','MEASUREMENT','SOLVED',
                               'DELIVERED','ABORTED','TIMEOUT','FAILED') NOT NULL,
    requested_accuracy_m  INT UNSIGNED NULL,
    method_ladder         JSON NULL COMMENT 'ordered methods the selector chose',
    used_method           VARCHAR(16) NULL,
    result_id             CHAR(36) NULL,
    failure_cause         VARCHAR(64) NULL,
    paging_performed      TINYINT(1) NOT NULL DEFAULT 0,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at            TIMESTAMP NULL,
    closed_at             TIMESTAMP NULL,
    PRIMARY KEY (tenant_id, session_id),
    KEY idx_lcs_session_open (tenant_id, state, expires_at),
    KEY idx_lcs_session_ue (tenant_id, ue_imsi, created_at),
    KEY idx_lcs_session_ref (tenant_id, external_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Positioning sessions handled by E-SMLC/LMF';

-- ----------------------------------------------------------------------------
-- Cached LPP capabilities per UE
--
-- The engine learns these over LPP; caching them per IMSI shortens the method
-- ladder for the next request. Cache only - a stale entry is refreshed on use.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tbl_ue_lcs_capability (
    tenant_id            BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ue_imsi              VARCHAR(15) NOT NULL,
    lpp_supported        TINYINT(1) NOT NULL DEFAULT 0,
    methods              JSON NULL COMMENT '["A_GNSS","E_CID",...] as reported',
    gnss_capable         TINYINT(1) NULL,
    raw_capabilities     JSON NULL COMMENT 'LPP ProvideCapabilities, verbatim',
    reported_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at         TIMESTAMP NULL,
    PRIMARY KEY (tenant_id, ue_imsi)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Per-UE LPP capability cache';

-- ----------------------------------------------------------------------------
-- Results
--
-- Immutable. A result is written once, before delivery, so a crash after
-- delivery cannot lose the evidence and a result can never be edited after
-- the fact. The envelope columns are mandatory (D10).
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tbl_lcs_result (
    tenant_id              BIGINT UNSIGNED NOT NULL DEFAULT 1,
    result_id              CHAR(36) NOT NULL,
    session_id             CHAR(36) NOT NULL,
    ue_imsi                VARCHAR(15) NOT NULL,
    rat                    ENUM('GSM','UMTS','LTE','NR') NOT NULL,
    method                 VARCHAR(16) NOT NULL,
    methods_attempted      JSON NOT NULL,
    shape                  ENUM('POINT','CIRCLE','ELLIPSE','POLYGON','ARC') NOT NULL,
    latitude               DECIMAL(9,7) NULL,
    longitude              DECIMAL(10,7) NULL,
    altitude_m             DECIMAL(7,1) NULL,
    uncertainty_m          INT UNSIGNED NOT NULL,
    confidence             TINYINT UNSIGNED NOT NULL,
    age_seconds            INT UNSIGNED NOT NULL,
    accuracy_requested_m   INT UNSIGNED NULL,
    accuracy_fulfilled     TINYINT(1) NOT NULL,
    serving_cell           VARCHAR(32) NULL,
    engine                 ENUM('E_SMLC','LMF','SMLC') NOT NULL,
    serving_node           VARCHAR(64) NOT NULL,
    produced_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    shape_payload          JSON NULL COMMENT 'TS 23.032 shape as delivered',
    PRIMARY KEY (tenant_id, result_id),
    KEY idx_lcs_result_session (tenant_id, session_id),
    KEY idx_lcs_result_time (tenant_id, produced_at),
    CONSTRAINT chk_lcs_result_confidence CHECK (confidence <= 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Positioning results with method, uncertainty, confidence and age';

INSERT IGNORE INTO tbl_lcs_schema_version (script, description)
VALUES ('001_location_schema.sql',
        'location tenant, cells, sessions, UE capability cache, results');
