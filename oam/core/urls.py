"""
OAM Core URLs - Full 3GPP Rel-15 to Rel-20 Support
"""
from django.urls import path
from . import views

urlpatterns = [
    # ========================================================================
    # DRA Management
    # ========================================================================
    path("dra/local/", views.DRALocalListView.as_view(), name="dra-local-list"),
    path("dra/peer-sets/", views.DRAPeerSetListView.as_view(), name="dra-peer-set-list"),
    path("dra/peers/", views.DRAPeerListView.as_view(), name="dra-peer-list"),
    path("dra/routes/", views.DRARouteListView.as_view(), name="dra-route-list"),
    path("dra/translates/", views.DRATranslateListView.as_view(), name="dra-translate-list"),

    # ========================================================================
    # STP/M3UA Management
    # ========================================================================
    path("stp/m3ua/global/", views.M3UAGlobalView.as_view(), name="m3ua-global"),
    path("stp/m3ua/local/", views.M3UALocalListView.as_view(), name="m3ua-local-list"),
    path("stp/m3ua/linksets/", views.M3UALinksetListView.as_view(), name="m3ua-linkset-list"),
    path("stp/m3ua/links/", views.M3UALinkListView.as_view(), name="m3ua-link-list"),
    path("stp/routes/", views.STPRouteListView.as_view(), name="stp-route-list"),
    path("stp/translates/", views.STPTranslateListView.as_view(), name="stp-translate-list"),

    # ========================================================================
    # Reference Data (MCC/MNC/PLMN)
    # ========================================================================
    path("reference/mcc-mnc/", views.MCCMNCListView.as_view(), name="mcc-mnc-list"),
    path("reference/plmn-profiles/", views.PLMNProfileListView.as_view(), name="plmn-profile-list"),

    # ========================================================================
    # UDM Subscriber Management
    # ========================================================================
    path("subscribers/", views.SubscriberListView.as_view(), name="subscriber-list"),
    path("subscribers/<str:imsi>/", views.SubscriberDetailView.as_view(), name="subscriber-detail"),
    path("subscribers/<str:imsi>/full-profile/", views.SubscriberFullProfileView.as_view(), name="subscriber-full-profile"),
    path("subscribers/<str:imsi>/auth-vector/", views.SubscriberAuthVectorView.as_view(), name="subscriber-auth-vector"),
    path("subscribers/<str:imsi>/auth-vector/generate/", views.SubscriberGenerateAuthVectorView.as_view(), name="subscriber-auth-vector-generate"),

    # Subscriptions (EPS, 5G, IMS)
    path("subscribers/<str:imsi>/eps-subscription/", views.EPSSubscriptionView.as_view(), name="subscriber-eps-subscription"),
    path("subscribers/<str:imsi>/5g-subscription/", views.FiveGSubscriptionView.as_view(), name="subscriber-5g-subscription"),
    path("subscribers/<str:imsi>/ims-subscription/", views.IMSSubscriptionView.as_view(), name="subscriber-ims-subscription"),

    # APN/DNN Profiles
    path("subscribers/<str:imsi>/apn-profiles/", views.APNProfileListView.as_view(), name="subscriber-apn-profiles"),
    path("subscribers/<str:imsi>/apn-profiles/<str:apn>/", views.APNProfileDetailView.as_view(), name="subscriber-apn-profile-detail"),

    # Supplementary Services
    path("subscribers/<str:imsi>/supplementary-services/", views.SupplementaryServiceListView.as_view(), name="subscriber-supplementary-services"),
    path("subscribers/<str:imsi>/supplementary-services/<str:service_code>/", views.SupplementaryServiceDetailView.as_view(), name="subscriber-supplementary-service-detail"),

    # Roaming Profiles
    path("subscribers/<str:imsi>/roaming-profiles/", views.RoamingProfileListView.as_view(), name="subscriber-roaming-profiles"),
    path("subscribers/<str:imsi>/roaming-profiles/<str:visited_plmn>/", views.RoamingProfileDetailView.as_view(), name="subscriber-roaming-profile-detail"),

    # CAMEL Profiles
    path("subscribers/<str:imsi>/camel-profiles/", views.CamelServiceProfileListView.as_view(), name="subscriber-camel-profiles"),

    # ========================================================================
    # Batch Upload
    # ========================================================================
    path("subscribers/batch/", views.BatchUploadView.as_view(), name="subscriber-batch-upload"),
    path("batches/<str:batch_id>/", views.BatchStatusView.as_view(), name="batch-status"),

    # ========================================================================
    # IMSI Range Management
    # ========================================================================
    path("imsi-ranges/", views.IMSIRangeListView.as_view(), name="imsi-range-list"),
    path("imsi-ranges/allocate/", views.IMSIAllocateView.as_view(), name="imsi-allocate"),

    # ========================================================================
    # USSD Routing
    # ========================================================================
    path("ussd-routes/", views.USSDRouteListView.as_view(), name="ussd-route-list"),

    # ========================================================================
    # Network Nodes
    # ========================================================================
    path("network-nodes/", views.NetworkNodeListView.as_view(), name="network-node-list"),

    # ========================================================================
    # Nudm_SDM Proxy (TS 29.503)
    # ========================================================================
    path("nudm-sdm/v2/<str:imsi>/am-data/", views.NudmAMDataView.as_view(), name="nudm-am-data"),
    path("nudm-sdm/v2/<str:imsi>/smf-select-data/", views.NudmSmfSelectDataView.as_view(), name="nudm-smf-select-data"),
    path("nudm-sdm/v2/<str:imsi>/ue-cm-data/", views.NudmUeCmDataView.as_view(), name="nudm-ue-cm-data"),
    path("nudm-sdm/v2/<str:imsi>/sm-data/", views.NudmSmDataView.as_view(), name="nudm-sm-data"),
    path("nudm-sdm/v2/<str:imsi>/trace-data/", views.NudmTraceDataView.as_view(), name="nudm-trace-data"),
    path("nudm-sdm/v2/<str:imsi>/sms-data/", views.NudmSmsDataView.as_view(), name="nudm-sms-data"),

    # UECM Registration
    # ========================================================================
    path("uecm/registrations/", views.UECMRegistrationListView.as_view(), name="uecm-registration-list"),
    path("uecm/registrations/<str:imsi>/<str:access_type>/", views.UECMRegistrationDetailView.as_view(), name="uecm-registration-detail"),
]