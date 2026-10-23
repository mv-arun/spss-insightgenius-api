"""Shared file resolution — load from Redis session (file_id) or direct upload."""

import json
import logging

from fastapi import HTTPException, UploadFile

from config import get_settings
from shared.validators import validate_upload

logger = logging.getLogger(__name__)


async def resolve_file(
    file: UploadFile | None = None,
    file_id: str | None = None,
    allowed_extensions: set[str] | None = None,
) -> tuple[bytes, str]:
    """Resolve file bytes from either a direct upload or a Redis file_id session.

    Priority: file_id (Redis session) > file (direct upload).

    Returns:
        Tuple of (file_bytes, filename).

    Raises:
        HTTPException 400: if neither file nor file_id provided, or file is empty/invalid.
        HTTPException 404: if file_id not found in Redis.
    """
    if file_id:
        return await _resolve_from_redis(file_id)

    if file and file.filename:
        validate_upload(file, allowed_extensions)
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(400, detail={
                "code": "INVALID_FILE_FORMAT",
                "message": "Empty file",
            })
        return file_bytes, file.filename or "upload.sav"

    raise HTTPException(400, detail={
        "code": "NO_FILE",
        "message": "Provide 'file' (upload) or 'file_id' (from /v1/files/upload). "
                   "Upload at https://crosstab.indicolabs.io/upload to get a file_id.",
    })


async def _resolve_from_redis(file_id: str) -> tuple[bytes, str]:
    """Load file bytes from Redis session cache."""
    settings = get_settings()
    if not settings.redis_url:
        raise HTTPException(400, detail={
            "code": "NO_FILE",
            "message": "file_id requires Redis. Upload a file directly or configure REDIS_URL.",
        })

    import redis.asyncio as aioredis
    r = aioredis.from_url(settings.redis_url, decode_responses=False)
    try:
        file_bytes = await r.get(f"spss:file:{file_id}")
        meta_raw = await r.get(f"spss:meta:{file_id}")
        filename = "upload.sav"
        if meta_raw:
            meta_info = json.loads(meta_raw)
            filename = meta_info.get("filename", filename)

        # Refresh TTL
        ttl = settings.spss_session_ttl_seconds
        await r.expire(f"spss:file:{file_id}", ttl)
        await r.expire(f"spss:meta:{file_id}", ttl)
        await r.aclose()
    except Exception as e:
        try:
            await r.aclose()
        except Exception:
            pass
        raise HTTPException(400, detail={
            "code": "SESSION_ERROR",
            "message": str(e),
        })

    if not file_bytes:
        raise HTTPException(404, detail={
            "code": "FILE_NOT_FOUND",
            "message": f"file_id '{file_id}' not found or expired. Re-upload with POST /v1/files/upload.",
        })

    return file_bytes, filename
