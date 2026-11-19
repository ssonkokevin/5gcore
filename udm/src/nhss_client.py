"""Nhss Client - UDM client for calling HSS Nhss APIs (TS 29.563).

Used by UDM (as consumer) to call HSS (as producer) for:
- Option 1 authentication: UDM requests 5G_AKA/EAP_AKA_PRIME vectors from HSS
- PDU continuity: UDM fetches PGW-C+SMF FQDN from HSS
- IRAT mobility: UDM tells HSS to cancel MME/SGSN/VLR
- Combined exposure: UDM configures EPC monitoring via HSS
- External provisioning: UDM pushes parameters to HSS for EPC enforcement

Per TS 23.632 L.3: UDM SHALL use Nhss services. Nhss uses IMSI only.
UDM maps SUPI->IMSI before calling Nhss.
"""

import json
import os
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field


class NhssConfig:
    HSS_HOST = os.getenv("HSS_HOST", "hss")
    HSS_PORT = int(os.getenv("HSS_PORT", "8090"))
    HSS_BASE_URL = f"http://{HSS_HOST}:{HSS_PORT}"
    UDM_NF_INSTANCE_ID = os.getenv("UDM_NF_INSTANCE_ID", "udm-01")
    UDM_CALLBACK_BASE = os.getenv("UDM_CALLBACK_BASE", "http://custom-udm:8080")
    AUTH_OPTION = os.getenv("AUTH_OPTION", "2")  # 1=HSS, 2=UDM, 3=split


# ============================================================================
# Nhss Client
# ============================================================================
class NhssClient:
    """Async client for all 5 Nhss APIs."""

    def __init__(self):
        self.base = NhssConfig.HSS_BASE_URL
        self.timeout = httpx.Timeout(10.0)

    async def _request(self, method: str, path: str, json_body: dict = None,
                       params: dict = None) -> tuple[int, Optional[dict]]:
        url = f"{self.base}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.request(method, url, json=json_body, params=params)
                if resp.status_code in (204, 304):
                    return resp.status_code, None
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    return resp.status_code, {"raw": resp.text}
            except httpx.ConnectError:
                return 503, {"error": "HSS_UNREACHABLE"}
            except httpx.TimeoutException:
                return 504, {"error": "HSS_TIMEOUT"}

    # ------------------------------------------------------------------
    # Nhss_UEAU: generate-av (Option 1: HSS computes 5G vectors)
    # ------------------------------------------------------------------
    async def generate_av(self, imsi: str, auth_type: str = "5G_AKA",
                          serving_network: str = "",
                          resync_info: Optional[dict] = None) -> tuple[int, Optional[dict]]:
        """POST /nhss-ueau/v1/generate-av
        
        UDM requests 5G authentication vector from HSS (ARPF).
        Used when subscriber credentials live in EPS-UDR (Option 1).
        """
        body = {
            "imsi": imsi,
            "authType": auth_type,
            "servingNetworkName": serving_network,
        }
        if resync_info:
            body["resynchronizationInfo"] = resync_info
        return await self._request("POST", "/nhss-ueau/v1/generate-av", json_body=body)

    # ------------------------------------------------------------------
    # Nhss_SDM: UE context in PGW data (PDU continuity)
    # ------------------------------------------------------------------
    async def get_ue_context_in_pgw_data(self, imsi: str) -> tuple[int, Optional[dict]]:
        """GET /nhss-sdm/v1/{imsi}/ue-context-in-pgw-data
        
        Fetch PGW-C+SMF FQDN per APN for PDU session continuity (5GC->EPC).
        """
        return await self._request("GET", f"/nhss-sdm/v1/{imsi}/ue-context-in-pgw-data")

    async def subscribe_pgw_data(self, imsi: str, callback_uri: str,
                                 nf_instance_id: str,
                                 monitored_uris: List[str],
                                 expires: Optional[str] = None,
                                 immediate_report: bool = False) -> tuple[int, Optional[dict]]:
        """POST /nhss-sdm/v1/{imsi}/subscriptions
        
        Subscribe to PGW data changes. HSS notifies UDM when FQDN changes.
        """
        body = {
            "nfInstanceId": nf_instance_id,
            "callbackReference": callback_uri,
            "monitoredResourceUris": monitored_uris,
            "expires": expires,
            "immediateReport": immediate_report,
        }
        return await self._request("POST", f"/nhss-sdm/v1/{imsi}/subscriptions", json_body=body)

    async def unsubscribe_pgw_data(self, imsi: str, subscription_id: str) -> tuple[int, Optional[dict]]:
        """DELETE /nhss-sdm/v1/{imsi}/subscriptions/{subscriptionId}"""
        return await self._request("DELETE", f"/nhss-sdm/v1/{imsi}/subscriptions/{subscription_id}")

    # ------------------------------------------------------------------
    # Nhss_UECM: SNDeregistration (IRAT mobility cancellation)
    # ------------------------------------------------------------------
    async def deregister_serving_node(self, imsi: str, dereg_reason: str,
                                      guami: Optional[str] = None) -> tuple[int, Optional[dict]]:
        """POST /nhss-uecm/v1/deregister-sn
        
        Tell HSS to cancel EPS/3G serving node after IRAT mobility.
        Four reasons map to specific CLR/MAP-D fan-out (TS 23.632 L.5.3).
        """
        body = {
            "imsi": imsi,
            "deregReason": dereg_reason,
        }
        if guami:
            body["guami"] = guami
        return await self._request("POST", "/nhss-uecm/v1/deregister-sn", json_body=body)

    async def update_imei(self, imsi: str, imei: Optional[str] = None,
                          imei_sv: Optional[str] = None) -> tuple[int, Optional[dict]]:
        """POST /nhss-uecm/v1/imei-update
        
        Tell HSS about IMEI/PEI change. HSS returns previous value if any.
        """
        body = {"imsi": imsi}
        if imei:
            body["imei"] = imei
        if imei_sv:
            body["imeiSv"] = imei_sv
        return await self._request("POST", "/nhss-uecm/v1/imei-update", json_body=body)

    async def update_roaming_status(self, imsi: str, plmn_id: str) -> tuple[int, Optional[dict]]:
        """POST /nhss-uecm/v1/roaming-status-update
        
        Tell HSS about roaming status (PLMN) change.
        """
        body = {"imsi": imsi, "plmnId": plmn_id}
        return await self._request("POST", "/nhss-uecm/v1/roaming-status-update", json_body=body)

    # ------------------------------------------------------------------
    # Nhss_EE: EPC monitoring (combined SCEF+NEF exposure)
    # ------------------------------------------------------------------
    async def subscribe_ee(self, imsi: str, callback_uri: str,
                           monitoring_configs: Dict[str, dict],
                           nf_instance_id: str,
                           supported_features: Optional[str] = None,
                           reporting_options: Optional[dict] = None,
                           mtc_provider_info: Optional[dict] = None) -> tuple[int, Optional[dict]]:
        """POST /nhss-ee/v1/{imsi}/ee-subscriptions
        
        Configure EPC monitoring events in HSS on behalf of combined SCEF+NEF.
        Supports ERIR (immediate reports in response) and GBEE (group-based).
        """
        body = {
            "callbackReference": callback_uri,
            "monitoringConfigurations": monitoring_configs,
            "supportedFeatures": supported_features,
            "reportingOptions": reporting_options,
            "mtcProviderInformation": mtc_provider_info,
        }
        return await self._request("POST", f"/nhss-ee/v1/{imsi}/ee-subscriptions", json_body=body)

    async def unsubscribe_ee(self, imsi: str, subscription_id: str) -> tuple[int, Optional[dict]]:
        """DELETE /nhss-ee/v1/{imsi}/ee-subscriptions/{subscriptionId}"""
        return await self._request("DELETE", f"/nhss-ee/v1/{imsi}/ee-subscriptions/{subscription_id}")

    async def modify_ee(self, imsi: str, subscription_id: str,
                        callback_uri: str,
                        monitoring_configs: Dict[str, dict],
                        reporting_options: Optional[dict] = None) -> tuple[int, Optional[dict]]:
        """PATCH /nhss-ee/v1/{imsi}/ee-subscriptions/{subscriptionId}"""
        body = {
            "callbackReference": callback_uri,
            "monitoringConfigurations": monitoring_configs,
            "reportingOptions": reporting_options,
        }
        return await self._request("PATCH", f"/nhss-ee/v1/{imsi}/ee-subscriptions/{subscription_id}", json_body=body)

    # ------------------------------------------------------------------
    # Nhss_PP: External parameter provisioning for EPC
    # ------------------------------------------------------------------
    async def pp_create(self, imsi: str, af_instance_id: str, reference_id: str,
                        characteristics: Optional[dict] = None,
                        validity_time: Optional[str] = None,
                        mtc_provider_info: Optional[dict] = None,
                        supported_features: Optional[str] = None) -> tuple[int, Optional[dict]]:
        """PUT /nhss-pp/v1/{imsi}/pp-data-store/{afInstanceId}
        
        Create/update per-AF parameter provisioning for EPC.
        Parameters: DL buffering, max response time, max latency, validity time.
        """
        body = {
            "referenceId": reference_id,
            "communicationCharacteristics": characteristics or {},
            "validityTime": validity_time,
            "mtcProviderInformation": mtc_provider_info,
            "supportedFeatures": supported_features,
        }
        return await self._request("PUT",
                                   f"/nhss-pp/v1/{imsi}/pp-data-store/{af_instance_id}",
                                   json_body=body)

    async def pp_delete(self, imsi: str, af_instance_id: str, reference_id: str) -> tuple[int, Optional[dict]]:
        """DELETE /nhss-pp/v1/{imsi}/pp-data-store/{afInstanceId}/{referenceId}"""
        return await self._request("DELETE",
                                   f"/nhss-pp/v1/{imsi}/pp-data-store/{af_instance_id}/{reference_id}")

    async def pp_get(self, imsi: str, af_instance_id: str, reference_id: str) -> tuple[int, Optional[dict]]:
        """GET /nhss-pp/v1/{imsi}/pp-data-store/{afInstanceId}/{referenceId}"""
        return await self._request("GET",
                                   f"/nhss-pp/v1/{imsi}/pp-data-store/{af_instance_id}/{reference_id}")


# ============================================================================
# Convenience functions (sync wrappers for use in FastAPI endpoints)
# ============================================================================
import asyncio

def sync_generate_av(imsi: str, auth_type: str = "5G_AKA",
                     serving_network: str = "") -> tuple[int, Optional[dict]]:
    """Synchronous wrapper for Nhss_UEAU generate-av."""
    client = NhssClient()
    try:
        return asyncio.run(client.generate_av(imsi, auth_type, serving_network))
    finally:
        pass


def sync_get_pgw_data(imsi: str) -> tuple[int, Optional[dict]]:
    """Synchronous wrapper for Nhss_SDM get UE context in PGW data."""
    client = NhssClient()
    try:
        return asyncio.run(client.get_ue_context_in_pgw_data(imsi))
    finally:
        pass


def sync_deregister_sn(imsi: str, dereg_reason: str,
                       guami: Optional[str] = None) -> tuple[int, Optional[dict]]:
    """Synchronous wrapper for Nhss_UECM deregister-sn."""
    client = NhssClient()
    try:
        return asyncio.run(client.deregister_serving_node(imsi, dereg_reason, guami))
    finally:
        pass


def sync_update_imei(imsi: str, imei: Optional[str] = None,
                     imei_sv: Optional[str] = None) -> tuple[int, Optional[dict]]:
    """Synchronous wrapper for Nhss_UECM imei-update."""
    client = NhssClient()
    try:
        return asyncio.run(client.update_imei(imsi, imei, imei_sv))
    finally:
        pass


def sync_update_roaming(imsi: str, plmn_id: str) -> tuple[int, Optional[dict]]:
    """Synchronous wrapper for Nhss_UECM roaming-status-update."""
    client = NhssClient()
    try:
        return asyncio.run(client.update_roaming_status(imsi, plmn_id))
    finally:
        pass


def sync_pp_create(imsi: str, af_instance_id: str, reference_id: str,
                   characteristics: Optional[dict] = None) -> tuple[int, Optional[dict]]:
    """Synchronous wrapper for Nhss_PP create."""
    client = NhssClient()
    try:
        return asyncio.run(client.pp_create(imsi, af_instance_id, reference_id, characteristics))
    finally:
        pass
