"""POST /v1/anova — One-way ANOVA with optional Tukey HSD post-hoc."""

import asyncio
import json
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


def _run_anova(file_bytes: bytes, filename: str, spec: dict):
    """Run ANOVA (blocking, executed in thread pool)."""
    data = load_data(file_bytes, filename)
    df = data.df

    dependent = spec.get("dependent", "")
    factor = spec.get("factor", "")
    weight = spec.get("weight")
    post_hoc = spec.get("post_hoc", True)

    if not dependent or not factor:
        raise ValueError("Both 'dependent' and 'factor' are required")
    for v in [dependent, factor]:
        if v not in df.columns:
            raise ValueError(f"Variable '{v}' not found in dataset")

    if not QUANTIPYMRX_AVAILABLE or data.mrx_dataset is None:
        raise RuntimeError("QuantipyMRX required for ANOVA")

    from quantipymrx.analysis.significance import anova_from_dataset

    ds = data.mrx_dataset
    result = anova_from_dataset(ds, variable=dependent, group_var=factor, weight=weight, sig_level=0.05)

    # Convert result to dict
    response = {
        "dependent": dependent,
        "factor": factor,
        "f_statistic": clean_numeric(result.statistic),
        "p_value": clean_numeric(result.p_value),
        "significant": result.significant,
        "df_between": None,
        "df_within": None,
        "eta_squared": None,
        "group_means": {str(k): clean_numeric(v) for k, v in result.group_means.items()},
        "group_stds": {str(k): clean_numeric(v) for k, v in result.group_stds.items()},
        "group_ns": {str(k): v for k, v in result.group_ns.items()},
    }

    # Extract eta-squared from details if available
    if result.details:
        response["eta_squared"] = clean_numeric(result.details.get("eta_squared"))
        response["df_between"] = result.details.get("df_between")
        response["df_within"] = result.details.get("df_within")

    # Post-hoc Tukey HSD
    if post_hoc and result.post_hoc is not None and not result.post_hoc.empty:
        tukey_rows = []
        for _, row in result.post_hoc.iterrows():
            tukey_rows.append({
                "group1": str(row.get("group1", row.get("Group 1", ""))),
                "group2": str(row.get("group2", row.get("Group 2", ""))),
                "mean_diff": clean_numeric(row.get("meandiff", row.get("Mean Diff", 0))),
                "p_value": clean_numeric(row.get("p-adj", row.get("p_value", 0))),
                "significant": bool(row.get("reject", row.get("significant", False))),
            })
        response["post_hoc_tukey"] = tukey_rows
    else:
        response["post_hoc_tukey"] = []

    # Add value labels for groups
    meta = data.meta
    if meta is not None:
        vl = meta.variable_value_labels.get(factor, {})
        response["group_labels"] = {str(k): v for k, v in vl.items()} if vl else {}

    return response


@router.post("/v1/anova", summary="One-way ANOVA",
             description="Test if means of a numeric variable differ across groups, with optional Tukey HSD post-hoc comparisons.")
async def anova(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    spec: str = Form(..., description='JSON: {"dependent": "Q1", "factor": "age_group", "post_hoc": true}'),
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
        result = await run_in_executor(_run_anova, file_bytes, filename, spec_dict)
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
