"""Loopback HTTP calls that cannot inherit a system proxy in strict mode."""
from __future__ import annotations

import ipaddress
import os
import urllib.request
from urllib.parse import urlsplit


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def open_local_url(request: str | urllib.request.Request, *, timeout: float):
    """Open a local URL; strict mode rejects proxies and redirect egress.

    Connected mode retains the existing urllib behavior. The strict path is
    shared by the CLI management calls and the optional local trace SDK.
    """
    if os.environ.get("REDFORGE_NETWORK_PROFILE", "strict").strip().lower() == "connected":
        return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310

    raw = request.full_url if isinstance(request, urllib.request.Request) else request
    parsed = urlsplit(raw)
    host = parsed.hostname or ""
    try:
        local = host.lower() == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host.lower() == "localhost"
    if parsed.scheme not in {"http", "https"} or not local or parsed.username or parsed.password:
        raise ValueError("Strict mode requires a loopback HTTP endpoint")

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    return opener.open(request, timeout=timeout)
