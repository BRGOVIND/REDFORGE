# Model Installation

RedForge evaluates models served by **Ollama**. Install Ollama first
(https://ollama.com/download), then pull models.

## Recommended starters

```bash
ollama pull qwen3:8b     # balanced, good default
ollama pull llama3       # widely used
ollama pull gemma        # small and fast
ollama pull mistral      # strong 7B
```

## Managing models

```bash
ollama list              # what you have
ollama pull <model>      # download a model
ollama rm <model>        # remove a model
redforge models          # installed + recommended, with pull commands
```

## Choosing a size
Model names include the parameter size (`:8b`, `:14b`, `:70b`). Bigger = smarter
but heavier:

| Size | Approx. RAM/VRAM (Q4) | Notes |
|------|----------------------|-------|
| ~1–3B | 1–3 GB | very fast, weaker |
| ~7–8B | ~5–6 GB | great default |
| ~13–14B | ~9–10 GB | needs a capable GPU |
| ~70B | ~40+ GB | high-end hardware only |

The **New Evaluation** page estimates memory before you run, and warns if a model
likely won't fit.

## Judge models
Profiles that use an **LLM judge** need a model for judging too (default
`llama3.2`). Pull it as well, or use a heuristic profile (Quick Scan) that needs
no judge.
