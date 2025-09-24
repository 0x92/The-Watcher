from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List


@dataclass
class IngestionJob:
    job_id: str
    source_id: int
    name: str
    endpoint: str
    started_at: datetime
    items_fetched: int = 0
    status: str = "running"
    duration_ms: int | None = None
    error: str | None = None


class IngestionTracker:
    """In-memory tracker for ingestion jobs used by API and tests."""

    def __init__(self) -> None:
        self._jobs: Dict[str, IngestionJob] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def _next_id(self, source_id: int) -> str:
        self._counter += 1
        return f"ingest-{source_id}-{self._counter}"

    def job_started(self, *, source_id: int, name: str, endpoint: str) -> str:
        job_id = self._next_id(source_id)
        job = IngestionJob(
            job_id=job_id,
            source_id=source_id,
            name=name,
            endpoint=endpoint,
            started_at=datetime.utcnow(),
        )
        with self._lock:
            self._jobs[job_id] = job
        return job_id

    def job_progress(self, job_id: str, *, items_fetched: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.items_fetched = items_fetched

    def job_finished(
        self,
        job_id: str,
        *,
        source_id: int,
        name: str,
        endpoint: str,
        started_at: datetime,
        status: str,
        items_fetched: int,
        duration_ms: int,
        error: str | None,
    ) -> None:
        record = IngestionJob(
            job_id=job_id,
            source_id=source_id,
            name=name,
            endpoint=endpoint,
            started_at=started_at,
            status=status,
            items_fetched=items_fetched,
            duration_ms=duration_ms,
            error=error,
        )
        with self._lock:
            self._jobs[job_id] = record

    def pop(self, job_id: str) -> IngestionJob | None:
        with self._lock:
            return self._jobs.pop(job_id, None)

    def snapshot(self) -> List[Dict[str, object]]:
        with self._lock:
            return [job.__dict__.copy() for job in self._jobs.values()]


ingestion_tracker = IngestionTracker()

__all__ = ["ingestion_tracker", "IngestionTracker", "IngestionJob"]
