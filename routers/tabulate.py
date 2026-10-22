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
from services.data_cache import load_data_cached
from services.banner_workbook import preview_tables
from services.tabulation_builder import TabulateSpec, build_tabulation, _build_excel, multiple_comparison_correction
from shared.filenames import output_filename
from shared.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Processing"])

# Max file size per plan (bytes)
_MAX_FILE_SIZE = {
    "free": 5 * 1024 * 1024,
    "pro": 50 * 1024 * 1024,
    "business": 200 * 1024 * 1024,
}


def _tab_spec(spec_dict: dict, cb) -> TabulateSpec:
    """The request's spec as a TabulateSpec (nets saved in the codebook added). 400 if invalid."""
    try:
        spec = TabulateSpec(
            banner=spec_dict.get("banner", ""),
            banners=spec_dict.get("banners"),  # none: a Total-only export
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
            sort_rows=_sort_rows(spec_dict.get("sort_rows", False)),
            hide_codes=_hide_codes(spec_dict.get("hide_codes")),
            show_row_pct=bool(spec_dict.get("show_row_pct", False)),
            table_specs=_table_specs(spec_dict.get("table_specs")),
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
    except (ValueError, TypeError) as e:
        raise HTTPException(400, detail={"code": "VALIDATION_ERROR", "message": str(e)})
    if spec.table_specs and spec.stubs == ["_all_"]:
        raise HTTPException(400, detail={"code": "VALIDATION_ERROR",
                                         "message": "With table_specs, name the tables in 'stubs' (and the groups), not [\"_all_\"]"})
    return spec


def _sort_rows(value) -> bool | str:
    """sort_rows: false / true (= "total") / "total" / "az"."""
    if value in (False, None, "", "none", "survey"):
        return False
    if value is True or value == "total":
        return "total"
    if value == "az":
        return "az"
    raise ValueError("sort_rows must be false, true, \"total\" or \"az\"")


def _hide_codes(value) -> dict | None:
    """hide_codes: {"Q1": [98, 99], "Brand awareness": ["AWARE_X"]} — answers / columns left out of the tables."""
    if not value:
        return None
    if not isinstance(value, dict) or not all(isinstance(v, list) for v in value.values()):
        raise ValueError("hide_codes must map a variable or group name to a list of codes")
    return value


def _table_specs(value) -> list | None:
    """table_specs: [{"table": "Q1", "banners": [...], "filters": [...], "custom_groups": bool}, …]."""
    if not value:
        return None
    if not isinstance(value, list) or not all(isinstance(t, dict) and isinstance(t.get("table"), str) for t in value):
        raise ValueError("table_specs must be a list of {\"table\": name, \"banners\": [...], \"filters\": [...]}")
    for t in value:
        if t.get("banners") is not None and not (isinstance(t["banners"], list) and all(isinstance(b, str) for b in t["banners"])):
            raise ValueError(f"table_specs[{t['table']}].banners must be a list of variable names")
        if t.get("filters") is not None and not isinstance(t["filters"], list):
            raise ValueError(f"table_specs[{t['table']}].filters must be a list of conditions")
    return value


async def _load(file_bytes: bytes, filename: str, cb):
    """Parse the file (once per worker: services.data_cache). 400 if it can't be read."""
    try:
        return await run_in_executor(load_data_cached, file_bytes, filename, cb)
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except Exception as e:
        raise HTTPException(400, detail={"code": "INVALID_FILE_FORMAT", "message": f"Failed to load SPSS file: {e}"})


def _check_variables(tab_spec: TabulateSpec, data) -> None:
    """Every banner, stub and multi-select member the spec names must be in the file."""
    table_banners = [b for t in tab_spec.table_specs or [] for b in (t.get("banners") or [])]
    for b in list(dict.fromkeys(tab_spec.resolved_banners + table_banners)):
        if b not in data.df.columns:
            raise HTTPException(400, detail={
                "code": "VARIABLE_NOT_FOUND",
                "message": f"Banner variable '{b}' not found. Available: {list(data.df.columns[:20])}...",
            })
    if tab_spec.stubs != ["_all_"]:
        missing = [s for s in tab_spec.stubs if s not in data.df.columns]
        if missing:
            raise HTTPException(400, detail={
                "code": "VARIABLE_NOT_FOUND",
                "message": f"Stub variables not found: {missing}",
            })
    for group_name, members in (tab_spec.mrs_groups or {}).items():
        missing = [m for m in members if m not in data.df.columns]
        if missing:
            raise HTTPException(400, detail={
                "code": "VARIABLE_NOT_FOUND",
                "message": f"MRS group '{group_name}' members not found: {missing}",
            })


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
        "with `*` / `**`.\n\n"
        "Per-table columns: `table_specs: [{\"table\": \"Q1\", \"banners\": [\"Gender\"], \"filters\": [...], "
        "\"custom_groups\": false}]` (name the tables in `stubs` / the groups). Tables not listed use "
        "`banners` / `filters` / `custom_groups`; each table is written with its own columns."
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
            data = await run_in_executor(load_data_cached, _file_bytes, _filename, cb)
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
            data_for_vars = await run_in_executor(load_data_cached, file_bytes, filename, cb)
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

    tab_spec = _tab_spec(spec_dict, cb)

    # ── Load SPSS ──
    data = await _load(file_bytes, filename, cb)
    _check_variables(tab_spec, data)

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


MAX_PREVIEW_TABLES = 50  # a preview draws what's on screen; the export does the rest


@router.post(
    "/v1/tabulate/preview",
    summary="Tabulation preview (JSON)",
    description=(
        "The tables `/v1/tabulate` would write, as JSON, for a live preview while the tables are built. "
        "Same inputs as `/v1/tabulate` (file or `file_id`, optional `codebook`, `spec`), and the same "
        "calculation: rows (answers or the nets that merge them, nets, NET), bases, column percentages "
        "and significance letters as on the banner workbook's Stat sheets "
        "(each banner tested on its own; columns lettered A, B, … within it).\n\n"
        "Add `\"tables\": [\"Q1\", \"Brand awareness\"]` to the spec to compute only those tables "
        f"(stub variables or multi-select / grid group names; at most {MAX_PREVIEW_TABLES}).\n\n"
        "Percentages are fractions (0.42 = 42%); `sig` is `-` where nothing is tested "
        "(the Total column, NET rows, a column with no base). With `table_specs` (each table its own "
        "columns and filters) every table carries its own `banners`."
    ),
)
async def tabulate_preview(
    file: UploadFile = File(None, description="Data file (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    codebook: str | None = Form(None, description="Codebook JSON from /v1/codebook (edited coding)"),
    spec: str = Form(..., description="JSON tabulation specification, as for /v1/tabulate, plus optional `tables`"),
    key: KeyConfig = Depends(require_scope("process")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()
    file_bytes, filename = await resolve_file(file=file, file_id=file_id)
    cb = await resolve_codebook(codebook, file_id)
    max_size = _MAX_FILE_SIZE.get(key.plan, _MAX_FILE_SIZE["free"])
    if len(file_bytes) > max_size:
        raise HTTPException(413, detail={
            "code": "FILE_TOO_LARGE",
            "message": f"File exceeds {max_size // (1024*1024)}MB limit for {key.plan} plan",
        })

    try:
        spec_dict = json.loads(spec)
    except json.JSONDecodeError as e:
        raise HTTPException(400, detail={"code": "INVALID_SPEC", "message": f"Invalid JSON in spec: {e}"})
    if not isinstance(spec_dict, dict):
        raise HTTPException(400, detail={"code": "INVALID_SPEC", "message": "spec must be a JSON object"})

    # Only the tables asked for: stubs, and the multi-select / grid groups named in `tables`
    tables = spec_dict.pop("tables", None)
    if tables is not None:
        if not isinstance(tables, list) or not all(isinstance(t, str) for t in tables):
            raise HTTPException(400, detail={"code": "VALIDATION_ERROR", "message": "'tables' must be a list of table names"})
        if len(tables) > MAX_PREVIEW_TABLES:
            raise HTTPException(400, detail={"code": "VALIDATION_ERROR",
                                             "message": f"A preview shows at most {MAX_PREVIEW_TABLES} tables; ask for fewer"})
        groups = set(spec_dict.get("mrs_groups") or {}) | set(spec_dict.get("grid_groups") or {})
        spec_dict["stubs"] = [t for t in tables if t not in groups]
        for k in ("mrs_groups", "grid_groups"):
            if spec_dict.get(k):
                spec_dict[k] = {name: members for name, members in spec_dict[k].items() if name in tables}
        if isinstance(spec_dict.get("table_specs"), list):
            spec_dict["table_specs"] = [t for t in spec_dict["table_specs"] if isinstance(t, dict) and t.get("table") in tables]
    elif spec_dict.get("stubs", ["_all_"]) == ["_all_"]:
        raise HTTPException(400, detail={"code": "VALIDATION_ERROR",
                                         "message": "Name the tables to preview: 'tables' (or 'stubs') in the spec"})

    tab_spec = _tab_spec(spec_dict, cb)
    data = await _load(file_bytes, filename, cb)
    _check_variables(tab_spec, data)

    def compute():
        result = build_tabulation(QuantiProEngine, data, tab_spec, build_excel=False)
        with multiple_comparison_correction(tab_spec.bonferroni):
            return preview_tables(result, tab_spec, data)

    try:
        body = await run_in_executor(compute)
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except Exception as e:
        logger.error("Tabulation preview failed: %s", e, exc_info=True)
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": str(e)})

    elapsed = int((time.perf_counter() - start) * 1000)
    return success_response(body, processing_time_ms=elapsed)
