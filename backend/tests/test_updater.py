"""Updater — version comparison, checksums, asset selection, and the safe
file-swap/rollback. All offline; no GitHub access."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_CLI = Path(__file__).resolve().parent.parent.parent / "cli"
if str(_CLI) not in sys.path:
    sys.path.insert(0, str(_CLI))

from redforge import updater  # noqa: E402


# -- version comparison -----------------------------------------------------

@pytest.mark.parametrize("cand,cur,expected", [
    ("1.3.0", "1.2.0", True),
    ("1.2.1", "1.2.0", True),
    ("2.0.0", "1.9.9", True),
    ("1.2.0", "1.2.0", False),
    ("1.1.0", "1.2.0", False),
    ("v1.3.0", "1.2.0", True),
    ("1.2.0", "1.2.0-beta", True),      # final release beats its prerelease
    ("1.2.0-rc1", "1.2.0", False),
])
def test_is_newer(cand, cur, expected):
    assert updater.is_newer(cand, cur) is expected


def test_parse_version_malformed():
    assert updater.parse_version("garbage") == (0, 0, 0, 0)


# -- checksums --------------------------------------------------------------

def test_sha256_and_verify(tmp_path):
    f = tmp_path / "redforge-1.2.0.zip"
    f.write_bytes(b"hello world")
    digest = updater.sha256_file(f)
    sums = updater.parse_sha256sums(f"{digest}  redforge-1.2.0.zip\n")
    assert updater.verify_sha256(f, sums) is True


def test_verify_sha256_mismatch(tmp_path):
    f = tmp_path / "redforge-1.2.0.zip"
    f.write_bytes(b"payload")
    sums = {"redforge-1.2.0.zip": "0" * 64}
    assert updater.verify_sha256(f, sums) is False


def test_verify_sha256_missing_entry(tmp_path):
    f = tmp_path / "x.zip"
    f.write_bytes(b"x")
    assert updater.verify_sha256(f, {}) is False


def test_parse_sha256sums_ignores_junk():
    text = "notahash  a\n" + ("a" * 64) + "  real.zip\n"
    assert updater.parse_sha256sums(text) == {"real.zip": "a" * 64}


# -- asset selection --------------------------------------------------------

def test_select_assets():
    release = {"assets": [
        {"name": "redforge-1.3.0.zip", "browser_download_url": "ZIP"},
        {"name": "redforge-1.3.0.tar.gz", "browser_download_url": "TGZ"},
        {"name": "SHA256SUMS.txt", "browser_download_url": "SUMS"},
    ]}
    assert updater.select_assets(release) == ("ZIP", "SUMS")


def test_select_assets_missing():
    assert updater.select_assets({"assets": []}) == (None, None)


# -- safe swap + rollback ---------------------------------------------------

def _fake_install(root: Path):
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "app.py").write_text("v1", encoding="utf-8")
    (root / "backend" / "redforge.db").write_bytes(b"USER_HISTORY")  # must survive
    (root / "VERSION").write_text("1.2.0\n", encoding="utf-8")


def _fake_staging(root: Path) -> Path:
    inner = root / "redforge-9.9.9"
    (inner / "backend").mkdir(parents=True)
    (inner / "backend" / "app.py").write_text("v2", encoding="utf-8")
    (inner / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    return root


def test_apply_release_swaps_and_preserves_db(tmp_path, monkeypatch):
    install_root = tmp_path / "install"
    install_root.mkdir()
    _fake_install(install_root)
    staging = tmp_path / "staging"
    staging.mkdir()
    _fake_staging(staging)

    # Route backups under the install root's .redforge.
    monkeypatch.setenv("REDFORGE_HOME", str(install_root))

    updater.apply_release(staging, install_root)

    assert (install_root / "VERSION").read_text().strip() == "9.9.9"
    assert (install_root / "backend" / "app.py").read_text() == "v2"
    # Evaluation history preserved through the backend replacement.
    assert (install_root / "backend" / "redforge.db").read_bytes() == b"USER_HISTORY"


def test_apply_release_rolls_back_on_failure(tmp_path, monkeypatch):
    install_root = tmp_path / "install"
    install_root.mkdir()
    _fake_install(install_root)
    staging = tmp_path / "staging"
    staging.mkdir()
    _fake_staging(staging)
    monkeypatch.setenv("REDFORGE_HOME", str(install_root))

    # Force a failure on the very first move (backend has been backed up + removed
    # by then — the rollback must still restore it).
    def boom(src, dst):
        raise RuntimeError("disk full")

    monkeypatch.setattr(updater.shutil, "move", boom)

    with pytest.raises(RuntimeError):
        updater.apply_release(staging, install_root)

    # Original tree restored — nothing half-updated.
    assert (install_root / "VERSION").read_text().strip() == "1.2.0"
    assert (install_root / "backend" / "app.py").read_text() == "v1"
    assert (install_root / "backend" / "redforge.db").read_bytes() == b"USER_HISTORY"
