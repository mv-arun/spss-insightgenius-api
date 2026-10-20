"""Derived-variable rules (PLAN_ANY_FORMAT.md §5): survey-specific logic as data, not code.

Seven rule types cover what analysts build by hand in Excel:

  recode       merge categories        {"from": var, "groups": [{"code", "label", "values": [codes|labels]}],
                                         "else": {"code", "label"} (optional: everything else answered)}
  bands        numeric ranges          {"from": var, "bands": [{"code", "label", "min", "max"}]}
  priority     first match wins        {"groups": [{"code", "label", "when": Cond}], "else": {"code", "label"}|null,
                                         "base": var}
  count        options ticked          {"from": multi, "exclude": [labels], "bands": [...] (optional)}
  combination  exact set ticked        {"from": multi, "combos": [{"code", "label", "exact"|"within": [labels]}],
                                         "ignore": [labels]}
  coalesce     first answered of       {"from": [multi, multi, ...]}  → one 0/1 variable per option
                                        {"from": [single, single, ...]} → one variable (the same question
                                         asked of different groups, e.g. age per condition)
  flags        one 0/1 per answer      {"from": var, "values": [codes|labels] (optional)}

Conditions (no eval — a fixed vocabulary evaluated with pandas masks):
  {"var": v, "any": [labels]}   {"var": v, "all": [labels]}   {"var": v, "none": [labels]}
  {"var": v, "in": [codes|labels]}   {"var": v, "between": [lo, hi]}   {"answered": v}
  {"and": [conds]}   {"or": [conds]}   {"not": cond}
`var` is a variable name, a derived variable, or a multi-select's column/label.
"""

from typing import Any

import pandas as pd

from services.codebook.model import Codebook, Derived

Output = tuple[str, str, pd.Series, dict[float, str] | None, str]  # name, label, values, value labels, measure


class RuleError(ValueError):
    """A derived rule refers to something that doesn't exist or is malformed."""


class Context:
    """Coded columns produced so far + the codebook, for resolving references."""

    def __init__(self, codebook: Codebook, columns: dict[str, pd.Series], index: pd.Index):
        self.codebook, self.columns, self.index = codebook, columns, index

    def is_multi(self, ref: str) -> bool:
        var = self.codebook.find(ref)
        if var is not None:
            return var.role == "multi"
        d = self.codebook.find_derived(ref)
        return bool(d and d.outputs)

    def options(self, ref: str) -> dict[str, pd.Series]:
        """Option label → 0/1 series of a multi-select (or a derived multi result)."""
        var = self.codebook.find(ref)
        if var is not None and var.role == "multi":
            return {o.label: self._column(o.name, ref) for o in var.options}
        d = self.codebook.find_derived(ref)
        if d is not None and d.outputs:
            return {o.label: self._column(o.name, ref) for o in d.outputs}
        raise RuleError(f"'{ref}' is not a multi-select question")

    def series(self, ref: str) -> pd.Series:
        var = self.codebook.find(ref)
        if var is not None and var.role == "multi":
            raise RuleError(f"'{ref}' is a multi-select: use any/all/none on its options")
        if var is not None and var.role == "ignore":
            raise RuleError(f"'{ref}' is ignored, so it can't be used in a rule")
        return self._column(var.name if var is not None else ref, ref)

    def answered(self, ref: str) -> pd.Series:
        if self.is_multi(ref):
            flags = list(self.options(ref).values())
            return pd.concat(flags, axis=1).notna().any(axis=1) if flags else pd.Series(False, index=self.index)
        return self.series(ref).notna()

    def codes(self, ref: str, values: list[Any]) -> list[float]:
        """Codes for a mix of numeric codes and answer labels."""
        var = self.codebook.find(ref)
        d = self.codebook.find_derived(ref)
        known = [*(var.codes + var.missing if var else []), *(d.codes if d else [])]
        by_label = {c.label.casefold(): c.code for c in known}
        out = []
        for v in values:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append(float(v))
            elif str(v).casefold() in by_label:
                out.append(by_label[str(v).casefold()])
            else:
                raise RuleError(f"'{v}' is not an answer of '{ref}'")
        return out

    def _column(self, name: str | None, ref: str) -> pd.Series:
        if name is None or name not in self.columns:
            raise RuleError(f"Unknown variable '{ref}' (or it is defined later in the file)")
        return self.columns[name]


# ── conditions ───────────────────────────────────────────────────────────────

def evaluate(cond: dict, ctx: Context) -> pd.Series:
    """Boolean mask; unanswered values count as False."""
    if not isinstance(cond, dict) or not cond:
        raise RuleError(f"Invalid condition: {cond!r}")
    if "and" in cond:
        return _combine([evaluate(c, ctx) for c in cond["and"]], all_=True, index=ctx.index)
    if "or" in cond:
        return _combine([evaluate(c, ctx) for c in cond["or"]], all_=False, index=ctx.index)
    if "not" in cond:
        return ~evaluate(cond["not"], ctx)
    if "answered" in cond:
        return ctx.answered(cond["answered"])

    ref = cond.get("var")
    if not ref:
        raise RuleError(f"Condition needs 'var': {cond!r}")
    if ctx.is_multi(ref):
        options = ctx.options(ref)
        ticked = {}
        for key in ("any", "all", "none"):
            for label in cond.get(key, []):
                if label not in options:
                    raise RuleError(f"'{label}' is not an option of '{ref}'")
                ticked[label] = options[label].eq(1)
        if "any" in cond:
            return _combine([ticked[l] for l in cond["any"]], all_=False, index=ctx.index)
        if "all" in cond:
            return _combine([ticked[l] for l in cond["all"]], all_=True, index=ctx.index)
        if "none" in cond:
            return ctx.answered(ref) & ~_combine([ticked[l] for l in cond["none"]], all_=False, index=ctx.index)
        raise RuleError(f"Multi-select conditions use any / all / none: {cond!r}")

    series = ctx.series(ref)
    if "between" in cond:
        lo, hi = cond["between"]
        return series.between(lo, hi).fillna(False)
    for key in ("in", "any"):
        if key in cond:
            return series.isin(ctx.codes(ref, cond[key]))
    if "none" in cond:
        return series.notna() & ~series.isin(ctx.codes(ref, cond["none"]))
    raise RuleError(f"Unsupported condition: {cond!r}")


def references(cond: Any) -> set[str]:
    """Variables a condition (or rule params) mentions."""
    if isinstance(cond, dict):
        found = {cond[k] for k in ("var", "answered") if isinstance(cond.get(k), str)}
        for v in cond.values():
            found |= references(v)
        return found
    if isinstance(cond, list):
        return set().union(*(references(c) for c in cond)) if cond else set()
    return set()


def _combine(masks: list[pd.Series], all_: bool, index: pd.Index) -> pd.Series:
    if not masks:
        return pd.Series(all_, index=index)
    out = masks[0].fillna(False).astype(bool)
    for m in masks[1:]:
        out = (out & m.fillna(False).astype(bool)) if all_ else (out | m.fillna(False).astype(bool))
    return out


# ── rules ────────────────────────────────────────────────────────────────────

def compute(d: Derived, ctx: Context) -> list[Output]:
    """Evaluate one derived rule → output variable(s)."""
    try:
        fn = _RULES[d.rule]
    except KeyError:
        raise RuleError(f"Unknown rule '{d.rule}'") from None
    return fn(d, ctx)


def _single(d: Derived, values: pd.Series) -> list[Output]:
    labels = {c.code: c.label for c in d.codes} or None
    return [(d.name, d.label, values, labels, d.measure if labels else "scale")]


def _from(d: Derived) -> Any:
    ref = d.params.get("from", d.source)
    if not ref:
        raise RuleError(f"Rule '{d.name}' needs a 'from' variable")
    return ref


def _recode(d: Derived, ctx: Context) -> list[Output]:
    ref = _from(d)
    src = ctx.series(ref)
    out = pd.Series(float("nan"), index=src.index)
    for group in d.params.get("groups", []):
        out[src.isin(ctx.codes(ref, group.get("values", [])))] = float(group["code"])
    fallback = d.params.get("else")
    if fallback:  # answers not put in any group → e.g. "Other" (else they stay missing)
        var = ctx.codebook.find(ref)
        excluded = {m.code for m in var.missing} if var else set()  # "Don't know" etc. stay out unless grouped
        out[src.notna() & ~src.isin(excluded) & out.isna()] = float(fallback["code"])
    return _single(d, out)


def _bands(d: Derived, ctx: Context) -> list[Output]:
    ref = _from(d)
    src = ctx.series(ref)
    var = ctx.codebook.find(ref)
    missing = {m.code for m in var.missing} if var else set()
    valid = src.where(~src.isin(missing))
    out = pd.Series(float("nan"), index=valid.index)
    for band in d.params.get("bands", []):
        lo = band.get("min", float("-inf"))
        hi = band.get("max", float("inf"))
        out[(valid >= (lo if lo is not None else float("-inf"))) &
            (valid <= (hi if hi is not None else float("inf")))] = float(band["code"])
    return _single(d, out)


def _priority(d: Derived, ctx: Context) -> list[Output]:
    groups = d.params.get("groups", [])
    base_ref = d.params.get("base") or d.source
    if not base_ref:
        refs = sorted(references(groups))
        if not refs:
            raise RuleError(f"Rule '{d.name}' needs a 'base' variable")
        base_ref = refs[0]
    answered = ctx.answered(base_ref)
    out = pd.Series(float("nan"), index=ctx.index)
    fallback = d.params.get("else")
    if fallback:
        out[answered] = float(fallback["code"])
    for group in reversed(groups):  # earlier groups win
        out[answered & evaluate(group["when"], ctx)] = float(group["code"])
    return _single(d, out)


def _ticked(d: Derived, ctx: Context, drop: list[str]) -> tuple[pd.Series, pd.Series]:
    """Per row: frozenset of ticked option labels (minus `drop`), and whether answered."""
    ref = _from(d)
    options = {k: v for k, v in ctx.options(ref).items() if k not in set(drop)}
    answered = ctx.answered(ref)
    frame = pd.DataFrame({k: v.eq(1) for k, v in options.items()}, index=ctx.index)
    ticked = frame.apply(lambda row: frozenset(row.index[row.values]), axis=1) if len(frame.columns) else \
        pd.Series([frozenset()] * len(ctx.index), index=ctx.index)
    return ticked, answered


def _count(d: Derived, ctx: Context) -> list[Output]:
    ticked, answered = _ticked(d, ctx, d.params.get("exclude", []))
    n = ticked.map(len).astype(float).where(answered)
    bands = d.params.get("bands")
    if not bands:
        return [(d.name, d.label, n, None, "scale")]
    out = pd.Series(float("nan"), index=n.index)
    for band in bands:
        lo, hi = band.get("min"), band.get("max")
        out[(n >= (lo if lo is not None else float("-inf"))) & (n <= (hi if hi is not None else float("inf")))] = \
            float(band["code"])
    return _single(d, out)


def _combination(d: Derived, ctx: Context) -> list[Output]:
    ticked, answered = _ticked(d, ctx, d.params.get("ignore", []))
    out = pd.Series(float("nan"), index=ticked.index)
    for combo in reversed(d.params.get("combos", [])):  # earlier combos win
        if "exact" in combo:
            target = frozenset(combo["exact"])
            hit = ticked.map(lambda s, t=target: s == t)
        elif "within" in combo:
            allowed = frozenset(combo["within"])
            hit = ticked.map(lambda s, a=allowed: bool(s) and s <= a)
        else:
            raise RuleError(f"Combination '{combo.get('label')}' needs 'exact' or 'within'")
        out[answered & hit.astype(bool)] = float(combo["code"])
    return _single(d, out)


def coalesce_refs(d: Derived, ctx: Context) -> tuple[list[str], bool]:
    """The variables a coalesce rule combines, and whether they are multi-selects (all or none)."""
    refs = d.params.get("from") or ([d.source] if d.source else [])
    if not refs:
        raise RuleError(f"Rule '{d.name}' needs 'from' variables")
    multi = [ctx.is_multi(r) for r in refs]
    if any(multi) and not all(multi):
        raise RuleError(f"Rule '{d.name}' mixes multi-select and single questions")
    return refs, all(multi)


def _coalesce(d: Derived, ctx: Context) -> list[Output]:
    refs, multi = coalesce_refs(d, ctx)
    if not multi:  # first answered value wins
        out = pd.Series(float("nan"), index=ctx.index)
        for ref in refs:
            out = out.fillna(ctx.series(ref))
        return _single(d, out)
    sources = [ctx.options(r) for r in refs]
    answered = [ctx.answered(r) for r in refs]
    outputs = []
    for opt in d.outputs:
        out = pd.Series(float("nan"), index=ctx.index)
        for flags, ans in zip(reversed(sources), reversed(answered)):  # first answered source wins
            if opt.label in flags:
                out[ans] = flags[opt.label][ans].fillna(0)
            else:
                out[ans] = 0.0
        outputs.append((opt.name, f"{d.label}: {opt.label}", out, {0.0: "Not selected", 1.0: "Selected"}, "nominal"))
    return outputs


def _flags(d: Derived, ctx: Context) -> list[Output]:
    ref = _from(d)
    src = ctx.series(ref)
    outputs = []
    for opt in d.outputs:
        code = ctx.codes(ref, [opt.label])[0]
        out = src.eq(code).astype(float).where(src.notna())
        outputs.append((opt.name, f"{d.label}: {opt.label}", out, {0.0: "Not selected", 1.0: "Selected"}, "nominal"))
    return outputs


_RULES = {
    "recode": _recode, "bands": _bands, "priority": _priority, "count": _count,
    "combination": _combination, "coalesce": _coalesce, "flags": _flags,
}


def multi_output_labels(d: Derived, ctx: Context) -> list[str]:
    """Option labels a coalesce/flags rule produces (used to name its outputs)."""
    if d.rule == "coalesce":
        refs, multi = coalesce_refs(d, ctx)
        if not multi:
            return []
        labels: list[str] = []
        for ref in refs:
            labels += [label for label in ctx.options(ref) if label not in labels]
        return labels
    if d.rule == "flags":
        ref = _from(d)
        var = ctx.codebook.find(ref)
        src = ctx.codebook.find_derived(ref)
        codes = var.codes if var else (src.codes if src else [])
        wanted = d.params.get("values")
        if wanted:
            keep = set(ctx.codes(ref, wanted))
            codes = [c for c in codes if c.code in keep]
        return [c.label for c in codes]
    return []
