"""Model Hub tests — catalog integrity, download routing, handler validation."""
from __future__ import annotations

import pytest

from app.model_hub import catalog, model_hub_service
from app.model_hub.download import _handle_model_download


def test_catalog_grouped_has_all_categories_with_models():
    groups = catalog.grouped()
    keys = {g["key"] for g in groups}
    # Every non-empty category shows up; beginner categories are present.
    assert {"small", "medium", "coding", "embedding", "vision", "experimental"} <= keys
    assert all(g["models"] for g in groups)


def test_beginner_model_badges_and_fields():
    m = catalog.get("qwen3-0_6b").to_dict()
    assert m["name"] == "Qwen3 0.6B" and m["family"] == "qwen3"
    assert m["hf_repo"] == "Qwen/Qwen3-0.6B" and m["ollama_tag"] == "qwen3:0.6b"
    assert set(m["sources"]) == {"huggingface", "ollama"}
    for badge in ("Great for Training", "Great for Benchmarking", "CPU Friendly", "8GB GPU"):
        assert badge in m["badges"]
    # required fields the UI shows exist
    for f in ("required_vram_gb", "estimated_ram_gb", "download_size_gb", "recommended_hardware",
              "training_suitability", "benchmark_suitability"):
        assert f in m


def test_large_model_not_marked_trainable_on_8gb():
    m = catalog.get("qwen3-8b").to_dict()
    assert "Great for Training" not in m["badges"]   # 8B doesn't fit 8 GB QLoRA
    assert m["training_suitability"] == "supported"  # trainable on bigger hardware


def test_embedding_model_is_not_trainable_or_benchmarkable():
    m = catalog.get("nomic-embed").to_dict()
    assert m["trainable"] is False and m["benchmarkable"] is False
    assert "Great for Training" not in m["badges"]


def test_service_get_and_catalog():
    assert model_hub_service.get("nope") is None
    assert model_hub_service.get("phi-2")["name"] == "Phi-2 2.7B"
    assert model_hub_service.catalog()["categories"]


@pytest.mark.asyncio
async def test_download_submits_a_job(monkeypatch):
    captured = {}

    async def fake_submit(**kw):
        captured.update(kw)
        return {"id": "job-1", "type": kw["type"], "status": "queued"}

    import app.jobs as jobs_pkg
    monkeypatch.setattr(jobs_pkg.job_service, "submit", fake_submit)

    job = await model_hub_service.download("qwen3-0_6b")
    assert job["type"] == "model_download"
    assert captured["params"]["model_id"] == "qwen3-0_6b"
    assert captured["params"]["source"] == "huggingface"   # HF preferred when available

    assert await model_hub_service.download("does-not-exist") is None


class _Ctx:
    def __init__(self):
        self.progress = []
        self.logs = []

    async def report_progress(self, f, m="", step=None, total=None):
        self.progress.append((f, m))

    async def log(self, m):
        self.logs.append(m)

    def is_cancelled(self):
        return False


class _Job:
    def __init__(self, params):
        self.params = params
        self.id = "j1"


@pytest.mark.asyncio
async def test_handler_rejects_unknown_model():
    res = await _handle_model_download(_Job({"model_id": "ghost"}), _Ctx())
    assert res.success is False and "unknown model" in res.message


@pytest.mark.asyncio
async def test_handler_rejects_ollama_only_request_for_hf_only_model():
    # bge-small has no ollama tag → asking for ollama fails clearly (no network touched)
    res = await _handle_model_download(_Job({"model_id": "bge-small", "source": "ollama"}), _Ctx())
    assert res.success is False and "not available via Ollama" in res.message
