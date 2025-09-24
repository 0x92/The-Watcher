from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency may be missing
    redis = None


REDIS_CACHE_TTL = int(os.getenv("INGESTION_CACHE_TTL", "300"))
REDIS_NAMESPACE = os.getenv("INGESTION_CACHE_NAMESPACE", "crawler:jobs")


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
    """Track ingestion jobs in-memory and mirror to Redis when available."""

    def __init__(self) -> None:
        self._jobs: Dict[str, IngestionJob] = {}
        self._lock = threading.Lock()
        self._counter = 0
        self._redis = self._init_redis()

    def _init_redis(self):
        url = os.getenv("REDIS_URL")
        if not url or redis is None:
            return None
        try:  # pragma: no cover - best effort cache connection
            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            return client
        except Exception:
            return None

    def _serialize(self, job: IngestionJob) -> Dict[str, object]:
        started = job.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return {
            "job_id": job.job_id,
            "source_id": job.source_id,
            "name": job.name,
            "endpoint": job.endpoint,
            "started_at": started.isoformat(),
            "items_fetched": job.items_fetched,
            "status": job.status,
            "duration_ms": job.duration_ms,
            "error": job.error,
        }

    def _store(self, job: IngestionJob) -> None:
        if not self._redis:
            return
        key = f"{REDIS_NAMESPACE}:{job.job_id}"
        try:
            self._redis.setex(key, REDIS_CACHE_TTL, json.dumps(self._serialize(job)))
        except Exception:  # pragma: no cover - cache best effort
            pass

    def _delete(self, job_id: str) -> None:
        if not self._redis:
            return
        key = f"{REDIS_NAMESPACE}:{job_id}"
        try:
            self._redis.delete(key)
        except Exception:  # pragma: no cover - cache best effort
            pass

    def _load_cached(self) -> List[Dict[str, object]]:
        if not self._redis:
            return []
        entries: List[Dict[str, object]] = []
        pattern = f"{REDIS_NAMESPACE}:*"
        try:  # pragma: no cover - cache best effort
            for key in self._redis.scan_iter(match=pattern):
                value = self._redis.get(key)
                if not value:
                    continue
                try:
                    entry = json.loads(value)
                except Exception:
                    continue
                entries.append(entry)
        except Exception:
            return []
        return entries

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
        self._store(job)
        return job_id

    def job_progress(self, job_id: str, *, items_fetched: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.items_fetched = items_fetched
                self._store(job)

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
        self._store(record)

    def pop(self, job_id: str) -> IngestionJob | None:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job is not None:
            self._delete(job.job_id)
        else:
            self._delete(job_id)
        return job

    def snapshot(self) -> List[Dict[str, object]]:
        with self._lock:
            snapshot = [job.__dict__.copy() for job in self._jobs.values()]
        cached = self._load_cached()
        existing = {entry.get("job_id") for entry in snapshot}
        for entry in cached:
            if entry.get("job_id") not in existing:
                snapshot.append(entry)
        return snapshot


ingestion_tracker = IngestionTracker()

__all__ = ["ingestion_tracker", "IngestionTracker", "IngestionJob"]
