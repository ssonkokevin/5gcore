"""Small JSON-over-HTTP helper on urllib so services need no third-party client."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple


class TransportError(Exception):
    def __init__(self, url: str, cause: Exception):
        super().__init__(f"{url}: {cause}")
        self.url = url
        self.cause = cause


def _perform(
    method: str,
    url: str,
    payload: Optional[Any],
    headers: Optional[Dict[str, str]],
    timeout: float,
) -> Tuple[int, Dict[str, str], bytes]:
    data = None
    req_headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req_headers.update(headers or {})

    request = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        response_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
    except (urllib.error.URLError, OSError) as exc:
        raise TransportError(url, exc) from exc
    return status, response_headers, raw


def _parse(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")


def request_json(
    method: str,
    url: str,
    payload: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 3.0,
) -> Tuple[int, Any]:
    """Return (status, parsed body). HTTP error statuses are returned, not raised."""
    status, _headers, raw = _perform(method, url, payload, headers, timeout)
    return status, _parse(raw)


def request_json_with_headers(
    method: str,
    url: str,
    payload: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 3.0,
) -> Tuple[int, Dict[str, str], Any]:
    """Like request_json but also returns response headers, lower-cased.

    HTTP error statuses are returned, not raised, so ETag/If-Match handling can
    inspect 412 and 428 responses instead of treating them as transport faults.
    """
    status, response_headers, raw = _perform(method, url, payload, headers, timeout)
    return status, response_headers, _parse(raw)


def with_query(url: str, params: Dict[str, str]) -> str:
    return f"{url}?{urllib.parse.urlencode(params)}"
