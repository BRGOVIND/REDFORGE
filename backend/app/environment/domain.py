"""Host-environment domain — pure data, no I/O, no SQLAlchemy.

Describes the external tools RedForge can make use of, whether they were found,
and — crucially — what the user should do when one is missing. Detection lives in
``detector.py``; this module only models the result so it can be unit-tested and
rendered without touching the host.

Design note: nothing here is "required" for RedForge itself. The desktop build
bundles its own backend, so a user with no Python, Node or Git still gets a fully
working app. These are capability unlocks, and the UI says so — an install that
warns about six missing tools it does not actually need trains users to ignore it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# How much a missing dependency actually matters.
#   required    — RedForge cannot function without it
#   recommended — a headline capability is unavailable without it
#   optional    — a specific, narrower workflow needs it
SEVERITIES = ("required", "recommended", "optional")


@dataclass(frozen=True)
class Remedy:
    """How to obtain a missing dependency on this platform."""

    url: str = ""
    command: str = ""          # copy-pasteable one-liner, when one exists
    manager: str = ""          # winget | brew | apt | … (what `command` uses)

    def to_dict(self) -> dict:
        return {"url": self.url, "command": self.command, "manager": self.manager}


@dataclass(frozen=True)
class Dependency:
    key: str
    label: str
    severity: str
    purpose: str               # why RedForge wants it, in the user's terms
    found: bool = False
    version: Optional[str] = None
    path: Optional[str] = None
    detail: str = ""           # human-readable status line
    remedy: Remedy = field(default_factory=Remedy)
    docs_url: str = ""

    @property
    def blocking(self) -> bool:
        return self.severity == "required" and not self.found

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "severity": self.severity,
            "purpose": self.purpose,
            "found": self.found,
            "version": self.version,
            "path": self.path,
            "detail": self.detail,
            "remedy": self.remedy.to_dict(),
            "docs_url": self.docs_url,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class EnvironmentReport:
    platform: str
    dependencies: list[Dependency]

    @property
    def ready(self) -> bool:
        """True when nothing *required* is missing."""
        return not any(d.blocking for d in self.dependencies)

    def missing(self, severity: str) -> list[Dependency]:
        return [d for d in self.dependencies if d.severity == severity and not d.found]

    def summary(self) -> str:
        found = sum(1 for d in self.dependencies if d.found)
        return f"{found}/{len(self.dependencies)} detected"

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "ready": self.ready,
            "summary": self.summary(),
            "counts": {
                "total": len(self.dependencies),
                "found": sum(1 for d in self.dependencies if d.found),
                "missing_required": len(self.missing("required")),
                "missing_recommended": len(self.missing("recommended")),
                "missing_optional": len(self.missing("optional")),
            },
            "dependencies": [d.to_dict() for d in self.dependencies],
        }
