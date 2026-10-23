"""POST /v1/gap-analysis — Importance-Performance gap analysis."""

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


def _run_gap_analysis(file_bytes: bytes, filename: str, spec: dict):
    """Run gap analysis (blocking, executed in thread pool)."""
    data = load_data(file_bytes, filename)
    df = data.df

    importance_vars = spec.get("importance_vars", [])
    performance_vars = spec.get("performance_vars", [])
    weight = spec.get("weight")

    if len(importance_vars) < 1 or len(performance_vars) < 1:
        raise ValueError("At least 1 importance and 1 performance variable required")
    if len(importance_vars) != len(performance_vars):
        raise ValueError(f"Importance ({len(importance_vars)}) and performance ({len(performance_vars)}) variable lists must be same length")

    for v in importance_vars + performance_vars:
        if v not in df.columns:
            raise ValueError(f"Variable '{v}' not found in dataset")

    # Compute means for importance and performance
    if weight and weight in df.columns:
        w = df[weight]
        importance_means = {}
        performance_means = {}
        for iv, pv in zip(importance_vars, performance_vars):
            valid_i = df[iv].notna() & w.notna()
            valid_p = df[pv].notna() & w.notna()
            importance_means[iv] = float((df.loc[valid_i, iv] * w[valid_i]).sum() / w[valid_i].sum()) if valid_i.any() else 0.0
            performance_means[pv] = float((df.loc[valid_p, pv] * w[valid_p]).sum() / w[valid_p].sum()) if valid_p.any() else 0.0
    else:
        importance_means = {v: float(df[v].mean()) for v in importance_vars}
        performance_means = {v: float(df[v].mean()) for v in performance_vars}

    if not QUANTIPYMRX_AVAILABLE:
        # Fallback: manual gap calculation
        items = []
        for iv, pv in zip(importance_vars, performance_vars):
            imp = importance_means[iv]
            perf = performance_means[pv]
            gap = imp - perf
            items.append({
                "item": iv,
                "importance_var": iv,
                "performance_var": pv,
                "importance": clean_numeric(imp),
                "performance": clean_numeric(perf),
                "gap": clean_numeric(gap),
                "priority": "High" if gap > 0.5 else ("Medium" if gap > 0 else "Low"),
            })
    else:
        from quantipymrx.analysis.mrx import gap_analysis
        results = gap_analysis(importance_means, performance_means)
        items = []
        for r in results:
            items.append({
                "item": r.item,
                "importance_var": r.item,
                "performance_var": performance_vars[importance_vars.index(r.item)] if r.item in importance_vars else r.item,
                "importance": clean_numeric(r.importance),
                "performance": clean_numeric(r.performance),
                "gap": clean_numeric(r.gap),
                "priority": r.priority,
            })

    # Add labels from metadata
    meta = data.meta
    if meta:
        labels = meta.column_names_to_labels if hasattr(meta, 'column_names_to_labels') else {}
        for item in items:
            item["importance_label"] = labels.get(item["importance_var"])
            item["performance_label"] = labels.get(item["performance_var"])

    # Determine quadrants
    avg_importance = sum(importance_means.values()) / len(importance_means) if importance_means else 0
    avg_performance = sum(performance_means.values()) / len(performance_means) if performance_means else 0
    for item in items:
        imp = item["importance"] or 0
        perf = item["performance"] or 0
        if imp >= avg_importance and perf < avg_performance:
            item["quadrant"] = "Concentrate Here"
        elif imp >= avg_importance and perf >= avg_performance:
            item["quadrant"] = "Keep Up the Good Work"
        elif imp < avg_importance and perf >= avg_performance:
            item["quadrant"] = "Possible Overkill"
        else:
            item["quadrant"] = "Low Priority"

    return {
        "items": items,
        "n_cases": len(df),
        "avg_importance": clean_numeric(avg_importance),
        "avg_performance": clean_numeric(avg_performance),
        "quadrant_thresholds": {
            "importance_midpoint": clean_numeric(avg_importance),
            "performance_midpoint": clean_numeric(avg_performance),
        },
    }


@router.post("/v1/gap-analysis", summary="Importance-Performance gap analysis",
             description="Analyze gaps between paired importance and performance variables. Returns gaps, priorities, and quadrant assignments.")
async def gap_analysis_endpoint(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    spec: str = Form(..., description='JSON: {"importance_vars": ["Q1_imp","Q2_imp"], "performance_vars": ["Q1_perf","Q2_perf"]}'),
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
        result = await run_in_executor(_run_gap_analysis, file_bytes, filename, spec_dict)
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
