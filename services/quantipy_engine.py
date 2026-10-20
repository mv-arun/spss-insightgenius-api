"""Core SPSS processing engine — stateless wrapper around QuantipyMRX + pandas.

Every function receives raw data and returns results. No instance state between requests.
All CPU-bound operations should be called via asyncio.to_thread() from routers.
"""

import logging
import math
import os
import string
import tempfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pyreadstat
from scipy import stats
from statsmodels.stats.proportion import proportions_ztest

from shared.significance import bonferroni_on, significant_at, z_test_proportions

logger = logging.getLogger(__name__)

# QuantipyMRX — graceful fallback
try:
    from quantipymrx import DataSet
    from quantipymrx.analysis.auto_detect import (
        auto_detect as mrx_auto_detect,
        suggest_banners as mrx_suggest_banners,
        detect_groups as mrx_detect_groups,
    )
    from quantipymrx.analysis.crosstab import crosstab as mrx_crosstab
    from quantipymrx.analysis.significance import z_test_proportions as mrx_z_test, t_test_means as mrx_t_test
    from quantipymrx.analysis.mrx import calculate_nps as mrx_nps

    QUANTIPYMRX_AVAILABLE = True
    logger.info("QuantipyMRX loaded successfully")
except ImportError:
    QUANTIPYMRX_AVAILABLE = False
    DataSet = None  # type: ignore[assignment,misc]
    logger.warning("QuantipyMRX not available — pandas-only mode")


@dataclass
class SPSSData:
    """Container for loaded SPSS data: DataFrame + pyreadstat meta + optional MRX DataSet."""
    df: pd.DataFrame
    meta: Any  # pyreadstat metadata
    mrx_dataset: Any = None  # QuantipyMRX DataSet or None
    file_name: str = ""


def _sanitize_value(v: Any) -> Any:
    """Convert numpy types and NaN to JSON-safe Python types."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def value_text(v: Any) -> str:
    """A code shown where a value has no label: 3.0 → '3', 2.5 → '2.5', 'x' → 'x'."""
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return str(v)


def _get_user_missing(variable: str, meta: Any) -> set:
    """Get SPSS user-defined missing values for a variable."""
    if not meta:
        return set()
    missing_dict = getattr(meta, "missing_user_values", {})
    vals = missing_dict.get(variable, {})
    if isinstance(vals, dict):
        result = set()
        for key, val in vals.items():
            if val is not None:
                result.add(val)
        return result
    if isinstance(vals, (list, set)):
        return set(vals)
    return set()


def _strip_common_label_prefix(labels: list[str]) -> list[str]:
    """Strip the longest common prefix from SPSS MRS variable labels.

    Example:
        ["Q2b: Aided Importance: Fast onset", "Q2b: Aided Importance: Good score"]
        → ["Fast onset", "Good score"]
    """
    if len(labels) < 2:
        return labels
    prefix = labels[0]
    for lbl in labels[1:]:
        while not lbl.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return labels
    # End the prefix at a separator, so options sharing first words ("Concerns with
    # safety" / "Concerns with cost", "Ask for a X" / "Ask for a Y") keep them
    if not prefix.endswith(tuple(":;-–—/?")):
        cut = max(prefix.rfind(ch) for ch in ":;-–—/?")
        prefix = prefix[:cut + 1] if cut >= 0 else ""
    if len(prefix) < 5:
        return labels
    cleaned = []
    for lbl in labels:
        suffix = lbl[len(prefix):].lstrip(":;-–—/ \t")
        cleaned.append(suffix if len(suffix) >= 2 else lbl)
    return cleaned


def _frequency_via_mrx(data: "SPSSData", variable: str, weight: str | None) -> dict[str, Any] | None:
    """Delegate frequency to MRX and add mean/std/median."""
    from quantipymrx.analysis.frequency import frequency as mrx_frequency

    fr = mrx_frequency(data.mrx_dataset, variable, weight=weight)

    meta = data.meta
    col_labels = getattr(meta, "column_names_to_labels", {})
    value_labels_map = getattr(meta, "variable_value_labels", {}).get(variable, {})

    # MRX FrequencyResult.table columns vary — detect dynamically
    tbl = fr.table
    tbl_cols = list(tbl.columns)
    count_col = next((c for c in tbl_cols if "count" in str(c).lower()), tbl_cols[0] if tbl_cols else None)
    pct_col = next((c for c in tbl_cols if "pct" in str(c).lower() or "percent" in str(c).lower()), None)

    frequencies = []
    for val, row in tbl.iterrows():
        if pd.isna(val):
            continue
        label = value_labels_map.get(val, str(val))
        raw_count = row.iloc[0] if count_col is None else row.get(count_col, 0)
        raw_pct = row.get(pct_col, 0) if pct_col else 0
        count = _sanitize_value(raw_count)
        pct = _sanitize_value(raw_pct)
        if count is None:
            count = 0
        if pct is None:
            pct = 0
        frequencies.append({
            "value": _sanitize_value(val),
            "label": str(label),
            "count": int(count) if not weight else round(float(count), 1),
            "percentage": round(float(pct), 1),
        })

    # If MRX didn't return percentages, compute them
    total_count = sum(f["count"] for f in frequencies)
    if total_count > 0 and all(f["percentage"] == 0 for f in frequencies):
        for f in frequencies:
            f["percentage"] = round(f["count"] / total_count * 100, 1)

    frequencies.sort(key=lambda x: x["count"], reverse=True)

    base = getattr(fr, "base", None)
    if base is None:
        base = total_count

    result: dict[str, Any] = {
        "variable": variable,
        "label": col_labels.get(variable),
        "base": _sanitize_value(base) or 0,
        "total_missing": _sanitize_value(getattr(fr, "missing", 0)) or 0,
        "pct_missing": round(float(getattr(fr, "pct_missing", 0) or 0), 1),
        "frequencies": frequencies,
    }

    # NEW fields from MRX — only for numeric variables
    for attr in ("mean", "std", "median"):
        val = getattr(fr, attr, None)
        if val is not None:
            val = _sanitize_value(val)
            if val is not None:
                result[attr] = round(float(val), 2)
    result["is_weighted"] = weight is not None

    return result


def _crosstab_via_mrx(
    data: "SPSSData", row: str, col: str, weight: str | None, significance_level: float,
) -> dict[str, Any] | None:
    """Delegate crosstab to MRX native function and convert to API response shape.

    IMPORTANT: MRX returns label-keyed DataFrames (e.g., column "Entre 18 y 24 años")
    while the tabulation builder expects value-keyed dicts (e.g., key "1.0").
    We must map MRX labels back to numeric values for compatibility.
    """
    alpha = 1 - significance_level
    sig_level_for_mrx = alpha  # MRX expects alpha (0.05), not confidence (0.95)

    ct = mrx_crosstab(
        data.mrx_dataset, x=row, y=col,
        weight=weight,
        sig_level=sig_level_for_mrx,
        test_significance=True,
        include_totals=True,
    )

    # Convert CrosstabResult to API response shape
    meta = data.meta
    row_vl = getattr(meta, "variable_value_labels", {}).get(row, {})
    col_vl = getattr(meta, "variable_value_labels", {}).get(col, {})

    # Build reverse maps: label → numeric value
    row_label_to_val = {str(v): k for k, v in row_vl.items()}
    col_label_to_val = {str(v): k for k, v in col_vl.items()}

    # MRX columns may be labels (str) or numeric values — detect which
    mrx_col_values = ct.col_pct.columns.tolist()
    mrx_uses_labels = len(mrx_col_values) > 0 and isinstance(mrx_col_values[0], str) and mrx_col_values[0] in col_label_to_val

    # Map MRX columns back to numeric values (for compat with tabulation builder)
    if mrx_uses_labels:
        col_values = sorted([col_label_to_val.get(str(c), c) for c in mrx_col_values])
        mrx_col_map = {col_label_to_val.get(str(c), c): c for c in mrx_col_values}  # numeric → mrx_label
    else:
        col_values = sorted(mrx_col_values)
        mrx_col_map = {c: c for c in mrx_col_values}

    letters = list(string.ascii_uppercase[:len(col_values)])
    col_letter_map = {str(val): letters[i] for i, val in enumerate(col_values)}

    # Same for rows
    mrx_row_values = ct.col_pct.index.tolist()
    mrx_row_uses_labels = len(mrx_row_values) > 0 and isinstance(mrx_row_values[0], str) and mrx_row_values[0] in row_label_to_val

    table = []
    for mrx_rv in mrx_row_values:
        if mrx_row_uses_labels:
            numeric_rv = row_label_to_val.get(str(mrx_rv), mrx_rv)
            row_label = str(mrx_rv)
        else:
            numeric_rv = mrx_rv
            row_label = row_vl.get(mrx_rv, value_text(mrx_rv))

        row_data: dict[str, Any] = {
            "row_value": _sanitize_value(numeric_rv),
            "row_label": row_label,
        }
        for i, cv in enumerate(col_values):
            mrx_cv = mrx_col_map.get(cv, cv)  # Get the MRX column key
            raw_count = ct.counts.loc[mrx_rv, mrx_cv] if mrx_cv in ct.counts.columns else 0
            raw_pct = ct.col_pct.loc[mrx_rv, mrx_cv] if mrx_cv in ct.col_pct.columns else 0
            count = _sanitize_value(raw_count) or 0
            pct = _sanitize_value(raw_pct) or 0

            # Get sig letters from MRX significance matrix
            sig_letters: list[str] = []
            if ct.significance is not None and mrx_cv in ct.significance.columns and mrx_rv in ct.significance.index:
                sig_cell = ct.significance.loc[mrx_rv, mrx_cv]
                if isinstance(sig_cell, str) and sig_cell:
                    sig_letters = list(sig_cell)

            row_data[str(cv)] = {
                "count": round(float(count), 1) if weight else int(count),
                "percentage": round(float(pct), 1),
                "column_letter": letters[i],
                "significance_letters": sorted(set(sig_letters)),
            }
        table.append(row_data)

    col_vl_map = {str(v): col_vl.get(v, value_text(v)) for v in col_values}
    raw_total = ct.total_base if ct.total_base else ct.counts.sum().sum()
    total = _sanitize_value(raw_total) or 0

    response: dict[str, Any] = {
        "row_variable": row,
        "col_variable": col,
        "total_responses": int(total),
        "table": table,
        "col_labels": col_letter_map,
        "col_value_labels": col_vl_map,
        "significance_level": significance_level,
        "significant_pairs": [],
    }

    # Add chi-square (NEW — free from MRX)
    if ct.chi2 is not None:
        chi2_val = _sanitize_value(ct.chi2)
        chi2_p = _sanitize_value(ct.chi2_pvalue)
        if chi2_val is not None:
            response["chi2"] = round(float(chi2_val), 4)
        if chi2_p is not None:
            response["chi2_pvalue"] = round(float(chi2_p), 6)
        response["chi2_warning"] = ct.chi2_warning

    return response


class QuantiProEngine:
    """Stateless SPSS processing engine."""

    @staticmethod
    def load_spss(file_bytes: bytes, file_name: str = "upload.sav") -> SPSSData:
        """Load .sav bytes into SPSSData (DataFrame + meta + optional MRX DataSet).

        This is a blocking/CPU-bound operation — call via asyncio.to_thread().
        """
        # Use mkstemp instead of NamedTemporaryFile to avoid Windows file locking
        fd, tmp_path = tempfile.mkstemp(suffix=".sav")
        try:
            os.write(fd, file_bytes)
            os.close(fd)

            # Load via pyreadstat (always reliable)
            df, meta = pyreadstat.read_sav(tmp_path)
            logger.info("Loaded SPSS: %d cases x %d variables", len(df), len(df.columns))

            # Load via QuantipyMRX (optional, for auto_detect + crosstab_with_sig)
            mrx_dataset = None
            if QUANTIPYMRX_AVAILABLE:
                try:
                    mrx_dataset = DataSet.from_spss(tmp_path, text_key="en-US")
                except Exception as e:
                    logger.warning("MRX DataSet load failed (pandas still available): %s", e)

            return SPSSData(df=df, meta=meta, mrx_dataset=mrx_dataset, file_name=file_name)
        finally:
            os.unlink(tmp_path)

    @staticmethod
    def load_spss_metadata_only(file_bytes: bytes) -> tuple[Any, str]:
        """Load only SPSS metadata (no data rows). Very fast.

        Returns (meta, tmp_path_for_mrx).
        """
        fd, tmp_path = tempfile.mkstemp(suffix=".sav")
        try:
            os.write(fd, file_bytes)
            os.close(fd)
            _, meta = pyreadstat.read_sav(tmp_path, metadataonly=True)
            return meta, tmp_path
        except Exception:
            os.unlink(tmp_path)
            raise

    @staticmethod
    def extract_metadata(data: SPSSData) -> dict[str, Any]:
        """Extract comprehensive metadata from loaded SPSS data."""
        df = data.df
        meta = data.meta

        col_labels = getattr(meta, "column_names_to_labels", {})
        value_labels = getattr(meta, "variable_value_labels", {})
        col_formats = getattr(meta, "original_variable_types", {})

        variables = []
        for col in df.columns:
            series = df[col]
            user_missing = _get_user_missing(col, meta)
            valid_mask = series.notna()
            if user_missing:
                valid_mask = valid_mask & ~series.isin(user_missing)

            # Determine type
            if pd.api.types.is_numeric_dtype(series):
                var_type = "numeric"
            elif pd.api.types.is_datetime64_any_dtype(series):
                var_type = "date"
            else:
                var_type = "string"

            # Value labels for this variable
            var_value_labels = value_labels.get(col, {})
            vl_dict = {str(k): str(v) for k, v in var_value_labels.items()} if var_value_labels else None

            variables.append({
                "name": col,
                "label": col_labels.get(col),
                "type": var_type,
                "measurement": None,  # SPSS measurement level not in pyreadstat
                "n_valid": int(valid_mask.sum()),
                "n_missing": int((~valid_mask).sum()),
                "value_labels": vl_dict,
                "detected_type": None,  # Filled by auto_detect
            })

        # Detect weight variables (heuristic: name contains 'weight' or 'wt' or 'pond')
        weight_candidates = [
            col for col in df.columns
            if any(w in col.lower() for w in ["weight", "wt_", "_wt", "pond", "ponder"])
        ]

        # Auto-detect via MRX
        auto_detect_result = None
        suggested_banners = None
        detected_groups = None
        preset_nets = None

        if data.mrx_dataset is not None:
            try:
                auto_detect_result = QuantiProEngine.auto_detect(data)
            except Exception as e:
                logger.warning("auto_detect failed: %s", e)

            # Suggest banners (Sprint B — from MRX)
            try:
                raw_banners = mrx_suggest_banners(data.mrx_dataset, max_banners=5)
                suggested_banners = [
                    {
                        "variable": getattr(b, "variable", str(b)),
                        "label": col_labels.get(getattr(b, "variable", str(b)), ""),
                        "n_categories": getattr(b, "n_categories", None),
                        "confidence": getattr(b, "confidence", None),
                        "reason": getattr(b, "reason", None),
                    }
                    for b in raw_banners
                ] if raw_banners else None
            except Exception as e:
                logger.warning("suggest_banners failed: %s", e)

            # Detect groups: grids, MRS, top-of-mind (Sprint B — from MRX)
            try:
                raw_groups = mrx_detect_groups(data.mrx_dataset)
                detected_groups = [
                    {
                        "name": getattr(g, "name", ""),
                        "display_name": getattr(g, "display_name", getattr(g, "name", "")),
                        "question_type": getattr(g, "question_type", "unknown"),
                        "variables": getattr(g, "variables", []),
                        "confidence": getattr(g, "confidence", None),
                    }
                    for g in raw_groups
                ] if raw_groups else None
            except Exception as e:
                logger.warning("detect_groups failed: %s", e)

        # ── Post-process MRX groups: fix misclassified GRID_SINGLE → awareness ──
        # MRX sometimes classifies binary MRS variables (1/NaN, no value_labels) as GRID_SINGLE.
        # If all members have only {0,1} or {1,NaN} data, reclassify as "awareness".
        if detected_groups:
            for g in detected_groups:
                q_type = str(g.get("question_type", ""))
                if "GRID" in q_type.upper() or q_type == "unknown":
                    members = g.get("variables", [])
                    if len(members) >= 2:
                        all_binary = all(
                            m in df.columns and set(df[m].dropna().unique().tolist()).issubset({0, 0.0, 1, 1.0})
                            for m in members
                        )
                        if all_binary:
                            g["question_type"] = "awareness"
                            g["source"] = "mrx_corrected"

        # ── Label-pattern fallback for flat variable files ──────────────────
        if not detected_groups:
            detected_groups = []
        _grouped_vars = {v for g in detected_groups for v in g.get("variables", [])}

        label_groups: dict[str, list[dict]] = {}
        for var_info in variables:
            vname = var_info["name"]
            if vname in _grouped_vars:
                continue  # Already in an MRX-detected group
            label = var_info.get("label") or ""
            if ":" not in label:
                continue
            prefix = label.split(":")[0].strip()
            if len(prefix) < 3:
                continue
            label_groups.setdefault(prefix, []).append(var_info)

        for prefix, members in label_groups.items():
            if len(members) < 2:
                continue  # Need at least 2 variables to form a group
            member_names = [m["name"] for m in members]
            # Determine type: all binary (2 labels OR 0/1 data) → awareness/MRS; all same scale → grid
            n_labels = [len(m.get("value_labels") or {}) for m in members]
            all_binary_labels = all(n == 2 for n in n_labels)

            # Check if binary by data values (handles MRS without value_labels like Q_12_1..Q_12_20)
            all_binary_data = False
            if all(n <= 2 for n in n_labels):  # No labels or ≤2 labels
                all_binary_data = all(
                    m["name"] in df.columns and set(df[m["name"]].dropna().unique().tolist()).issubset({0, 0.0, 1, 1.0})
                    for m in members
                )

            all_same_scale = len(set(n_labels)) == 1 and n_labels[0] >= 3

            if all_binary_labels or all_binary_data:
                q_type = "awareness"
            elif all_same_scale:
                q_type = "scale"
            else:
                q_type = "mixed"

            detected_groups.append({
                "name": prefix,
                "display_name": prefix,
                "question_type": q_type,
                "variables": member_names,
                "confidence": 0.7,
                "source": "label_pattern",
            })
            _grouped_vars.update(member_names)

        # Also detect by variable name prefix (sat_*, AWARE_*)
        name_groups: dict[str, list[dict]] = {}
        for var_info in variables:
            vname = var_info["name"]
            if vname in _grouped_vars:
                continue
            # Split on _ and use first part as prefix
            parts = vname.split("_")
            if len(parts) < 2:
                continue
            prefix = parts[0]
            if len(prefix) < 2:
                continue
            name_groups.setdefault(prefix, []).append(var_info)

        for prefix, members in name_groups.items():
            if len(members) < 3:
                continue  # Need at least 3 to be a meaningful group
            member_names = [m["name"] for m in members]
            n_labels = [len(m.get("value_labels") or {}) for m in members]
            all_binary_labels = all(n == 2 for n in n_labels)
            all_binary_data = False
            if all(n <= 2 for n in n_labels):
                all_binary_data = all(
                    m["name"] in df.columns and set(df[m["name"]].dropna().unique().tolist()).issubset({0, 0.0, 1, 1.0})
                    for m in members
                )
            all_same_scale = len(set(n_labels)) == 1 and n_labels[0] >= 3

            if all_binary_labels or all_binary_data:
                q_type = "awareness"
            elif all_same_scale:
                q_type = "scale"
            else:
                continue  # Mixed types by name prefix — not reliable

            # Use label prefix if available, else name prefix
            first_label = (members[0].get("label") or "").split(":")[0].strip()
            display = first_label if first_label and len(first_label) > 2 else prefix.upper()

            detected_groups.append({
                "name": prefix,
                "display_name": display,
                "question_type": q_type,
                "variables": member_names,
                "confidence": 0.5,
                "source": "name_pattern",
            })
            _grouped_vars.update(member_names)

        # Preset nets based on detected scale ranges
        preset_nets = {}
        for var_info in variables:
            vl = var_info.get("value_labels")
            if not vl or var_info["type"] != "numeric":
                continue
            try:
                keys = sorted([float(k) for k in vl.keys()])
            except (ValueError, TypeError):
                continue
            n = len(keys)
            if n == 5:
                preset_nets[var_info["name"]] = {
                    "Top 2 Box": [int(keys[-2]), int(keys[-1])],
                    "Bottom 2 Box": [int(keys[0]), int(keys[1])],
                }
            elif n == 7:
                preset_nets[var_info["name"]] = {
                    "Top 2 Box": [int(keys[-2]), int(keys[-1])],
                    "Bottom 2 Box": [int(keys[0]), int(keys[1])],
                }
            elif n == 11 and keys[0] == 0 and keys[-1] == 10:
                preset_nets[var_info["name"]] = {
                    "Promoters (9-10)": [9, 10],
                    "Passives (7-8)": [7, 8],
                    "Detractors (0-6)": [0, 1, 2, 3, 4, 5, 6],
                }

        return {
            "file_name": data.file_name,
            "n_cases": len(df),
            "n_variables": len(df.columns),
            "variables": variables,
            "detected_weights": weight_candidates,
            "auto_detect": auto_detect_result,
            "suggested_banners": suggested_banners,
            "detected_groups": detected_groups,
            "preset_nets": preset_nets if preset_nets else None,
            "file_label": getattr(meta, "file_label", None),
        }

    @staticmethod
    def auto_detect(data: SPSSData, timeout: int = 10) -> dict[str, Any] | None:
        """Run QuantipyMRX auto_detect with timeout protection."""
        if data.mrx_dataset is None:
            return None

        def _run():
            spec = mrx_auto_detect(data.mrx_dataset)
            if spec is not None and hasattr(spec, "to_dict"):
                return spec.to_dict()
            return {}

        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                future = pool.submit(_run)
                return future.result(timeout=timeout)
            except FuturesTimeoutError:
                logger.warning("auto_detect timed out after %ds", timeout)
                return None
            except Exception as e:
                logger.warning("auto_detect failed: %s", e)
                return None

    @staticmethod
    def frequency(
        data: SPSSData,
        variable: str,
        weight: str | None = None,
    ) -> dict[str, Any]:
        """Frequency table for a single variable. Delegates to MRX when available."""
        df = data.df
        meta = data.meta

        if variable not in df.columns:
            raise ValueError(f"Variable '{variable}' not found in dataset")

        # Try MRX native frequency
        if data.mrx_dataset is not None:
            try:
                result = _frequency_via_mrx(data, variable, weight)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning("MRX frequency failed for %s, falling back: %s", variable, e)

        user_missing = _get_user_missing(variable, meta)
        col_labels = getattr(meta, "column_names_to_labels", {})
        value_labels_map = getattr(meta, "variable_value_labels", {}).get(variable, {})

        # Weight series
        w = None
        if weight and weight in df.columns:
            w = df[weight]

        if w is not None:
            # Weighted frequency
            valid_mask = df[variable].notna()
            if user_missing:
                valid_mask = valid_mask & ~df[variable].isin(user_missing)
            total_weight = float(w[valid_mask].sum())

            frequencies = []
            weighted_missing = 0.0
            for value in df[variable].dropna().unique():
                if value in user_missing:
                    mask = df[variable] == value
                    weighted_missing += float(w[mask].sum())
                    continue
                mask = df[variable] == value
                wc = float(w[mask].sum())
                label = value_labels_map.get(value, str(value))
                frequencies.append({
                    "value": _sanitize_value(value),
                    "label": str(label),
                    "count": round(wc, 1),
                    "percentage": round((wc / total_weight * 100) if total_weight > 0 else 0, 1),
                })

            # Add NaN missing
            nan_mask = df[variable].isna()
            weighted_missing += float(w[nan_mask].sum())

            frequencies.sort(key=lambda x: x["count"], reverse=True)
            total_all_w = float(w.sum())

            return {
                "variable": variable,
                "label": col_labels.get(variable),
                "base": round(total_weight, 1),
                "total_missing": int(round(weighted_missing)),
                "pct_missing": round(weighted_missing / total_all_w * 100, 1) if total_all_w > 0 else 0.0,
                "frequencies": frequencies,
            }

        # Unweighted path
        valid_series = df[variable].dropna()
        if user_missing:
            valid_series = valid_series[~valid_series.isin(user_missing)]
        total = len(valid_series)
        total_all = len(df)

        value_counts = df[variable].value_counts(dropna=False)
        frequencies = []
        missing_count = 0

        for value, count in value_counts.items():
            is_missing = pd.isna(value) or value in user_missing
            if is_missing:
                missing_count += int(count)
                continue
            label = value_labels_map.get(value, str(value))
            pct = round((count / total * 100) if total > 0 else 0, 1)
            frequencies.append({
                "value": _sanitize_value(value),
                "label": str(label),
                "count": int(count),
                "percentage": pct,
            })

        frequencies.sort(key=lambda x: x["count"], reverse=True)

        return {
            "variable": variable,
            "label": col_labels.get(variable),
            "base": total,
            "total_missing": missing_count,
            "pct_missing": round(missing_count / total_all * 100, 1) if total_all > 0 else 0.0,
            "frequencies": frequencies,
        }

    @staticmethod
    def crosstab_with_significance(
        data: SPSSData,
        row: str,
        col: str,
        weight: str | None = None,
        significance_level: float = 0.95,
        secondary_level: float | None = None,
    ) -> dict[str, Any]:
        """Crosstab with column proportion significance testing (A/B/C letter notation).

        Uses proportions_ztest for unweighted, effective-n z-test for weighted.
        With `secondary_level` (e.g. 0.90), differences significant only at that lower
        level are listed in each cell's `significance_letters_secondary`.
        """
        df = data.df
        meta = data.meta

        if row not in df.columns:
            raise ValueError(f"Row variable '{row}' not found in dataset")
        if col not in df.columns:
            raise ValueError(f"Column variable '{col}' not found in dataset")

        # Try MRX native crosstab first — validate result before using.
        # MRX tests a single level with its own correction, so two-level requests and
        # runs without Bonferroni use the pandas path.
        if data.mrx_dataset is not None and secondary_level is None and bonferroni_on():
            try:
                result = _crosstab_via_mrx(data, row, col, weight, significance_level)
                if result is not None:
                    # Sanity check: MRX result should have similar total to pandas
                    pandas_total = len(df[[row, col]].dropna())
                    mrx_total = result.get("total_responses", 0)
                    # Also check that we have reasonable number of columns
                    n_pandas_cols = len(df[col].dropna().unique())
                    n_mrx_cols = len(result.get("col_labels", {}))
                    if mrx_total > 0 and n_mrx_cols >= n_pandas_cols * 0.5:
                        return result
                    else:
                        logger.warning(
                            "MRX crosstab sanity check failed for %s x %s: "
                            "mrx_total=%d vs pandas=%d, mrx_cols=%d vs pandas=%d. Falling back.",
                            row, col, mrx_total, pandas_total, n_mrx_cols, n_pandas_cols,
                        )
            except Exception as e:
                logger.warning("MRX crosstab failed for %s x %s, falling back to pandas: %s", row, col, e)

        w = df[weight] if weight and weight in df.columns else None

        # Value labels
        row_value_labels = getattr(meta, "variable_value_labels", {}).get(row, {})
        col_value_labels = getattr(meta, "variable_value_labels", {}).get(col, {})
        col_labels_map = getattr(meta, "column_names_to_labels", {})

        alpha = 1 - significance_level
        alpha2 = None if secondary_level is None else 1 - secondary_level

        if w is not None:
            # Weighted path
            valid = df[[row, col]].dropna()
            w_valid = w.loc[valid.index]
            weighted_ct = valid.assign(_w=w_valid).groupby([row, col])["_w"].sum().unstack(fill_value=0)

            if weighted_ct.empty:
                raise ValueError(f"No valid observations for {row} x {col}")

            col_values = sorted(weighted_ct.columns.tolist())
            letters = list(string.ascii_uppercase[:len(col_values)])
            col_letter_map = {str(val): letters[i] for i, val in enumerate(col_values)}
            w_col_totals = weighted_ct.sum(axis=0)

            # Effective n per column (Kish design effect)
            col_eff_n = {}
            for cv in col_values:
                col_mask = valid[col] == cv
                cw = w_valid[col_mask]
                sw = float(cw.sum())
                sw2 = float((cw ** 2).sum())
                col_eff_n[cv] = sw ** 2 / sw2 if sw2 > 0 else 0

            table = []
            significant_pairs = []

            for row_val in weighted_ct.index:
                row_data = {
                    "row_value": _sanitize_value(row_val),
                    "row_label": row_value_labels.get(row_val, value_text(row_val)),
                }
                for i, cv in enumerate(col_values):
                    wc = float(weighted_ct.loc[row_val, cv]) if cv in weighted_ct.columns else 0
                    ct = float(w_col_totals[cv])
                    pct = round((wc / ct * 100) if ct > 0 else 0, 1)

                    sig_letters, sig_letters2 = [], []
                    n_cols = len(col_values)
                    for j, ocv in enumerate(col_values):
                        if i == j:
                            continue
                        owc = float(weighted_ct.loc[row_val, ocv]) if ocv in weighted_ct.columns else 0
                        oct = float(w_col_totals[ocv])
                        n_eff_i = col_eff_n.get(cv, 0)
                        n_eff_j = col_eff_n.get(ocv, 0)
                        p_i = wc / ct if ct > 0 else 0
                        p_j = owc / oct if oct > 0 else 0
                        p_val, is_sig = z_test_proportions(
                            p_i, n_eff_i, p_j, n_eff_j, alpha, n_cols,
                            variable=f"{row}x{col}[{_sanitize_value(row_val)}]",
                            col_a=letters[i], col_b=letters[j],
                        )
                        if is_sig:
                            sig_letters.append(letters[j])
                            significant_pairs.append({
                                "row_value": _sanitize_value(row_val),
                                "col1": str(cv), "col1_letter": letters[i],
                                "col2": str(ocv), "col2_letter": letters[j],
                                "p_value": round(p_val, 4),
                                "higher_column": letters[i],
                            })
                        elif significant_at(p_val, alpha2, n_cols, p_i > p_j):
                            sig_letters2.append(letters[j])

                    row_data[str(cv)] = {
                        "count": round(float(wc), 1),
                        "percentage": pct,
                        "column_letter": letters[i],
                        "significance_letters": sorted(set(sig_letters)),
                    }
                    if alpha2 is not None:
                        row_data[str(cv)]["significance_letters_secondary"] = sorted(set(sig_letters2))
                table.append(row_data)

            col_vl_map = {str(v): col_value_labels.get(v, value_text(v)) for v in col_values}
            return {
                "row_variable": row,
                "col_variable": col,
                "total_responses": int(round(float(w_col_totals.sum()))),
                "table": table,
                "col_labels": col_letter_map,
                "col_value_labels": col_vl_map,
                "significance_level": significance_level,
                **({"significance_level_secondary": secondary_level} if alpha2 is not None else {}),
                "significant_pairs": significant_pairs,
            }

        # Unweighted path
        crosstab = pd.crosstab(df[row], df[col])
        if crosstab.empty:
            raise ValueError(f"No valid observations for {row} x {col}")

        col_values = sorted(crosstab.columns.tolist())
        letters = list(string.ascii_uppercase[:len(col_values)])
        col_letter_map = {str(val): letters[i] for i, val in enumerate(col_values)}
        col_totals = crosstab.sum(axis=0)

        table = []
        significant_pairs = []

        for row_val in crosstab.index:
            row_data = {
                "row_value": _sanitize_value(row_val),
                "row_label": row_value_labels.get(row_val, value_text(row_val)),
            }
            for i, cv in enumerate(col_values):
                count = int(crosstab.loc[row_val, cv])
                col_total = int(col_totals[cv])
                pct = round((count / col_total * 100) if col_total > 0 else 0, 1)

                sig_letters, sig_letters2 = [], []
                n_cols = len(col_values)
                for j, ocv in enumerate(col_values):
                    if i == j:
                        continue
                    other_count = int(crosstab.loc[row_val, ocv])
                    other_total = int(col_totals[ocv])
                    this_pct = count / col_total if col_total > 0 else 0
                    other_pct = other_count / other_total if other_total > 0 else 0
                    p_val, is_sig = z_test_proportions(
                        this_pct, col_total, other_pct, other_total, alpha, n_cols,
                        variable=f"{row}x{col}[{_sanitize_value(row_val)}]",
                        col_a=letters[i], col_b=letters[j],
                    )
                    if is_sig:
                        sig_letters.append(letters[j])
                        significant_pairs.append({
                            "row_value": _sanitize_value(row_val),
                            "col1": str(cv), "col1_letter": letters[i],
                            "col2": str(ocv), "col2_letter": letters[j],
                            "p_value": round(float(p_val), 4),
                            "higher_column": letters[i],
                        })
                    elif significant_at(p_val, alpha2, n_cols, this_pct > other_pct):
                        sig_letters2.append(letters[j])

                row_data[str(cv)] = {
                    "count": count,
                    "percentage": pct,
                    "column_letter": letters[i],
                    "significance_letters": sorted(set(sig_letters)),
                }
                if alpha2 is not None:
                    row_data[str(cv)]["significance_letters_secondary"] = sorted(set(sig_letters2))
            table.append(row_data)

        col_vl_map = {str(v): col_value_labels.get(v, value_text(v)) for v in col_values}
        return {
            "row_variable": row,
            "col_variable": col,
            "total_responses": int(crosstab.sum().sum()),
            "table": table,
            "col_labels": col_letter_map,
            "col_value_labels": col_vl_map,
            "significance_level": significance_level,
            **({"significance_level_secondary": secondary_level} if alpha2 is not None else {}),
            "significant_pairs": significant_pairs,
        }

    @staticmethod
    def nps(data: SPSSData, variable: str, weight: str | None = None) -> dict[str, Any]:
        """Net Promoter Score: 9-10=promoter, 7-8=passive, 0-6=detractor."""
        df = data.df
        if variable not in df.columns:
            raise ValueError(f"Variable '{variable}' not found in dataset")

        col_labels = getattr(data.meta, "column_names_to_labels", {})

        # Try MRX native NPS
        if data.mrx_dataset is not None:
            try:
                series = df[variable].dropna()
                nps_result = mrx_nps(series, scale="0-10")
                return {
                    "variable": variable,
                    "label": col_labels.get(variable),
                    "nps_score": round(float(nps_result.nps), 1),
                    "base": nps_result.base,
                    "promoters": {"count": nps_result.promoters_count, "percentage": round(nps_result.promoters_pct, 1)},
                    "passives": {"count": nps_result.passives_count, "percentage": round(nps_result.passives_pct, 1)},
                    "detractors": {"count": nps_result.detractors_count, "percentage": round(nps_result.detractors_pct, 1)},
                }
            except Exception as e:
                logger.warning("MRX NPS failed for %s, falling back: %s", variable, e)

        series = df[variable].dropna()
        base = len(series)
        if base == 0:
            raise ValueError(f"No valid data for variable '{variable}'")

        promoters = int((series >= 9).sum())
        passives = int(((series >= 7) & (series < 9)).sum())
        detractors = int((series < 7).sum())

        prom_pct = round(promoters / base * 100, 1)
        det_pct = round(detractors / base * 100, 1)
        score = round(prom_pct - det_pct, 1)

        return {
            "variable": variable,
            "label": col_labels.get(variable),
            "nps_score": score,
            "base": base,
            "promoters": {"count": promoters, "percentage": prom_pct},
            "passives": {"count": passives, "percentage": round(passives / base * 100, 1)},
            "detractors": {"count": detractors, "percentage": det_pct},
        }

    @staticmethod
    def top_bottom_box(
        data: SPSSData,
        variable: str,
        top_values: list[Any] | None = None,
        bottom_values: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Top Box / Bottom Box scores with auto-detect of scale endpoints."""
        df = data.df
        if variable not in df.columns:
            raise ValueError(f"Variable '{variable}' not found in dataset")

        series = df[variable].dropna()
        col_labels = getattr(data.meta, "column_names_to_labels", {})
        user_missing = _get_user_missing(variable, data.meta)
        if user_missing:
            series = series[~series.isin(user_missing)]
        base = len(series)
        if base == 0:
            raise ValueError(f"No valid data for variable '{variable}'")

        if top_values is None:
            max_val = series.max()
            top_values = [max_val, max_val - 1] if max_val > 2 else [max_val]
        if bottom_values is None:
            min_val = series.min()
            bottom_values = [min_val, min_val + 1] if min_val < series.max() - 1 else [min_val]

        top_count = int(series.isin(top_values).sum())
        bot_count = int(series.isin(bottom_values).sum())

        return {
            "variable": variable,
            "label": col_labels.get(variable),
            "base": base,
            "top_box": {
                "values": [_sanitize_value(v) for v in top_values],
                "count": top_count,
                "percentage": round(top_count / base * 100, 1),
            },
            "bottom_box": {
                "values": [_sanitize_value(v) for v in bottom_values],
                "count": bot_count,
                "percentage": round(bot_count / base * 100, 1),
            },
        }

    @staticmethod
    def nets(
        data: SPSSData,
        variable: str,
        net_definitions: dict[str, list[Any]],
    ) -> dict[str, Any]:
        """Net scores — grouped response counts by user-defined nets."""
        df = data.df
        if variable not in df.columns:
            raise ValueError(f"Variable '{variable}' not found in dataset")

        series = df[variable].dropna()
        col_labels = getattr(data.meta, "column_names_to_labels", {})
        user_missing = _get_user_missing(variable, data.meta)
        if user_missing:
            series = series[~series.isin(user_missing)]
        base = len(series)

        results = {}
        for name, values in net_definitions.items():
            count = int(series.isin(values).sum())
            results[name] = {
                "values": [_sanitize_value(v) for v in values],
                "count": count,
                "percentage": round(count / base * 100, 1) if base > 0 else 0,
            }

        return {
            "variable": variable,
            "label": col_labels.get(variable),
            "base": base,
            "nets": results,
        }
