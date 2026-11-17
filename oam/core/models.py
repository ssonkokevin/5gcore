"""
OAM Core Models - 5G Core Network Management
Maps to database schema from srg_db.sql (STP/DRA tables) and hssdbInitial.sql (UDM tables)
Extended for 5G/4G/3G/2G tri-mode with full key hierarchy, batch provisioning
Release: 3GPP Rel-15 through Rel-20 (R20)
"""
from django.db import models


class DRAView(models.Model):
    """Read-only views for DRA management (tbl_dra_*)"""
    class Meta:
        managed = False
        abstract = True


class DRALocal(DRAView):
    id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=255)
    name = models.CharField(max_length=32, unique=True)
    ip = models.CharField(max_length=32)
    port = models.SmallIntegerField(default=3868)
    protocol = models.CharField(max_length=32)
    realm = models.CharField(max_length=256)
    host = models.CharField(max_length=256)
    vendor_id = models.PositiveIntegerField(default=10415)
    application_ids = models.CharField(max_length=255)
    product_name = models.CharField(max_length=32)
    tls_flag = models.BooleanField(default=False)
    crt_file_name = models.CharField(max_length=255, default="")
    key_file_name = models.CharField(max_length=255, default="")

    class Meta:
        db_table = "tbl_dra_local"


class DRAPeerSet(DRAView):
    peerset_id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=255)
    name = models.CharField(max_length=32, unique=True)
    mode = models.CharField(max_length=32, default="balance")

    class Meta:
        db_table = "tbl_dra_peer_set"


class DRAPeer(DRAView):
    peer_id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=255)
    name = models.CharField(max_length=32, unique=True)
    local = models.ForeignKey(DRALocal, on_delete=models.DO_NOTHING, db_column="local_id")
    peer_set = models.ForeignKey(DRAPeerSet, on_delete=models.DO_NOTHING, db_column="peer_set_id")
    remote_ip = models.CharField(max_length=32)
    remote_port = models.PositiveIntegerField(default=3868)
    remote_host = models.CharField(max_length=256)
    remote_realm = models.CharField(max_length=256)
    remote_type = models.CharField(max_length=64)
    protocol = models.CharField(max_length=256, default="sctp")
    priority = models.PositiveSmallIntegerField(default=1)
    enable = models.BooleanField(default=True)
    application_ids = models.CharField(max_length=256)
    vendor_id = models.PositiveIntegerField(default=10415)
    product_name = models.CharField(max_length=32)
    tls_flag = models.BooleanField(default=False)
    crt_file_name = models.CharField(max_length=256, default="")
    key_file_name = models.CharField(max_length=256, default="")
    loop_flag = models.BooleanField(default=False)
    watchdog_interval = models.PositiveSmallIntegerField(default=5)
    retransmit_timer = models.PositiveSmallIntegerField(default=10)
    max_retransmit = models.PositiveSmallIntegerField(default=3)

    class Meta:
        db_table = "tbl_dra_peer"


class DRARoute(DRAView):
    route_id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=255)
    name = models.CharField(max_length=32, unique=True)
    origin_peer_set = models.ForeignKey(DRAPeerSet, on_delete=models.DO_NOTHING, db_column="origin_peer_set_id", related_name="origin_routes")
    dest_peer_set = models.ForeignKey(DRAPeerSet, on_delete=models.DO_NOTHING, db_column="dest_peer_set_id", related_name="dest_routes")
    imsi = models.CharField(max_length=64, blank=True, null=True)
    impi = models.CharField(max_length=64, blank=True, null=True)
    impu = models.CharField(max_length=64, blank=True, null=True)
    ip_addr = models.CharField(max_length=64, blank=True, null=True)
    msisdn = models.CharField(max_length=64, blank=True, null=True)
    origin_host = models.CharField(max_length=256, blank=True, null=True)
    application_id = models.CharField(max_length=255, blank=True, null=True)
    origin_realm = models.CharField(max_length=256, blank=True, null=True)
    destination_host = models.CharField(max_length=256, blank=True, null=True)
    destination_realm = models.CharField(max_length=256, blank=True, null=True)
    priority = models.PositiveSmallIntegerField(default=1)
    origin_peer_set_json = models.TextField(blank=True, null=True, db_column="origin_peer_set")
    dest_peer_set_json = models.TextField(blank=True, null=True, db_column="dest_peer_set")

    class Meta:
        db_table = "tbl_dra_route"


class DRATranslate(DRAView):
    translate_id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=255)
    name = models.CharField(max_length=32, unique=True)
    origin_peer_set = models.ForeignKey(DRAPeerSet, on_delete=models.DO_NOTHING, db_column="origin_peer_set_name_id", related_name="origin_translates")
    dest_peer_set = models.ForeignKey(DRAPeerSet, on_delete=models.DO_NOTHING, db_column="dest_peer_set_name_id", related_name="dest_translates")
    avp_code = models.PositiveIntegerField()
    avp_type = models.CharField(max_length=64)
    avp_value = models.CharField(max_length=255)
    command_code = models.BigIntegerField(default=0)
    application_ids = models.CharField(max_length=256)
    set_session_id = models.BooleanField(default=False)
    origin_peer_set_json = models.TextField(blank=True, null=True, db_column="origin_peer_set")
    dest_peer_set_json = models.TextField(blank=True, null=True, db_column="dest_peer_set")

    class Meta:
        db_table = "tbl_dra_translate"


class STPView(models.Model):
    """Read-only views for STP management (tbl_stp_*, tbl_m3ua_*)"""
    class Meta:
        managed = False
        abstract = True


class M3UAGlobal(STPView):
    id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=32)
    audit_interval = models.PositiveIntegerField(default=30000)
    multiple_network_appearances = models.CharField(max_length=8, default="disabled")
    max_deactivate_attempts = models.PositiveSmallIntegerField(default=3)
    fsm_timeout = models.PositiveSmallIntegerField(default=2000)
    tx_buffer_size = models.PositiveIntegerField(default=102400)
    rx_buffer_size = models.PositiveIntegerField(default=102400)
    max_ingress_streams = models.PositiveSmallIntegerField(default=16)
    num_egress_streams = models.PositiveSmallIntegerField(default=16)
    hb_interval = models.PositiveIntegerField(default=30000)
    cong_onset_level1 = models.PositiveSmallIntegerField(default=80)
    cong_abatement_level1 = models.PositiveSmallIntegerField(default=70)
    cong_onset_level2 = models.PositiveSmallIntegerField(default=90)
    cong_abatement_level2 = models.PositiveSmallIntegerField(default=80)
    cong_onset_level3 = models.PositiveSmallIntegerField(default=100)
    cong_abatement_level3 = models.PositiveSmallIntegerField(default=90)
    cong_report_frequency = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = "tbl_m3ua_global"


class M3UALocal(STPView):
    id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=32)
    name = models.CharField(max_length=32)
    local_point_code = models.CharField(max_length=11)
    point_code_length = models.PositiveSmallIntegerField(default=14)
    network_indicator = models.CharField(max_length=16, default="intl")

    class Meta:
        db_table = "tbl_m3ua_local"
        unique_together = [("instance_id", "name"), ("instance_id", "local_point_code")]


class M3UALinkset(STPView):
    id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=32)
    name = models.CharField(max_length=32)
    m3ua_local = models.CharField(max_length=32, db_column="m3ua_local_name")
    adjacent_point_code = models.CharField(max_length=11)
    traffic_mode = models.CharField(max_length=11, default="loadshare")

    class Meta:
        db_table = "tbl_m3ua_linkset"
        unique_together = [("instance_id", "name"), ("instance_id", "adjacent_point_code")]


class M3UALink(STPView):
    id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=32)
    name = models.CharField(max_length=32)
    linkset_name = models.CharField(max_length=32, db_column="m3ua_linkset_name")
    local_ip_addr = models.CharField(max_length=32)
    local_port = models.PositiveSmallIntegerField(default=2905)
    remote_ip_addr = models.CharField(max_length=32)
    remote_port = models.PositiveSmallIntegerField(default=2905)
    link_type = models.CharField(max_length=32, default="sgp")
    compat_mode = models.CharField(max_length=32, default="standard")
    max_ingress_streams = models.PositiveSmallIntegerField(default=16)
    num_egress_streams = models.PositiveSmallIntegerField(default=16)
    association_creation = models.CharField(max_length=32, default="initiate")
    max_path_mtu = models.PositiveIntegerField(default=1500)
    network_appearance = models.PositiveIntegerField(default=0)
    link_status = models.CharField(max_length=32, default="activated")

    class Meta:
        db_table = "tbl_m3ua_link"
        unique_together = [("instance_id", "name"), ("instance_id", "local_ip_addr", "local_port", "remote_ip_addr", "remote_port")]


class STPRoute(STPView):
    id = models.BigAutoField(primary_key=True)
    instance_id = models.CharField(max_length=255)
    name = models.CharField(max_length=32)
    enable = models.PositiveSmallIntegerField(default=1)
    priority = models.PositiveSmallIntegerField(default=1)
    linkset_ingress = models.CharField(max_length=32, default="")
    linkset_egress = models.CharField(max_length=32, default="")
    calling_gt = models.CharField(max_length=32, default="")
    called_gt = models.CharField(max_length=32, default="")
    imsi = models.TextField()
    translate_group = models.CharField(max_length=32, default="")
    route_mode = models.CharField(max_length=32, default="loadshare")
    called_identity = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "tbl_stp_route"
        unique_together = [("instance_id", "name")]


class STPTranslate(STPView):
    tid = models.PositiveIntegerField(primary_key=True)
    instance_id = models.CharField(max_length=32)
    name = models.CharField(max_length=32)
    spc_rule = models.CharField(max_length=32, default="ignore")
    spc = models.CharField(max_length=32, default="")
    dpc = models.CharField(max_length=32, default="")
    spc_ni = models.CharField(max_length=32, default="intl")
    calling_rule = models.CharField(max_length=32, default="ignore")
    called_rule = models.CharField(max_length=32, default="ignore")
    calling_origin = models.CharField(max_length=32, default="")
    calling_dest = models.CharField(max_length=32, default="")
    called_origin = models.CharField(max_length=32, default="")
    called_dest = models.CharField(max_length=32, default="")

    class Meta:
        db_table = "tbl_stp_translate"
        unique_together = [("instance_id", "name")]


# ============================================================================
# Reference Tables (MCC/MNC/PLMN Management for MVNO hosting)
# ============================================================================
class MCCMNC(models.Model):
    """MCC/MNC Registry per TS 23.003 (Rel-15+)"""
    id = models.BigAutoField(primary_key=True)
    mcc = models.CharField(max_length=3)
    mnc = models.CharField(max_length=3)
    country_name = models.CharField(max_length=100, blank=True, null=True)
    network_name = models.CharField(max_length=100, blank=True, null=True)
    network_type = models.CharField(max_length=10, choices=[('MNO', 'MNO'), ('MVNO', 'MVNO'), ('Test', 'Test')], default='MNO')
    parent_mcc = models.CharField(max_length=3, blank=True, null=True)
    parent_mnc = models.CharField(max_length=3, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_mcc_mnc"
        unique_together = [("mcc", "mnc")]


class PLMNProfile(models.Model):
    """PLMN Profile per TS 23.003/23.501 (Rel-15 to Rel-20)"""
    id = models.BigAutoField(primary_key=True)
    plmn_id = models.CharField(max_length=6, unique=True)
    plmn_name = models.CharField(max_length=100, blank=True, null=True)
    eps_supported = models.BooleanField(default=True)
    fiveg_supported = models.BooleanField(default=True)
    redcap_supported = models.BooleanField(default=False)
    ntn_supported = models.BooleanField(default=False)
    fiveg_advanced_supported = models.BooleanField(default=False)
    hplmn_allowed = models.BooleanField(default=True)
    vplmn_allowed = models.BooleanField(default=True)
    diameter_realm = models.CharField(max_length=255, blank=True, null=True)
    tac_range_start = models.PositiveIntegerField(default=1)
    tac_range_end = models.PositiveIntegerField(default=65535)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_plmn_profile"


# ============================================================================
# Core Subscriber (TS 23.008 Organization of Subscriber Data)
# ============================================================================
class Subscriber(models.Model):
    """UDM Subscriber model (from hssdbInitial.sql / protei-scp-platform)"""
    imsi = models.CharField(max_length=15, primary_key=True)
    msisdn = models.CharField(max_length=15, blank=True, null=True)
    imei = models.CharField(max_length=15, blank=True, null=True)
    imei_sv = models.CharField(max_length=16, blank=True, null=True)
    
    # 5G/4G Root Keys
    k = models.CharField(max_length=64, blank=True, null=True, help_text="5G root key (K4) - 256-bit hex")
    ki = models.CharField(max_length=32, blank=True, null=True, help_text="4G/3G/2G root key (Ki) - 128-bit hex")
    
    # OP/OPc
    op = models.CharField(max_length=32, blank=True, null=True, help_text="OP (Operator Variant) - 128-bit hex")
    opc = models.CharField(max_length=32, blank=True, null=True, help_text="OPc (derived) - 128-bit hex")
    
    # Sequence & AMF
    sqn = models.BigIntegerField(default=0, help_text="Sequence number for AKA (48-bit)")
    amf = models.CharField(max_length=8, default="8000", help_text="Authentication Management Field (hex)")
    
    # Derived 5G Key Hierarchy
    k_asme = models.CharField(max_length=64, blank=True, null=True, help_text="K_ASME")
    k_seaf = models.CharField(max_length=64, blank=True, null=True, help_text="K_SEAF")
    k_ausf = models.CharField(max_length=64, blank=True, null=True, help_text="K_AUSF")
    
    # 2G/3G Cipher & Auth
    kc = models.CharField(max_length=16, blank=True, null=True, help_text="Kc (2G/3G Cipher Key) - 64-bit hex")
    sres = models.CharField(max_length=8, blank=True, null=True, help_text="SRES (2G/3G Auth Response) - 32-bit hex")
    
    # Network Access
    network_access_mode = models.SmallIntegerField(default=2, help_text="0=GPRS,1=CS,2=Both,3=5G")
    subscriber_status = models.SmallIntegerField(default=0, help_text="0=Active,1=Barred,2=Suspended,3=Detached")
    roaming_restricted = models.BooleanField(default=False)
    regional_restriction = models.JSONField(blank=True, null=True)
    odb_data = models.JSONField(blank=True, null=True)
    trace_config = models.JSONField(blank=True, null=True)
    
    # Rel-17: 5G ProSe, RedCap
    prose_enabled = models.BooleanField(default=False)
    redcap_allowed = models.BooleanField(default=False)
    
    # Rel-18: NR-NTN, eRedCap
    ntn_allowed = models.BooleanField(default=False)
    eredcap_allowed = models.BooleanField(default=False)
    
    # Rel-19: 5G-Advanced MIMO, XR
    xr_allowed = models.BooleanField(default=False)
    
    # Rel-20: AI/ML, reduced capability
    aiml_allowed = models.BooleanField(default=False)
    
    # Batch/MVNO
    batch_id = models.CharField(max_length=64, blank=True, null=True)
    imsi_range_start = models.CharField(max_length=15, blank=True, null=True)
    imsi_range_end = models.CharField(max_length=15, blank=True, null=True)
    mvno_mcc = models.CharField(max_length=3, blank=True, null=True)
    mvno_mnc = models.CharField(max_length=3, blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_subscriber"
        indexes = [
            models.Index(fields=["batch_id"]),
            models.Index(fields=["imsi_range_start", "imsi_range_end"]),
            models.Index(fields=["mvno_mcc", "mvno_mnc"]),
            models.Index(fields=["subscriber_status"]),
        ]


# ============================================================================
# Authentication Vectors (TS 33.102, 33.501, 29.272)
# ============================================================================
class AuthVector(models.Model):
    """Authentication vectors (pre-computed)"""
    imsi = models.OneToOneField(Subscriber, on_delete=models.CASCADE, primary_key=True, db_column="imsi")
    
    # 5G (TS 33.501)
    rand_5g = models.CharField(max_length=32, blank=True, null=True, help_text="RAND (128-bit)")
    autn_5g = models.CharField(max_length=32, blank=True, null=True, help_text="AUTN (128-bit)")
    xres_5g = models.CharField(max_length=64, blank=True, null=True, help_text="XRES* (256-bit for 5G)")
    k_ausf = models.CharField(max_length=64, blank=True, null=True, help_text="K_AUSF")
    k_seaf = models.CharField(max_length=64, blank=True, null=True, help_text="K_SEAF")
    k_amf = models.CharField(max_length=64, blank=True, null=True, help_text="K_AMF")
    
    # 4G (TS 33.401)
    rand_4g = models.CharField(max_length=32, blank=True, null=True)
    autn_4g = models.CharField(max_length=32, blank=True, null=True)
    xres_4g = models.CharField(max_length=16, blank=True, null=True)
    ck_4g = models.CharField(max_length=32, blank=True, null=True)
    ik_4g = models.CharField(max_length=32, blank=True, null=True)
    k_asme_4g = models.CharField(max_length=64, blank=True, null=True)
    
    # 3G (TS 33.102)
    rand_3g = models.CharField(max_length=32, blank=True, null=True)
    autn_3g = models.CharField(max_length=32, blank=True, null=True)
    xres_3g = models.CharField(max_length=16, blank=True, null=True)
    ck_3g = models.CharField(max_length=32, blank=True, null=True)
    ik_3g = models.CharField(max_length=32, blank=True, null=True)
    
    # 2G (TS 33.102)
    rand_2g = models.CharField(max_length=32, blank=True, null=True)
    sres_2g = models.CharField(max_length=8, blank=True, null=True)
    kc_2g = models.CharField(max_length=16, blank=True, null=True)
    
    # Rel-17: RedCap auth
    rand_redcap = models.CharField(max_length=32, blank=True, null=True)
    
    # Metadata
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    algorithm = models.CharField(max_length=32, default="milenage")
    opc_used = models.CharField(max_length=32, blank=True, null=True)
    sqn_used = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = "tbl_auth_vector"


# ============================================================================
# EPS Subscription Data (TS 29.272 S6a, TS 23.401)
# ============================================================================
class EPSSubscription(models.Model):
    """EPS Subscription Data per TS 29.272 (Rel-15 to Rel-20)"""
    imsi = models.OneToOneField(Subscriber, on_delete=models.CASCADE, primary_key=True, db_column="imsi")
    apn_config = models.JSONField(blank=True, null=True)
    default_apn = models.CharField(max_length=100, blank=True, null=True)
    ue_ambr_ul = models.BigIntegerField(default=100000000)
    ue_ambr_dl = models.BigIntegerField(default=100000000)
    rat_restrictions = models.JSONField(blank=True, null=True)
    msisdn_list = models.JSONField(blank=True, null=True)
    csg_subscription = models.JSONField(blank=True, null=True)
    mme_subscription = models.JSONField(blank=True, null=True)
    hss_subscription = models.JSONField(blank=True, null=True)
    lcs_privacy = models.JSONField(blank=True, null=True)
    vplmn_dynamic = models.JSONField(blank=True, null=True)
    nb_iot_allowed = models.BooleanField(default=False)
    emtc_allowed = models.BooleanField(default=False)
    v2x_allowed = models.BooleanField(default=False)
    industrial_iot_allowed = models.BooleanField(default=False)
    redcap_allowed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_eps_subscription"


# ============================================================================
# 5G Subscription Data (TS 29.503 Nudm_SDM, TS 23.501)
# ============================================================================
class FiveGSubscription(models.Model):
    """5G Subscription Data per TS 29.503 (Rel-15 to Rel-20)"""
    imsi = models.OneToOneField(Subscriber, on_delete=models.CASCADE, primary_key=True, db_column="imsi")
    supi = models.CharField(max_length=20, blank=True, null=True)
    suci_calc_info = models.JSONField(blank=True, null=True)
    default_nssai = models.JSONField(blank=True, null=True)
    allowed_nssai = models.JSONField(blank=True, null=True)
    ue_ambr_ul = models.BigIntegerField(default=1000000000)
    ue_ambr_dl = models.BigIntegerField(default=1000000000)
    rat_restrictions_5g = models.JSONField(blank=True, null=True)
    smf_selection = models.JSONField(blank=True, null=True)
    gmlc_address = models.CharField(max_length=255, blank=True, null=True)
    lcs_privacy_5g = models.JSONField(blank=True, null=True)
    sor_info = models.JSONField(blank=True, null=True)
    ue_id_mapping = models.JSONField(blank=True, null=True)
    nssaa_info = models.JSONField(blank=True, null=True)
    vplmn_5g_data = models.JSONField(blank=True, null=True)
    urllc_allowed = models.BooleanField(default=False)
    mmtc_allowed = models.BooleanField(default=False)
    v2x_allowed_5g = models.BooleanField(default=False)
    redcap_allowed_5g = models.BooleanField(default=False)
    ntn_allowed_5g = models.BooleanField(default=False)
    pni_npn_allowed = models.BooleanField(default=False)
    eredcap_allowed_5g = models.BooleanField(default=False)
    mbs_allowed = models.BooleanField(default=False)
    xr_allowed_5g = models.BooleanField(default=False)
    aiml_allowed_5g = models.BooleanField(default=False)
    multicast_mbs_allowed = models.BooleanField(default=False)
    reduced_cap_allowed = models.BooleanField(default=False)
    aiml_enhanced_allowed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_5g_subscription"


# ============================================================================
# IMS Subscription Profile (TS 29.228/229, IR.92)
# ============================================================================
class IMSSubscription(models.Model):
    """IMS Subscription per TS 29.228/229 (Rel-15 to Rel-20)"""
    imsi = models.OneToOneField(Subscriber, on_delete=models.CASCADE, primary_key=True, db_column="imsi")
    impu_list = models.JSONField(blank=True, null=True)
    impi = models.CharField(max_length=255, blank=True, null=True)
    ims_domain = models.CharField(max_length=255, blank=True, null=True)
    service_profile_id = models.CharField(max_length=64, blank=True, null=True)
    scscf_name = models.CharField(max_length=255, blank=True, null=True)
    scscf_realm = models.CharField(max_length=255, blank=True, null=True)
    reg_status = models.CharField(max_length=20, choices=[('registered', 'Registered'), ('unregistered', 'Unregistered')], default='unregistered')
    reg_expires = models.BigIntegerField(default=0)
    contact_list = models.JSONField(blank=True, null=True)
    auth_scheme = models.CharField(max_length=20, choices=[('AKAv1-MD5', 'AKAv1-MD5'), ('AKAv2-SHA-256', 'AKAv2-SHA-256')], default='AKAv1-MD5')
    wildcarded_impu = models.BooleanField(default=False)
    mtsi_allowed = models.BooleanField(default=False)
    rcs_allowed = models.BooleanField(default=False)
    nr_multicast_allowed = models.BooleanField(default=False)
    emtsi_allowed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_ims_subscription"


# ============================================================================
# APN/DNN Profile (TS 23.060, 23.401, 23.501)
# ============================================================================
class APNProfile(models.Model):
    """APN/DNN Profile per TS 23.060/23.401/23.501 (Rel-15 to Rel-20)"""
    id = models.BigAutoField(primary_key=True)
    imsi = models.ForeignKey(Subscriber, on_delete=models.CASCADE, db_column="imsi")
    apn = models.CharField(max_length=100)
    apn_type = models.CharField(max_length=20, choices=[
        ('internet', 'Internet'), ('ims', 'IMS'), ('emergency', 'Emergency'),
        ('mms', 'MMS'), ('enterprise', 'Enterprise'), ('m2m', 'M2M'),
        ('mbs', 'MBS'), ('fmc', 'FMC')
    ], default='internet')
    qci = models.PositiveSmallIntegerField(default=9)
    arp_priority = models.PositiveSmallIntegerField(default=8)
    arp_preempt_cap = models.BooleanField(default=False)
    arp_preempt_vuln = models.BooleanField(default=False)
    apn_ambr_ul = models.BigIntegerField(default=100000000)
    apn_ambr_dl = models.BigIntegerField(default=100000000)
    ue_ambr_ul = models.BigIntegerField(default=100000000)
    ue_ambr_dl = models.BigIntegerField(default=100000000)
    pcc_rule_name = models.CharField(max_length=64, blank=True, null=True)
    pcc_rule_version = models.PositiveIntegerField(default=1)
    pdn_type = models.CharField(max_length=20, choices=[('ipv4', 'IPv4'), ('ipv6', 'IPv6'), ('ipv4v6', 'IPv4v6'), ('non-ip', 'Non-IP')], default='ipv4v6')
    ipv4_addr_alloc = models.CharField(max_length=20, choices=[('dynamic', 'Dynamic'), ('static', 'Static'), ('dhcp', 'DHCP')], default='dynamic')
    ipv6_prefix_len = models.PositiveSmallIntegerField(default=64)
    static_ipv4 = models.CharField(max_length=45, blank=True, null=True)
    static_ipv6 = models.CharField(max_length=45, blank=True, null=True)
    dns_primary = models.CharField(max_length=45, default='8.8.8.8')
    dns_secondary = models.CharField(max_length=45, default='8.8.4.4')
    pgw_fqdn = models.CharField(max_length=255, blank=True, null=True)
    pgw_ipv4 = models.CharField(max_length=45, blank=True, null=True)
    pgw_ipv6 = models.CharField(max_length=45, blank=True, null=True)
    sgw_fqdn = models.CharField(max_length=255, blank=True, null=True)
    sgw_ipv4 = models.CharField(max_length=45, blank=True, null=True)
    charging_id = models.PositiveIntegerField(default=0)
    charging_gateway = models.CharField(max_length=255, blank=True, null=True)
    is_emergency = models.BooleanField(default=False)
    dnn_selection_mode = models.CharField(max_length=20, choices=[('UE-provided', 'UE-provided'), ('Network-provided', 'Network-provided'), ('Verified', 'Verified')], default='Verified')
    mvno_reseller_id = models.CharField(max_length=64, blank=True, null=True)
    urllc_qos = models.BooleanField(default=False)
    redcap_qos = models.BooleanField(default=False)
    mbs_qos = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_apn_profile"
        unique_together = [("imsi", "apn")]


# ============================================================================
# Supplementary Services (TS 23.011, 23.018, 29.002, 29.272)
# ============================================================================
class SupplementaryService(models.Model):
    """Supplementary Services per TS 23.011/018/078 (Rel-15 to Rel-20)"""
    id = models.BigAutoField(primary_key=True)
    imsi = models.ForeignKey(Subscriber, on_delete=models.CASCADE, db_column="imsi")
    service_code = models.CharField(max_length=20)
    service_name = models.CharField(max_length=100, blank=True, null=True)
    provision_status = models.CharField(max_length=20, choices=[
        ('not_provisioned', 'Not Provisioned'), ('provisioned', 'Provisioned'),
        ('active', 'Active'), ('deactivated', 'Deactivated')
    ], default='not_provisioned')
    activation_code = models.CharField(max_length=32, blank=True, null=True)
    deactivation_code = models.CharField(max_length=32, blank=True, null=True)
    interrogation_code = models.CharField(max_length=32, blank=True, null=True)
    registration_code = models.CharField(max_length=32, blank=True, null=True)
    erasure_code = models.CharField(max_length=32, blank=True, null=True)
    forwarding_number = models.CharField(max_length=20, blank=True, null=True)
    forwarding_condition = models.CharField(max_length=20, choices=[
        ('unconditional', 'Unconditional'), ('busy', 'Busy'),
        ('no_reply', 'No Reply'), ('not_reachable', 'Not Reachable'),
        ('all', 'All')
    ], default='unconditional')
    no_reply_timer = models.PositiveSmallIntegerField(default=20)
    override_category = models.CharField(max_length=20, choices=[
        ('none', 'None'), ('operator', 'Operator'), ('subscriber', 'Subscriber')
    ], default='none')
    max_simultaneous_calls = models.PositiveSmallIntegerField(default=0)
    clip_provisioned = models.BooleanField(default=True)
    clir_provisioned = models.BooleanField(default=True)
    clir_option = models.CharField(max_length=30, choices=[
        ('presentation_allowed', 'Presentation Allowed'),
        ('presentation_restricted', 'Presentation Restricted'),
        ('network_default', 'Network Default')
    ], default='network_default')
    ussd_enabled = models.BooleanField(default=True)
    ussd_string_length = models.PositiveSmallIntegerField(default=160)
    camel_phase = models.PositiveSmallIntegerField(default=3)
    camel_tdp_list = models.JSONField(blank=True, null=True)
    mmtel_allowed = models.BooleanField(default=False)
    rcs_allowed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_supplementary_service"
        unique_together = [("imsi", "service_code")]


# ============================================================================
# Roaming & Operator Policies (TS 23.060, 29.272, 29.503)
# ============================================================================
class RoamingProfile(models.Model):
    """Per-VPLMN Roaming Profile per TS 23.060/29.272/29.503 (Rel-15 to Rel-20)"""
    id = models.BigAutoField(primary_key=True)
    imsi = models.ForeignKey(Subscriber, on_delete=models.CASCADE, db_column="imsi")
    visited_plmn = models.CharField(max_length=6)
    roaming_allowed = models.BooleanField(default=True)
    rat_allowed = models.JSONField(blank=True, null=True)
    odb_roaming = models.BooleanField(default=False)
    odb_outgoing = models.BooleanField(default=False)
    odb_incoming = models.BooleanField(default=False)
    odb_premium = models.BooleanField(default=False)
    ho_restriction = models.JSONField(blank=True, null=True)
    charging_profile_id = models.CharField(max_length=64, blank=True, null=True)
    v_mme_fqdn = models.CharField(max_length=255, blank=True, null=True)
    v_mme_ipv4 = models.CharField(max_length=45, blank=True, null=True)
    v_sgsn_fqdn = models.CharField(max_length=255, blank=True, null=True)
    v_sgsn_ipv4 = models.CharField(max_length=45, blank=True, null=True)
    v_pgw_fqdn = models.CharField(max_length=255, blank=True, null=True)
    v_pgw_ipv4 = models.CharField(max_length=45, blank=True, null=True)
    v_amf_fqdn = models.CharField(max_length=255, blank=True, null=True)
    v_amf_ipv4 = models.CharField(max_length=45, blank=True, null=True)
    v_smf_fqdn = models.CharField(max_length=255, blank=True, null=True)
    v2x_roaming = models.BooleanField(default=False)
    redcap_roaming = models.BooleanField(default=False)
    ntn_roaming = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_roaming_profile"
        unique_together = [("imsi", "visited_plmn")]


# ============================================================================
# USSD / CAMEL / MAP Routing (TS 29.002, 23.090, 23.078)
# ============================================================================
class USSDRoute(models.Model):
    """USSD/CAMEL Routing per TS 29.002/23.090/23.078 (Rel-15 to Rel-20)"""
    id = models.BigAutoField(primary_key=True)
    ussd_string = models.CharField(max_length=32, unique=True)
    destination_type = models.CharField(max_length=30, choices=[
        ('internal', 'Internal'), ('external_ussd_gw', 'External USSD GW'),
        ('scp', 'SCP'), ('gmlc', 'GMLC'), ('imsi_based', 'IMSI Based')
    ], default='internal')
    destination_address = models.CharField(max_length=255, blank=True, null=True)
    gsm_scf_address = models.CharField(max_length=255, blank=True, null=True)
    service_key = models.PositiveIntegerField(default=0)
    default_response = models.CharField(max_length=255, blank=True, null=True)
    timeout_sec = models.PositiveSmallIntegerField(default=10)
    mvno_mcc = models.CharField(max_length=3, blank=True, null=True)
    mvno_mnc = models.CharField(max_length=3, blank=True, null=True)
    fiveg_ussd_allowed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_ussd_routing"


class CamelServiceProfile(models.Model):
    """CAMEL Service Profile per TS 23.078/29.078 (Rel-15 to Rel-20)"""
    id = models.BigAutoField(primary_key=True)
    imsi = models.ForeignKey(Subscriber, on_delete=models.CASCADE, db_column="imsi")
    service_key = models.PositiveIntegerField()
    tdp_list = models.JSONField(blank=True, null=True)
    gsm_scf_address = models.CharField(max_length=255)
    default_call_handling = models.CharField(max_length=20, choices=[
        ('continue', 'Continue'), ('release', 'Release'), ('route_to_scf', 'Route to SCF')
    ], default='continue')
    csi_psi = models.JSONField(blank=True, null=True)
    csi_csi = models.JSONField(blank=True, null=True)
    csi_ssi = models.JSONField(blank=True, null=True)
    csi_msi = models.JSONField(blank=True, null=True)
    csi_lsi = models.JSONField(blank=True, null=True)
    csi_v2x = models.JSONField(blank=True, null=True)
    csi_redcap = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_camel_service_profile"
        unique_together = [("imsi", "service_key")]


# ============================================================================
# Network Interface / Node Management (for MME/MSC/PGW/GMLC integration)
# ============================================================================
class NetworkNode(models.Model):
    """Network Node Registry for Interworking (Rel-15 to Rel-20)"""
    id = models.BigAutoField(primary_key=True)
    node_name = models.CharField(max_length=64, unique=True)
    node_type = models.CharField(max_length=20, choices=[
        ('MME', 'MME'), ('MSC', 'MSC'), ('SGSN', 'SGSN'), ('PGW', 'PGW'),
        ('SGW', 'SGW'), ('HSS', 'HSS'), ('PCRF', 'PCRF'), ('PCF', 'PCF'),
        ('SMF', 'SMF'), ('UPF', 'UPF'), ('AMF', 'AMF'), ('GMLC', 'GMLC'),
        ('SCP', 'SCP'), ('USSD_GW', 'USSD_GW'), ('SMSC', 'SMSC'),
        ('NRF', 'NRF'), ('AUSF', 'AUSF'), ('UDM', 'UDM'), ('NEF', 'NEF'),
        ('BSF', 'BSF'), ('UDSF', 'UDSF'), ('NSSF', 'NSSF')
    ])
    fqdn = models.CharField(max_length=255, blank=True, null=True)
    ipv4 = models.CharField(max_length=45, blank=True, null=True)
    ipv6 = models.CharField(max_length=45, blank=True, null=True)
    diameter_host = models.CharField(max_length=255, blank=True, null=True)
    diameter_realm = models.CharField(max_length=255, blank=True, null=True)
    diameter_port = models.PositiveIntegerField(default=3868)
    sctp_port = models.PositiveIntegerField(default=2905)
    point_code = models.CharField(max_length=11, blank=True, null=True)
    global_title = models.CharField(max_length=20, blank=True, null=True)
    gt_translation_type = models.PositiveSmallIntegerField(default=0)
    gt_numbering_plan = models.PositiveSmallIntegerField(default=1)
    gt_nature_of_address = models.PositiveSmallIntegerField(default=4)
    plmn_id = models.CharField(max_length=6, blank=True, null=True)
    supported_interfaces = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    health_check_url = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_network_node"
        indexes = [
            models.Index(fields=["node_type", "plmn_id"]),
        ]


# ============================================================================
# Batch & IMSI Range Management
# ============================================================================
class BatchUpload(models.Model):
    """Batch Upload Audit"""
    id = models.BigAutoField(primary_key=True)
    batch_id = models.CharField(max_length=64, unique=True)
    filename = models.CharField(max_length=255, blank=True, null=True)
    total_records = models.PositiveIntegerField(default=0)
    successful_records = models.PositiveIntegerField(default=0)
    failed_records = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')],
        default='pending'
    )
    error_log = models.JSONField(blank=True, null=True)
    created_by = models.CharField(max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "tbl_batch_upload"


class IMSIRange(models.Model):
    """IMSI Range Management for MVNO"""
    id = models.BigAutoField(primary_key=True)
    range_name = models.CharField(max_length=64, unique=True)
    mcc = models.CharField(max_length=3)
    mnc = models.CharField(max_length=3)
    msisdn_prefix = models.CharField(max_length=10, blank=True, null=True)
    imsi_start = models.CharField(max_length=15)
    imsi_end = models.CharField(max_length=15)
    next_imsi = models.CharField(max_length=15)
    allocated_count = models.BigIntegerField(default=0)
    total_count = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[('available', 'Available'), ('exhausted', 'Exhausted'), ('reserved', 'Reserved')],
        default='available'
    )
    mvno_id = models.CharField(max_length=64, blank=True, null=True)
    default_k = models.CharField(max_length=64, blank=True, null=True)
    default_ki = models.CharField(max_length=32, blank=True, null=True)
    default_op = models.CharField(max_length=32, blank=True, null=True)
    default_opc = models.CharField(max_length=32, blank=True, null=True)
    default_algorithm = models.CharField(max_length=32, default='milenage')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_imsi_range"
        unique_together = [("mcc", "mnc", "imsi_start", "imsi_end")]


class UECMRegistration(models.Model):
    """UECM Registration Data per TS 29.503 Nudm_UECM"""
    id = models.BigAutoField(primary_key=True)
    imsi = models.CharField(max_length=15)
    access_type = models.CharField(max_length=20, choices=[('3GPP', '3GPP'), ('non-3GPP', 'non-3GPP')])
    registration_data = models.JSONField(blank=True, null=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_uecm_registration"
        unique_together = [("imsi", "access_type")]