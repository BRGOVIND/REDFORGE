"""Maintenance-pass refactors (v2.0.x): deterministic DB path, training-backend
auto-detection, the runtime-helper rename, and the sessions→runtime dependency
inversion. Offline."""
from __future__ import annotations

from pathlib import Path

import pytest


# -- deterministic DB path --------------------------------------------------

def test_db_url_honours_explicit_env(monkeypatch):
    import app.config as config
    monkeypatch.setenv("REDFORGE_DATABASE_URL", "sqlite+aiosqlite:///custom.db")
    assert config._resolve_database_url() == "sqlite+aiosqlite:///custom.db"


def test_db_url_prefers_legacy_cwd_file(monkeypatch, tmp_path):
    import app.config as config
    monkeypatch.delenv("REDFORGE_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "redforge.db").write_bytes(b"")  # legacy DB present
    url = config._resolve_database_url()
    assert url.endswith("redforge.db") and "sqlite+aiosqlite:///" in url
    # points at the legacy file, not app-data
    assert tmp_path.as_posix() in url


def test_db_url_defaults_to_absolute_app_data(monkeypatch, tmp_path):
    import app.config as config
    monkeypatch.delenv("REDFORGE_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # no legacy file here
    monkeypatch.setattr(config, "_app_data_dir", lambda: tmp_path / "appdata")
    url = config._resolve_database_url()
    assert url == f"sqlite+aiosqlite:///{(tmp_path / 'appdata' / 'redforge.db').as_posix()}"
    assert Path(url.split(':///', 1)[1]).is_absolute()


# -- training backend auto-detection ----------------------------------------

def test_default_backend_falls_back_to_simulation():
    from app.training import manager
    # No GPU / ML stack in CI → unsloth unavailable → simulation.
    assert manager.default_backend() == "simulation"


def test_default_backend_picks_unsloth_when_available(monkeypatch):
    from app.training import manager

    class _FakeReady:
        label = "fake"
        def is_available(self):
            return True, "ready"

    monkeypatch.setitem(manager._PROVIDERS, "unsloth", lambda: _FakeReady())
    assert manager.default_backend() == "unsloth"


def test_get_provider_uses_auto_default():
    from app.training import manager
    assert manager.get_provider(None).name == "simulation"


# -- rename + dependency inversion ------------------------------------------

def test_runtime_helper_renamed():
    import app.api.runs as runs
    assert hasattr(runs, "generate_via_runtime")
    assert not hasattr(runs, "call_ollama")  # legacy name gone


def test_sessions_does_not_import_api_layer():
    """The session (domain) layer must not import the API layer."""
    src = (Path(__file__).resolve().parents[1] / "app" / "sessions" / "session_manager.py").read_text()
    assert "from app.api" not in src
    assert "call_ollama" not in src


@pytest.mark.asyncio
async def test_session_manager_generate_uses_runtime(monkeypatch):
    """_generate falls through to get_runtime().generate (not the API layer)."""
    from app.sessions.session_manager import SessionManager
    import app.runtime.manager as rt

    class _FakeResult:
        text = "ok"
        latency_ms = 5

    class _FakeRuntime:
        async def generate(self, model, prompt):
            return _FakeResult()

    monkeypatch.setattr(rt, "get_runtime", lambda: _FakeRuntime())
    sm = SessionManager(session_factory=lambda: None)  # factory unused by _generate
    text, latency = await sm._generate("m", "p")
    assert text == "ok" and latency == 5
