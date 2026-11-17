"""
OAM Core Serializers
"""
from rest_framework import serializers
from .models import (
    DRALocal, DRAPeerSet, DRAPeer, DRARoute, DRATranslate,
    M3UAGlobal, M3UALocal, M3UALinkset, M3UALink,
    STPRoute, STPTranslate, Subscriber
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


class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = "__all__"


class SubscriberCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = [
            "imsi", "msisdn", "imei", "authentication_key", "opc",
            "network_access_mode", "subscriber_status", "roaming_restricted",
            "ambr_ul", "ambr_dl"
        ]