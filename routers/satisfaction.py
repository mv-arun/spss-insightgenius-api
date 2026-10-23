"""POST /v1/satisfaction-summary — Compact satisfaction summary for multiple variables."""

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


def _detect_scale(values):
    """Detect the scale type from numeric values."""
    vals = sorted([v for v in values if not math.isnan(v)])
    if not vals:
        return "1-5"
    min_v, max_v = vals[0], vals[-1]
    if max_v <= 5:
        return "1-5"
    elif max_v <= 7:
        return "1-7"
    else:
        return "1-10"


def _run_satisfaction_summary(file_bytes: bytes, filename: str, spec: dict):
    """Run satisfaction summary (blocking, executed in thread pool)."""
    data = load_data(file_bytes, filename)
    df = data.df

    variables = spec.get("variables", [])
    weight = spec.get("weight")
    scale = spec.get("scale")  # auto-detect if not specified

    if len(variables) < 1:
        raise ValueError("At least 1 variable required")

    for v in variables:
        if v not in df.columns:
            raise ValueError(f"Variable '{v}' not found in dataset")

    # Get labels from metadata
    meta = data.meta
    labels = {}
    if meta:
        if hasattr(meta, 'column_names_to_labels'):
            labels = meta.column_names_to_labels or {}

    summaries = []
    for var in variables:
        series = df[var].dropna()
        if len(series) == 0:
            summaries.append({"variable": var, "label": labels.get(var), "n_valid": 0, "error": "No valid data"})
            continue

        var_scale = scale or _detect_scale(series.values)

        if QUANTIPYMRX_AVAILABLE:
            from quantipymrx.analysis.mrx import satisfaction_summary
            import numpy as np

            w = df[weight].values if weight and weight in df.columns else None
            try:
                result = satisfaction_summary(series, scale=var_scale, weights=w)
            except Exception:
                # Fallback to manual if MRX fails
                result = None
        else:
            result = None

        if result:
            summaries.append({
                "variable": var,
                "label": labels.get(var),
                "n_valid": int(series.count()),
                "scale": var_scale,
                **{k: clean_numeric(v) if isinstance(v, float) else v for k, v in result.items()},
            })
        else:
            # Manual fallback
            values = series.values
            n = len(values)
            mean_val = float(series.mean())
            std_val = float(series.std())

            # Determine T2B/B2B based on scale
            if var_scale == "1-5":
                t2b_vals, b2b_vals = [4, 5], [1, 2]
            elif var_scale == "1-7":
                t2b_vals, b2b_vals = [6, 7], [1, 2]
            else:  # 1-10
                t2b_vals, b2b_vals = [9, 10], [1, 2]

            t2b_count = int(series.isin(t2b_vals).sum())
            b2b_count = int(series.isin(b2b_vals).sum())

            # Distribution
            dist = {}
            for val in sorted(series.unique()):
                dist[str(int(val) if val == int(val) else val)] = int((series == val).sum())

            summaries.append({
                "variable": var,
                "label": labels.get(var),
                "n_valid": n,
                "scale": var_scale,
                "mean": clean_numeric(mean_val),
                "std": clean_numeric(std_val),
                "median": clean_numeric(float(series.median())),
                "t2b": clean_numeric(t2b_count / n * 100) if n > 0 else 0,
                "b2b": clean_numeric(b2b_count / n * 100) if n > 0 else 0,
                "distribution": dist,
            })

    return {
        "summaries": summaries,
        "n_cases": len(df),
        "n_variables": len(variables),
    }


@router.post("/v1/satisfaction-summary", summary="Satisfaction summary",
             description="Compact summary of T2B%, B2B%, Mean, and distribution for multiple scale variables in one call.")
async def satisfaction_summary_endpoint(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    spec: str = Form(..., description='JSON: {"variables": ["sat_speed","sat_price"], "scale": "1-5"}'),
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
        result = await run_in_executor(_run_satisfaction_summary, file_bytes, filename, spec_dict)
    except (asyncio.TimeoutError, RuntimeError):
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
