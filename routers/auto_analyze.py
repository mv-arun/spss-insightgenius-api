"""POST /v1/auto-analyze — Zero-config SPSS analysis. Upload a .sav, get a complete Excel back."""

import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from auth import require_scope, KeyConfig
from middleware.processing import run_in_executor
from middleware.rate_limiter import check_rate_limit
from shared.codebook_resolver import resolve_codebook
from shared.file_resolver import resolve_file
from services.quantipy_engine import QuantiProEngine, QUANTIPYMRX_AVAILABLE
from shared.file_output import RESPONSE_FORMAT_HELP, check_response_format, file_response
from services.data_loader import SPSS_FORMATS, file_format, load_data
from services.data_workbook import append_data_workbook
from services.tabulation_builder import TabulateSpec, build_tabulation
from shared.filenames import output_filename

router = APIRouter(tags=["Processing"])


def _run_auto_analyze(file_bytes: bytes, filename: str, options: dict):
    """Zero-config analysis pipeline:
    1. Load SPSS → extract metadata with auto-detect
    2. Pick best banner(s) from suggested_banners
    3. Detect groups (MRS, Grid, Top-of-Mind) → exclude members from individual stubs
    4. Remaining ungrouped variables → individual stubs
    5. Auto-detect nets (T2B/B2B for Likert scales)
    6. Build tabulation → return Excel bytes

    Key insight: variables that belong to a detected group (MRS, Grid, Top-of-Mind)
    are NOT exported as individual crosstabs. They're exported as their group type
    (MRS sheet or Grid summary). Only ungrouped variables get individual sheets.
    """
    # Step 1: Load and extract metadata
    data = load_data(file_bytes, filename, options.get("_codebook"))
    meta = QuantiProEngine.extract_metadata(data)

    # Step 2: Pick banners — ticket overrides auto-detect
    ticket_banners = options.get("ticket_banners")
    if ticket_banners:
        # Validate ticket banners exist in the dataset
        valid_cols = set(data.df.columns)
        banners = [b for b in ticket_banners if b in valid_cols]
        if not banners:
            logger.warning("[AUTO] Ticket banners %s not found in dataset, falling back to auto-detect", ticket_banners)
    else:
        banners = []

    if not banners:
        suggested = meta.get("suggested_banners") or []
        max_banners = options.get("max_banners", 3)
        if suggested:
            banners = [b["variable"] for b in suggested[:max_banners]]
        else:
            for v in meta.get("variables", []):
                vl = v.get("value_labels")
                if vl and 2 <= len(vl) <= 8 and v["name"] not in banners:
                    banners.append(v["name"])
                    if len(banners) >= max_banners:
                        break

    if not banners:
        raise ValueError("No suitable banner variables found in the dataset")

    banner_set = set(banners)

    # Step 3: Detect groups and collect grouped variables
    mrs_groups = {}
    grid_groups = {}
    grouped_vars = set()  # Track ALL variables that belong to a group

    detected_groups = meta.get("detected_groups") or []
    for g in detected_groups:
        q_type = g.get("question_type", "")
        members = g.get("variables") or []
        if len(members) < 2:
            continue

        name = g.get("display_name") or g.get("name", f"Group_{len(grouped_vars)}")

        if q_type in ("awareness", "top_of_mind"):
            # MRS: "select all that apply" — one sheet, members as rows, % can exceed 100%
            mrs_groups[name] = members
            grouped_vars.update(members)
        elif q_type == "scale":
            # Grid: same scale across variables — compact T2B/Mean summary
            grid_groups[name] = {"variables": members, "show": ["t2b", "b2b", "mean"]}
            grouped_vars.update(members)

    # A single option of a multi-select set is a poor banner, and tabulating the set
    # against one of its own members fails — drop auto-picked banners that are grouped.
    if not ticket_banners and banner_set & grouped_vars:
        banners = [b for b in banners if b not in grouped_vars]
        if not banners:
            for v in meta.get("variables", []):
                vl = v.get("value_labels")
                if vl and 2 <= len(vl) <= 8 and v["name"] not in grouped_vars:
                    banners.append(v["name"])
                    if len(banners) >= options.get("max_banners", 3):
                        break
        if not banners:
            raise ValueError("No suitable banner variables found in the dataset")
        banner_set = set(banners)

    # Step 4: Build stubs — ticket overrides auto-detect
    ticket_stubs = options.get("ticket_stubs")
    if ticket_stubs:
        valid_cols = set(data.df.columns)
        stubs = [s for s in ticket_stubs if s in valid_cols and s not in banner_set]
    else:
        # Only UNGROUPED variables with value labels
        stubs = []
        for v in meta.get("variables") or []:
            vname = v["name"]
            vl = v.get("value_labels")
            if not vl or len(vl) < 2:
                continue
            if vname in grouped_vars:
                continue  # Skip — this variable is in an MRS or Grid group
            if vname in banner_set:
                continue  # Skip — this is a banner variable
            stubs.append(vname)

    if not stubs and not mrs_groups and not grid_groups:
        stubs = ["_all_"]  # Fallback: export everything if nothing detected

    # Step 5: Nets — ticket overrides auto-detect
    ticket_nets = options.get("ticket_nets")
    if ticket_nets and isinstance(ticket_nets, dict):
        nets = ticket_nets
    else:
        all_nets = meta.get("preset_nets") or {}
        if options.get("_codebook") is not None:  # nets set in the codebook replace the guessed ones
            all_nets = {**all_nets, **options["_codebook"].table_nets()}
        nets = {k: v for k, v in all_nets.items() if k in set(stubs)}

    # Step 6: Build spec
    # Decipher-style default: CAPITAL letters at the main level (95%), lowercase at 90%
    levels = options.get("significance_levels")
    if not levels:
        primary = float(options.get("significance_level", 0.95))
        levels = [primary, 0.90] if primary > 0.90 else [primary]

    spec = TabulateSpec(
        banners=banners,
        stubs=stubs if stubs else ["_all_"],
        significance_levels=levels,
        include_means=True,
        include_total_column=True,
        output_mode=options.get("output_mode", "multi_sheet"),
        title=options.get("title", f"Auto-Analysis: {filename}"),
        nets=nets or {},
        mrs_groups=mrs_groups or {},
        grid_groups=grid_groups or {},
    )

    logger.info(
        "[AUTO] banners=%s stubs=%d mrs=%d(%d vars) grids=%d(%d vars) nets=%d grouped_excluded=%d",
        banners, len(stubs), len(mrs_groups), sum(len(v) for v in mrs_groups.values()),
        len(grid_groups), sum(len(g["variables"]) for g in grid_groups.values()),
        len(nets), len(grouped_vars),
    )

    # Step 7: Build tabulation
    result = build_tabulation(QuantiProEngine, data, spec)

    # Build sheet summaries for executive summary
    sheet_summaries = []
    for s in result.sheets:
        if s.status != "success":
            continue
        entry = {"variable": s.variable, "label": s.label, "status": s.status}
        first_ct = list((s.crosstab_data or {}).values())[0] if s.crosstab_data else {}
        sig_cells = []
        for row in first_ct.get("table", []):
            for k, v in row.items():
                if isinstance(v, dict) and v.get("significance_letters"):
                    sig_cells.append(f"{row.get('row_label','?')}:{k} {v['percentage']}% ({','.join(v['significance_letters'])})")
        entry["significant_cells"] = sig_cells[:5]
        sheet_summaries.append(entry)

    return {
        "excel_bytes": result.excel_bytes,
        "filename": output_filename("analysis", filename),
        "_tabulation_result": result,
        "_spec": spec,
        "_data": data,
        "sheet_summaries": sheet_summaries,
        "summary": {
            "banners": banners,
            "banner_labels": [
                next((v.get("label", v["name"]) for v in meta["variables"] if v["name"] == b), b)
                for b in banners
            ],
            "total_stubs": result.total_stubs,
            "stubs_success": result.successful,
            "stubs_failed": result.failed,
            "mrs_groups": len(mrs_groups),
            "grid_groups": len(grid_groups),
            "nets_applied": len(nets),
            "n_cases": meta.get("n_cases", 0),
            "processing_time_ms": 0,
        },
    }


@router.post("/v1/auto-analyze", summary="Zero-config auto analysis",
             description="Upload a .sav file and get a complete Excel workbook with auto-detected banners, "
                         "stubs, nets, MRS groups, and significance testing. No configuration needed.")
async def auto_analyze(
    request: Request,
    file: UploadFile = File(None, description="Data file: .sav, .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    codebook: str | None = Form(None, description="Codebook JSON from /v1/codebook (edited coding); default: inferred, or saved for file_id"),
    ticket: UploadFile = File(None, description="Reporting Ticket .docx — AI parses it to override auto-detection"),
    options: str = Form("{}", description='Optional JSON: {"max_banners": 3, "output_mode": "multi_sheet", "significance_level": 0.95, '
                                         '"significance_levels": [0.95, 0.90]}. Default: CAPITAL letters at 95%, lowercase at 90%'),
    response_format: str = Form("file", description=RESPONSE_FORMAT_HELP),
    key: KeyConfig = Depends(require_scope("process")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()
    response_format = check_response_format(response_format)

    file_bytes, filename = await resolve_file(file=file, file_id=file_id)
    cb = await resolve_codebook(codebook, file_id)

    try:
        options_dict = json.loads(options)
    except json.JSONDecodeError as e:
        raise HTTPException(400, detail={"code": "INVALID_SPEC", "message": f"Invalid JSON in options: {e}"})
    if not isinstance(options_dict, dict):
        raise HTTPException(400, detail={"code": "INVALID_SPEC", "message": "options must be a JSON object"})

    # Parse Reporting Ticket if provided — override auto-detection with ticket spec
    if ticket and ticket.filename and ticket.filename.endswith('.docx'):
        try:
            ticket_bytes = await ticket.read()
            from services.ticket_parser import TicketParser
            parser = TicketParser()
            # Get variable list for fuzzy matching
            data_tmp = await run_in_executor(load_data, file_bytes, filename, cb)
            meta_tmp = await run_in_executor(QuantiProEngine.extract_metadata, data_tmp)
            var_list = [v["name"] for v in (meta_tmp.get("variables") or [])]
            ticket_spec = await parser.parse(ticket_bytes, var_list)
            logger.info("[AUTO] Ticket parsed: banners=%s stubs=%s sig=%s",
                        ticket_spec.get("banners"), ticket_spec.get("stubs"), ticket_spec.get("sig_level"))
            # Merge ticket spec into options
            if ticket_spec.get("banners"):
                options_dict["ticket_banners"] = ticket_spec["banners"]
            if ticket_spec.get("stubs"):
                options_dict["ticket_stubs"] = ticket_spec["stubs"]
            if ticket_spec.get("sig_level"):
                options_dict["significance_level"] = ticket_spec["sig_level"]
            if ticket_spec.get("nets"):
                options_dict["ticket_nets"] = ticket_spec["nets"]
            if ticket_spec.get("additional_cuts"):
                options_dict["ticket_additional_cuts"] = ticket_spec["additional_cuts"]
        except Exception as e:
            logger.warning("[AUTO] Ticket parsing failed (continuing with auto-detect): %s", e)

    try:
        options_dict["_codebook"] = cb
        result = await run_in_executor(_run_auto_analyze, file_bytes, filename, options_dict)
    except (asyncio.TimeoutError, RuntimeError):
        raise
    except ValueError as e:
        raise HTTPException(400, detail={"code": "PROCESSING_FAILED", "message": str(e)})
    except Exception as e:
        import traceback
        logger.error("Auto-analyze failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, detail={"code": "PROCESSING_FAILED", "message": str(e)})

    elapsed = int((time.perf_counter() - start) * 1000)
    summary = result["summary"]
    excel_bytes = result["excel_bytes"]

    # Executive Summary (#5) — add AI summary as first sheet if requested
    include_summary = options_dict.get("include_summary", True)  # Default ON for auto-analyze
    if include_summary:
        try:
            from services.executive_summary import generate_executive_summary
            summary_text = await generate_executive_summary(
                tabulation_results=result.get("sheet_summaries", []),
                banner_labels=summary.get("banner_labels", []),
                study_context=options_dict.get("study_context"),
                file_name=result["filename"],
                n_cases=summary.get("n_cases", 0),
            )
            if summary_text:
                # Rebuild Excel with summary sheet prepended
                from services.tabulation_builder import _build_excel
                tab_result = result.get("_tabulation_result")
                if tab_result:
                    tab_result.executive_summary = summary_text
                    excel_bytes = _build_excel(tab_result, result.get("_spec"), result.get("_data"))
                    logger.info("[AUTO] Executive summary added (%d chars)", len(summary_text))
        except Exception as e:
            logger.warning("[AUTO] Executive summary failed (non-blocking): %s", e)

    # Respondent data sheets (FULL DATA + category tabs) when the codebook asks for them (e.g. a setup)
    if (cb is not None and cb.data_workbook is not None and file_format(filename) not in SPSS_FORMATS
            and options_dict.get("include_data_workbook", True)):
        try:
            excel_bytes = await run_in_executor(append_data_workbook, excel_bytes, file_bytes, filename, cb)
        except Exception as e:
            logger.warning("[AUTO] Data workbook failed (non-blocking): %s", e)

    return await file_response(
        excel_bytes, result["filename"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        response_format,
        headers={
            "X-Processing-Time-Ms": str(elapsed),
            "X-Stubs-Total": str(summary["total_stubs"]),
            "X-Stubs-Success": str(summary["stubs_success"]),
            "X-Stubs-Failed": str(summary["stubs_failed"]),
            "X-Banners": ",".join(summary["banners"]),
            "X-MRS-Groups": str(summary["mrs_groups"]),
            "X-Grid-Groups": str(summary["grid_groups"]),
            "X-Nets-Applied": str(summary["nets_applied"]),
        },
    )
