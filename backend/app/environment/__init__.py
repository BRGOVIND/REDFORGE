"""Host-environment detection (bounded context).

Answers one question for the first-run wizard and Settings → Diagnostics: *which
external tools are available on this machine, and what should the user do about
the ones that aren't?*

Public surface:
    environment_service.report(refresh=False) -> EnvironmentReport

Imports nothing from other contexts, so it stays trivially testable.
"""
from .domain import Dependency, EnvironmentReport, Remedy
from .service import EnvironmentService, environment_service

__all__ = [
    "Dependency",
    "EnvironmentReport",
    "Remedy",
    "EnvironmentService",
    "environment_service",
]
