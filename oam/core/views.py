"""
OAM Core Views - REST API for 5G Core Network Management
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from .models import (
    DRALocal, DRAPeerSet, DRAPeer, DRARoute, DRATranslate,
    M3UAGlobal, M3UALocal, M3UALinkset, M3UALink,
    STPRoute, STPTranslate,
    Subscriber, AuthVector, Roaming, ServiceProfile,
    BatchUpload, IMSIRange
)
from .serializers import (
    DRALocalSerializer, DRAPeerSetSerializer, DRAPeerSerializer,
    DRARouteSerializer, DRATranslateSerializer,
    M3UAGlobalSerializer, M3UALocalSerializer, M3UALinksetSerializer, M3UALinkSerializer,
    STPRouteSerializer, STPTranslateSerializer,
    SubscriberSerializer, SubscriberCreateSerializer, SubscriberUpdateSerializer,
    AuthVectorSerializer, RoamingSerializer, ServiceProfileSerializer,
    BatchUploadSerializer, IMSIRangeSerializer, IMSIRangeCreateSerializer
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
        serializer = SubscriberUpdateSerializer(subscriber, data=request.data, partial=True)
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
        # Return pre-computed auth vector if available
        try:
            av = AuthVector.objects.get(imsi=subscriber)
            serializer = AuthVectorSerializer(av)
            return Response(serializer.data)
        except AuthVector.DoesNotExist:
            # Generate stub
            return Response({
                "imsi": imsi,
                "rand": request.GET.get("rand", "00" * 16),
                "autn": "00" * 32,
                "res": "00" * 8,
                "xres": "00" * 32,
                "ck": "00" * 32,
                "ik": "00" * 32,
                "k_asme": "00" * 32,
                "k_seaf": "00" * 32,
                "k_ausf": "00" * 32,
            })


# Batch Upload Views
class BatchUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """Upload CSV/JSON file for batch subscriber provisioning.
        
        Form fields:
        - file: CSV/JSON file
        - batch_id: Optional batch identifier
        - auto_derive: Auto-derive OPc/5G keys (default: true)
        - default_ki: Default Ki for records without
        - default_op: Default OP for records without
        - default_k: Default K for records without
        - default_network_access_mode: Default (default: 2)
        - default_subscriber_status: Default (default: 0)
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Proxy to UDM service
        import requests
        try:
            udm_url = "http://udm:8080/subscribers/batch"
            files = {'file': (file_obj.name, file_obj.read(), file_obj.content_type)}
            data = {
                'batch_id': request.data.get('batch_id', ''),
                'auto_derive': request.data.get('auto_derive', 'true'),
                'default_ki': request.data.get('default_ki', ''),
                'default_op': request.data.get('default_op', ''),
                'default_k': request.data.get('default_k', ''),
                'default_network_access_mode': request.data.get('default_network_access_mode', '2'),
                'default_subscriber_status': request.data.get('default_subscriber_status', '0'),
            }
            resp = requests.post(udm_url, files=files, data=data, timeout=300)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class BatchStatusView(APIView):
    def get(self, request, batch_id):
        import requests
        try:
            resp = requests.get(f"http://udm:8080/batches/{batch_id}", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# IMSI Range Views
class IMSIRangeListView(APIView):
    def get(self, request):
        import requests
        try:
            resp = requests.get("http://udm:8080/imsi-ranges/", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request):
        import requests
        try:
            resp = requests.post("http://udm:8080/imsi-ranges/", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class IMSIAllocateView(APIView):
    def post(self, request):
        import requests
        try:
            resp = requests.post("http://udm:8080/imsi-ranges/allocate", json=request.data, timeout=30)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# Roaming & Service Profile Views
class RoamingListView(APIView):
    def get(self, request, imsi):
        queryset = Roaming.objects.filter(imsi=imsi)
        serializer = RoamingSerializer(queryset, many=True)
        return Response(serializer.data)


class ServiceProfileView(APIView):
    def get(self, request, imsi):
        try:
            profile = ServiceProfile.objects.get(imsi=imsi)
        except ServiceProfile.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = ServiceProfileSerializer(profile)
        return Response(serializer.data)