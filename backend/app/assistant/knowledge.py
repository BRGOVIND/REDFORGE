"""Curated local knowledge base and its retriever.

Fully offline: no model, no network. The retriever is deliberately pluggable —
swap :func:`retrieve` for a vector/RAG search later without touching the API or
the answerers; the return shape (a list of KB entries) is the contract.
"""
from __future__ import annotations

import re

# Curated knowledge. Each entry is a small, self-contained explainer. Keywords
# drive retrieval; a RAG retriever would replace this list with an index.
_KB: list[dict] = [
    {
        "id": "eval-score",
        "title": "Reading a security score",
        "keywords": ["score", "result", "evaluation", "verdict", "pass", "fail", "report"],
        "body": "A RedForge security score (0–100) summarizes how well a model resisted the "
                "attack suite: higher is safer. Each attack yields PASS / FAIL / UNCERTAIN. "
                "Open the report for category breakdowns, ranked vulnerabilities, and "
                "recommendations.",
    },
    {
        "id": "prompt-injection",
        "title": "What is prompt injection?",
        "keywords": ["prompt", "injection", "attack", "override", "instructions"],
        "body": "Prompt injection tries to override the model's instructions with adversarial "
                "input (e.g. 'ignore previous instructions'). RedForge tests many variants; a "
                "FAIL means the model followed the injected instruction.",
    },
    {
        "id": "jailbreak",
        "title": "What is a jailbreak?",
        "keywords": ["jailbreak", "roleplay", "dan", "bypass", "policy", "evasion"],
        "body": "A jailbreak coaxes a model past its safety policy, often via roleplay or "
                "hypotheticals. RedForge groups these under Jailbreak / Roleplay / Policy "
                "Evasion categories in the Attack Library.",
    },
    {
        "id": "provider-setup",
        "title": "Setting up a runtime provider",
        "keywords": ["provider", "runtime", "ollama", "lmstudio", "llama", "vllm", "setup", "offline",
                     "api key", "openai", "anthropic", "gemini", "groq"],
        "body": "RedForge runs models through a runtime provider — Ollama (recommended default), "
                "LM Studio, llama.cpp, or vLLM locally, or OpenAI/Anthropic/Gemini/Groq/OpenRouter "
                "with an API key. Pick one on the Runtime page; onboarding can recommend and "
                "download a model that fits your hardware.",
    },
    {
        "id": "provider-offline",
        "title": "Fixing 'runtime provider is offline'",
        "keywords": ["offline", "unreachable", "error", "provider", "not running", "connection"],
        "body": "Your selected runtime isn't reachable. Start it (for Ollama: `ollama serve`), "
                "confirm its base URL, then re-check on the Runtime page or with `redforge doctor`. "
                "Cloud providers need their API key set.",
    },
    {
        "id": "playground",
        "title": "Using the Playground",
        "keywords": ["playground", "chat", "temperature", "top_p", "system prompt", "seed", "tokens"],
        "body": "The Playground lets you chat with any configured provider and tune sampling "
                "(temperature, top-p, max tokens, seed, system prompt). Click 'Run Security "
                "Evaluation' to send the current prompt straight into the evaluation engine.",
    },
    {
        "id": "projects",
        "title": "Projects and the AI Studio",
        "keywords": ["project", "workspace", "studio", "organize", "recent", "duplicate"],
        "body": "Projects are local workspaces that group models, evaluations, reports, and "
                "settings. Create, open, rename, duplicate, or delete them from the Studio. "
                "Recent projects appear on the dashboard. Everything stays on your machine.",
    },
    {
        "id": "local-first",
        "title": "Is my data private?",
        "keywords": ["privacy", "local", "cloud", "data", "telemetry", "account", "offline"],
        "body": "Yes. RedForge is local-first: no accounts, no telemetry, no required API keys, "
                "and it works fully offline. Nothing — models, datasets, prompts, or results — "
                "leaves your machine unless you explicitly configure a cloud provider.",
    },
    {
        "id": "dataset-lab",
        "title": "The Dataset Lab",
        "keywords": ["dataset", "datasets", "import", "quality", "clean", "split", "version",
                     "duplicates", "tuning", "csv", "jsonl"],
        "body": "The Dataset Lab manages local datasets as project assets: import CSV/JSON/JSONL/"
                "TXT/MD/PDF/DOCX, preview rows, analyze quality, clean (dedupe, trim, normalize, "
                "drop empty), split train/validation/test, and version every save. Open a dataset "
                "and ask me about its quality for specifics.",
    },
    {
        "id": "lora-vs-qlora",
        "title": "LoRA vs QLoRA",
        "keywords": ["lora", "qlora", "method", "quantized", "4bit", "which", "choose", "vram"],
        "body": "LoRA trains small adapter matrices on top of a frozen model — fast, but the base "
                "weights sit in full/half precision. QLoRA loads the base model in 4-bit (quantized) "
                "and trains LoRA adapters on top, cutting VRAM sharply. Use QLoRA when VRAM is tight "
                "or the model is large; LoRA when you have VRAM to spare and want maximum quality.",
    },
    {
        "id": "rank",
        "title": "Explain LoRA rank (r)",
        "keywords": ["rank", "r", "lora"],
        "body": "Rank is the size of the low-rank adapter matrices. Higher rank = more trainable "
                "capacity (can fit more, but risks overfitting and uses more memory); lower rank = "
                "lighter, more regularized. 8–32 is a common range; 16 is a solid default.",
    },
    {
        "id": "alpha",
        "title": "Explain LoRA alpha",
        "keywords": ["alpha", "scaling", "lora"],
        "body": "Alpha scales the LoRA update (effective scale ≈ alpha / rank). A common convention "
                "is alpha = 2×rank (e.g. rank 16, alpha 32). Raising alpha strengthens the adapter's "
                "influence; lowering it softens it.",
    },
    {
        "id": "batch-size",
        "title": "Explain batch size & gradient accumulation",
        "keywords": ["batch", "size", "gradient", "accumulation", "memory", "oom"],
        "body": "Batch size is how many samples are processed before an optimizer step; larger "
                "batches are smoother but use more VRAM. Gradient accumulation simulates a larger "
                "effective batch (batch_size × accumulation) without the memory cost — lower the "
                "batch size and raise accumulation if you hit out-of-memory.",
    },
    {
        "id": "learning-rate",
        "title": "Learning rate & loss behavior",
        "keywords": ["learning", "rate", "lr", "loss", "increasing", "diverge", "reduce", "scheduler"],
        "body": "If loss increases or spikes, the learning rate is likely too high — reduce it "
                "(e.g. halve it) or add warmup. LoRA typically uses 1e-4 to 3e-4. A cosine scheduler "
                "with a short warmup is a good default. Steadily rising validation loss while train "
                "loss falls means overfitting — fewer epochs or lower rank.",
    },
    {
        "id": "vram",
        "title": "Why is VRAM full?",
        "keywords": ["vram", "memory", "full", "oom", "out of memory", "gpu"],
        "body": "VRAM fills from model weights + activations + optimizer state. To reduce it: use "
                "QLoRA (4-bit base), lower the batch size (raise gradient accumulation to compensate), "
                "shorten max sequence length, or pick a smaller base model.",
    },
]

_SUGGESTIONS = [
    "How do I read a security score?",
    "What is prompt injection?",
    "How do I set up a runtime provider?",
    "The provider is offline — how do I fix it?",
    "How do Projects work?",
    "Is my data private?",
]

_WORD = re.compile(r"[a-z0-9_]+")


def retrieve(question: str, k: int = 2) -> list[dict]:
    """Keyword-overlap retriever. Swap for a vector/RAG search later — the return
    shape (list of KB entries) is what the API contract depends on."""
    terms = set(_WORD.findall(question.lower()))
    scored = []
    for entry in _KB:
        kw = set(entry["keywords"])
        overlap = len(terms & kw)
        # small boost when a keyword appears verbatim in the question
        boost = sum(1 for k_ in kw if k_ in question.lower())
        score = overlap * 2 + boost
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [e for _, e in scored[:k]]
