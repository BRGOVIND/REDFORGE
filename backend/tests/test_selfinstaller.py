"""Installer + diagnose: detection, state, secret redaction, bundle contents.
No venv is created and no network is used; slow/side-effecting calls are stubbed."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

_CLI = Path(__file__).resolve().parent.parent.parent / "cli"
if str(_CLI) not in sys.path:
    sys.path.insert(0, str(_CLI))

from redforge import diagnose, installer  # noqa: E402


# -- installer detection ----------------------------------------------------

def test_detect_os_is_string():
    assert isinstance(installer.detect_os(), str)
    assert installer.detect_os()


def test_check_python_passes_on_current():
    major, minor, _ = installer.check_python()
    assert (major, minor) >= installer.MIN_PYTHON


def test_detect_providers_shape():
    providers = installer.detect_providers()
    labels = {p["label"] for p in providers}
    assert labels == {"Ollama", "LM Studio", "llama.cpp", "vLLM"}
    for p in providers:
        assert set(p) == {"label", "present", "running", "detail"}
        assert isinstance(p["present"], bool)


def test_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("REDFORGE_HOME", str(tmp_path))
    installer._write_state(tmp_path / "venv")
    state = installer.read_state()
    assert state["venv"].endswith("venv")
    assert state["version"]


# -- config redaction (no API keys ever) ------------------------------------

def test_collect_config_redacts_secrets(monkeypatch):
    monkeypatch.setenv("REDFORGE_API_KEY", "super-secret-value")
    monkeypatch.setenv("REDFORGE_LOG_LEVEL", "INFO")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-appear")

    cfg = diagnose.collect_config()
    assert cfg["redforge_env"]["REDFORGE_API_KEY"] == diagnose._REDACTED
    assert cfg["redforge_env"]["REDFORGE_LOG_LEVEL"] == "INFO"
    # Provider keys: presence only, never the value.
    assert cfg["provider_api_keys_present"]["OPENAI_API_KEY"] is True
    assert "sk-should-not-appear" not in json.dumps(cfg)


def test_scrub_redacts_nested_secret_keys():
    data = {"providers": [{"name": "openai", "api_key": "sk-xyz", "base_url": "u"}]}
    scrubbed = diagnose._scrub(data)
    assert scrubbed["providers"][0]["api_key"] == diagnose._REDACTED
    assert scrubbed["providers"][0]["base_url"] == "u"
    assert "sk-xyz" not in json.dumps(scrubbed)


# -- full bundle (offline, stubbed) -----------------------------------------

def test_diagnose_writes_safe_zip(tmp_path, monkeypatch):
    monkeypatch.setenv("REDFORGE_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak-me")
    # Keep it fast and hermetic: no server, no real health/pip.
    monkeypatch.setattr(diagnose, "_server_up", lambda port: False)
    monkeypatch.setattr(installer, "run_health", lambda venv: {
        "status": "warning", "summary": {"healthy": 1, "warning": 1, "error": 0}, "checks": [],
    })
    monkeypatch.setattr(diagnose, "collect_packages", lambda: "fastapi==0.115.6\n")

    out = tmp_path / "diagnostics.zip"
    rc = diagnose.diagnose(port=8000, output=out)
    assert rc == 0
    assert out.is_file()

    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert {"system.json", "config.json", "health.json", "providers.json",
                "packages.txt", "logs.txt", "MANIFEST.txt"} <= names
        blob = b"".join(zf.read(n) for n in names)
    # The whole bundle must not contain the API key value anywhere.
    assert b"sk-leak-me" not in blob
