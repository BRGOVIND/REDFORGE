"""Detect the external tools RedForge can use.

Every probe is bounded (short timeout), never raises, and runs off the event loop —
a hung `nvidia-smi` on a broken driver must not stall the API. The probe function
is injected so tests can exercise the whole matrix without touching the host.

Adding a dependency is one ``_SPEC`` entry plus, if the version lives somewhere
unusual, a small parser.
"""
from __future__ import annotations

import asyncio
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from .domain import Dependency, EnvironmentReport, Remedy

PROBE_TIMEOUT_S = 4.0


@dataclass(frozen=True)
class ProbeResult:
    found: bool
    version: Optional[str] = None
    path: Optional[str] = None
    detail: str = ""


# A probe takes the executable names to look for and returns a ProbeResult.
ProbeFn = Callable[[list[str], list[str]], ProbeResult]


def _run_version(executables: list[str], version_args: list[str]) -> ProbeResult:
    """Find the first executable on PATH and ask it for its version."""
    for name in executables:
        path = shutil.which(name)
        if not path:
            continue
        if not version_args:
            return ProbeResult(found=True, path=path)
        try:
            proc = subprocess.run(
                [path, *version_args],
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT_S,
                # Never pop a console window on Windows.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
        except (OSError, subprocess.SubprocessError):
            # It exists but would not run — still "found", just unusable.
            return ProbeResult(found=True, path=path, detail="found but did not respond to --version")
        output = (proc.stdout or proc.stderr or "").strip()
        return ProbeResult(found=True, version=_first_version(output) or None, path=path)
    return ProbeResult(found=False)


def _first_version(text: str) -> str:
    match = re.search(r"\d+\.\d+(?:\.\d+)?", text or "")
    return match.group(0) if match else ""


# --- the dependency matrix --------------------------------------------------
# (key, label, severity, purpose, executables, version_args, docs)
_SPEC: list[tuple[str, str, str, str, list[str], list[str], str]] = [
    (
        "python", "Python", "optional",
        "Only needed to run experimental GPU training or the CLI from source. "
        "The desktop app bundles its own backend.",
        ["python3", "python"], ["--version"], "https://www.python.org/downloads/",
    ),
    (
        "cuda", "CUDA / NVIDIA driver", "optional",
        "Unlocks real GPU fine-tuning and much faster local inference. "
        "Without it, RedForge runs on CPU.",
        ["nvidia-smi"], [], "https://developer.nvidia.com/cuda-downloads",
    ),
    (
        "git", "Git", "optional",
        "Used to clone datasets and models from repositories.",
        ["git"], ["--version"], "https://git-scm.com/downloads",
    ),
    (
        "ollama", "Ollama", "recommended",
        "The default local runtime. RedForge uses it to run models for chat, "
        "benchmarking and security evaluation.",
        ["ollama"], ["--version"], "https://ollama.com/download",
    ),
    (
        "lmstudio", "LM Studio", "optional",
        "An alternative local runtime with a built-in model browser.",
        ["lms", "lmstudio"], ["version"], "https://lmstudio.ai/",
    ),
    (
        "llamacpp", "llama.cpp", "optional",
        "A lightweight local runtime for GGUF models.",
        ["llama-server", "llama-cli", "llama"], ["--version"], "https://github.com/ggerganov/llama.cpp",
    ),
    (
        "node", "Node.js", "optional",
        "Only needed to build the RedForge UI from source. Not required to use the app.",
        ["node"], ["--version"], "https://nodejs.org/en/download",
    ),
]

# Per-platform install remedies. A command is offered only where it is genuinely
# a safe, official one-liner — otherwise the user gets the official download page.
_REMEDIES: dict[str, dict[str, Remedy]] = {
    "Windows": {
        "python": Remedy(url="https://www.python.org/downloads/", command="winget install Python.Python.3.11", manager="winget"),
        "git": Remedy(url="https://git-scm.com/download/win", command="winget install Git.Git", manager="winget"),
        "ollama": Remedy(url="https://ollama.com/download/windows", command="winget install Ollama.Ollama", manager="winget"),
        "node": Remedy(url="https://nodejs.org/en/download", command="winget install OpenJS.NodeJS.LTS", manager="winget"),
        "cuda": Remedy(url="https://www.nvidia.com/download/index.aspx"),
        "lmstudio": Remedy(url="https://lmstudio.ai/"),
        "llamacpp": Remedy(url="https://github.com/ggerganov/llama.cpp/releases"),
    },
    "Darwin": {
        "python": Remedy(url="https://www.python.org/downloads/", command="brew install python@3.11", manager="brew"),
        "git": Remedy(url="https://git-scm.com/download/mac", command="brew install git", manager="brew"),
        "ollama": Remedy(url="https://ollama.com/download/mac", command="brew install ollama", manager="brew"),
        "node": Remedy(url="https://nodejs.org/en/download", command="brew install node", manager="brew"),
        "cuda": Remedy(url="https://developer.apple.com/metal/"),
        "lmstudio": Remedy(url="https://lmstudio.ai/"),
        "llamacpp": Remedy(url="https://github.com/ggerganov/llama.cpp", command="brew install llama.cpp", manager="brew"),
    },
    "Linux": {
        "python": Remedy(url="https://www.python.org/downloads/", command="sudo apt install python3.11", manager="apt"),
        "git": Remedy(url="https://git-scm.com/download/linux", command="sudo apt install git", manager="apt"),
        "ollama": Remedy(url="https://ollama.com/download/linux", command="curl -fsSL https://ollama.com/install.sh | sh", manager="shell"),
        "node": Remedy(url="https://nodejs.org/en/download", command="sudo apt install nodejs npm", manager="apt"),
        "cuda": Remedy(url="https://developer.nvidia.com/cuda-downloads"),
        "lmstudio": Remedy(url="https://lmstudio.ai/"),
        "llamacpp": Remedy(url="https://github.com/ggerganov/llama.cpp"),
    },
}


def _remedy(key: str, system: str) -> Remedy:
    return _REMEDIES.get(system, {}).get(key, Remedy())


def _detail(key: str, result: ProbeResult) -> str:
    if result.detail:
        return result.detail
    if not result.found:
        return "not detected on this system"
    if result.version:
        return f"version {result.version}"
    return "detected"


def detect_sync(probe: ProbeFn | None = None, system: str | None = None) -> EnvironmentReport:
    """Blocking detection. Prefer ``detect()`` from async code."""
    probe = probe or _run_version
    system = system or platform.system()
    deps: list[Dependency] = []

    for key, label, severity, purpose, executables, version_args, docs in _SPEC:
        result = probe(executables, version_args)

        # Python is special: the interpreter running this process is the most
        # accurate answer, and it is always available unless we are a frozen
        # binary. Probing PATH instead would report the Microsoft Store alias
        # stub on Windows, which answers `--version` with nothing at all.
        if key == "python" and not getattr(sys, "frozen", False):
            result = ProbeResult(found=True, version=platform.python_version(), path=sys.executable)

        version = result.version
        path = result.path

        deps.append(
            Dependency(
                key=key,
                label=label,
                severity=severity,
                purpose=purpose,
                found=result.found,
                version=version,
                path=path,
                detail=_detail(key, result),
                remedy=_remedy(key, system),
                docs_url=docs,
            )
        )

    return EnvironmentReport(platform=system, dependencies=deps)


async def detect(probe: ProbeFn | None = None) -> EnvironmentReport:
    """Detect off the event loop — several probes shell out."""
    return await asyncio.to_thread(detect_sync, probe)
