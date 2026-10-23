"""Application-level outbound policy for the local-first release.

This blocks RedForge-managed requests. It is not an OS firewall and cannot
control external runtimes, browser links, or third-party code run by the user.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from app.config import settings

LOCAL_RUNTIME_PROVIDERS = frozenset({"ollama", "lmstudio", "llamacpp", "vllm"})


class NetworkPolicyError(Exception):
    """Operation needs network access forbidden by the release profile."""


def is_strict() -> bool:
    # Unknown values fail closed, including misspelled opt-ins.
    return settings.NETWORK_PROFILE != "connected"


def effective_profile() -> str:
    return "strict" if is_strict() else "connected"


def is_loopback_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password or parsed.fragment:
        return False
    if parsed.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


def require_local_url(url: str, *, action: str) -> None:
    if is_strict() and not is_loopback_url(url):
        raise NetworkPolicyError(
            f"{action} requires a loopback endpoint in strict no-egress mode. "
            "Set REDFORGE_NETWORK_PROFILE=connected only in a network-enabled deployment."
        )


def require_provider(name: str, *, base_url: str | None = None) -> None:
    if not is_strict():
        return
    if name.lower() not in LOCAL_RUNTIME_PROVIDERS:
        raise NetworkPolicyError(
            f"Provider '{name}' is disabled in strict no-egress mode. "
            "Use a local runtime on this machine."
        )
    if base_url is not None:
        require_local_url(base_url, action=f"Provider '{name}'")


def require_network_action(action: str) -> None:
    if is_strict():
        raise NetworkPolicyError(
            f"{action} is disabled in strict no-egress mode. "
            "Use an offline/local alternative or a separately configured connected deployment."
        )
