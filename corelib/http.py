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


def request_json(
    method: str,
    url: str,
    payload: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 3.0,
) -> Tuple[int, Any]:
    """Return (status, parsed body). HTTP error statuses are returned, not raised."""
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
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except (urllib.error.URLError, OSError) as exc:
        raise TransportError(url, exc) from exc

    if not raw:
        return status, None
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode("utf-8", "replace")


def with_query(url: str, params: Dict[str, str]) -> str:
    return f"{url}?{urllib.parse.urlencode(params)}"
