"""POST /v1/correlation — Correlation matrix between numeric variables."""

import asyncio
import json
import math
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from auth import require_scope, KeyConfig
from middleware.processing import run_in_executor
from middleware.rate_limiter import check_rate_limit
from shared.file_resolver import resolve_file
from shared.response import success_response
from shared.validators import clean_numeric
from services.quantipy_engine import QuantiProEngine, QUANTIPYMRX_AVAILABLE
from services.data_loader import load_data

router = APIRouter(tags=["Analysis"])


def _run_correlation(file_bytes: bytes, filename: str, spec: dict):
    """Run correlation analysis (blocking, executed in thread pool)."""
    data = load_data(file_bytes, filename)

    variables = spec.get("variables", [])
    method = spec.get("method", "pearson")
    weight = spec.get("weight")

    if len(variables) < 2:
        raise ValueError("At least 2 variables required for correlation analysis")

    for v in variables:
        if v not in data.df.columns:
            raise ValueError(f"Variable '{v}' not found in dataset")

    if not QUANTIPYMRX_AVAILABLE or data.mrx_dataset is None:
        raise RuntimeError("QuantipyMRX required for correlation analysis")

    from quantipymrx.analysis.significance import correlation_matrix

    corr_df, pval_df = correlation_matrix(data.mrx_dataset, variables=variables, method=method)

    # Convert DataFrames to serializable dicts, handling NaN
    matrix = {}
    p_values = {}
    significant_pairs = []

    for row_var in corr_df.index:
        matrix[row_var] = {col: clean_numeric(corr_df.loc[row_var, col]) for col in corr_df.columns}
        p_values[row_var] = {col: clean_numeric(pval_df.loc[row_var, col]) for col in pval_df.columns}

        for col_var in corr_df.columns:
            if row_var < col_var:  # upper triangle only
                p = pval_df.loc[row_var, col_var]
                r = corr_df.loc[row_var, col_var]
                if not math.isnan(p) and p < 0.05:
                    significant_pairs.append({
                        "var1": row_var, "var2": col_var,
                        "r": clean_numeric(r), "p_value": clean_numeric(p),
                    })

    return {
        "variables": variables,
        "method": method,
        "n_cases": len(data.df),
        "matrix": matrix,
        "p_values": p_values,
        "significant_pairs": significant_pairs,
    }


@router.post("/v1/correlation", summary="Correlation matrix",
             description="Calculate correlation matrix between 2+ numeric variables with p-values and significance flags.")
async def correlation(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    spec: str = Form(..., description='JSON: {"variables": ["Q1","Q2","Q3"], "method": "pearson"}'),
    key: KeyConfig = Depends(require_scope("crosstab")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()

    file_bytes, filename = await resolve_file(file=file, file_id=file_id)

    try:
        spec_dict = json.loads(spec)
    except json.JSONDecodeError:
        raise HTTPException(400, detail={"code": "INVALID_SPEC", "message": "Invalid JSON in spec"})

    try:
        result = await run_in_executor(_run_correlation, file_bytes, filename, spec_dict)
    except (asyncio.TimeoutError, RuntimeError) as e:
        if "QuantipyMRX required" in str(e):
            raise HTTPException(501, detail={"code": "ENGINE_UNAVAILABLE", "message": str(e)})
        raise
    except ValueError as e:
        raise HTTPException(400, detail={"code": "VARIABLE_NOT_FOUND", "message": str(e)})
    except Exception as e:
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": str(e)})

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return success_response(result, processing_time_ms=elapsed_ms, meta={
        "engine_version": "1.0.0",
        "quantipymrx_available": QUANTIPYMRX_AVAILABLE,
    })
