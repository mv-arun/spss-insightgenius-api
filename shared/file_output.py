"""How endpoints that produce a file (Excel, CSV, …) hand it back: `response_format`.

- "file" (default): the bytes, with Content-Disposition — for browsers and `curl -o`.
- "url": JSON envelope with a temporary `download_url` — for apps that pass the file on.
- "base64": JSON envelope with the bytes as base64 — for apps that can only speak JSON.

The extra headers an endpoint sets (X-Stubs-Total, X-Warnings, …) are sent either way and,
for the JSON formats, also put in `data.info`.
"""

import base64
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

from shared.response import success_response

RESPONSE_FORMATS = ("file", "url", "base64")
URL_TTL_SECONDS = 900  # 15 minutes
RESPONSE_FORMAT_HELP = (
    'How the file comes back: "file" (default, the bytes), "url" (JSON with a download_url valid '
    f'{URL_TTL_SECONDS // 60} minutes) or "base64" (JSON with content_base64)'
)


def check_response_format(value: str | None) -> str:
    value = (value or "file").strip().lower()
    if value not in RESPONSE_FORMATS:
        raise HTTPException(400, detail={
            "code": "VALIDATION_ERROR",
            "message": f"Unsupported response_format '{value}'. Accepted: {', '.join(RESPONSE_FORMATS)}",
        })
    return value


async def file_response(
    content: bytes,
    filename: str,
    media_type: str,
    response_format: str = "file",
    headers: dict[str, str] | None = None,
    started: float | None = None,
) -> Response:
    """Return `content` in the asked-for format (see module docstring)."""
    headers = dict(headers or {})
    elapsed = int((time.perf_counter() - started) * 1000) if started is not None else None
    if elapsed is not None:
        headers.setdefault("X-Processing-Time-Ms", str(elapsed))
    info = {k[2:].lower().replace("-", "_"): v for k, v in headers.items() if k.startswith("X-")}
    info.pop("request_id", None)
    data = {"filename": filename, "content_type": media_type, "size_bytes": len(content), "info": info}

    if response_format == "url":
        from routers.downloads import store_download
        token, url = await store_download(content, filename, ttl=URL_TTL_SECONDS)
        if not token:
            raise HTTPException(503, detail={
                "code": "DOWNLOADS_UNAVAILABLE",
                "message": 'Download links need Redis. Use response_format "file" or "base64".',
            })
        data |= {"download_url": url, "expires_in_seconds": URL_TTL_SECONDS}
    elif response_format == "base64":
        data["content_base64"] = base64.b64encode(content).decode("ascii")
    else:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return Response(content, media_type=media_type, headers=headers)

    return JSONResponse(success_response(data, processing_time_ms=elapsed), headers=headers)
