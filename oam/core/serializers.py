"""
OAM Core Serializers
"""
from rest_framework import serializers
from .models import (
    DRALocal, DRAPeerSet, DRAPeer, DRARoute, DRATranslate,
    M3UAGlobal, M3UALocal, M3UALinkset, M3UALink,
    STPRoute, STPTranslate,
    Subscriber, AuthVector, Roaming, ServiceProfile,
    BatchUpload, IMSIRange
)


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


# UDM Serializers
class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = "__all__"


class SubscriberCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = [
            "imsi", "msisdn", "imei", "k", "ki", "op", "opc", "sqn", "amf",
            "k_asme", "k_seaf", "k_ausf", "kc", "sres",
            "network_access_mode", "subscriber_status", "roaming_restricted",
            "ambr_ul", "ambr_dl", "batch_id", "imsi_range_start", "imsi_range_end"
        ]


class SubscriberUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = [
            "msisdn", "imei", "k", "ki", "op", "opc", "sqn", "amf",
            "k_asme", "k_seaf", "k_ausf", "kc", "sres",
            "network_access_mode", "subscriber_status", "roaming_restricted",
            "ambr_ul", "ambr_dl", "batch_id"
        ]


class AuthVectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthVector
        fields = "__all__"


class RoamingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Roaming
        fields = "__all__"


class ServiceProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceProfile
        fields = "__all__"


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
        fields = ["range_name", "mcc", "mnc", "msisdn_prefix", "imsi_start", "imsi_end"]