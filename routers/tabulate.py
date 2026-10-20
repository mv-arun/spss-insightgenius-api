"""POST /v1/tabulate — Full tabulation: all stubs × banner → Excel with sig letters.

The core endpoint for market research. Upload a .sav, specify a banner
(demographic) and stubs (questions), get back a professional Excel workbook
with crosstabs, significance letters, nets, and a summary sheet.
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from auth import KeyConfig, require_scope
from middleware.processing import run_in_executor
from middleware.rate_limiter import check_rate_limit
from shared.codebook_resolver import resolve_codebook
from shared.file_resolver import resolve_file
from services.quantipy_engine import QuantiProEngine
from services.data_loader import load_data
from services.tabulation_builder import TabulateSpec, build_tabulation, _build_excel
from shared.filenames import output_filename

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Processing"])

# Max file size per plan (bytes)
_MAX_FILE_SIZE = {
    "free": 5 * 1024 * 1024,
    "pro": 50 * 1024 * 1024,
    "business": 200 * 1024 * 1024,
}


@router.post(
    "/v1/tabulate",
    summary="Full tabulation → Excel",
    description=(
        "Upload a .sav file, specify a banner variable (demographic) and stub variables "
        "(questions to analyze), and receive a professional Excel workbook with:\n\n"
        "- One sheet per stub variable\n"
        "- Crosstab with column percentages\n"
        "- Significance letters (A/B/C notation)\n"
        "- Column bases (N)\n"
        "- Optional nets (Top 2 Box, Bottom 2 Box, etc.)\n"
        "- Summary sheet with column legend and stub index\n\n"
        "**Example spec:**\n```json\n{\n"
        '  "banner": "Q_4",\n'
        '  "stubs": ["Q_2", "Q_3", "Q_5"],\n'
        '  "significance_level": 0.95,\n'
        '  "weight": "WEIGHT1",\n'
        '  "nets": {"Q_2": {"Top 2 Box": [5, 6], "Bottom 2 Box": [1, 2]}},\n'
        '  "title": "Customer Satisfaction Study 2026"\n'
        "}\n```\n\n"
        "Set `stubs` to `[\"_all_\"]` to auto-select all variables with value labels.\n\n"
        "Optional: `significance_levels: [0.95, 0.90]` shows CAPITAL letters at 95% and lowercase "
        "at 90%; `low_base_warn` / `low_base_flag` (default 100 / 30, 0 = off) mark small bases "
        "with `*` / `**`."
    ),
    response_class=StreamingResponse,
)
async def tabulate(
    request: Request,
    file: UploadFile = File(None, description=".sav file to tabulate (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/library/upload"),
    codebook: str | None = Form(None, description="Codebook JSON from /v1/codebook (edited coding); default: inferred, or saved for file_id"),
    spec: str = Form(..., description="JSON tabulation specification"),
    ticket: UploadFile | None = File(None, description="Optional .docx Reporting Ticket — Haiku parses it into a tab plan"),
    webhook_url: str | None = Form(None, description="URL to POST job result when processing completes. If provided, returns 202 with job_id instead of blocking."),
    key: KeyConfig = Depends(require_scope("process")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()
    request_id = getattr(request.state, "request_id", "")

    file_bytes, filename = await resolve_file(file=file, file_id=file_id)
    cb = await resolve_codebook(codebook, file_id)

    # ── Check file size ──
    max_size = _MAX_FILE_SIZE.get(key.plan, _MAX_FILE_SIZE["free"])
    if len(file_bytes) > max_size:
        raise HTTPException(413, detail={
            "code": "FILE_TOO_LARGE",
            "message": f"File exceeds {max_size // (1024*1024)}MB limit for {key.plan} plan",
        })

    # ── Async mode: return 202 + job_id ──
    if webhook_url:
        from fastapi.responses import JSONResponse
        from shared.job_store import JobStore
        from services.job_runner import run_tabulation_job
        from routers.downloads import store_download

        store = JobStore()
        job_id = store.create(user_id=key.name, endpoint="/v1/tabulate", webhook_url=webhook_url)

        # Capture current args for background execution
        _file_bytes, _filename, _spec, _ticket_bytes = file_bytes, filename, spec, None
        if ticket and ticket.filename:
            _ticket_bytes = await ticket.read()

        async def _do_tabulate():
            data = await run_in_executor(load_data, _file_bytes, _filename, cb)
            spec_dict = json.loads(_spec)
            if cb is not None:
                spec_dict["nets"] = cb.table_nets(spec_dict.get("nets"))
            spec_obj = TabulateSpec(**spec_dict)
            result = await run_in_executor(build_tabulation, QuantiProEngine, data, spec_obj)
            excel_bytes = await run_in_executor(_build_excel, result, spec_obj, data)
            token, download_url = await store_download(excel_bytes, output_filename("tables", _filename))
            return excel_bytes, download_url

        asyncio.create_task(run_tabulation_job(job_id, _do_tabulate))
        return JSONResponse(status_code=202, content={
            "success": True,
            "data": {
                "job_id": job_id,
                "status": "pending",
                "poll_url": f"/v1/jobs/{job_id}",
                "webhook_url": webhook_url,
                "message": "Processing started. Poll the job URL or wait for webhook callback.",
            },
        })

    # ── Parse spec ──
    try:
        spec_dict = json.loads(spec)
    except json.JSONDecodeError as e:
        raise HTTPException(400, detail={"code": "INVALID_SPEC", "message": f"Invalid JSON in spec: {e}"})

    # ── Ticket parsing (Haiku) — overrides spec with extracted tab plan ──
    if ticket and ticket.filename and ticket.filename.lower().endswith(".docx"):
        try:
            from services.ticket_parser import TicketParser
            ticket_bytes = await ticket.read()
            parser = TicketParser()

            # Load SPSS first for variable list context
            data_for_vars = await run_in_executor(
                load_data, file_bytes, filename, cb
            )
            var_info = [
                {"name": c, "label": "", "type": str(data_for_vars.df[c].dtype)}
                for c in data_for_vars.df.columns
            ]
            ticket_plan = await parser.parse(ticket_bytes, available_variables=var_info)

            # Extract banner and stubs from ticket plan
            if ticket_plan.get("operations"):
                # Find cross_variables used (those are banners)
                cross_vars = set()
                stub_vars = []
                for op in ticket_plan["operations"]:
                    if op.get("cross_variable"):
                        cross_vars.add(op["cross_variable"])
                    if op.get("variable"):
                        stub_vars.append(op["variable"])

                if cross_vars and not spec_dict.get("banners") and not spec_dict.get("banner"):
                    spec_dict["banners"] = list(cross_vars)
                if stub_vars and spec_dict.get("stubs", ["_all_"]) == ["_all_"]:
                    spec_dict["stubs"] = stub_vars
                if ticket_plan.get("weight") and not spec_dict.get("weight"):
                    spec_dict["weight"] = ticket_plan["weight"]

            logger.info("[TICKET] Parsed ticket: %d operations, banners=%s", len(ticket_plan.get("operations", [])), spec_dict.get("banners"))
        except ValueError as e:
            logger.warning("Ticket parsing skipped (no API key?): %s", e)
        except Exception as e:
            logger.warning("Ticket parsing failed, continuing with manual spec: %s", e)

    banner = spec_dict.get("banner", "")
    banners = spec_dict.get("banners")
    custom_groups = spec_dict.get("custom_groups")
    # Allow Total-only export (no banners) — include_total_column will provide the Total column

    try:
        tab_spec = TabulateSpec(
            banner=banner,
            banners=banners,
            custom_groups=spec_dict.get("custom_groups"),
            stubs=spec_dict.get("stubs", ["_all_"]),
            weight=spec_dict.get("weight"),
            significance_level=spec_dict.get("significance_level", 0.95),
            significance_levels=spec_dict.get("significance_levels"),
            bonferroni=bool(spec_dict.get("bonferroni", True)),
            low_base_warn=int(spec_dict.get("low_base_warn", 100)),
            low_base_flag=int(spec_dict.get("low_base_flag", 30)),
            nets=cb.table_nets(spec_dict.get("nets")) if cb is not None else spec_dict.get("nets"),
            mrs_groups=spec_dict.get("mrs_groups"),
            grid_groups=spec_dict.get("grid_groups"),
            grid_mode=spec_dict.get("grid_mode", "individual"),
            include_means=spec_dict.get("include_means", False),
            include_total_column=spec_dict.get("include_total_column", True),
            output_mode=spec_dict.get("output_mode", "multi_sheet"),
            custom_groups_label=spec_dict.get("custom_groups_label") or "Custom Groups",
            sort_rows=bool(spec_dict.get("sort_rows", False)),
            table_order=spec_dict.get("table_order"),
            table_titles=spec_dict.get("table_titles"),
            show_counts=spec_dict.get("show_counts", True),
            show_percentages=spec_dict.get("show_percentages", True),
            show_chi2=spec_dict.get("show_chi2", True),
            include_summary=spec_dict.get("include_summary", False),
            study_context=spec_dict.get("study_context"),
            filters=spec_dict.get("filters"),
            title=spec_dict.get("title", ""),
        )
    except ValueError as e:
        raise HTTPException(400, detail={"code": "VALIDATION_ERROR", "message": str(e)})

    # ── Load SPSS ──
    try:
        data = await run_in_executor(
            load_data, file_bytes, filename, cb
        )
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except Exception as e:
        raise HTTPException(400, detail={"code": "INVALID_FILE_FORMAT", "message": f"Failed to load SPSS file: {e}"})

    # Validate banners exist
    for b in tab_spec.resolved_banners:
        if b not in data.df.columns:
            raise HTTPException(400, detail={
                "code": "VARIABLE_NOT_FOUND",
                "message": f"Banner variable '{b}' not found. Available: {list(data.df.columns[:20])}...",
            })

    # Validate stubs exist (if explicitly specified)
    if tab_spec.stubs != ["_all_"]:
        missing = [s for s in tab_spec.stubs if s not in data.df.columns]
        if missing:
            raise HTTPException(400, detail={
                "code": "VARIABLE_NOT_FOUND",
                "message": f"Stub variables not found: {missing}",
            })

    # Validate MRS members exist
    for group_name, members in (tab_spec.mrs_groups or {}).items():
        missing = [m for m in members if m not in data.df.columns]
        if missing:
            raise HTTPException(400, detail={
                "code": "VARIABLE_NOT_FOUND",
                "message": f"MRS group '{group_name}' members not found: {missing}",
            })

    # ── Run tabulation ──
    try:
        result = await run_in_executor(
            build_tabulation, QuantiProEngine, data, tab_spec,
        )
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except Exception as e:
        logger.error("Tabulation failed [%s]: %s", request_id, e, exc_info=True)
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": str(e)})

    # ── Executive Summary (Story #4) ──
    logger.info("[TABULATE] include_summary=%s successful=%d", tab_spec.include_summary, result.successful)
    if tab_spec.include_summary and result.successful > 0:
        try:
            from services.executive_summary import generate_executive_summary
            # Build condensed results for the summary
            summary_results = []
            for s in result.sheets:
                if s.status != "success":
                    continue
                entry = {"variable": s.variable, "label": s.label, "status": s.status}
                # Extract significant cells from first banner's crosstab
                first_ct = list((s.crosstab_data or {}).values())[0] if s.crosstab_data else {}
                sig_cells = []
                for row in first_ct.get("table", []):
                    for k, v in row.items():
                        if isinstance(v, dict) and v.get("significance_letters"):
                            sig_cells.append(f"{row.get('row_label','?')}:{k} {v['percentage']}% ({','.join(v['significance_letters'])})")
                entry["significant_cells"] = sig_cells[:5]
                summary_results.append(entry)

            banner_labels = list(set(b.banner_label for b in result.banner_columns if b.banner_label))
            summary_text = await generate_executive_summary(
                tabulation_results=summary_results,
                banner_labels=banner_labels,
                study_context=tab_spec.study_context,
                file_name=data.file_name,
                n_cases=len(data.df),
            )
            result.executive_summary = summary_text
            # Rebuild Excel with summary sheet
            result.excel_bytes = _build_excel(result, tab_spec, data)
            logger.info("[TABULATE] Executive summary generated (%d chars)", len(summary_text))
        except Exception as e:
            logger.warning("[TABULATE] Executive summary failed: %s", e)

    elapsed = int((time.perf_counter() - start) * 1000)
    banners_str = "+".join(tab_spec.resolved_banners)
    logger.info(
        "[TABULATE] key=%s banners=%s stubs=%d success=%d failed=%d time_ms=%d",
        key.name, banners_str, result.total_stubs, result.successful, result.failed, elapsed,
    )

    # ── Return Excel ──
    import io
    file_name = output_filename("tables", data.file_name)

    return StreamingResponse(
        io.BytesIO(result.excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "X-Request-Id": request_id,
            "X-Processing-Time-Ms": str(elapsed),
            "X-Stubs-Total": str(result.total_stubs),
            "X-Stubs-Success": str(result.successful),
            "X-Stubs-Failed": str(result.failed),
        },
    )
