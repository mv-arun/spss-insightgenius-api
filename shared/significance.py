"""Significance testing with proper Bonferroni correction.

This module centralizes ALL pairwise significance testing to ensure:
1. Bonferroni correction is applied consistently
2. Failures are logged (never silently swallowed)
3. Warnings are collected and returned to the user

Industry standard: Column proportion z-test with Bonferroni adjustment.
Bonferroni: alpha_adjusted = alpha / n_comparisons
Where n_comparisons = K*(K-1)/2 for K columns (all pairwise).
"""

import contextvars
import logging
import math
from contextlib import contextmanager
from typing import Any

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


# Whether pairwise tests correct for multiple comparisons when the caller doesn't say.
# A tabulation run sets it from its spec (Displayr's column comparisons don't correct).
_BONFERRONI = contextvars.ContextVar("bonferroni", default=True)


@contextmanager
def multiple_comparison_correction(bonferroni: bool):
    """Within this block, tests that don't pass `apply_bonferroni` use `bonferroni`."""
    token = _BONFERRONI.set(bonferroni)
    try:
        yield
    finally:
        _BONFERRONI.reset(token)


def bonferroni_on() -> bool:
    """The run's default for multiple-comparison correction."""
    return _BONFERRONI.get()


def _adjusted(alpha: float, n_columns: int, apply_bonferroni: bool | None) -> float:
    on = _BONFERRONI.get() if apply_bonferroni is None else apply_bonferroni
    return bonferroni_alpha(alpha, n_columns) if on else alpha


def bonferroni_alpha(alpha: float, n_columns: int) -> float:
    """Compute Bonferroni-adjusted alpha for pairwise comparisons.

    For K columns, there are K*(K-1)/2 unique pairs.
    Adjusted alpha = raw_alpha / n_pairs.
    """
    if n_columns <= 1:
        return alpha
    n_pairs = n_columns * (n_columns - 1) / 2
    return alpha / n_pairs


def significant_at(
    p_val: float, alpha: float | None, n_columns: int, higher: bool, apply_bonferroni: bool | None = None,
) -> bool:
    """Whether a pairwise test's p-value passes a (secondary) level, e.g. 90% after 95% failed.

    Reuses the p-value from z_test_proportions / t_test_means, so the second level costs
    no extra test. Like the primary test, only the higher of the two columns gets the letter.
    """
    if alpha is None or not higher:
        return False
    return p_val < _adjusted(alpha, n_columns, apply_bonferroni)


def low_base_marker(base: float, warn: int = 100, flag: int = 30) -> str:
    """Decipher-style low-sample marker: '**' below `flag`, '*' below `warn`, else ''."""
    if flag and base < flag:
        return "**"
    if warn and base < warn:
        return "*"
    return ""


def z_test_proportions(
    p1: float, n1: float, p2: float, n2: float,
    alpha: float, n_columns: int,
    apply_bonferroni: bool | None = None,
    variable: str = "", col_a: str = "", col_b: str = "",
    warnings_list: list | None = None,
) -> tuple[float, bool]:
    """Column proportion z-test with optional Bonferroni correction.

    Args:
        p1, n1: proportion and base for column A
        p2, n2: proportion and base for column B
        alpha: raw significance level (e.g., 0.05)
        n_columns: total number of banner columns (for Bonferroni)
        apply_bonferroni: whether to adjust alpha (None: the run's setting, Bonferroni by default)
        variable: variable name (for logging)
        col_a, col_b: column labels (for logging)
        warnings_list: optional list to append warnings to

    Returns:
        (p_value, is_significant)
    """
    if n1 <= 0 or n2 <= 0:
        return 1.0, False

    adjusted_alpha = _adjusted(alpha, n_columns, apply_bonferroni)

    try:
        p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
        if se <= 0:
            return 1.0, False
        z = (p1 - p2) / se
        p_val = 2 * stats.norm.sf(abs(z))
        is_sig = p_val < adjusted_alpha and p1 > p2
        return p_val, is_sig
    except (ZeroDivisionError, ValueError, FloatingPointError) as e:
        if warnings_list is not None:
            warnings_list.append(
                f"Sig test failed for {variable} ({col_a} vs {col_b}): {e}"
            )
        else:
            logger.warning("Sig test failed for %s (%s vs %s): %s", variable, col_a, col_b, e)
        return 1.0, False


def t_test_means(
    mean1: float, std1: float, n1: float,
    mean2: float, std2: float, n2: float,
    alpha: float, n_columns: int,
    apply_bonferroni: bool | None = None,
    variable: str = "", col_a: str = "", col_b: str = "",
    warnings_list: list | None = None,
) -> tuple[float, bool]:
    """Independent samples t-test with optional Bonferroni correction.

    Uses Welch's t-test (unequal variances).

    Returns:
        (p_value, is_significant) — significant if mean1 > mean2
    """
    if n1 <= 1 or n2 <= 1:
        return 1.0, False

    adjusted_alpha = _adjusted(alpha, n_columns, apply_bonferroni)

    try:
        se = math.sqrt((std1 ** 2 / n1) + (std2 ** 2 / n2))
        if se <= 0:
            return 1.0, False
        t_stat = (mean1 - mean2) / se

        # Welch-Satterthwaite degrees of freedom
        num = ((std1 ** 2 / n1) + (std2 ** 2 / n2)) ** 2
        den = ((std1 ** 2 / n1) ** 2 / (n1 - 1)) + ((std2 ** 2 / n2) ** 2 / (n2 - 1))
        if den <= 0:
            return 1.0, False
        df = num / den

        p_val = 2 * stats.t.sf(abs(t_stat), df)
        is_sig = p_val < adjusted_alpha and mean1 > mean2
        return p_val, is_sig
    except (ZeroDivisionError, ValueError, FloatingPointError) as e:
        if warnings_list is not None:
            warnings_list.append(
                f"T-test failed for {variable} ({col_a} vs {col_b}): {e}"
            )
        else:
            logger.warning("T-test failed for %s (%s vs %s): %s", variable, col_a, col_b, e)
        return 1.0, False
