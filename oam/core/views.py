"""
OAM Core Views - REST API for 5G Core Network Management
Full 3GPP Rel-15 to Rel-20 Support
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
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
    # UECM
    UECMRegistration,
)
from .serializers import (
    # DRA
    DRALocalSerializer, DRAPeerSetSerializer, DRAPeerSerializer,
    DRARouteSerializer, DRATranslateSerializer,
    # STP
    M3UAGlobalSerializer, M3UALocalSerializer, M3UALinksetSerializer, M3UALinkSerializer,
    STPRouteSerializer, STPTranslateSerializer,
    # Reference
    MCCMNCSerializer, PLMNProfileSerializer,
    # Subscriber
    SubscriberSerializer, SubscriberCreateSerializer, SubscriberUpdateSerializer,
    AuthVectorSerializer,
    # Subscriptions
    EPSSubscriptionSerializer, FiveGSubscriptionSerializer, IMSSubscriptionSerializer,
    # Profiles
    APNProfileSerializer, SupplementaryServiceSerializer, RoamingProfileSerializer,
    # Routing
    USSDRouteSerializer, CamelServiceProfileSerializer,
    # Network
    NetworkNodeSerializer,
    # Batch
    BatchUploadSerializer, IMSIRangeSerializer, IMSIRangeCreateSerializer,
    # Full Profile
    FullProfileSerializer,
    # UECM
    UECMRegistrationSerializer,
)


# ============================================================================
# DRA Management Views
# ============================================================================
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


# ============================================================================
# STP/M3UA Management Views
# ============================================================================
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


# ============================================================================
# Reference Data Views (MCC/MNC/PLMN)
# ============================================================================
class MCCMNCListView(APIView):
    def get(self, request):
        queryset = MCCMNC.objects.filter(is_active=True)
        serializer = MCCMNCSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MCCMNCSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PLMNProfileListView(APIView):
    def get(self, request):
        queryset = PLMNProfile.objects.all()
        serializer = PLMNProfileSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PLMNProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================================================
# UDM Subscriber Management Views
# ============================================================================
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


class SubscriberFullProfileView(APIView):
    """Get complete subscriber profile across all tables"""
    def get(self, request, imsi):
        import requests
        try:
            resp = requests.get(f"http://custom-udm:8080/subscribers/{imsi}/full-profile", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class SubscriberAuthVectorView(APIView):
    def get(self, request, imsi):
        import requests
        rand = request.GET.get("rand")
        algorithm = request.GET.get("algorithm", "milenage")
        try:
            url = f"http://custom-udm:8080/subscribers/{imsi}/auth-vector"
            params = {}
            if rand:
                params["rand"] = rand
            if algorithm:
                params["algorithm"] = algorithm
            resp = requests.get(url, params=params, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class SubscriberGenerateAuthVectorView(APIView):
    def post(self, request, imsi):
        import requests
        try:
            resp = requests.post(f"http://custom-udm:8080/subscribers/{imsi}/auth-vector/generate", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# Subscription Views (EPS, 5G, IMS)
# ============================================================================
class EPSSubscriptionView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            resp = requests.get(f"http://custom-udm:8080/subscribers/{imsi}/eps-subscription", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def put(self, request, imsi):
        import requests
        try:
            resp = requests.put(f"http://custom-udm:8080/subscribers/{imsi}/eps-subscription", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class FiveGSubscriptionView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            resp = requests.get(f"http://custom-udm:8080/subscribers/{imsi}/5g-subscription", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def put(self, request, imsi):
        import requests
        try:
            resp = requests.put(f"http://custom-udm:8080/subscribers/{imsi}/5g-subscription", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class IMSSubscriptionView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            resp = requests.get(f"http://custom-udm:8080/subscribers/{imsi}/ims-subscription", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def put(self, request, imsi):
        import requests
        try:
            resp = requests.put(f"http://custom-udm:8080/subscribers/{imsi}/ims-subscription", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# APN/DNN Profile Views
# ============================================================================
class APNProfileListView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            resp = requests.get(f"http://custom-udm:8080/subscribers/{imsi}/apn-profiles", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request, imsi):
        import requests
        try:
            resp = requests.post(f"http://custom-udm:8080/subscribers/{imsi}/apn-profiles", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class APNProfileDetailView(APIView):
    def put(self, request, imsi, apn):
        import requests
        try:
            resp = requests.put(f"http://custom-udm:8080/subscribers/{imsi}/apn-profiles/{apn}", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def delete(self, request, imsi, apn):
        import requests
        try:
            resp = requests.delete(f"http://custom-udm:8080/subscribers/{imsi}/apn-profiles/{apn}", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# Supplementary Service Views
# ============================================================================
class SupplementaryServiceListView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            resp = requests.get(f"http://custom-udm:8080/subscribers/{imsi}/supplementary-services", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request, imsi):
        import requests
        try:
            resp = requests.post(f"http://custom-udm:8080/subscribers/{imsi}/supplementary-services", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class SupplementaryServiceDetailView(APIView):
    def put(self, request, imsi, service_code):
        import requests
        try:
            resp = requests.put(f"http://custom-udm:8080/subscribers/{imsi}/supplementary-services/{service_code}", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def delete(self, request, imsi, service_code):
        import requests
        try:
            resp = requests.delete(f"http://custom-udm:8080/subscribers/{imsi}/supplementary-services/{service_code}", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# Roaming Profile Views
# ============================================================================
class RoamingProfileListView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            resp = requests.get(f"http://custom-udm:8080/subscribers/{imsi}/roaming-profiles", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request, imsi):
        import requests
        try:
            resp = requests.post(f"http://custom-udm:8080/subscribers/{imsi}/roaming-profiles", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class RoamingProfileDetailView(APIView):
    def put(self, request, imsi, visited_plmn):
        import requests
        try:
            resp = requests.put(f"http://custom-udm:8080/subscribers/{imsi}/roaming-profiles/{visited_plmn}", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def delete(self, request, imsi, visited_plmn):
        import requests
        try:
            resp = requests.delete(f"http://custom-udm:8080/subscribers/{imsi}/roaming-profiles/{visited_plmn}", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# USSD Routing Views
# ============================================================================
class USSDRouteListView(APIView):
    def get(self, request):
        import requests
        try:
            resp = requests.get("http://custom-udm:8080/ussd-routes", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request):
        import requests
        try:
            resp = requests.post("http://custom-udm:8080/ussd-routes", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# CAMEL Profile Views
# ============================================================================
class CamelServiceProfileListView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            resp = requests.get(f"http://custom-udm:8080/subscribers/{imsi}/camel-profiles", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request, imsi):
        import requests
        try:
            resp = requests.post(f"http://custom-udm:8080/subscribers/{imsi}/camel-profiles", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# Network Node Views
# ============================================================================
class NetworkNodeListView(APIView):
    def get(self, request):
        import requests
        try:
            params = {}
            if request.GET.get("node_type"):
                params["node_type"] = request.GET.get("node_type")
            if request.GET.get("plmn_id"):
                params["plmn_id"] = request.GET.get("plmn_id")
            resp = requests.get("http://custom-udm:8080/network-nodes", params=params, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request):
        import requests
        try:
            resp = requests.post("http://custom-udm:8080/network-nodes", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# Batch Upload Views
# ============================================================================
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

        import requests
        try:
            udm_url = "http://custom-udm:8080/subscribers/batch"
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
            resp = requests.get(f"http://custom-udm:8080/batches/{batch_id}", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# IMSI Range Views
# ============================================================================
class IMSIRangeListView(APIView):
    def get(self, request):
        import requests
        try:
            resp = requests.get("http://custom-udm:8080/imsi-ranges/", timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request):
        import requests
        try:
            resp = requests.post("http://custom-udm:8080/imsi-ranges/", json=request.data, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class IMSIAllocateView(APIView):
    def post(self, request):
        import requests
        try:
            resp = requests.post("http://custom-udm:8080/imsi-ranges/allocate", json=request.data, timeout=30)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# Nudm_SDM Proxy Views (TS 29.503)
# ============================================================================
class NudmAMDataView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            params = {}
            if request.GET.get("supported_features"):
                params["supported_features"] = request.GET.get("supported_features")
            resp = requests.get(f"http://custom-udm:8080/nudm-sdm/v2/{imsi}/am-data", params=params, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class NudmSmfSelectDataView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            params = {}
            if request.GET.get("supported_features"):
                params["supported_features"] = request.GET.get("supported_features")
            resp = requests.get(f"http://custom-udm:8080/nudm-sdm/v2/{imsi}/smf-select-data", params=params, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class NudmUeCmDataView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            params = {}
            if request.GET.get("supported_features"):
                params["supported_features"] = request.GET.get("supported_features")
            resp = requests.get(f"http://custom-udm:8080/nudm-sdm/v2/{imsi}/ue-cm-data", params=params, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class NudmSmDataView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            params = {}
            if request.GET.get("supported_features"):
                params["supported_features"] = request.GET.get("supported_features")
            if request.GET.get("dnn"):
                params["dnn"] = request.GET.get("dnn")
            resp = requests.get(f"http://custom-udm:8080/nudm-sdm/v2/{imsi}/sm-data", params=params, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class NudmTraceDataView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            params = {}
            if request.GET.get("supported_features"):
                params["supported_features"] = request.GET.get("supported_features")
            resp = requests.get(f"http://custom-udm:8080/nudm-sdm/v2/{imsi}/trace-data", params=params, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class NudmSmsDataView(APIView):
    def get(self, request, imsi):
        import requests
        try:
            params = {}
            if request.GET.get("supported_features"):
                params["supported_features"] = request.GET.get("supported_features")
            resp = requests.get(f"http://custom-udm:8080/nudm-sdm/v2/{imsi}/sms-data", params=params, timeout=10)
            return Response(resp.json(), status=resp.status_code)
        except requests.RequestException as e:
            return Response({"error": f"UDM service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ============================================================================
# UECM Registration Views (Direct DB Access)
# ============================================================================
class UECMRegistrationListView(APIView):
    def get(self, request):
        queryset = UECMRegistration.objects.all()[:100]
        serializer = UECMRegistrationSerializer(queryset, many=True)
        return Response(serializer.data)


class UECMRegistrationDetailView(APIView):
    def get(self, request, imsi, access_type):
        try:
            reg = UECMRegistration.objects.get(imsi=imsi, access_type=access_type)
        except UECMRegistration.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = UECMRegistrationSerializer(reg)
        return Response(serializer.data)
