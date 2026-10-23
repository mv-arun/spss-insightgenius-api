"""POST /v1/process — Main endpoint: upload .sav + optional ticket/operations → full analysis."""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from auth import require_scope, KeyConfig
from config import get_settings
from middleware.processing import run_in_executor
from middleware.rate_limiter import check_rate_limit
from shared.file_resolver import resolve_file
from shared.response import success_response
from services.quantipy_engine import QuantiProEngine, QUANTIPYMRX_AVAILABLE
from services.data_loader import load_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Processing"])


async def _execute_operation(data, op: dict, op_id: str) -> dict:
    """Execute a single analysis operation and return OperationResult."""
    op_type = op.get("type", "")
    variable = op.get("variable", "")
    params = op.get("params", {})
    weight = op.get("weight")

    try:
        if op_type == "frequency":
            result = await run_in_executor(QuantiProEngine.frequency, data, variable, weight)
        elif op_type == "crosstab":
            cross_var = op.get("cross_variable", "")
            sig = params.get("significance_level", 0.95)
            result = await run_in_executor(
                QuantiProEngine.crosstab_with_significance, data, variable, cross_var, weight, sig
            )
        elif op_type == "nps":
            result = await run_in_executor(QuantiProEngine.nps, data, variable, weight)
        elif op_type == "top_bottom_box":
            top_vals = params.get("top_values")
            bot_vals = params.get("bottom_values")
            result = await run_in_executor(QuantiProEngine.top_bottom_box, data, variable, top_vals, bot_vals)
        elif op_type == "nets":
            net_defs = params.get("net_definitions", {})
            result = await run_in_executor(QuantiProEngine.nets, data, variable, net_defs)
        else:
            return {"operation_id": op_id, "type": op_type, "variable": variable, "status": "error", "data": None, "error": f"Unknown operation type: {op_type}"}

        return {"operation_id": op_id, "type": op_type, "variable": variable, "status": "success", "data": result, "error": None}

    except (asyncio.TimeoutError, RuntimeError):
        raise  # handled by global exception handlers (504 / 503)
    except Exception as e:
        return {"operation_id": op_id, "type": op_type, "variable": variable, "status": "error", "data": None, "error": str(e)}


@router.post("/v1/process", summary="Full processing pipeline", description="Upload a .sav file with optional Reporting Ticket or manual operations spec. Returns metadata + all analysis results.")
async def process(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    operations: str | None = Form(None, description="JSON array of operation specs"),
    ticket: UploadFile | None = File(None, description="Reporting Ticket .docx (optional)"),
    weight: str | None = Form(None, description="Default weight variable"),
    key: KeyConfig = Depends(require_scope("process")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()

    file_bytes, filename = await resolve_file(file=file, file_id=file_id)

    # Load SPSS
    try:
        data = await run_in_executor(load_data, file_bytes, filename)
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except Exception as e:
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": f"Failed to load SPSS: {e}"})

    # Extract metadata
    metadata = await run_in_executor(QuantiProEngine.extract_metadata, data)

    # Determine operations
    ops_list = []
    ticket_plan = None

    # 1. If ticket provided, parse it via Haiku
    if ticket and ticket.filename:
        settings = get_settings()
        if settings.anthropic_api_key:
            try:
                from services.ticket_parser import TicketParser
                ticket_bytes = await ticket.read()
                parser = TicketParser()
                ticket_plan = await parser.parse(ticket_bytes, metadata.get("variables", []))
                ops_list = ticket_plan.get("operations", [])
                if not weight and ticket_plan.get("weight"):
                    weight = ticket_plan["weight"]
            except Exception as e:
                logger.warning("Ticket parsing failed: %s", e)
                ticket_plan = {"raw_text": "", "operations": [], "notes": [f"Parsing failed: {e}"]}

    # 2. If explicit operations provided, use them (override ticket)
    if operations:
        try:
            parsed_ops = json.loads(operations)
            if isinstance(parsed_ops, list):
                ops_list = parsed_ops
        except json.JSONDecodeError:
            raise HTTPException(400, detail={"code": "INVALID_OPERATIONS", "message": "Invalid JSON in 'operations' field"})

    # 3. If neither, use auto_planner for default operations
    if not ops_list:
        try:
            from services.auto_planner import AutoPlanner
            ops_list = AutoPlanner.plan(metadata)
        except ImportError:
            # Auto planner not yet implemented — return metadata only
            ops_list = []
        except Exception as e:
            logger.warning("Auto planner failed: %s", e)

    # Apply default weight to operations that don't specify one
    for op in ops_list:
        if isinstance(op, dict) and not op.get("weight") and weight:
            op["weight"] = weight

    # Execute all operations in parallel
    tasks = [
        _execute_operation(data, op, f"op_{i+1}")
        for i, op in enumerate(ops_list)
    ]
    results = await asyncio.gather(*tasks) if tasks else []

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return success_response(
        {
            "metadata": metadata,
            "results": list(results),
            "ticket_plan": ticket_plan,
        },
        processing_time_ms=elapsed_ms,
        meta={
            "engine_version": "1.0.0",
            "quantipymrx_available": QUANTIPYMRX_AVAILABLE,
        },
    )
