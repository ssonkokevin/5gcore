"""
OAM Core Serializers - Full 3GPP Rel-15 to Rel-20 Support
"""
from rest_framework import serializers
from .models import (
    # DRA
    DRALocal, DRAPeerSet, DRAPeer, DRARoute, DRATranslate,
    # STP
    M3UAGlobal, M3UALocal, M3UALinkset, M3UALink,
    STPRoute, STPTranslate,
    # Reference
    MCCMNC, PLMNProfile,
    # Subscriber
    Subscriber, AuthVector,
    # Subscriptions
    EPSSubscription, FiveGSubscription, IMSSubscription,
    # Profiles
    APNProfile, SupplementaryService, RoamingProfile,
    # Routing
    USSDRoute, CamelServiceProfile,
    # Network
    NetworkNode,
    # Batch
    BatchUpload, IMSIRange,
)


# DRA Serializers
class DRALocalSerializer(serializers.ModelSerializer):
    class Meta:
        model = DRALocal
        fields = "__all__"


class DRAPeerSetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DRAPeerSet
        fields = "__all__"


class DRAPeerSerializer(serializers.ModelSerializer):
    local_name = serializers.CharField(source="local.name", read_only=True)
    peer_set_name = serializers.CharField(source="peer_set.name", read_only=True)

    class Meta:
        model = DRAPeer
        fields = "__all__"


class DRARouteSerializer(serializers.ModelSerializer):
    origin_peer_set_name = serializers.CharField(source="origin_peer_set.name", read_only=True)
    dest_peer_set_name = serializers.CharField(source="dest_peer_set.name", read_only=True)

    class Meta:
        model = DRARoute
        fields = "__all__"


class DRATranslateSerializer(serializers.ModelSerializer):
    origin_peer_set_name = serializers.CharField(source="origin_peer_set.name", read_only=True)
    dest_peer_set_name = serializers.CharField(source="dest_peer_set.name", read_only=True)

    class Meta:
        model = DRATranslate
        fields = "__all__"


# STP Serializers
class M3UAGlobalSerializer(serializers.ModelSerializer):
    class Meta:
        model = M3UAGlobal
        fields = "__all__"


class M3UALocalSerializer(serializers.ModelSerializer):
    class Meta:
        model = M3UALocal
        fields = "__all__"


class M3UALinksetSerializer(serializers.ModelSerializer):
    class Meta:
        model = M3UALinkset
        fields = "__all__"


class M3UALinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = M3UALink
        fields = "__all__"


class STPRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = STPRoute
        fields = "__all__"


class STPTranslateSerializer(serializers.ModelSerializer):
    class Meta:
        model = STPTranslate
        fields = "__all__"


# Reference Serializers
class MCCMNCSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCCMNC
        fields = "__all__"


class PLMNProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PLMNProfile
        fields = "__all__"


# Subscriber Serializers
class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = "__all__"


class SubscriberCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = [
            "imsi", "msisdn", "imei", "imei_sv", "k", "ki", "op", "opc", "sqn", "amf",
            "k_asme", "k_seaf", "k_ausf", "kc", "sres",
            "network_access_mode", "subscriber_status", "roaming_restricted",
            "regional_restriction", "odb_data", "trace_config",
            "prose_enabled", "redcap_allowed", "ntn_allowed", "eredcap_allowed", "xr_allowed", "aiml_allowed",
            "ambr_ul", "ambr_dl", "batch_id", "imsi_range_start", "imsi_range_end",
            "mvno_mcc", "mvno_mnc"
        ]


class SubscriberUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = [
            "msisdn", "imei", "imei_sv", "k", "ki", "op", "opc", "sqn", "amf",
            "k_asme", "k_seaf", "k_ausf", "kc", "sres",
            "network_access_mode", "subscriber_status", "roaming_restricted",
            "regional_restriction", "odb_data", "trace_config",
            "prose_enabled", "redcap_allowed", "ntn_allowed", "eredcap_allowed", "xr_allowed", "aiml_allowed",
            "ambr_ul", "ambr_dl", "batch_id"
        ]


class AuthVectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthVector
        fields = "__all__"


# Subscription Serializers
class EPSSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EPSSubscription
        fields = "__all__"


class FiveGSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiveGSubscription
        fields = "__all__"


class IMSSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = IMSSubscription
        fields = "__all__"


# Profile Serializers
class APNProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = APNProfile
        fields = "__all__"


class SupplementaryServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplementaryService
        fields = "__all__"


class RoamingProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoamingProfile
        fields = "__all__"


# Routing Serializers
class USSDRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = USSDRoute
        fields = "__all__"


class CamelServiceProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CamelServiceProfile
        fields = "__all__"


# Network Serializers
class NetworkNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkNode
        fields = "__all__"


# Batch Serializers
class BatchUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchUpload
        fields = "__all__"


class IMSIRangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IMSIRange
        fields = "__all__"


class IMSIRangeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = IMSIRange
        fields = ["range_name", "mcc", "mnc", "msisdn_prefix", "imsi_start", "imsi_end",
                  "default_k", "default_ki", "default_op", "default_opc", "default_algorithm", "mvno_id"]


# Full Profile Serializer (Combined)
class FullProfileSerializer(serializers.Serializer):
    """Combined subscriber full profile"""
    subscriber = SubscriberSerializer()
    eps = EPSSubscriptionSerializer(required=False, allow_null=True)
    fiveg = FiveGSubscriptionSerializer(required=False, allow_null=True)
    ims = IMSSubscriptionSerializer(required=False, allow_null=True)
    apn_profiles = APNProfileSerializer(many=True, required=False)
    supplementary_services = SupplementaryServiceSerializer(many=True, required=False)
    roaming_profiles = RoamingProfileSerializer(many=True, required=False)
    camel_profiles = CamelServiceProfileSerializer(many=True, required=False)