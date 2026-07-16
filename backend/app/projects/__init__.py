"""AI Studio workspace (RedForge V2, Phase 1).

Local-only project management layered additively on the existing database. No
cloud sync, no accounts. The service is pure persistence/orchestration over the
``projects`` table; it never touches the runtime or provider logic.
"""
from app.projects.service import ProjectService, project_service

__all__ = ["ProjectService", "project_service"]
