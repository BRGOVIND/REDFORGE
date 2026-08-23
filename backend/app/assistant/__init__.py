"""RedForge Assistant — local, offline question answering.

Fully offline: no model, no network, no accounts, no telemetry. Answers come
from the user's own database rows, cached metadata, and a curated in-repo
knowledge base.

`app.api.assistant` is the HTTP transport for this module and holds no logic.
"""
from app.assistant.service import Answer, AssistantQuery, Citation, answer

__all__ = ["Answer", "AssistantQuery", "Citation", "answer"]
