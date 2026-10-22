"""Library endpoints: persistent file storage with metadata indexing.

SECURITY: All endpoints require authentication via require_auth.
user_id is derived from the authenticated API key — NEVER from request input.
"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from auth import require_auth, KeyConfig
from middleware.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Library"])


def _user_id(key: KeyConfig) -> str:
    """Derive user_id from authenticated key. Never trust client input."""
    return key.name


@router.post("/v1/library/upload", summary="Upload file to persistent library")
async def library_upload(
    file: UploadFile = File(...),
    description: str = Form(""),
    tags: str = Form(""),
    key: KeyConfig = Depends(require_auth),
    _rl: None = Depends(check_rate_limit),
):
    """Upload a file to the persistent library. Returns library_id + file_id (Redis session)."""
    from services.library_service import LibraryService
    user_id = _user_id(key)

    file_bytes = await file.read()
    filename = file.filename or "upload.sav"

    try:
        svc = LibraryService()
        result = await svc.upload_file(file_bytes, filename, user_id=user_id)
        file_id = await svc.load_to_redis(result["library_id"])
        return {
            "success": True,
            "data": {
                **result,
                "file_id": file_id or result["library_id"],
                "description": description,
            },
        }
    except Exception as e:
        logger.error("Library upload failed: %s", e, exc_info=True)
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": {"code": "LIBRARY_ERROR", "message": str(e)},
        })


@router.get("/v1/library/files", summary="List all files in library")
async def library_list(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    key: KeyConfig = Depends(require_auth),
):
    """List all files for the authenticated user."""
    from services.library_service import LibraryService
    user_id = _user_id(key)

    try:
        svc = LibraryService()
        all_files = await svc.list_files(user_id)
        total = len(all_files)
        paginated = all_files[offset:offset + limit]
        return {
            "success": True,
            "data": {
                "files": paginated, "total": total,
                "limit": limit, "offset": offset,
                "has_more": (offset + limit) < total,
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": {"code": "LIBRARY_ERROR", "message": str(e)},
        })


@router.get("/v1/library/{library_id}", summary="Get file metadata")
async def library_get(library_id: str, key: KeyConfig = Depends(require_auth)):
    """Get metadata for a specific library file. Only accessible by the file owner."""
    from services.library_service import LibraryService

    try:
        svc = LibraryService()
        meta = await svc.get_file_metadata(library_id)
        if not meta:
            return JSONResponse(status_code=404, content={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": f"File {library_id} not found"},
            })
        # Ownership check
        if meta.get("user_id") and meta["user_id"] != _user_id(key):
            return JSONResponse(status_code=403, content={
                "success": False,
                "error": {"code": "FORBIDDEN", "message": "You do not own this file"},
            })
        return {"success": True, "data": meta}
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": {"code": "LIBRARY_ERROR", "message": str(e)},
        })


@router.get("/v1/library/{library_id}/variables", summary="Get file variables")
async def library_variables(library_id: str, key: KeyConfig = Depends(require_auth)):
    from services.library_service import LibraryService

    try:
        svc = LibraryService()
        meta = await svc.get_file_metadata(library_id)
        if not meta:
            return JSONResponse(status_code=404, content={
                "success": False, "error": {"code": "NOT_FOUND", "message": f"File {library_id} not found"},
            })
        if meta.get("user_id") and meta["user_id"] != _user_id(key):
            return JSONResponse(status_code=403, content={
                "success": False, "error": {"code": "FORBIDDEN", "message": "You do not own this file"},
            })
        variables = await svc.get_file_variables(library_id)
        return {"success": True, "data": {"variables": variables, "total": len(variables)}}
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": {"code": "LIBRARY_ERROR", "message": str(e)},
        })


@router.get("/v1/library/{library_id}/file", summary="Download the original file")
async def library_file(library_id: str, key: KeyConfig = Depends(require_auth)):
    """The file's bytes, so the web app can open a library dataset as if it had just been uploaded."""
    from services.library_service import LibraryService

    try:
        svc = LibraryService()
        meta = await svc.get_file_metadata(library_id)
        if not meta:
            return JSONResponse(status_code=404, content={
                "success": False, "error": {"code": "NOT_FOUND", "message": f"File {library_id} not found"},
            })
        if meta.get("user_id") and meta["user_id"] != _user_id(key):
            return JSONResponse(status_code=403, content={
                "success": False, "error": {"code": "FORBIDDEN", "message": "You do not own this file"},
            })
        downloaded = await svc.download_file(library_id)
        if not downloaded:
            return JSONResponse(status_code=404, content={
                "success": False, "error": {"code": "NOT_FOUND", "message": "File not found in storage"},
            })
        file_bytes, filename = downloaded
        safe_name = quote(filename or "dataset")
        return Response(content=file_bytes, media_type="application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False, "error": {"code": "LIBRARY_ERROR", "message": str(e)},
        })


@router.post("/v1/library/{library_id}/load", summary="Load library file into active session")
async def library_load(library_id: str, key: KeyConfig = Depends(require_auth)):
    from services.library_service import LibraryService

    try:
        svc = LibraryService()
        meta = await svc.get_file_metadata(library_id)
        if not meta:
            return JSONResponse(status_code=404, content={
                "success": False, "error": {"code": "NOT_FOUND", "message": f"File {library_id} not found"},
            })
        if meta.get("user_id") and meta["user_id"] != _user_id(key):
            return JSONResponse(status_code=403, content={
                "success": False, "error": {"code": "FORBIDDEN", "message": "You do not own this file"},
            })
        file_id = await svc.load_to_redis(library_id)
        if not file_id:
            return JSONResponse(status_code=404, content={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "File not found or Redis unavailable"},
            })
        return {"success": True, "data": {"file_id": file_id, "library_id": library_id}}
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": {"code": "LIBRARY_ERROR", "message": str(e)},
        })


@router.patch("/v1/library/{library_id}", summary="Update file metadata")
async def library_update(
    library_id: str,
    display_name: str = Form(None),
    description: str = Form(None),
    tags: str = Form(None),
    key: KeyConfig = Depends(require_auth),
):
    from services.library_service import LibraryService
    import httpx

    try:
        svc = LibraryService()
        updates = {}
        if display_name is not None:
            updates["display_name"] = display_name
        if description is not None:
            updates["description"] = description
        if tags is not None:
            updates["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        if not updates:
            return JSONResponse(status_code=400, content={"success": False, "error": {"message": "No fields to update"}})

        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{svc.rest_url}/library_files?id=eq.{library_id}&user_id=eq.{_user_id(key)}",
                headers={**svc.headers, "Content-Type": "application/json", "Prefer": "return=representation"},
                json=updates,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"success": True, "data": data[0] if data else {}}
            return JSONResponse(status_code=resp.status_code, content={"success": False, "error": {"message": resp.text[:200]}})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": {"code": "LIBRARY_ERROR", "message": str(e)}})


@router.delete("/v1/library/{library_id}", summary="Delete file from library")
async def library_delete(library_id: str, key: KeyConfig = Depends(require_auth)):
    from services.library_service import LibraryService

    try:
        svc = LibraryService()
        meta = await svc.get_file_metadata(library_id)
        if not meta:
            return JSONResponse(status_code=404, content={
                "success": False, "error": {"code": "NOT_FOUND", "message": f"File {library_id} not found"},
            })
        if meta.get("user_id") and meta["user_id"] != _user_id(key):
            return JSONResponse(status_code=403, content={
                "success": False, "error": {"code": "FORBIDDEN", "message": "You do not own this file"},
            })
        deleted = await svc.delete_file(library_id)
        if not deleted:
            return JSONResponse(status_code=404, content={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "File not found"},
            })
        return {"success": True, "message": "File deleted"}
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": {"code": "LIBRARY_ERROR", "message": str(e)},
        })


@router.get("/v1/library/search/files", summary="Search across library")
async def library_search(q: str = Query(...), key: KeyConfig = Depends(require_auth)):
    """Search files and variables by keyword. Only searches authenticated user's files."""
    from services.library_service import LibraryService
    user_id = _user_id(key)

    try:
        svc = LibraryService()
        results = await svc.search_files(user_id, q)
        return {"success": True, "data": {"results": results, "total": len(results)}}
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": {"code": "LIBRARY_ERROR", "message": str(e)},
        })
