"""POST /v1/crosstab — Crosstab with significance testing."""

import asyncio
import json
import time

import pandas as pd

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from auth import require_scope, KeyConfig
from middleware.processing import run_in_executor
from middleware.rate_limiter import check_rate_limit
from shared.codebook_resolver import resolve_codebook
from shared.file_resolver import resolve_file
from shared.response import success_response
from shared.significance import low_base_marker
from services.quantipy_engine import QuantiProEngine, QUANTIPYMRX_AVAILABLE, _sanitize_value
from services.data_cache import load_data_cached
from services.tabulation_builder import _mrs_crosstab

router = APIRouter(tags=["Analysis"])


@router.post("/v1/crosstab", summary="Crosstab with significance", description="Cross-tabulation with column proportion z-test significance letters (A/B/C notation).")
async def crosstab(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/library/upload"),
    codebook: str | None = Form(None, description="Codebook JSON from /v1/codebook (edited coding); default: inferred, or saved for file_id"),
    spec: str = Form(..., description='JSON object: {"row": "Q1", "col": "S2", "weight": null, "significance_level": 0.95, "significance_levels": [0.95, 0.90] (optional, lowercase letters at the 2nd level), "low_base_warn": 100, "low_base_flag": 30}. For a multi-select question pass "rows": [its 0/1 option variables] instead of "row": one table, % of respondents ticking each option (bases = people who answered the question).'),
    key: KeyConfig = Depends(require_scope("crosstab")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()

    file_bytes, filename = await resolve_file(file=file, file_id=file_id)
    cb = await resolve_codebook(codebook, file_id)

    # Parse spec JSON
    try:
        spec_data = json.loads(spec)
    except json.JSONDecodeError:
        raise HTTPException(400, detail={"code": "VALIDATION_ERROR", "message": "Invalid JSON in 'spec' field"})

    row_var = spec_data.get("row")
    col_var = spec_data.get("col")
    rows = spec_data.get("rows")  # multi-select: its option variables
    if rows is not None and (not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows)):
        raise HTTPException(400, detail={"code": "VALIDATION_ERROR", "message": "'rows' must be a non-empty list of variable names"})
    if not (row_var or rows) or not col_var:
        raise HTTPException(400, detail={"code": "VALIDATION_ERROR", "message": "'row' (or 'rows') and 'col' are required in spec"})

    weight = spec_data.get("weight")
    sig_level = spec_data.get("significance_level", 0.95)
    secondary_level = None
    if spec_data.get("significance_levels"):
        try:
            levels = sorted({float(level) for level in spec_data["significance_levels"]}, reverse=True)
        except (TypeError, ValueError):
            levels = []
        if not levels or not all(0 < level < 1 for level in levels):
            raise HTTPException(400, detail={"code": "VALIDATION_ERROR",
                                             "message": "significance_levels must be numbers between 0 and 1, e.g. [0.95, 0.90]"})
        sig_level = levels[0]
        secondary_level = levels[1] if len(levels) > 1 else None
    low_base_warn = int(spec_data.get("low_base_warn", 100))
    low_base_flag = int(spec_data.get("low_base_flag", 30))

    try:
        data = await run_in_executor(load_data_cached, file_bytes, filename, cb)
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except Exception as e:
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": f"Failed to load SPSS: {e}"})

    try:
        if rows:
            missing = [r for r in [*rows, col_var] if r not in data.df.columns]
            if missing:
                raise ValueError(f"Variables not found in dataset: {', '.join(missing)}")
            not_flags = [r for r in rows if not pd.api.types.is_numeric_dtype(data.df[r])]
            if not_flags:
                raise ValueError(f"'rows' must be 0/1 option variables of a multi-select; not numeric: {', '.join(not_flags)}")
            result = await run_in_executor(_mrs_crosstab, data, rows, col_var, weight, sig_level, secondary_level)
        else:
            result = await run_in_executor(
                QuantiProEngine.crosstab_with_significance, data, row_var, col_var, weight, sig_level,
                secondary_level,
            )
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except ValueError as e:
        raise HTTPException(400, detail={"code": "VARIABLE_NOT_FOUND", "message": str(e)})
    except Exception as e:
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": str(e)})

    # Unweighted base per banner column, with Decipher-style low-sample markers
    if rows:  # multi-select: base = respondents who answered the question
        answered = data.df[rows].notna().any(axis=1) & data.df[col_var].notna()
        bases = {str(_sanitize_value(v)): int(n) for v, n in data.df.loc[answered, col_var].value_counts().items()}
    else:
        valid = data.df[[row_var, col_var]].dropna()
        bases = {str(_sanitize_value(v)): int(n) for v, n in valid[col_var].value_counts().items()}
    result["column_bases"] = bases
    result["low_base"] = {v: m for v, n in bases.items() if (m := low_base_marker(n, low_base_warn, low_base_flag))}

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return success_response(result, processing_time_ms=elapsed_ms, meta={
        "engine_version": "1.0.0",
        "quantipymrx_available": QUANTIPYMRX_AVAILABLE,
    })
