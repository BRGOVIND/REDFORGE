"""The repo-root VERSION file is the single source of truth for the version.

These tests fail if any component re-introduces a hardcoded version literal.
The full drift guard (packaging manifests, installer, package.json) lives in
``scripts/version.py --check`` and runs in CI.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


@pytest.fixture(scope="module")
def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_version_file_is_semver(version: str):
    assert SEMVER.match(version), f"VERSION is not semver: {version!r}"


def test_backend_resolver_matches(version: str):
    from app.version import read_version

    assert read_version() == version


def test_fastapi_app_reports_version(version: str):
    from app.main import app

    assert app.version == version


def test_openapi_reports_version(version: str):
    from app.main import app

    assert app.openapi()["info"]["version"] == version


def test_pyproject_declares_version_dynamic():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in text
    assert not re.search(r'^version\s*=\s*"\d+\.\d+\.\d+"', text, re.MULTILINE)


def test_frontend_package_json_has_no_version():
    data = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert "version" not in data, "vite.config.ts injects __APP_VERSION__ from VERSION"


def test_installer_reads_version_file():
    iss = (ROOT / "installers" / "windows" / "redforge.iss").read_text(encoding="utf-8")
    assert not re.search(r'#define\s+AppVersion\s+"\d+\.\d+\.\d+"', iss)
    assert "FileRead" in iss
