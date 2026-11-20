"""Nudr_DataRepository client (TS 29.504) for the authentication subscription.

Only the resource the ARPF needs is modelled here:

    /nudr-dr/v2/subscription-data/{ueId}/authentication-data/authentication-subscription

GET returns the stored subscription plus its strong ETag. PUT and PATCH are
conditional writes: the caller passes the ETag it read, and the UDR answers
412 PRECONDITION_FAILED if another writer advanced SQN in between. Callers must
retry with a fresh GET rather than reuse the vector they built from stale data.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from corelib.http import TransportError, request_json_with_headers  # noqa: F401 (re-exported)

AUTH_SUBSCRIPTION_PATH = (
    "/nudr-dr/v2/subscription-data/{ue_id}"
    "/authentication-data/authentication-subscription"
)


class UdrError(RuntimeError):
    """The UDR answered with a status the caller cannot handle."""

    def __init__(self, status: int, body: Any):
        super().__init__(f"UDR answered HTTP {status}: {str(body)[:200]}")
        self.status = status
        self.body = body


class UdrClient:
    def __init__(self, base_url: str, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _url(self, ue_id: str) -> str:
        return self.base_url + AUTH_SUBSCRIPTION_PATH.format(ue_id=ue_id)

    def get_authentication_subscription(
        self, ue_id: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Return (etag, body), or None when the subscriber does not exist."""
        status, headers, body = request_json_with_headers(
            "GET", self._url(ue_id), timeout=self.timeout
        )
        if status == 404:
            return None
        if status != 200 or not isinstance(body, dict):
            raise UdrError(status, body)
        return headers.get("etag", ""), body

    def put_authentication_subscription(
        self,
        ue_id: str,
        body: Dict[str, Any],
        if_match: Optional[str] = None,
    ) -> Tuple[int, str]:
        """Create or replace the subscription; returns (status, new ETag)."""
        headers = {}
        if if_match:
            headers["If-Match"] = if_match
        status, response_headers, _ = request_json_with_headers(
            "PUT", self._url(ue_id), payload=body, headers=headers, timeout=self.timeout
        )
        return status, response_headers.get("etag", "")

    def patch_sequence_number(
        self, ue_id: str, sequence_hex: str, if_match: str
    ) -> Tuple[int, str]:
        """Compare-and-set SQN (TS 29.504 JSON Patch); returns (status, new ETag)."""
        patch = [{"op": "replace", "path": "/sequenceNumber", "value": sequence_hex}]
        status, response_headers, _ = request_json_with_headers(
            "PATCH",
            self._url(ue_id),
            payload=patch,
            headers={
                "Content-Type": "application/json-patch+json",
                "If-Match": if_match,
            },
            timeout=self.timeout,
        )
        return status, response_headers.get("etag", "")
