"""Background job runner — executes tabulation async + delivers webhook."""

import asyncio
import logging
import time

import httpx
from fastapi import HTTPException

from shared.job_store import JobStore, JobStatus

logger = logging.getLogger(__name__)
_store = JobStore()

JOB_DOWNLOAD_TTL = 3600  # a job's file stays downloadable as long as the job is kept


async def run_tabulation_job(
    job_id: str,
    tabulate_fn,
    *args,
    **kwargs,
) -> None:
    """Run tabulation in background, store result, fire webhook."""
    _store.update(job_id, JobStatus.RUNNING)
    job = _store.get(job_id)
    webhook_url = job.get("webhook_url") if job else None

    try:
        result = await tabulate_fn(*args, **kwargs)
        # result is (excel_bytes, download_url)
        excel_bytes, download_url = result
        if not download_url:
            raise RuntimeError("The file was built but couldn't be stored for download (Redis unavailable)")
        _store.complete(job_id, download_url=download_url, size_bytes=len(excel_bytes),
                        expires_at=time.time() + JOB_DOWNLOAD_TTL)
        logger.info("[JOB] %s completed → %s", job_id, download_url)
    except HTTPException as e:  # the same errors a synchronous request would get
        detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        _store.fail(job_id, error_code=detail.get("code", "PROCESSING_ERROR"), error_message=detail.get("message", ""))
        logger.warning("[JOB] %s failed: %s", job_id, detail)
    except Exception as e:
        _store.fail(job_id, error_code="PROCESSING_ERROR", error_message=str(e))
        logger.error("[JOB] %s failed: %s", job_id, e, exc_info=True)

    # Fire webhook if configured
    if webhook_url:
        await _deliver_webhook(job_id, webhook_url)


async def _deliver_webhook(job_id: str, url: str, max_retries: int = 3) -> None:
    """POST job result to webhook URL with retries."""
    job = _store.get(job_id)
    if not job:
        return

    payload = {
        "event": "job.completed" if job["status"] == JobStatus.DONE else "job.failed",
        "job_id": job_id,
        "status": job["status"],
        "result": job["result"],
        "timestamp": time.time(),
    }

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code < 400:
                    logger.info("[WEBHOOK] %s → %s (%d)", job_id, url, resp.status_code)
                    return
                logger.warning("[WEBHOOK] %s → %s returned %d", job_id, url, resp.status_code)
        except Exception as e:
            logger.warning("[WEBHOOK] %s attempt %d failed: %s", job_id, attempt + 1, e)

        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)

    logger.error("[WEBHOOK] %s → %s failed after %d attempts", job_id, url, max_retries)
