"""Experiment Platform — application service (RedForge V3, Epic 4).

Owns experiment lifecycle, snapshots, cloning, notes/tags, and comparison. References
work via the Artifact Registry (✅) and its own timeline/job-ref tables (populated by
the event subscriber). It does NOT import the Job System or the engines — associations
arrive through events (Constitution §14). Depends on repository interfaces.
"""
from __future__ import annotations

import platform as _platform
import sys
from typing import Optional
from uuid import uuid4

from app.experiments.domain import (
    Experiment,
    ExperimentConfiguration,
    ExperimentNote,
    ExperimentSnapshot,
    ExperimentStatus,
    ExperimentTimelineEvent,
)
from app.experiments.repository import (
    JobRefRepository,
    NoteRepository,
    SqlExperimentRepository,
    SqlJobRefRepository,
    SqlNoteRepository,
    SqlTimelineRepository,
    TimelineRepository,
    ExperimentRepository,
)
from app.logging_config import get_logger

logger = get_logger("experiments")


class ExperimentService:
    def __init__(self, experiment_repo: Optional[ExperimentRepository] = None,
                 timeline_repo: Optional[TimelineRepository] = None,
                 note_repo: Optional[NoteRepository] = None,
                 jobref_repo: Optional[JobRefRepository] = None,
                 artifact_query=None) -> None:
        self._experiments = experiment_repo or SqlExperimentRepository()
        self._timeline = timeline_repo or SqlTimelineRepository()
        self._notes = note_repo or SqlNoteRepository()
        self._jobrefs = jobref_repo or SqlJobRefRepository()
        self._artifact_query = artifact_query

    def _artifacts(self):
        if self._artifact_query is not None:
            return self._artifact_query
        from app.artifacts import artifact_query
        return artifact_query

    # -- timeline (also used by the subscriber) -------------------------------

    async def record_timeline(self, experiment_id: str, *, kind: str, title: str,
                              payload: Optional[dict] = None, source: str = "system") -> Optional[dict]:
        exp = await self._experiments.get(experiment_id)
        if exp is None:
            return None
        evt = await self._timeline.add(ExperimentTimelineEvent(
            id=str(uuid4()), experiment_id=experiment_id, kind=kind, title=title,
            payload=payload or {}, source=source))
        return evt.to_dict()

    async def upsert_job_ref(self, experiment_id: str, job_id: str, *, job_type: str = "",
                             status: str = "") -> None:
        from app.experiments.domain import ExperimentJobReference
        await self._jobrefs.upsert(ExperimentJobReference(
            experiment_id=experiment_id, job_id=job_id, job_type=job_type, status=status))

    async def record_metric(self, experiment_id: str, key: str, value) -> None:
        exp = await self._experiments.get(experiment_id)
        if exp is None:
            return
        exp.metrics = {**(exp.metrics or {}), key: value}
        await self._experiments.update(exp)

    # -- create / snapshot ----------------------------------------------------

    async def _build_snapshot(self, config: ExperimentConfiguration) -> ExperimentSnapshot:
        """Capture a reproducibility snapshot from the current subject + environment.
        Best-effort — never fails experiment creation."""
        snap = ExperimentSnapshot(strategy=config.strategy, provider=config.provider or "",
                                  hyperparameters=config.hyperparameters,
                                  dataset_version=config.dataset_version)
        try:
            from app.version import __version__
            snap.redforge_version = __version__
        except Exception:  # noqa: BLE001
            pass
        snap.platform = {"python": sys.version.split()[0], "system": _platform.system(),
                         "machine": _platform.machine()}
        try:
            from app.resources import detect_resources
            snap.gpu = (detect_resources().to_dict() or {}).get("gpu", {})
        except Exception:  # noqa: BLE001
            pass
        if config.foundation_model_id:
            try:
                from app.foundation_models import foundation_model_service
                fm = await foundation_model_service.get(config.foundation_model_id)
                if fm:
                    snap.foundation_model = {"id": fm["id"], "hf_repo": fm["hf_repo"],
                                             "quantization": fm["quantization"]}
            except Exception:  # noqa: BLE001
                pass
        if config.dataset_id:
            try:
                from app.datasets import dataset_platform
                d = await dataset_platform.get(config.dataset_id)
                if d:
                    snap.dataset_content_hash = d.get("content_hash", "")
                    snap.dataset_version = d.get("current_version")
            except Exception:  # noqa: BLE001
                pass
        # Resource estimate reuses the training estimator (read-only).
        try:
            from app.training import estimation
            from app.training.domain import TrainingConfiguration
            tc = TrainingConfiguration(
                foundation_model_id=config.foundation_model_id, base_model=config.base_model,
                dataset_id=config.dataset_id, dataset_version=config.dataset_version,
                strategy=config.strategy, provider=config.provider or "simulation")
            snap.resource_estimate = estimation.estimate(tc).to_dict()
        except Exception:  # noqa: BLE001
            pass
        return snap

    async def create(self, *, name: str, description: str = "",
                     configuration: Optional[dict] = None, tags: Optional[list[str]] = None,
                     project_id: Optional[str] = None) -> dict:
        config = ExperimentConfiguration.from_dict(configuration or {})
        exp = Experiment(id=str(uuid4()), name=name, status=ExperimentStatus.ACTIVE,
                         description=description, configuration=config, tags=list(tags or []),
                         project_id=project_id)
        exp.snapshot = await self._build_snapshot(config)
        created = await self._experiments.add(exp)
        await self.record_timeline(created.id, kind="experiment.created",
                                   title=f"Experiment '{name}' created")
        logger.info("created experiment %s", created.id)
        return created.to_dict()

    async def snapshot(self, experiment_id: str) -> Optional[dict]:
        exp = await self._experiments.get(experiment_id)
        if exp is None:
            return None
        exp.snapshot = await self._build_snapshot(exp.configuration)
        updated = await self._experiments.update(exp)
        await self.record_timeline(experiment_id, kind="snapshot.captured", title="Snapshot captured")
        return updated.snapshot.to_dict() if updated and updated.snapshot else None

    # -- reads ----------------------------------------------------------------

    async def get(self, experiment_id: str) -> Optional[dict]:
        exp = await self._experiments.get(experiment_id)
        return exp.to_dict() if exp else None

    async def list(self, *, project_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        return [e.to_dict() for e in await self._experiments.list(project_id=project_id, status=status)]

    async def timeline(self, experiment_id: str) -> list[dict]:
        return [e.to_dict() for e in await self._timeline.list(experiment_id)]

    async def artifacts(self, experiment_id: str) -> list[dict]:
        return await self._artifacts().search(experiment_id=experiment_id, limit=500)

    async def jobs(self, experiment_id: str) -> list[dict]:
        return [r.to_dict() for r in await self._jobrefs.list(experiment_id)]

    async def notes(self, experiment_id: str) -> list[dict]:
        return [n.to_dict() for n in await self._notes.list(experiment_id)]

    # -- update / notes / tags ------------------------------------------------

    async def update(self, experiment_id: str, **fields) -> Optional[dict]:
        exp = await self._experiments.get(experiment_id)
        if exp is None:
            return None
        if fields.get("name") is not None:
            exp.name = fields["name"]
        if fields.get("description") is not None:
            exp.description = fields["description"]
        if fields.get("tags") is not None:
            exp.tags = fields["tags"]
        if fields.get("status") is not None:
            exp.status = Experiment.coerce_status(fields["status"])
            if exp.status == ExperimentStatus.CONCLUDED:
                from datetime import datetime, timezone
                exp.concluded_at = datetime.now(timezone.utc)
        updated = await self._experiments.update(exp)
        return updated.to_dict() if updated else None

    async def add_note(self, experiment_id: str, body: str) -> Optional[dict]:
        exp = await self._experiments.get(experiment_id)
        if exp is None:
            return None
        note = await self._notes.add(ExperimentNote(id=str(uuid4()), experiment_id=experiment_id, body=body))
        await self.record_timeline(experiment_id, kind="note", title="Note added",
                                   payload={"note_id": note.id}, source="user")
        return note.to_dict()

    async def delete_note(self, note_id: str) -> bool:
        return await self._notes.delete(note_id)

    async def delete(self, experiment_id: str) -> bool:
        return await self._experiments.delete(experiment_id)

    # -- clone ----------------------------------------------------------------

    async def clone(self, experiment_id: str, *, include_notes: bool = False,
                    name: Optional[str] = None) -> Optional[dict]:
        """Clone an experiment: copy configuration, subject references, tags, and
        (optionally) notes. Artifacts are NOT duplicated — a clone is a fresh line of
        inquiry that references the parent (Constitution §7 cloning)."""
        parent = await self._experiments.get(experiment_id)
        if parent is None:
            return None
        clone = Experiment(
            id=str(uuid4()), name=name or f"{parent.name} (clone)",
            status=ExperimentStatus.ACTIVE, description=parent.description,
            configuration=ExperimentConfiguration.from_dict(parent.configuration.to_dict()),
            tags=list(parent.tags or []), project_id=parent.project_id,
            parent_experiment_id=parent.id)
        clone.snapshot = await self._build_snapshot(clone.configuration)
        created = await self._experiments.add(clone)
        await self.record_timeline(created.id, kind="experiment.cloned",
                                   title=f"Cloned from '{parent.name}'",
                                   payload={"parent_experiment_id": parent.id})
        if include_notes:
            for note in await self._notes.list(experiment_id):
                await self._notes.add(ExperimentNote(id=str(uuid4()), experiment_id=created.id, body=note.body))
        return created.to_dict()

    # -- comparison -----------------------------------------------------------

    async def compare(self, ids: list[str]) -> dict:
        """Side-by-side comparison of experiments (Constitution §7 comparison)."""
        columns = []
        for eid in ids:
            exp = await self._experiments.get(eid)
            if exp is None:
                continue
            artifacts = await self.artifacts(eid)
            by_type: dict[str, int] = {}
            for a in artifacts:
                by_type[a["type"]] = by_type.get(a["type"], 0) + 1
            jobs = await self._jobrefs.list(eid)
            columns.append({
                "id": exp.id, "name": exp.name, "status": exp.status.value,
                "strategy": exp.configuration.strategy, "provider": exp.configuration.provider,
                "base_model": exp.configuration.base_model,
                "hyperparameters": exp.configuration.hyperparameters,
                "metrics": exp.metrics or {},
                "artifact_counts": by_type, "artifacts_total": len(artifacts),
                "jobs_total": len(jobs),
                "training_duration": (exp.metrics or {}).get("training_duration_seconds"),
                "final_loss": (exp.metrics or {}).get("final_loss"),
                "gpu": (exp.snapshot.gpu if exp.snapshot else {}),
            })
        return {"experiments": columns}


experiment_service = ExperimentService()
