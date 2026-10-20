"""Format-agnostic data loading: .sav / .csv / .tsv / .xlsx / .xls → SPSSData.

Tabular formats (Excel, CSV) carry no SPSS metadata, so they go through the
codebook pipeline (PLAN_ANY_FORMAT.md §3):

    read_raw()        ① raw respondent table           services.ingest.readers
    infer_codebook()  ③ decide how to code each column  services.codebook.infer
    apply_codebook()  ⑤ code it, deterministically      services.codebook.apply

…then the coded data is written to an in-memory .sav and loaded through the regular
QuantiProEngine.load_spss path, so the rest of the system sees exactly the same
shape as for a native SPSS file. Pass a `codebook` to skip inference.

What inference does (details in services.codebook.heuristics):
  - Text columns with few distinct values → numeric codes + value labels, in scale
    order for known rating scales or numeric prefixes ("10 - Extremely likely");
    "Don't know" / "Not applicable" on scales → user-missing codes 96-99
  - Delimited answers ("A; B") → one 0/1 variable per option
  - Open text, constant columns → SPSS string variables
  - A 0-10 "recommend" / NPS question → derived Detractor/Passive/Promoter variable

Excel workbooks may optionally include the sheets written by /v1/convert:
  - "Data"            — the respondent-level data (else the first non-label sheet)
  - "Variable Labels" — columns: Variable, Label
  - "Value Labels"    — columns: Variable, Value, Label (for numeric-coded data)
"""

import logging

import pandas as pd
import pyreadstat

from services.codebook.apply import apply_codebook, write_sav
from services.codebook.describe import annotate_counts, summarize
from services.codebook.infer import infer_codebook
from services.codebook.model import Code, Codebook, Inferred, Source, Variable
from services.codebook.patch import EditError, apply_ops  # noqa: F401
from services.quantipy_engine import QuantiProEngine, SPSSData

# Re-exported for existing importers (routers, MCP, tests)
from services.codebook.heuristics import (  # noqa: F401
    MAX_CATEGORIES,
    MULTI_SELECT_DELIMITER,
    RATING_SCALES,
    _NPS_HEADER,
    _normalize,
    _spss_name,
    _split_multi_select,
    is_non_substantive,
)
from services.ingest.readers import (  # noqa: F401
    CSV_FORMATS,
    EXCEL_FORMATS,
    SPSS_FORMATS,
    SUPPORTED_FORMATS,
    RawTable,
    file_format,
    read_raw,
    read_table,
)

logger = logging.getLogger(__name__)


def load_data(file_bytes: bytes, filename: str = "upload.sav", codebook: Codebook | None = None) -> SPSSData:
    """Load any supported data file into SPSSData.

    This is a blocking/CPU-bound operation — call via run_in_executor().

    Raises:
        ValueError: unsupported format or unreadable file contents.
    """
    if file_format(filename) in SPSS_FORMATS and codebook is None:
        return QuantiProEngine.load_spss(file_bytes, filename)
    data, _ = load_with_codebook(file_bytes, filename, codebook)
    return data


def load_with_codebook(
    file_bytes: bytes, filename: str, codebook: Codebook | None = None,
) -> tuple[SPSSData, Codebook]:
    """Load a file and return the codebook that was applied (inferred if none given)."""
    if file_format(filename) in SPSS_FORMATS:
        data = QuantiProEngine.load_spss(file_bytes, filename)
        if codebook is None:
            return data, codebook_from_spss(file_bytes, data, filename)
        # An edited SPSS codebook (labels, nets, excluded codes, combined questions) is
        # applied like any other: the file's own values are its "raw" answers.
        coded = apply_codebook(data.df, codebook)
        return QuantiProEngine.load_spss(write_sav(coded), filename), codebook

    raw = read_raw(file_bytes, filename)
    codebook = codebook or infer_codebook(raw)
    coded = apply_codebook(raw.df, codebook)
    if coded.unmatched:
        logger.warning("Answers not in the codebook (coded as missing): %s",
                       {k: v[:5] for k, v in coded.unmatched.items()})
    data = QuantiProEngine.load_spss(write_sav(coded), filename)
    logger.info("Loaded %s as SPSS: %d cases x %d variables", raw.fmt, len(data.df), len(data.df.columns))
    return data, codebook


def describe_file(file_bytes: bytes, filename: str, codebook: Codebook | None = None) -> dict:
    """Codebook with counts + summary: how every column of the file is (or would be) coded."""
    if file_format(filename) in SPSS_FORMATS:
        data = QuantiProEngine.load_spss(file_bytes, filename)
        cb = codebook or codebook_from_spss(file_bytes, data, filename)
        coded = apply_codebook(data.df, cb)
        columns, unmatched = coded.columns, coded.unmatched
    else:
        raw = read_raw(file_bytes, filename)
        cb = codebook or infer_codebook(raw)
        coded = apply_codebook(raw.df, cb)
        columns, unmatched = coded.columns, coded.unmatched
    cb = annotate_counts(cb, columns)
    return {"summary": summarize(cb, unmatched), "codebook": cb.model_dump(mode="json")}


def edit_codebook(file_bytes: bytes, filename: str, edits: list[dict], codebook: Codebook | None = None) -> dict:
    """Apply edits to the file's codebook (inferred if none given) → described result.

    An SPSS file starts from its own metadata (codebook_from_spss); its values are the
    answers the edits refer to. Raises EditError for invalid edits.
    """
    if file_format(filename) in SPSS_FORMATS:
        data = QuantiProEngine.load_spss(file_bytes, filename)
        edited = apply_ops(codebook or codebook_from_spss(file_bytes, data, filename), edits, data.df)
        return describe_file(file_bytes, filename, edited)
    raw = read_raw(file_bytes, filename)
    edited = apply_ops(codebook or infer_codebook(raw), edits, raw.df)
    return describe_file(file_bytes, filename, edited)


def codebook_from_spss(file_bytes: bytes, data: SPSSData, filename: str = "upload.sav") -> Codebook:
    """Describe a native SPSS file as a codebook (its metadata already holds the decisions)."""
    meta = data.meta
    labels = getattr(meta, "column_names_to_labels", {}) or {}
    value_labels = getattr(meta, "variable_value_labels", {}) or {}
    measures = getattr(meta, "variable_measure", {}) or {}
    missing = _spss_user_missing(file_bytes)

    variables = []
    for name in data.df.columns:
        series = data.df[name]
        vl = value_labels.get(name) or {}
        miss = missing.get(name, set())
        if pd.api.types.is_datetime64_any_dtype(series):
            role = "date"
        elif not pd.api.types.is_numeric_dtype(series):
            role = "text"
        elif vl:
            role = "single"
        else:
            role = "numeric"
        measure = measures.get(name)
        variables.append(Variable(
            column=name, name=name, label=labels.get(name) or name, role=role,
            measure=measure if measure in ("nominal", "ordinal", "scale") else None,
            codes=[Code(code=float(k), label=str(v)) for k, v in vl.items() if float(k) not in miss],
            missing=[Code(code=float(k), label=str(v)) for k, v in vl.items() if float(k) in miss],
            source="number" if role in ("single", "numeric") else None,
            inferred=Inferred(rule="spss:metadata", reason="Defined in the SPSS file"),
        ))
    return Codebook(source=Source(format=file_format(filename), rows=len(data.df), columns=len(data.df.columns)),
                    variables=variables)


def _spss_user_missing(file_bytes: bytes) -> dict[str, set[float]]:
    """User-missing codes per variable (load_spss reads them as NaN, losing the definition)."""
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".sav")
    try:
        os.write(fd, file_bytes)
        os.close(fd)
        _, meta = pyreadstat.read_sav(path, metadataonly=True, user_missing=True)
    except Exception:
        return {}
    finally:
        os.unlink(path)
    out: dict[str, set[float]] = {}
    for name, ranges in (getattr(meta, "missing_ranges", {}) or {}).items():
        for r in ranges:
            if isinstance(r, dict) and r.get("lo") == r.get("hi"):
                out.setdefault(name, set()).add(float(r["lo"]))
    return out
