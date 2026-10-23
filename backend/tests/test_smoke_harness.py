"""The packaged-app smoke harness must launch the real backend on every OS.

The 2.0.4 release failed on macOS and Ubuntu — and only there — inside
`scripts/smoke_packaged_app.py`:

    launching frozen backend: desktop/resources/backend/redforge-backend
    FileNotFoundError: [Errno 2] No such file or directory:
    'desktop/resources/backend/redforge-backend'

The executable was present (staging logged `contains binary: True`). The harness
passed a RELATIVE program path together with ``cwd=<bundle>``. On POSIX the child
runs ``chdir(cwd)`` before ``exec``, so the program was looked up at
``<bundle>/<bundle>/redforge-backend``. Windows resolves the program against the
parent's directory instead, so the identical call worked there and the fault was
invisible until the release matrix ran.

These tests emulate POSIX resolution explicitly, so the regression is caught on
any platform rather than only on the one where it bites.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import smoke_packaged_app as smoke  # noqa: E402


class _FakeProc:
    pid = -1

    def poll(self):
        return None


def _posix_style_popen(recorder):
    """Stand-in for subprocess.Popen that resolves like POSIX fork+exec.

    The child chdirs into ``cwd`` and only then execs ``args[0]``, so a relative
    program is resolved from there. This is the behaviour that broke the release.
    """
    def popen(args, cwd=None, env=None, **kwargs):
        program = Path(args[0])
        if not program.is_absolute():
            program = Path(cwd or ".") / program
        if not program.exists():
            raise FileNotFoundError(2, "No such file or directory", str(args[0]))
        recorder.append({"program": args[0], "cwd": cwd, "env": env})
        return _FakeProc()
    return popen


@pytest.fixture()
def staged_bundle(tmp_path: Path) -> Path:
    """A bundle shaped exactly like desktop/resources/backend after staging."""
    bundle = tmp_path / "desktop" / "resources" / "backend"
    (bundle / "app" / "static" / "assets").mkdir(parents=True)
    (bundle / "app" / "static" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    exe = bundle / smoke.exe_name()
    exe.write_bytes(b"#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    return bundle


def test_exe_name_matches_the_staging_contract():
    """One filename rule, shared by staging, Electron and this harness."""
    assert smoke.exe_name() == ("redforge-backend.exe" if os.name == "nt" else "redforge-backend")
    staging = (ROOT / "desktop" / "scripts" / "stage-backend.py").read_text(encoding="utf-8")
    assert 'EXE = "redforge-backend.exe" if os.name == "nt" else "redforge-backend"' in staging, (
        "stage-backend.py no longer stages the filename this harness launches"
    )


def test_launch_uses_an_absolute_program_path(monkeypatch, staged_bundle: Path, tmp_path: Path):
    """The regression: a relative program plus cwd resolves to nothing on POSIX."""
    calls: list = []
    monkeypatch.setattr(subprocess, "Popen", _posix_style_popen(calls))
    monkeypatch.chdir(tmp_path)          # run from the "repo root", as CI does

    sinks: list = []
    try:
        smoke.launch(staged_bundle, staged_bundle / "app" / "static", 8123,
                     tmp_path, tmp_path / "backend.log", sinks)
    finally:
        for s in sinks:
            s.close()

    assert len(calls) == 1
    program = Path(calls[0]["program"])
    assert program.is_absolute(), (
        f"program path must be absolute; POSIX resolves a relative one against cwd "
        f"({calls[0]['cwd']}) and the exec fails with ENOENT"
    )
    assert program.exists()


def test_child_environment_paths_are_absolute(monkeypatch, staged_bundle: Path, tmp_path: Path):
    """Same trap, quieter failure.

    The child runs with cwd=<bundle>. A relative REDFORGE_STATIC_DIR would be
    resolved from there, miss, and silently fall back to the PyInstaller-collected
    copy — so the harness would report on a directory it was not asked to test.
    """
    calls: list = []
    monkeypatch.setattr(subprocess, "Popen", _posix_style_popen(calls))
    monkeypatch.chdir(tmp_path)

    sinks: list = []
    try:
        smoke.launch(staged_bundle, staged_bundle / "app" / "static", 8124,
                     tmp_path, tmp_path / "backend.log", sinks)
    finally:
        for s in sinks:
            s.close()

    env = calls[0]["env"]
    for key in ("REDFORGE_STATIC_DIR", "REDFORGE_HOME"):
        assert Path(env[key]).is_absolute(), f"{key} must be absolute, got {env[key]!r}"
    assert Path(env["REDFORGE_STATIC_DIR"]).is_dir()
    assert env["REDFORGE_DATABASE_URL"] == (
        f"sqlite+aiosqlite:///{(tmp_path / 'redforge.db').as_posix()}"
    )


def test_relative_inputs_are_rejected_rather_than_silently_wrong(staged_bundle: Path, tmp_path: Path):
    """launch() refuses relative paths outright, so the class cannot come back."""
    with pytest.raises(AssertionError):
        smoke.launch(Path("desktop/resources/backend"),
                     staged_bundle / "app" / "static", 8125, tmp_path,
                     tmp_path / "x.log", [])


def test_missing_frozen_backend_fails_instead_of_using_the_source_backend(
    monkeypatch, staged_bundle: Path, capsys
):
    """A named bundle without its executable is a packaging failure, not a fallback.

    Falling back to the source backend here would let a release publish an
    installer whose executable never started, behind a green smoke test.
    """
    (staged_bundle / smoke.exe_name()).unlink()
    monkeypatch.setattr(sys, "argv", ["smoke_packaged_app.py", str(staged_bundle)])
    assert smoke.main() == 1
    out = capsys.readouterr()
    assert "no frozen backend" in out.err
    # It must not announce the source-backend fallback (the phrase launch() prints).
    assert "launching backend from source" not in (out.out + out.err).lower()


@pytest.mark.parametrize("no_proxy", ["", "127.0.0.1"])
def test_smoke_probe_ignores_proxy_and_does_not_follow_redirect(monkeypatch, no_proxy):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "https://example.com/")
            else:
                self.send_response(200)
            self.end_headers()

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            pass

    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(key, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", no_proxy)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        assert smoke.get(base + "/healthz", retries=0)[0] == 200
        assert smoke.get(base + "/redirect", retries=0)[0] == 302
        request = smoke.urllib.request.Request(base + "/chat", data=b"{}", method="POST")
        assert smoke.get(request, retries=0)[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
