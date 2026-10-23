"""POST /v1/frequency — Frequency table for a single variable."""

import asyncio
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from auth import require_scope, KeyConfig
from middleware.processing import run_in_executor
from middleware.rate_limiter import check_rate_limit
from services.quantipy_engine import QuantiProEngine, QUANTIPYMRX_AVAILABLE
from services.data_loader import load_data
from shared.codebook_resolver import resolve_codebook
from shared.file_resolver import resolve_file
from shared.response import success_response

router = APIRouter(tags=["Analysis"])


@router.post("/v1/frequency", summary="Frequency table",
             description="Calculate frequency distribution for a single variable, optionally weighted.")
async def frequency(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    codebook: str | None = Form(None, description="Codebook JSON from /v1/codebook (edited coding); default: inferred, or saved for file_id"),
    variable: str = Form(..., description="Variable name to analyze"),
    weight: str | None = Form(None, description="Weight variable name"),
    key: KeyConfig = Depends(require_scope("frequency")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()
    file_bytes, filename = await resolve_file(file=file, file_id=file_id)
    cb = await resolve_codebook(codebook, file_id)

    try:
        data = await run_in_executor(load_data, file_bytes, filename, cb)
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except Exception as e:
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": f"Failed to load SPSS: {e}"})

    try:
        result = await run_in_executor(QuantiProEngine.frequency, data, variable, weight)
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except ValueError as e:
        raise HTTPException(400, detail={"code": "VARIABLE_NOT_FOUND", "message": str(e)})
    except Exception as e:
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": str(e)})

    return success_response(result, processing_time_ms=int((time.perf_counter() - start) * 1000))
