"""Model Hub — curated model catalog (RedForge V3).

A hand-maintained catalog of models a user can browse and one-click download from
inside RedForge — no terminal, no ``huggingface-cli``, no ``ollama pull``. Each entry
carries the identity + the resource facts the UI shows (VRAM/RAM/size/hardware) and
per-model badges. Beginner-friendly, trainable models are prioritized.

This is DATA, not logic: adding a model is one dict. Suitability badges are derived
from the parameter count using the same thresholds as the Hardware Compatibility
Engine, so the catalog never contradicts the pre-flight checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Categories in display order.
CATEGORIES = [
    ("small", "Small Models (0.5B–3B)"),
    ("medium", "Medium Models (4B–8B)"),
    ("coding", "Coding Models"),
    ("chat", "Chat Models"),
    ("embedding", "Embedding Models"),
    ("vision", "Vision Models"),
    ("experimental", "Experimental"),
]


@dataclass(frozen=True)
class ModelEntry:
    id: str
    name: str
    family: str
    parameters_b: float
    category: str
    quantization: str            # the format downloaded for local use
    download_size_gb: float
    required_vram_gb: float       # inference (4-bit) VRAM
    estimated_ram_gb: float
    hf_repo: Optional[str]        # Hugging Face source (None → Ollama-only)
    ollama_tag: Optional[str]     # Ollama availability (None → HF-only)
    recommended_hardware: str
    trainable: bool = True        # architecture RedForge can fine-tune (LoRA/QLoRA)
    benchmarkable: bool = True    # can be scored by the Benchmark Center
    description: str = ""

    def badges(self) -> list[str]:
        b: list[str] = []
        # Training fit uses the HCE's rule of thumb: ≤4B QLoRA fits an 8 GB GPU.
        if self.trainable and self.parameters_b <= 4.0:
            b.append("Great for Training")
        if self.benchmarkable:
            b.append("Great for Benchmarking")
        if self.parameters_b <= 3.0 and self.category not in ("vision",):
            b.append("CPU Friendly")
        if self.parameters_b <= 8.0:
            b.append("8GB GPU")
        return b

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "family": self.family,
            "parameters_b": self.parameters_b, "category": self.category,
            "quantization": self.quantization, "download_size_gb": self.download_size_gb,
            "required_vram_gb": self.required_vram_gb, "estimated_ram_gb": self.estimated_ram_gb,
            "hf_repo": self.hf_repo, "ollama_tag": self.ollama_tag,
            "sources": [s for s in (("huggingface" if self.hf_repo else None),
                                    ("ollama" if self.ollama_tag else None)) if s],
            "recommended_hardware": self.recommended_hardware,
            "training_suitability": "recommended" if (self.trainable and self.parameters_b <= 4.0)
                                    else ("supported" if self.trainable else "not supported"),
            "benchmark_suitability": "recommended" if self.benchmarkable else "limited",
            "trainable": self.trainable, "benchmarkable": self.benchmarkable,
            "badges": self.badges(), "description": self.description,
        }


def _e(**kw) -> ModelEntry:
    return ModelEntry(**kw)


# --- The catalog -----------------------------------------------------------
_CATALOG: list[ModelEntry] = [
    # Small (0.5B–3B) — beginner-friendly, trainable, CPU-friendly.
    _e(id="qwen3-0_6b", name="Qwen3 0.6B", family="qwen3", parameters_b=0.6, category="small",
       quantization="4-bit (bnb)", download_size_gb=0.5, required_vram_gb=1.5, estimated_ram_gb=2,
       hf_repo="Qwen/Qwen3-0.6B", ollama_tag="qwen3:0.6b", recommended_hardware="Any GPU or CPU",
       description="Tiny, fast, and easy to fine-tune — the recommended first model."),
    _e(id="qwen3-1_7b", name="Qwen3 1.7B", family="qwen3", parameters_b=1.7, category="small",
       quantization="4-bit (bnb)", download_size_gb=1.2, required_vram_gb=2.5, estimated_ram_gb=4,
       hf_repo="Qwen/Qwen3-1.7B", ollama_tag="qwen3:1.7b", recommended_hardware="4GB+ GPU or CPU",
       description="Strong small model; great balance of quality and speed for training."),
    _e(id="tinyllama-1_1b", name="TinyLlama 1.1B", family="llama", parameters_b=1.1, category="small",
       quantization="Q4_K_M", download_size_gb=0.7, required_vram_gb=1.5, estimated_ram_gb=2,
       hf_repo="TinyLlama/TinyLlama-1.1B-Chat-v1.0", ollama_tag="tinyllama",
       recommended_hardware="Any GPU or CPU", description="Classic tiny chat model for quick experiments."),
    _e(id="smollm2-1_7b", name="SmolLM2 1.7B", family="llama", parameters_b=1.7, category="small",
       quantization="Q4_K_M", download_size_gb=1.1, required_vram_gb=2.5, estimated_ram_gb=4,
       hf_repo="HuggingFaceTB/SmolLM2-1.7B-Instruct", ollama_tag="smollm2:1.7b",
       recommended_hardware="4GB+ GPU or CPU", description="Efficient small instruct model."),
    _e(id="gemma2-2b", name="Gemma 2 2B", family="gemma", parameters_b=2.0, category="small",
       quantization="Q4_K_M", download_size_gb=1.6, required_vram_gb=3, estimated_ram_gb=4,
       hf_repo="google/gemma-2-2b-it", ollama_tag="gemma2:2b", recommended_hardware="4GB+ GPU",
       description="Google's compact, high-quality 2B chat model."),
    _e(id="phi-2", name="Phi-2 2.7B", family="phi", parameters_b=2.7, category="small",
       quantization="Q4_K_M", download_size_gb=1.7, required_vram_gb=3, estimated_ram_gb=6,
       hf_repo="microsoft/phi-2", ollama_tag="phi", recommended_hardware="4GB+ GPU",
       description="Small model with surprisingly strong reasoning."),
    _e(id="llama32-1b", name="Llama 3.2 1B", family="llama", parameters_b=1.0, category="small",
       quantization="Q4_K_M", download_size_gb=0.8, required_vram_gb=1.5, estimated_ram_gb=2,
       hf_repo="meta-llama/Llama-3.2-1B-Instruct", ollama_tag="llama3.2:1b",
       recommended_hardware="Any GPU or CPU", description="Meta's tiny instruct model."),
    _e(id="llama32-3b", name="Llama 3.2 3B", family="llama", parameters_b=3.0, category="small",
       quantization="Q4_K_M", download_size_gb=2.0, required_vram_gb=3.5, estimated_ram_gb=6,
       hf_repo="meta-llama/Llama-3.2-3B-Instruct", ollama_tag="llama3.2:3b",
       recommended_hardware="6GB+ GPU", description="Capable 3B instruct model."),

    # Medium (4B–8B)
    _e(id="qwen3-4b", name="Qwen3 4B", family="qwen3", parameters_b=4.0, category="medium",
       quantization="4-bit (bnb)", download_size_gb=2.5, required_vram_gb=4, estimated_ram_gb=8,
       hf_repo="Qwen/Qwen3-4B", ollama_tag="qwen3:4b", recommended_hardware="8GB GPU (reduced settings for training)",
       description="Largest model that comfortably trains on an 8 GB GPU."),
    _e(id="qwen25-7b", name="Qwen2.5 7B", family="qwen", parameters_b=7.0, category="medium",
       quantization="4-bit (bnb)", download_size_gb=4.5, required_vram_gb=6, estimated_ram_gb=10,
       hf_repo="Qwen/Qwen2.5-7B-Instruct", ollama_tag="qwen2.5:7b", recommended_hardware="8GB GPU (inference); 12GB+ to train",
       trainable=True, description="Strong general 7B model."),
    _e(id="llama31-8b", name="Llama 3.1 8B", family="llama", parameters_b=8.0, category="medium",
       quantization="4-bit (bnb)", download_size_gb=5.5, required_vram_gb=6.5, estimated_ram_gb=12,
       hf_repo="meta-llama/Llama-3.1-8B-Instruct", ollama_tag="llama3.1:8b",
       recommended_hardware="8GB GPU (inference); 12GB+ to train", description="Popular 8B instruct model."),
    _e(id="mistral-7b", name="Mistral 7B", family="mistral", parameters_b=7.0, category="medium",
       quantization="4-bit (bnb)", download_size_gb=4.1, required_vram_gb=6, estimated_ram_gb=10,
       hf_repo="mistralai/Mistral-7B-Instruct-v0.3", ollama_tag="mistral",
       recommended_hardware="8GB GPU", description="Efficient, high-quality 7B model."),

    # Coding
    _e(id="qwen25-coder-1_5b", name="Qwen2.5-Coder 1.5B", family="qwen", parameters_b=1.5, category="coding",
       quantization="4-bit (bnb)", download_size_gb=1.1, required_vram_gb=2.5, estimated_ram_gb=4,
       hf_repo="Qwen/Qwen2.5-Coder-1.5B-Instruct", ollama_tag="qwen2.5-coder:1.5b",
       recommended_hardware="4GB+ GPU", description="Small, trainable coding model."),
    _e(id="qwen25-coder-7b", name="Qwen2.5-Coder 7B", family="qwen", parameters_b=7.0, category="coding",
       quantization="4-bit (bnb)", download_size_gb=4.5, required_vram_gb=6, estimated_ram_gb=10,
       hf_repo="Qwen/Qwen2.5-Coder-7B-Instruct", ollama_tag="qwen2.5-coder:7b",
       recommended_hardware="8GB GPU", description="Strong code generation model."),
    _e(id="deepseek-coder-1_3b", name="DeepSeek-Coder 1.3B", family="llama", parameters_b=1.3, category="coding",
       quantization="Q4_K_M", download_size_gb=0.9, required_vram_gb=2, estimated_ram_gb=4,
       hf_repo="deepseek-ai/deepseek-coder-1.3b-instruct", ollama_tag="deepseek-coder:1.3b",
       recommended_hardware="Any GPU or CPU", description="Tiny coding assistant."),

    # Chat
    _e(id="phi3-mini", name="Phi-3 Mini 3.8B", family="phi3", parameters_b=3.8, category="chat",
       quantization="Q4_K_M", download_size_gb=2.3, required_vram_gb=4, estimated_ram_gb=8,
       hf_repo="microsoft/Phi-3-mini-4k-instruct", ollama_tag="phi3:mini",
       recommended_hardware="6GB+ GPU", description="Compact, capable chat model."),

    # Embedding (not trainable/benchmarkable in the LLM sense)
    _e(id="nomic-embed", name="Nomic Embed Text v1.5", family="nomic", parameters_b=0.14, category="embedding",
       quantization="F16", download_size_gb=0.3, required_vram_gb=1, estimated_ram_gb=1,
       hf_repo="nomic-ai/nomic-embed-text-v1.5", ollama_tag="nomic-embed-text",
       recommended_hardware="CPU", trainable=False, benchmarkable=False,
       description="High-quality local text-embedding model."),
    _e(id="bge-small", name="BGE Small EN v1.5", family="bge", parameters_b=0.03, category="embedding",
       quantization="F16", download_size_gb=0.1, required_vram_gb=1, estimated_ram_gb=1,
       hf_repo="BAAI/bge-small-en-v1.5", ollama_tag=None, recommended_hardware="CPU",
       trainable=False, benchmarkable=False, description="Fast, tiny embedding model."),

    # Vision
    _e(id="qwen2-vl-2b", name="Qwen2-VL 2B", family="qwen2-vl", parameters_b=2.0, category="vision",
       quantization="4-bit (bnb)", download_size_gb=2.2, required_vram_gb=4, estimated_ram_gb=6,
       hf_repo="Qwen/Qwen2-VL-2B-Instruct", ollama_tag=None, recommended_hardware="6GB+ GPU",
       trainable=False, description="Small vision-language model."),
    _e(id="llava-7b", name="LLaVA 1.6 7B", family="llava", parameters_b=7.0, category="vision",
       quantization="Q4_K_M", download_size_gb=4.7, required_vram_gb=7, estimated_ram_gb=12,
       hf_repo=None, ollama_tag="llava", recommended_hardware="8GB GPU", trainable=False,
       description="Popular open vision-language model (via Ollama)."),

    # Experimental
    _e(id="smollm2-135m", name="SmolLM2 135M", family="llama", parameters_b=0.135, category="experimental",
       quantization="Q4_K_M", download_size_gb=0.1, required_vram_gb=1, estimated_ram_gb=1,
       hf_repo="HuggingFaceTB/SmolLM2-135M-Instruct", ollama_tag="smollm2:135m",
       recommended_hardware="CPU", description="Ultra-tiny — instant to download and train."),
    _e(id="qwen3-8b", name="Qwen3 8B", family="qwen3", parameters_b=8.0, category="experimental",
       quantization="4-bit (bnb)", download_size_gb=6.5, required_vram_gb=7, estimated_ram_gb=12,
       hf_repo="Qwen/Qwen3-8B", ollama_tag="qwen3:8b",
       recommended_hardware="12GB+ GPU to train (too large for 8 GB QLoRA)", trainable=True,
       description="8B model — inference on 8 GB; training needs a larger GPU."),
]

_BY_ID = {m.id: m for m in _CATALOG}


def list_catalog() -> list[ModelEntry]:
    return list(_CATALOG)


def get(model_id: str) -> Optional[ModelEntry]:
    return _BY_ID.get(model_id)


def grouped() -> list[dict]:
    """Catalog grouped by category, in display order (empty categories omitted)."""
    out = []
    for key, label in CATEGORIES:
        items = [m.to_dict() for m in _CATALOG if m.category == key]
        if items:
            out.append({"key": key, "label": label, "models": items})
    return out
