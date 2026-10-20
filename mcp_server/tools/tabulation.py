"""MCP tools: tabulation and auto-analyze."""

import base64
from typing import Any

from fastmcp.exceptions import ToolError

from middleware.processing import run_in_executor
from routers.downloads import store_download
from services.quantipy_engine import QuantiProEngine
from services.response_formatter import build_mcp_response
from services.tabulation_builder import TabulateSpec, build_tabulation

from mcp_server.auth import _auth_async
from mcp_server.file_session import _resolve_file, _load_data
from shared.filenames import output_filename


def _extract_tables_summary(sheets: list) -> list[dict[str, Any]]:
    """Extract a JSON-friendly summary from TabulationResult.sheets.

    Each entry: {stub, stub_label, base_total, top_finding}
    """
    summary = []
    for sheet in sheets:
        if sheet.status != "success":
            continue
        entry: dict[str, Any] = {
            "stub": sheet.variable,
            "stub_label": sheet.label or sheet.variable,
            "base_total": None,
            "top_finding": "",
        }
        ct = sheet.crosstab_data
        if ct and isinstance(ct, dict):
            entry["base_total"] = ct.get("total_responses", ct.get("base", None))
            # Extract top finding from the data
            rows = ct.get("rows", ct.get("table", []))
            if rows and isinstance(rows, list) and len(rows) > 0:
                # Find row with highest total percentage
                best_row = None
                best_pct = -1
                for row in rows:
                    total_cell = row.get("Total", row.get("total", {}))
                    if isinstance(total_cell, dict):
                        pct = total_cell.get("percentage", 0)
                    elif isinstance(total_cell, (int, float)):
                        pct = total_cell
                    else:
                        pct = 0
                    if pct > best_pct:
                        best_pct = pct
                        best_row = row
                if best_row:
                    label = best_row.get("row_label", best_row.get("label", ""))
                    entry["top_finding"] = (
                        f"Most common: '{label}' ({best_pct:.1f}%)"
                        if best_pct > 0 else ""
                    )
        elif sheet.is_mrs and sheet.mrs_members:
            entry["top_finding"] = f"MRS group with {len(sheet.mrs_members)} items"
        elif sheet.is_grid and sheet.grid_data:
            n_vars = len(sheet.grid_data.get("variables", []))
            entry["top_finding"] = f"Grid summary with {n_vars} variables"

        summary.append(entry)
    return summary


async def create_tabulation(
    api_key: str = "",
    banner: str = "",
    banners: list[str] | None = None,
    stubs: list[str] | None = None,
    significance_level: float = 0.95,
    significance_levels: list[float] | None = None,
    weight: str | None = None,
    title: str = "",
    include_means: bool = False,
    include_total_column: bool = True,
    output_mode: str = "multi_sheet",
    nets: dict | None = None,
    mrs_groups: dict | None = None,
    grid_groups: dict | None = None,
    custom_groups: list[dict] | None = None,
    file_base64: str | None = None,
    filename: str = "upload.sav",
    file_id: str | None = None,
    response_format: str = "json",
) -> dict[str, Any]:
    """Professional Excel tabulation with significance letters, nets, means, MRS groups, and Grid/Battery summaries. Publication-ready output matching the format used by market research agencies worldwide.

    Generates a professional .xlsx workbook:
    - Summary sheet: column legend (letter -> label) + stub index
    - One sheet per stub variable with column percentages + significance letters (A/B/C)
    - Column bases (N), Top/Bottom 2 Box nets, means with T-test significance
    - Download URL (5-min TTL) for easy sharing

    Authentication: If connected via OAuth (Claude.ai connector), no api_key needed. If using Claude Desktop or direct API, pass api_key (sk_test_... or sk_live_...).

    Requires a file_id from a previous spss_upload_file call, or pass file_base64 directly.

    Args:
        api_key:              Your API key (sk_test_... or sk_live_...). REQUIRED.
        banner:               Single banner variable (v1 compat).
        banners:              List of banner variables (v2, preferred).
        stubs:                List of stub variable names, or null for all.
        significance_level:   Confidence threshold (0.90, 0.95, 0.99).
        significance_levels:  Two levels, e.g. [0.95, 0.90]: CAPITAL letters at the first,
                              lowercase at the second (Decipher style). Overrides significance_level.
        weight:               Optional weight variable name.
        title:                Report title in the Summary sheet.
        include_means:        Add means row with T-test significance.
        include_total_column: Include Total as first column.
        output_mode:          'multi_sheet', 'single_sheet', or 'banner_sheets'.
        nets:                 Net definitions per stub.
        mrs_groups:           MRS group definitions.
        grid_groups:          Grid/battery summary definitions.
        custom_groups:        Custom break definitions.
        file_id:              File session ID from spss_upload_file.
        file_base64:          Base64-encoded file content.
        filename:             Original filename (default: upload.sav).
        response_format:      'json' or 'markdown'.
    """
    await _auth_async(api_key)
    file_bytes, fmt = await _resolve_file(file_id, file_base64, filename)
    try:
        data = await run_in_executor(_load_data, file_bytes, fmt, filename)
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Failed to load file: {e}")

    # Resolve banner(s)
    resolved_banners = banners or ([banner] if banner else [])
    if not resolved_banners:
        raise ToolError("At least one banner variable is required.")

    for b in resolved_banners:
        if b not in data.df.columns:
            available = list(data.df.columns[:20])
            raise ToolError(
                f"Banner variable '{b}' not found. "
                f"Available (first 20): {available}"
            )

    resolved_stubs = stubs if stubs else ["_all_"]
    if resolved_stubs != ["_all_"]:
        missing_stubs = [s for s in resolved_stubs if s not in data.df.columns]
        if missing_stubs:
            raise ToolError(f"Stub variables not found: {missing_stubs}")

    tab_spec = TabulateSpec(
        banners=resolved_banners,
        stubs=resolved_stubs,
        weight=weight,
        significance_level=significance_level,
        significance_levels=significance_levels,
        title=title,
        include_means=include_means,
        include_total_column=include_total_column,
        output_mode=output_mode,
        nets=nets or {},
        mrs_groups=mrs_groups or {},
        grid_groups=grid_groups or {},
        custom_groups=custom_groups,
    )
    try:
        result = await run_in_executor(build_tabulation, QuantiProEngine, data, tab_spec)
    except Exception as e:
        raise ToolError(f"Tabulation failed: {e}")

    # Extract tables_summary from sheets
    tables_summary = _extract_tables_summary(result.sheets)

    # Store for download
    dl_filename = output_filename("tables", filename)
    _, download_url = await store_download(result.excel_bytes, dl_filename)

    tab_results = {
        "banners": resolved_banners,
        "total_stubs": result.total_stubs,
        "stubs_success": result.successful,
        "stubs_failed": result.failed,
        "tables_summary": tables_summary,
        "title": title,
        "sample_size": len(data.df),
    }

    envelope = build_mcp_response(
        tool="spss_create_tabulation",
        results=tab_results,
        file_id=file_id,
        variables_analyzed=resolved_stubs[:20],
        sample_size=len(data.df),
        weighted=weight is not None,
        format_detected=fmt,
        response_format=response_format,
        download_url=download_url or None,
        download_expires=300,
        download_filename=dl_filename,
    )

    # Include base64 fallback if no download URL
    if not download_url:
        envelope["data_base64"] = base64.b64encode(result.excel_bytes).decode()
    envelope["filename"] = dl_filename

    return envelope


async def auto_analyze(
    api_key: str = "",
    max_banners: int = 3,
    output_mode: str = "multi_sheet",
    significance_level: float = 0.95,
    significance_levels: list[float] | None = None,
    include_means: bool = True,
    file_base64: str | None = None,
    filename: str = "upload.sav",
    file_id: str | None = None,
    response_format: str = "json",
) -> dict[str, Any]:
    """Zero-config complete analysis: upload a file, get a full Excel workbook with AI-detected banners, MRS groups, grids, nets, and significance-tested cross-tabulations. No configuration needed — the engine detects the optimal analysis structure automatically.

    Returns a download URL for the Excel file (valid 5 minutes) plus a structured summary with content_blocks for presentations.

    Authentication: If connected via OAuth (Claude.ai connector), no api_key needed. If using Claude Desktop or direct API, pass api_key (sk_test_... or sk_live_...).

    Requires a file_id from a previous spss_upload_file call, or pass file_base64 directly.

    Args:
        api_key:            Your API key (sk_test_... or sk_live_...). REQUIRED.
        max_banners:        Maximum number of banner variables to use (default 3).
        output_mode:        Output mode — "multi_sheet", "single_sheet", or "banner_sheets".
        significance_level: Confidence threshold (0.90, 0.95, 0.99). By default 90% is added as
                            a second level (lowercase letters).
        significance_levels: Explicit levels, e.g. [0.95] for a single level.
        include_means:      Include means with T-test (default True).
        file_id:            File session ID from spss_upload_file.
        file_base64:        Base64-encoded file content.
        filename:           Original filename (default: upload.sav).
        response_format:    'json' or 'markdown'.
    """
    await _auth_async(api_key)
    from routers.auto_analyze import _run_auto_analyze

    file_bytes, fmt = await _resolve_file(file_id, file_base64, filename)
    try:
        result = await run_in_executor(
            _run_auto_analyze, file_bytes, filename,
            {
                "max_banners": max_banners,
                "output_mode": output_mode,
                "significance_level": significance_level,
                "significance_levels": significance_levels,
                "include_means": include_means,
            },
        )
    except (ValueError, RuntimeError) as e:
        raise ToolError(str(e))
    except Exception as e:
        raise ToolError(f"Auto-analyze failed: {e}")

    # Store for download
    dl_filename = result.get("filename") or output_filename("analysis", filename)
    _, download_url = await store_download(result["excel_bytes"], dl_filename)

    summary = result["summary"]
    auto_results = {
        "banners": summary.get("banners", []),
        "banner_labels": summary.get("banner_labels", []),
        "total_stubs": summary.get("total_stubs", 0),
        "stubs_success": summary.get("stubs_success", 0),
        "stubs_failed": summary.get("stubs_failed", 0),
        "mrs_groups": summary.get("mrs_groups", 0),
        "grid_groups": summary.get("grid_groups", 0),
        "nets_applied": summary.get("nets_applied", 0),
        "title": f"Auto-Analysis: {filename}",
        "sample_size": 0,
    }

    envelope = build_mcp_response(
        tool="spss_auto_analyze",
        results=auto_results,
        file_id=file_id,
        format_detected=fmt,
        response_format=response_format,
        download_url=download_url or None,
        download_expires=300,
        download_filename=dl_filename,
    )

    # Include base64 fallback if no download URL
    if not download_url:
        envelope["data_base64"] = base64.b64encode(result["excel_bytes"]).decode()
    envelope["filename"] = dl_filename

    return envelope
