"""Job store: in memory, written through to Redis when REDIS_URL is set.

Jobs track async processing requests (tabulation, auto-analyze).
Each job has: id, status, endpoint, user_id, webhook_url, result, timestamps.

The API runs several workers on several replicas, so a job started on one is polled on
another: with Redis every worker sees every job. Without it (local runs, tests) jobs live
in this worker's memory only.
"""

import json
import logging
import time
import uuid
from enum import Enum
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# This worker's jobs (also the only store when there's no Redis)
_jobs: dict[str, dict] = {}

# Jobs older than this are evicted on next create/get
_JOB_TTL_SECONDS = 3600  # 1 hour

_redis = None


def _get_redis():
    """Sync Redis client (job reads/writes are tiny), or None without REDIS_URL."""
    global _redis
    url = get_settings().redis_url
    if not url:
        return None
    if _redis is None:
        import redis
        _redis = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
    return _redis


def _save(job: dict) -> None:
    _jobs[job["id"]] = job
    r = _get_redis()
    if r is None:
        return
    try:
        r.set(f"job:{job['id']}", json.dumps(job), ex=_JOB_TTL_SECONDS)
    except Exception as e:
        logger.warning("Job %s not saved to Redis: %s", job["id"], e)


def _load(job_id: str) -> Optional[dict]:
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(f"job:{job_id}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("Job %s not read from Redis: %s", job_id, e)
    return _jobs.get(job_id)


def _evict_expired() -> None:
    """Remove jobs older than TTL to prevent unbounded memory growth."""
    cutoff = time.time() - _JOB_TTL_SECONDS
    expired = [jid for jid, j in _jobs.items() if j["updated_at"] < cutoff]
    for jid in expired:
        del _jobs[jid]


class JobStore:
    """Manages async job lifecycle (see module docstring)."""

    def create(
        self,
        user_id: str,
        endpoint: str,
        webhook_url: Optional[str] = None,
    ) -> str:
        _evict_expired()
        job_id = str(uuid.uuid4())
        _save({
            "id": job_id,
            "status": JobStatus.PENDING,
            "endpoint": endpoint,
            "user_id": user_id,
            "webhook_url": webhook_url,
            "result": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        })
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        _evict_expired()
        return _load(job_id)

    def _change(self, job_id: str, status: JobStatus, result: dict | None = None, keep_result: bool = False) -> None:
        job = _load(job_id)
        if job is None:
            return
        job["status"] = status
        if not keep_result:
            job["result"] = result
        job["updated_at"] = time.time()
        _save(job)

    def update(self, job_id: str, status: JobStatus) -> None:
        self._change(job_id, status, keep_result=True)

    def complete(self, job_id: str, download_url: str, **extra) -> None:
        self._change(job_id, JobStatus.DONE, {"download_url": download_url, **extra})

    def fail(self, job_id: str, error_code: str, error_message: str) -> None:
        self._change(job_id, JobStatus.FAILED, {"error": {"code": error_code, "message": error_message}})
