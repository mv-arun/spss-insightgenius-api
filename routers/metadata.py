"""POST /v1/metadata — Extract variable metadata from an SPSS file."""

import asyncio
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from auth import require_scope, KeyConfig
from middleware.processing import run_in_executor
from middleware.rate_limiter import check_rate_limit
from shared.codebook_resolver import resolve_codebook
from shared.file_resolver import resolve_file
from shared.response import success_response
from services.quantipy_engine import QuantiProEngine, QUANTIPYMRX_AVAILABLE
from services.data_loader import load_data

router = APIRouter(tags=["Metadata"])


@router.post("/v1/metadata", summary="Extract SPSS file metadata", description="Returns variable names, labels, types, value labels, and auto-detected question types. No analysis is performed.")
async def metadata(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    codebook: str | None = Form(None, description="Codebook JSON from /v1/codebook (edited coding); default: inferred, or saved for file_id"),
    key: KeyConfig = Depends(require_scope("metadata")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()

    file_bytes, filename = await resolve_file(file=file, file_id=file_id)
    cb = await resolve_codebook(codebook, file_id)

    try:
        data = await run_in_executor(load_data, file_bytes, filename, cb)
        result = await run_in_executor(QuantiProEngine.extract_metadata, data)
    except (asyncio.TimeoutError, RuntimeError):
        raise  # handled by global exception handlers (504 / 503)
    except Exception as e:
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": str(e)})

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return success_response(result, processing_time_ms=elapsed_ms, meta={
        "engine_version": "1.0.0",
        "quantipymrx_available": QUANTIPYMRX_AVAILABLE,
    })
