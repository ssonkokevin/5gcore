"""
OAM Core Views - REST API for 5G Core Network Management
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import (
    DRALocal, DRAPeerSet, DRAPeer, DRARoute, DRATranslate,
    M3UAGlobal, M3UALocal, M3UALinkset, M3UALink,
    STPRoute, STPTranslate, Subscriber
)
from .serializers import (
    DRALocalSerializer, DRAPeerSetSerializer, DRAPeerSerializer,
    DRARouteSerializer, DRATranslateSerializer,
    M3UAGlobalSerializer, M3UALocalSerializer, M3UALinksetSerializer, M3UALinkSerializer,
    STPRouteSerializer, STPTranslateSerializer,
    SubscriberSerializer, SubscriberCreateSerializer
)


# DRA Management Views
class DRALocalListView(APIView):
    def get(self, request):
        queryset = DRALocal.objects.all()
        serializer = DRALocalSerializer(queryset, many=True)
        return Response(serializer.data)


class DRAPeerSetListView(APIView):
    def get(self, request):
        queryset = DRAPeerSet.objects.all()
        serializer = DRAPeerSetSerializer(queryset, many=True)
        return Response(serializer.data)


class DRAPeerListView(APIView):
    def get(self, request):
        queryset = DRAPeer.objects.select_related("local", "peer_set").all()
        serializer = DRAPeerSerializer(queryset, many=True)
        return Response(serializer.data)


class DRARouteListView(APIView):
    def get(self, request):
        queryset = DRARoute.objects.select_related("origin_peer_set", "dest_peer_set").all()
        serializer = DRARouteSerializer(queryset, many=True)
        return Response(serializer.data)


class DRATranslateListView(APIView):
    def get(self, request):
        queryset = DRATranslate.objects.select_related("origin_peer_set", "dest_peer_set").all()
        serializer = DRATranslateSerializer(queryset, many=True)
        return Response(serializer.data)


# STP/M3UA Management Views
class M3UAGlobalView(APIView):
    def get(self, request):
        queryset = M3UAGlobal.objects.all()
        serializer = M3UAGlobalSerializer(queryset, many=True)
        return Response(serializer.data)


class M3UALocalListView(APIView):
    def get(self, request):
        queryset = M3UALocal.objects.all()
        serializer = M3UALocalSerializer(queryset, many=True)
        return Response(serializer.data)


class M3UALinksetListView(APIView):
    def get(self, request):
        queryset = M3UALinkset.objects.all()
        serializer = M3UALinksetSerializer(queryset, many=True)
        return Response(serializer.data)


class M3UALinkListView(APIView):
    def get(self, request):
        queryset = M3UALink.objects.all()
        serializer = M3UALinkSerializer(queryset, many=True)
        return Response(serializer.data)


class STPRouteListView(APIView):
    def get(self, request):
        queryset = STPRoute.objects.all()
        serializer = STPRouteSerializer(queryset, many=True)
        return Response(serializer.data)


class STPTranslateListView(APIView):
    def get(self, request):
        queryset = STPTranslate.objects.all()
        serializer = STPTranslateSerializer(queryset, many=True)
        return Response(serializer.data)


# UDM Subscriber Management Views
class SubscriberListView(APIView):
    def get(self, request):
        queryset = Subscriber.objects.all()[:100]
        serializer = SubscriberSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SubscriberCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubscriberDetailView(APIView):
    def get(self, request, imsi):
        try:
            subscriber = Subscriber.objects.get(imsi=imsi)
        except Subscriber.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = SubscriberSerializer(subscriber)
        return Response(serializer.data)

    def put(self, request, imsi):
        try:
            subscriber = Subscriber.objects.get(imsi=imsi)
        except Subscriber.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = SubscriberSerializer(subscriber, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, imsi):
        try:
            subscriber = Subscriber.objects.get(imsi=imsi)
        except Subscriber.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        subscriber.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubscriberAuthVectorView(APIView):
    def get(self, request, imsi):
        try:
            subscriber = Subscriber.objects.get(imsi=imsi)
        except Subscriber.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "imsi": imsi,
            "rand": request.GET.get("rand", "00" * 16),
            "autn": "00" * 16,
            "res": "00" * 8,
            "ck": "00" * 16,
            "ik": "00" * 16,
        })