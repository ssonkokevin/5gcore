"""
OAM Core URLs
"""
from django.urls import path
from . import views

urlpatterns = [
    # DRA Management
    path("dra/local/", views.DRALocalListView.as_view(), name="dra-local-list"),
    path("dra/peer-sets/", views.DRAPeerSetListView.as_view(), name="dra-peer-set-list"),
    path("dra/peers/", views.DRAPeerListView.as_view(), name="dra-peer-list"),
    path("dra/routes/", views.DRARouteListView.as_view(), name="dra-route-list"),
    path("dra/translates/", views.DRATranslateListView.as_view(), name="dra-translate-list"),

    # STP/M3UA Management
    path("stp/m3ua/global/", views.M3UAGlobalView.as_view(), name="m3ua-global"),
    path("stp/m3ua/local/", views.M3UALocalListView.as_view(), name="m3ua-local-list"),
    path("stp/m3ua/linksets/", views.M3UALinksetListView.as_view(), name="m3ua-linkset-list"),
    path("stp/m3ua/links/", views.M3UALinkListView.as_view(), name="m3ua-link-list"),
    path("stp/routes/", views.STPRouteListView.as_view(), name="stp-route-list"),
    path("stp/translates/", views.STPTranslateListView.as_view(), name="stp-translate-list"),

    # UDM Subscriber Management
    path("subscribers/", views.SubscriberListView.as_view(), name="subscriber-list"),
    path("subscribers/<str:imsi>/", views.SubscriberDetailView.as_view(), name="subscriber-detail"),
    path("subscribers/<str:imsi>/auth-vector/", views.SubscriberAuthVectorView.as_view(), name="subscriber-auth-vector"),
]