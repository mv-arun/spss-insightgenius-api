"""GET /downloads/{token} — Serve temporary files from Redis.

Files are stored by MCP tools (tabulation, auto-analyze, export) with a 5-minute TTL.
The token itself is the secret — no auth required on this endpoint.
"""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Downloads"])

DOWNLOAD_TTL = 300  # 5 minutes


async def store_download(file_bytes: bytes, filename: str, ttl: int = DOWNLOAD_TTL) -> tuple[str, str]:
    """Store file bytes in Redis for temporary download (`ttl` seconds). Returns (token, download_url).

    Used by MCP tools, `response_format: "url"` and async jobs to make files downloadable.
    """
    import uuid

    settings = get_settings()
    token = str(uuid.uuid4())
    base_url = settings.base_url or f"https://crosstab.indicolabs.io"
    download_url = f"{base_url}/downloads/{token}"

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=False)
        await r.set(f"dl:{token}", file_bytes, ex=ttl)
        await r.set(f"dl:name:{token}", filename.encode(), ex=ttl)
        await r.aclose()
        logger.info("Stored download: %s (%d bytes, TTL=%ds)", filename, len(file_bytes), ttl)
        return token, download_url
    except Exception as e:
        logger.warning("Redis unavailable for downloads: %s. Returning base64 fallback.", e)
        return "", ""


@router.get("/downloads/{token}", summary="Download temporary file",
            description="Retrieve a file from a `download_url` (MCP tools, `response_format: \"url\"`, async jobs). "
                        "The token is the secret: no Authorization header needed. Links expire (5 minutes for "
                        "MCP tools, 15 for `response_format: \"url\"`, 1 hour for async jobs).")
async def download_file(token: str):
    settings = get_settings()
    if not settings.redis_url:
        raise HTTPException(404, detail="Download service unavailable (no Redis)")

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=False)
        file_bytes = await r.get(f"dl:{token}")
        filename_bytes = await r.get(f"dl:name:{token}")
        await r.aclose()
    except Exception as e:
        logger.error("Redis error on download: %s", e)
        raise HTTPException(503, detail="Download service temporarily unavailable")

    if not file_bytes:
        raise HTTPException(404, detail={
            "code": "DOWNLOAD_EXPIRED",
            "message": "Download link expired or invalid.",
            "hint": "Run the analysis again to get a new download link.",
        })

    filename = filename_bytes.decode() if filename_bytes else "download.xlsx"

    # Determine content type
    if filename.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename.endswith(".csv"):
        media_type = "text/csv"
    elif filename.endswith(".dta"):
        media_type = "application/x-stata-dta"
    else:
        media_type = "application/octet-stream"

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
