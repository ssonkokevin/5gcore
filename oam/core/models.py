"""
OAM Core Models - 5G Core Network Management
Maps to database schema from srg_db.sql (STP/DRA tables) and hssdbInitial.sql (UDM tables)
Extended for 5G/4G/3G/2G tri-mode with full key hierarchy, batch provisioning
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
# UDM/HSS/HLR Tri-Mode Subscriber Models (hssdb database)
# ============================================================================
class Subscriber(models.Model):
    """UDM Subscriber model (from hssdbInitial.sql / protei-scp-platform)"""
    imsi = models.CharField(max_length=15, primary_key=True)
    msisdn = models.CharField(max_length=15, blank=True, null=True)
    imei = models.CharField(max_length=15, blank=True, null=True)
    
    # 5G/4G Root Keys
    k = models.CharField(max_length=32, blank=True, null=True, help_text="5G root key (K4) - 256-bit hex")
    ki = models.CharField(max_length=32, blank=True, null=True, help_text="4G/3G/2G root key (Ki) - 128-bit hex")
    
    # OP/OPc
    op = models.CharField(max_length=32, blank=True, null=True, help_text="OP (Operator Variant) - 128-bit hex")
    opc = models.CharField(max_length=32, blank=True, null=True, help_text="OPc (derived) - 128-bit hex")
    
    # Sequence & AMF
    sqn = models.BigIntegerField(default=0, help_text="Sequence number for AKA")
    amf = models.CharField(max_length=8, default="8000", help_text="Authentication Management Field (hex)")
    
    # Derived 5G Key Hierarchy
    k_asme = models.CharField(max_length=32, blank=True, null=True, help_text="K_ASME")
    k_seaf = models.CharField(max_length=32, blank=True, null=True, help_text="K_SEAF")
    k_ausf = models.CharField(max_length=32, blank=True, null=True, help_text="K_AUSF")
    
    # 2G/3G Cipher & Auth
    kc = models.CharField(max_length=16, blank=True, null=True, help_text="Kc (2G/3G Cipher Key) - 64-bit hex")
    sres = models.CharField(max_length=8, blank=True, null=True, help_text="SRES (2G/3G Auth Response) - 32-bit hex")
    
    # Network Access
    network_access_mode = models.SmallIntegerField(default=2, help_text="0=GPRS,1=CS,2=Both,3=5G")
    subscriber_status = models.SmallIntegerField(default=0, help_text="0=Active,1=Barred,2=Suspended")
    roaming_restricted = models.BooleanField(default=False)
    
    # QoS
    ambr_ul = models.CharField(max_length=32, blank=True, null=True)
    ambr_dl = models.CharField(max_length=32, blank=True, null=True)
    
    # Batch Provisioning
    batch_id = models.CharField(max_length=64, blank=True, null=True)
    imsi_range_start = models.CharField(max_length=15, blank=True, null=True)
    imsi_range_end = models.CharField(max_length=15, blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_subscriber"
        indexes = [
            models.Index(fields=["batch_id"]),
            models.Index(fields=["imsi_range_start", "imsi_range_end"]),
        ]


class AuthVector(models.Model):
    """Authentication vectors (pre-computed)"""
    imsi = models.OneToOneField(Subscriber, on_delete=models.CASCADE, primary_key=True, db_column="imsi")
    rand = models.CharField(max_length=32, blank=True, null=True)
    autn = models.CharField(max_length=32, blank=True, null=True)
    res = models.CharField(max_length=16, blank=True, null=True)
    xres = models.CharField(max_length=32, blank=True, null=True)
    ck = models.CharField(max_length=32, blank=True, null=True)
    ik = models.CharField(max_length=32, blank=True, null=True)
    k_asme = models.CharField(max_length=32, blank=True, null=True)
    k_seaf = models.CharField(max_length=32, blank=True, null=True)
    k_ausf = models.CharField(max_length=32, blank=True, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "tbl_auth_vector"


class Roaming(models.Model):
    """Roaming restrictions per visited PLMN"""
    imsi = models.ForeignKey(Subscriber, on_delete=models.CASCADE, db_column="imsi")
    visited_plmn = models.CharField(max_length=6)
    roaming_allowed = models.BooleanField(default=True)

    class Meta:
        db_table = "tbl_roaming"
        unique_together = [("imsi", "visited_plmn")]


class ServiceProfile(models.Model):
    """Service control profile (SCP linkage)"""
    imsi = models.OneToOneField(Subscriber, on_delete=models.CASCADE, primary_key=True, db_column="imsi")
    service_key = models.CharField(max_length=64, blank=True, null=True)
    scp_trigger = models.CharField(max_length=64, blank=True, null=True)
    camel_phase = models.SmallIntegerField(default=1)

    class Meta:
        db_table = "tbl_service_profile"


class BatchUpload(models.Model):
    """Batch upload tracking & audit"""
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
    """IMSI range management for allocations"""
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_imsi_range"
        unique_together = [("mcc", "mnc", "imsi_start", "imsi_end")]