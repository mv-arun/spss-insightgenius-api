"""POST /v1/exports/data-workbook — respondent-level data sheets from the codebook (RECODING_PLAN.md R6)."""

import json
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from auth import require_scope, KeyConfig
from middleware.rate_limiter import check_rate_limit
from routers.codebook import CODEBOOK_HELP, _run
from shared.codebook_resolver import resolve_codebook
from shared.file_output import RESPONSE_FORMAT_HELP, check_response_format, file_response
from shared.file_resolver import resolve_file
from shared.filenames import output_filename
from services.codebook.infer import infer_codebook
from services.codebook.model import Codebook, DataWorkbook
from services.data_loader import SPSS_FORMATS, file_format, read_raw
from services.data_workbook import data_workbook_bytes

router = APIRouter(tags=["Export"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _export(file_bytes: bytes, filename: str, codebook: Codebook | None, settings: DataWorkbook | None):
    if file_format(filename) in SPSS_FORMATS:
        raise ValueError("Data sheets are built from Excel/CSV exports; an SPSS file already is respondent data")
    codebook = codebook or infer_codebook(read_raw(file_bytes, filename))
    return data_workbook_bytes(file_bytes, filename, codebook, settings)


@router.post(
    "/v1/exports/data-workbook", summary="Respondent data sheets (FULL DATA + category tabs)",
    description="An Excel workbook with every respondent's answers (FULL DATA) plus 1/blank flag columns and one "
                "sheet per reporting category, each with % and count rows (live formulas). What goes in comes "
                "from `settings`, else the codebook's `data_workbook` (set in the review page or by a setup, "
                "e.g. HubSpot CX), else just FULL DATA. Columns or tabs that don't fit the file are left out "
                "and listed in the `X-Warnings` header.",
    response_class=Response,
)
async def data_workbook_endpoint(
    request: Request,
    file: UploadFile = File(None, description="Data file: .csv, .tsv, .xlsx, .xls (or use file_id)"),
    file_id: str | None = Form(None, description="File session ID from /v1/files/upload"),
    codebook: str | None = Form(None, description=CODEBOOK_HELP),
    settings: str | None = Form(None, description="Data workbook settings JSON: {title, drop_columns, groups, score_flags, tabs}"),
    response_format: str = Form("file", description=RESPONSE_FORMAT_HELP),
    key: KeyConfig = Depends(require_scope("process")),
    _rl: None = Depends(check_rate_limit),
):
    start = time.perf_counter()
    response_format = check_response_format(response_format)
    try:
        chosen = DataWorkbook.model_validate(json.loads(settings)) if settings else None
    except (ValueError, ValidationError) as e:
        raise HTTPException(400, detail={"code": "INVALID_SETTINGS", "message": f"Invalid settings: {e}"})
    file_bytes, filename = await resolve_file(file=file, file_id=file_id)
    xlsx, warnings = await _run(_export, file_bytes, filename, await resolve_codebook(codebook, file_id), chosen)
    return await file_response(xlsx, output_filename("data", filename), XLSX_MIME, response_format, headers={
        "X-Warnings": json.dumps(warnings, ensure_ascii=True),
        "Access-Control-Expose-Headers": "X-Warnings",
    }, started=start)
