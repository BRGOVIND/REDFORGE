"""Strict release policy blocks managed egress before transport starts."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.health.checks import check_network
from app.main import app
from app.network_policy import NetworkPolicyError, effective_profile, is_loopback_url, require_local_url
from app.runtime import manager
from app.runtime.providers.ollama import OllamaProvider
from app.runtime.providers.openai_compat import LMStudioProvider


@pytest.fixture(autouse=True)
def strict_profile(monkeypatch):
    monkeypatch.setattr(settings, "NETWORK_PROFILE", "strict")
    monkeypatch.setattr(settings, "RUNTIME_PROVIDER", "ollama")
    manager.reset_runtime()
    yield
    manager.reset_runtime()


def test_strict_provider_boundary_and_local_endpoint(monkeypatch):
    assert effective_profile() == "strict"
    assert manager.available_providers() == ["llamacpp", "lmstudio", "ollama", "vllm"]
    assert isinstance(manager.build_provider("ollama"), OllamaProvider)
    with pytest.raises(NetworkPolicyError, match="disabled"):
        manager.build_provider("openai")
    with pytest.raises(NetworkPolicyError, match="disabled"):
        manager.set_default_provider("anthropic")
    with pytest.raises(NetworkPolicyError, match="disabled"):
        manager.get_runtime_for("gemini")
    with pytest.raises(NetworkPolicyError, match="loopback"):
        OllamaProvider("https://example.com")
    monkeypatch.setenv("REDFORGE_LMSTUDIO_URL", "http://192.0.2.3:1234")
    with pytest.raises(NetworkPolicyError, match="loopback"):
        manager.build_provider("lmstudio")
    assert is_loopback_url("http://127.0.0.1:11434")
    assert is_loopback_url("http://[::1]:11434")
    assert not is_loopback_url("http://localhost.example.com")
    assert not is_loopback_url("http://localhost@evil.example")


def test_connected_profile_is_explicit_and_invalid_values_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "NETWORK_PROFILE", "connected")
    assert "openai" in manager.available_providers()
    assert manager.build_provider("openai").name == "openai"
    monkeypatch.setattr(settings, "NETWORK_PROFILE", "conencted")
    assert effective_profile() == "strict"
    with pytest.raises(NetworkPolicyError):
        manager.build_provider("openai")


def test_strict_rejects_external_dns_and_direct_ip_before_resolution(monkeypatch):
    lookups = []

    def unexpected_dns(*args, **kwargs):
        lookups.append((args, kwargs))
        raise AssertionError("DNS lookup should not start")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_dns)
    for url in ("https://provider.example/v1", "http://192.0.2.1:1234",
                "http://[2001:db8::1]:1234", "http://localhost.evil.example:1234"):
        with pytest.raises(NetworkPolicyError, match="loopback"):
            require_local_url(url, action="Runtime")
    assert lookups == []


@pytest.mark.asyncio
async def test_strict_routes_reject_download_and_remote_ingestion():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        for path, body in (
            ("/api/model-hub/llama32-3b/download", {}),
            ("/api/onboarding/models/pull", {"model": "llama3.2:3b"}),
            ("/api/training-runtime/install", {}),
        ):
            response = await client.post(path, json=body)
            assert response.status_code == 403, (path, response.text)
            assert response.json()["error"]["code"] == "network_policy_blocked"
        providers = (await client.get("/api/providers")).json()
        assert providers["network_profile"] == "strict"
        assert all(p["name"] not in {"openai", "anthropic", "gemini"} for p in providers["providers"])
    async with AsyncClient(transport=ASGITransport(app=app, client=("192.0.2.2", 12345)), base_url="http://192.0.2.2") as client:
        response = await client.post("/api/v1/traces/events", json={"events": []})
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_strict_health_does_not_probe_internet(monkeypatch):
    import httpx

    def fail_transport(*args, **kwargs):
        raise AssertionError("network transport opened")

    monkeypatch.setattr(httpx, "AsyncClient", fail_transport)
    result = await check_network(None)
    assert "disabled" in result.message.lower()


def test_sdk_rejects_remote_trace_endpoint(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cli"))
    from redforge.observability import Tracer

    monkeypatch.delenv("REDFORGE_NETWORK_PROFILE", raising=False)
    with pytest.raises(ValueError, match="Remote trace ingestion"):
        Tracer(endpoint="https://traces.example.com", token="rft_test")
    assert Tracer(endpoint="http://127.0.0.1:8000", token="rft_test").enabled
    monkeypatch.setenv("REDFORGE_NETWORK_PROFILE", "connected")
    assert Tracer(endpoint="https://traces.example.com", token="rft_test").enabled


def test_hugging_face_offline_environment_set_in_strict_release():
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_DATASETS_OFFLINE"] == "1"


def test_cli_refuses_non_loopback_bind_even_with_yes(monkeypatch):
    from argparse import Namespace

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cli"))
    from redforge import cli

    monkeypatch.delenv("REDFORGE_NETWORK_PROFILE", raising=False)
    monkeypatch.setattr(cli.process, "start", lambda *args, **kwargs: pytest.fail("server started"))
    args = Namespace(host="0.0.0.0", port=8760, yes=True, dev=False, no_browser=True)
    assert cli.cmd_start(args) == 1


def test_cli_update_check_never_contacts_release_feed(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cli"))
    from redforge import updater

    monkeypatch.delenv("REDFORGE_NETWORK_PROFILE", raising=False)
    monkeypatch.setattr(updater, "fetch_latest_release", lambda *args: pytest.fail("release feed contacted"))
    assert updater.update(check_only=True) == 1


@pytest.mark.asyncio
async def test_direct_ollama_pull_is_blocked_in_strict_mode():
    provider = OllamaProvider("http://127.0.0.1:11434")
    with pytest.raises(NetworkPolicyError, match="Model download"):
        async for _ in provider.pull_model("some-model"):
            pytest.fail("download started")


def test_source_release_installer_defaults_to_no_index(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from scripts.build_release import ROOT, _backend_ignore, _cli_ignore, _write_launchers

    _write_launchers(tmp_path)
    for name in ("install.cmd", "install.sh"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "--no-index" in text
        assert "REDFORGE_WHEELHOUSE" in text
        assert "connected" in text
    generated = {".redforge", "artifacts", "checkpoints", "logs", "outputs",
                 "runs", "unsloth_compiled_cache"}
    assert generated <= _backend_ignore(str(ROOT / "backend"), list(generated))
    assert {"build", "redforge_cli.egg-info", "redforge.egg-info"} <= _cli_ignore(
        str(ROOT / "cli"), ["build", "redforge_cli.egg-info", "redforge.egg-info"])


def test_release_staging_refuses_stale_frontend_shortcut():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "desktop" / "scripts" / "stage-backend.py"),
         "--skip-frontend", "--require-frozen"],
        cwd=root, capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 2
    assert "stale UI" in result.stderr


@pytest.fixture
def local_http_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redirect" or self.path.startswith("/redirect/"):
                self.send_response(302)
                self.send_header("Location", "https://example.com/")
                self.end_headers()
                return
            body = b'{"version":"test","data":[]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.do_GET()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _poison_proxy(monkeypatch, no_proxy=""):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", no_proxy)
    monkeypatch.setenv("no_proxy", no_proxy)


@pytest.mark.parametrize("no_proxy", ["", "localhost", "127.0.0.1", "example.com"])
@pytest.mark.asyncio
async def test_strict_local_providers_ignore_proxy_environment(monkeypatch, local_http_server, no_proxy):
    _poison_proxy(monkeypatch, no_proxy)
    assert await OllamaProvider(local_http_server).health()
    assert await LMStudioProvider(local_http_server).health()


@pytest.mark.asyncio
async def test_strict_local_provider_does_not_follow_external_redirect(monkeypatch, local_http_server):
    _poison_proxy(monkeypatch)
    assert not await OllamaProvider(local_http_server + "/redirect").health()
    assert not await LMStudioProvider(local_http_server + "/redirect").health()


@pytest.mark.asyncio
async def test_connected_provider_retains_configured_proxy_behavior(monkeypatch, local_http_server):
    monkeypatch.setattr(settings, "NETWORK_PROFILE", "connected")
    _poison_proxy(monkeypatch)
    assert not await OllamaProvider(local_http_server).health()
    _poison_proxy(monkeypatch, "127.0.0.1")
    assert await OllamaProvider(local_http_server).health()


def test_strict_cli_loopback_ignores_proxy_and_rejects_redirect(monkeypatch, local_http_server):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cli"))
    from redforge.local_http import open_local_url

    _poison_proxy(monkeypatch)
    with open_local_url(local_http_server + "/api/version", timeout=2) as response:
        assert response.status == 200
    with pytest.raises(urllib.error.HTTPError) as redirected:
        open_local_url(local_http_server + "/redirect", timeout=2)
    assert redirected.value.code == 302
    with pytest.raises(ValueError, match="loopback"):
        open_local_url("https://example.com/", timeout=2)


def test_strict_cli_entry_points_share_proxy_safe_transport(monkeypatch, local_http_server):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cli"))
    from redforge import cli, diagnose, process

    _poison_proxy(monkeypatch)
    assert cli._get_json(local_http_server + "/api/version")["version"] == "test"
    assert cli._post_json(local_http_server + "/api/test", {})["version"] == "test"
    assert diagnose._get_json(local_http_server + "/api/version")["version"] == "test"
    assert process._http_json(local_http_server + "/api/version")["version"] == "test"


@pytest.mark.asyncio
async def test_strict_local_inference_still_works(monkeypatch):
    import httpx
    from app.runtime.providers import ollama

    requests = []

    def handle(request):
        requests.append(str(request.url))
        return httpx.Response(200, json={"response": "local answer", "eval_count": 2})

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    result = await OllamaProvider("http://127.0.0.1:11434").generate("local-model", "hello")
    assert result.text == "local answer"
    assert requests == ["http://127.0.0.1:11434/api/generate"]
