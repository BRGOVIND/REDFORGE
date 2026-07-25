"""Hardware Compatibility Engine tests — pure + deterministic (no GPU needed)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.hardware.domain import GpuProfile, Verdict
from app.hardware.engine import HardwareCompatibilityEngine


@pytest_asyncio.fixture
async def client(db_session):
    from app.main import app
    from app.db.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

ENGINE = HardwareCompatibilityEngine()
# An RTX 4060 Laptop: 8 GB total, ~7.8 GB free.
GPU_8GB = GpuProfile(available=True, name="RTX 4060 Laptop GPU", total_mb=8188, free_mb=7957, backend="cuda")
GPU_24GB = GpuProfile(available=True, name="RTX 4090", total_mb=24564, free_mb=24000, backend="cuda")
NO_GPU = GpuProfile(available=False)


def _assess(pb_model: str, gpu=GPU_8GB, seq=2048, bs=2, ga=4, strategy="qlora", pb=None):
    return ENGINE.assess(parameter_billions=pb, strategy=strategy, max_seq_length=seq,
                         batch_size=bs, gradient_accumulation=ga, gpu=gpu)


def test_8b_qlora_does_not_fit_8gb_and_recommends_smaller():
    a = ENGINE.assess(parameter_billions=8.0, strategy="qlora", max_seq_length=2048,
                      batch_size=2, gradient_accumulation=4, gpu=GPU_8GB)
    assert a.verdict is Verdict.INSUFFICIENT
    assert a.can_launch is False
    # Even minimum settings overflow the ~7.8 GB usable.
    assert a.estimate_safe.total_mb > a.usable_mb
    # Recommends a strictly smaller model that fits.
    assert a.recommended_max_billions is not None and a.recommended_max_billions < 8.0
    assert a.recommended_models  # concrete suggestions provided


def test_8b_qlora_fits_on_24gb():
    a = ENGINE.assess(parameter_billions=8.0, strategy="qlora", max_seq_length=2048,
                      batch_size=2, gradient_accumulation=4, gpu=GPU_24GB)
    assert a.verdict is Verdict.FITS and a.can_launch


def test_small_model_fits_8gb():
    a = ENGINE.assess(parameter_billions=1.0, strategy="qlora", max_seq_length=2048,
                      batch_size=2, gradient_accumulation=4, gpu=GPU_8GB)
    assert a.verdict is Verdict.FITS and a.can_launch


def test_tight_applies_safe_defaults():
    # 4B on 8 GB: overflows at seq2048/bs2 but fits at seq512/bs1.
    a = ENGINE.assess(parameter_billions=4.0, strategy="qlora", max_seq_length=2048,
                      batch_size=2, gradient_accumulation=4, gpu=GPU_8GB)
    assert a.verdict is Verdict.TIGHT and a.can_launch
    assert a.safe_defaults.max_seq_length == 512
    assert a.safe_defaults.batch_size == 1
    assert a.estimate_safe.total_mb <= a.usable_mb


def test_no_gpu_is_insufficient():
    a = ENGINE.assess(parameter_billions=1.0, strategy="qlora", max_seq_length=512,
                      batch_size=1, gradient_accumulation=1, gpu=NO_GPU)
    assert a.verdict is Verdict.INSUFFICIENT and not a.can_launch


def test_estimate_is_monotonic_in_size_and_seq():
    e_small = ENGINE.estimate(1.0, "qlora", 512, 1)
    e_big = ENGINE.estimate(8.0, "qlora", 512, 1)
    e_longseq = ENGINE.estimate(1.0, "qlora", 2048, 1)
    assert e_big.total_mb > e_small.total_mb          # bigger model → more memory
    assert e_longseq.activations_mb > e_small.activations_mb  # longer seq → more activations


def test_sft_needs_much_more_than_qlora():
    q = ENGINE.estimate(8.0, "qlora", 512, 1)
    s = ENGINE.estimate(8.0, "sft", 512, 1)
    assert s.total_mb > q.total_mb * 2  # full fine-tune dwarfs QLoRA


@pytest.mark.asyncio
async def test_hardware_endpoints(client):
    r = await client.get("/api/hardware")
    assert r.status_code == 200 and "gpu" in r.json()
    r2 = await client.post("/api/hardware/check", json={
        "base_model": "Qwen/Qwen3-8B", "strategy": "qlora",
        "hyperparameters": {"max_seq_length": 2048, "batch_size": 2}})
    assert r2.status_code == 200
    body = r2.json()
    assert body["verdict"] in ("fits", "tight", "insufficient")
    assert "estimate_requested" in body and "gpu" in body
