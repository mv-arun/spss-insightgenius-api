"""File sessions: upload a data file once, then refer to it by `file_id`.

  POST   /v1/files/upload         multipart/form-data upload
  POST   /v1/files/upload-base64  the same, for callers that only send JSON
  GET    /v1/files/{file_id}      what's in a session (and whether it's still there)
  DELETE /v1/files/{file_id}      end a session now

Sessions live in Redis (the same store as MCP `spss_upload_file`) with a sliding TTL:
every request that uses the file_id renews it.
"""

import base64
import binascii
import json
import logging
import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from auth import require_auth, KeyConfig
from config import get_settings
from middleware.processing import run_in_executor
from middleware.rate_limiter import check_rate_limit
from mcp_server.file_session import _get_redis, _load_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Files"])

# Supported formats
ALLOWED_EXTENSIONS = {"sav", "csv", "tsv", "xlsx", "xls"}

SESSION_RESPONSES = {
    401: {"description": "Invalid or missing API key"},
    413: {"description": "File exceeds the size limit (FILE_TOO_LARGE)"},
    415: {"description": "Unsupported file format (UNSUPPORTED_FORMAT)"},
    422: {"description": "File is empty, corrupted or unreadable (INVALID_FILE)"},
    503: {"description": "File sessions need Redis (SESSIONS_UNAVAILABLE)"},
}


def _get_extension(filename: str) -> str:
    """Extract and validate file extension."""
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


async def _open_session(content: bytes, filename: str, key: KeyConfig) -> dict:
    """Check the file, store it in Redis and return the session description."""
    ext = _get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, detail={
            "code": "UNSUPPORTED_FORMAT",
            "message": f"Unsupported format '.{ext}'. Accepted: {', '.join('.' + e for e in sorted(ALLOWED_EXTENSIONS))}",
        })
    if not content:
        raise HTTPException(422, detail={"code": "INVALID_FILE", "message": "Empty file."})

    settings = get_settings()
    max_bytes = settings.redis_max_file_size_mb * 1024 * 1024
    size_mb = len(content) / (1024 * 1024)
    if len(content) > max_bytes:
        raise HTTPException(413, detail={
            "code": "FILE_TOO_LARGE",
            "message": f"File too large ({size_mb:.1f} MB). Maximum: {settings.redis_max_file_size_mb} MB.",
        })

    # The file must be readable before a session is opened for it
    try:
        data = await run_in_executor(_load_data, content, ext, filename)
    except Exception as e:
        raise HTTPException(422, detail={"code": "INVALID_FILE", "message": f"File is corrupted or unreadable: {e}"})

    r = await _get_redis()
    if r is None:
        raise HTTPException(503, detail={"code": "SESSIONS_UNAVAILABLE",
                                         "message": "File sessions need Redis. Send the file with each request instead."})

    file_id = str(uuid.uuid4())
    ttl = settings.spss_session_ttl_seconds
    info = {
        "filename": filename,
        "format": ext,
        "n_cases": len(data.df),
        "n_variables": len(data.df.columns),
        "size_bytes": len(content),
    }
    try:
        await r.set(f"spss:file:{file_id}", content, ex=ttl)
        await r.set(f"spss:meta:{file_id}", json.dumps(info).encode(), ex=ttl)
    except Exception as e:
        logger.error("Redis error storing upload: %s", e)
        raise HTTPException(503, detail={"code": "SESSIONS_UNAVAILABLE", "message": "Failed to store file session. Try again."})
    finally:
        await r.aclose()

    logger.info(
        "[UPLOAD] key=%s file=%s size=%.1fMB cases=%d vars=%d file_id=%s",
        key.name if key else "demo", filename, size_mb, info["n_cases"], info["n_variables"], file_id,
    )

    return {
        "file_id": file_id,
        **info,
        "session_ttl_seconds": ttl,
        "message": (
            f"File uploaded successfully. Use file_id='{file_id}' with any MCP tool or API endpoint. "
            f"Session expires after {ttl // 60} minutes of inactivity."
        ),
    }


@router.post(
    "/v1/files/upload",
    summary="Upload a file (start a file session)",
    description=(
        "Upload a .sav, .csv, .tsv, .xlsx or .xls file as multipart/form-data. Returns a `file_id` to pass "
        "to any endpoint (instead of the file) or MCP tool. The session lasts 30 minutes from its last use."
    ),
    responses={200: {"description": "File uploaded, session created"}, **SESSION_RESPONSES},
)
async def upload_file(
    file: UploadFile = File(..., description="Data file (.sav, .csv, .tsv, .xlsx, .xls)"),
    key: KeyConfig = Depends(require_auth),
    _rl: None = Depends(check_rate_limit),
):
    return await _open_session(await file.read(), file.filename or "", key)


@router.post(
    "/v1/files/upload-base64",
    summary="Upload a file as base64 JSON",
    description=(
        "The same as `/v1/files/upload`, for callers that can only send JSON: "
        '`{"filename": "survey.sav", "content_base64": "<base64 of the file>"}`. '
        "The filename's extension says how the file is read."
    ),
    responses={200: {"description": "File uploaded, session created"},
               400: {"description": "content_base64 isn't valid base64 (INVALID_BASE64)"}, **SESSION_RESPONSES},
)
async def upload_file_base64(
    filename: str = Body(..., embed=True, description="Original file name, e.g. survey.sav"),
    content_base64: str = Body(..., embed=True, description="The file's bytes, base64-encoded"),
    key: KeyConfig = Depends(require_auth),
    _rl: None = Depends(check_rate_limit),
):
    try:
        content = base64.b64decode(content_base64.split(",", 1)[-1], validate=True)  # "data:...;base64," allowed
    except (binascii.Error, ValueError) as e:
        raise HTTPException(400, detail={"code": "INVALID_BASE64", "message": f"content_base64 isn't valid base64: {e}"})
    return await _open_session(content, filename, key)


async def _session_info(file_id: str) -> tuple[dict, int]:
    r = await _get_redis()
    if r is None:
        raise HTTPException(503, detail={"code": "SESSIONS_UNAVAILABLE", "message": "File sessions need Redis."})
    try:
        meta = await r.get(f"spss:meta:{file_id}")
        ttl = await r.ttl(f"spss:file:{file_id}")
    finally:
        await r.aclose()
    if not meta or ttl == -2:
        raise HTTPException(404, detail={"code": "FILE_NOT_FOUND", "message": f"file_id '{file_id}' not found or expired."})
    return json.loads(meta), ttl


@router.get(
    "/v1/files/{file_id}",
    summary="File session info",
    description="What a file session holds and how long it has left. Doesn't renew the session.",
    responses={404: {"description": "Unknown or expired file_id (FILE_NOT_FOUND)"}},
)
async def get_file(file_id: str, key: KeyConfig = Depends(require_auth)):
    info, ttl = await _session_info(file_id)
    return {"success": True, "data": {"file_id": file_id, **info, "expires_in_seconds": max(ttl, 0)}}


@router.delete(
    "/v1/files/{file_id}",
    summary="Delete a file session",
    description="Removes the uploaded file (and any codebook saved with it) now, instead of waiting for it to expire.",
    responses={404: {"description": "Unknown or expired file_id (FILE_NOT_FOUND)"}},
)
async def delete_file(file_id: str, key: KeyConfig = Depends(require_auth)):
    await _session_info(file_id)
    r = await _get_redis()
    try:
        await r.delete(f"spss:file:{file_id}", f"spss:meta:{file_id}", f"spss:codebook:{file_id}")
    finally:
        await r.aclose()
    logger.info("[UPLOAD] key=%s deleted file_id=%s", key.name if key else "demo", file_id)
    return {"success": True, "data": {"file_id": file_id, "deleted": True}}
