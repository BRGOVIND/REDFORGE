"""Model Hub — application service. Reads the catalog and turns a one-click download
into a Job (which the Global Task Manager then tracks)."""
from __future__ import annotations

from typing import Optional

from app.model_hub import catalog


class ModelHubService:
    def catalog(self) -> dict:
        return {"categories": catalog.grouped()}

    def get(self, model_id: str) -> Optional[dict]:
        m = catalog.get(model_id)
        return m.to_dict() if m else None

    async def download(self, model_id: str, source: Optional[str] = None,
                       project_id: Optional[str] = None) -> Optional[dict]:
        """Submit a ``model_download`` Job. Returns the queued job (a Task) or None if
        the model is unknown. Source defaults to Hugging Face when available."""
        entry = catalog.get(model_id)
        if entry is None:
            return None
        src = (source or ("huggingface" if entry.hf_repo else "ollama")).lower()
        from app.jobs import job_service
        return await job_service.submit(
            type="model_download", target_ref=entry.name, project_id=project_id,
            params={"model_id": entry.id, "source": src},
        )


model_hub_service = ModelHubService()
