"""Edit a codebook with a list of operations (IMPLEMENTATION_PLAN.md M4.1).

Every edit is validated by applying the result to the file; an invalid edit raises
EditError with a message fit for the user. Operations (`var` = SPSS name, or a
multi-select's / ignored column's header):

  {"op": "set_label",      "var": v, "label": "…"}
  {"op": "set_role",       "var": v, "role": "single" | "text" | "numeric" | "ignore"}
  {"op": "set_measure",    "var": v, "measure": "nominal" | "ordinal" | "scale"}
  {"op": "relabel_code",   "var": v, "code": 3, "label": "…"}
  {"op": "set_missing",    "var": v, "code": 98, "missing": true}      # exclude from bases or not
  {"op": "merge_codes",    "var": v, "codes": [4, 5], "into": 4}
  {"op": "reorder_codes",  "var": v, "order": [codes or labels]}        # renumbers 1..n
  {"op": "set_codes",      "var": v, "map": [[old, new], …]}             # new values (reverse, mid-points)
  {"op": "set_nets",       "var": v, "nets": [{"label": "Top 2 Box", "codes": [4, 5]}, …]}  # table rows
                           (nets also work on a derived variable with categories: "var": its name)
  {"op": "add_net",        "var": v, "label": "Top 2 Box", "codes": [4, 5]}
  {"op": "remove_net",     "var": v, "label": "Top 2 Box"}
  {"op": "set_data_workbook", "settings": {title, drop_columns, groups, score_flags, tabs} | null}
  {"op": "add_derived",    "derived": {name?, label, rule, params, codes?, after?}}
  {"op": "update_derived", "name": n, "derived": {…}}
  {"op": "remove_derived", "name": n}
"""

from typing import Any

import pandas as pd

from services.codebook.apply import apply_codebook, clean_text
from services.codebook.heuristics import MAX_CATEGORIES, _merge_case_variants, _natural_key, _spss_name
from services.codebook.model import Code, Codebook, DataWorkbook, Derived, Inferred, Net, Option, Variable
from services.codebook.rules import Context, RuleError, coalesce_refs, multi_output_labels


class EditError(ValueError):
    """An edit that can't be applied (unknown variable, invalid rule, …)."""


def apply_ops(codebook: Codebook, ops: list[dict[str, Any]], df: pd.DataFrame) -> Codebook:
    """Return a new codebook with `ops` applied; raises EditError if any is invalid."""
    cb = codebook.model_copy(deep=True)
    for i, op in enumerate(ops):
        kind = op.get("op")
        handler = _OPS.get(kind)
        if handler is None:
            raise EditError(f"Edit {i + 1}: unknown operation '{kind}'")
        try:
            handler(cb, op, df)
        except EditError as e:
            raise EditError(f"Edit {i + 1} ({kind}): {e}") from None
        except (KeyError, TypeError) as e:
            raise EditError(f"Edit {i + 1} ({kind}): missing or invalid field {e}") from None
    _validate(cb, df)
    return cb


def _validate(cb: Codebook, df: pd.DataFrame) -> None:
    names = [n.lower() for n in cb.output_names()]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise EditError(f"Variable names used twice: {', '.join(dupes)}")
    try:
        apply_codebook(df, cb)
    except (RuleError, ValueError) as e:
        raise EditError(str(e)) from None


# ── helpers ──────────────────────────────────────────────────────────────────

def _var(cb: Codebook, ref: str) -> Variable:
    var = cb.find(ref) or next((v for v in cb.variables if v.column == ref or v.column.strip() == ref), None)
    if var is None:
        raise EditError(f"no variable or column '{ref}'")
    return var


def _used_names(cb: Codebook) -> set[str]:
    names = {v.name for v in cb.variables if v.name}
    names |= {o.name for v in cb.variables for o in v.options}
    names |= {n for d in cb.derived for n in [d.name, *[o.name for o in d.outputs]]}
    return {n.lower() for n in names}


def _code(var: Variable, value: Any) -> Code:
    """A number is a code value (labels can be numbers too: code 6 may read "7"); a string is a label."""
    codes = [*var.codes, *var.missing]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        match = next((c for c in codes if c.code == float(value)), None)
    else:
        match = next((c for c in codes if str(value).casefold() == c.label.casefold()), None)
    if match is None:
        raise EditError(f"'{value}' is not a code of '{var.name or var.column}'")
    return match


def _pin(var: Variable, code: Code) -> None:
    """Remember which raw answer a code stands for before its label or value changes."""
    if not code.match:
        code.match = [f"{code.code:g}"] if var.source in ("number", "bool") else [code.label]


def _holds(codes: list[Code], code: Code) -> bool:
    return any(c is code for c in codes)


def _remap_nets(var: Variable, mapping: dict[float, float | None]) -> None:
    """Keep nets pointing at the same answers after codes change (None = answer left the base)."""
    for net in var.nets:
        codes = [mapping.get(c, c) for c in net.codes]
        net.codes = list(dict.fromkeys(c for c in codes if c is not None))
    var.nets = [n for n in var.nets if n.codes]


def _needs_codes(var: Variable):
    if var.role not in ("single", "numeric") or not (var.codes or var.missing):
        raise EditError(f"'{var.name or var.column}' has no codes to edit")


# ── operations ───────────────────────────────────────────────────────────────

def _set_label(cb, op, df):
    _var(cb, op["var"]).label = str(op["label"]).strip() or _var(cb, op["var"]).label


def _set_measure(cb, op, df):
    if op["measure"] not in ("nominal", "ordinal", "scale"):
        raise EditError("measure must be nominal, ordinal or scale")
    _var(cb, op["var"]).measure = op["measure"]


def _set_role(cb, op, df):
    var, role = _var(cb, op["var"]), op["role"]
    if role not in ("single", "text", "numeric", "ignore"):
        raise EditError("role must be single, text, numeric or ignore")
    if role == var.role:
        return
    var.nets = []
    if role == "ignore":
        var.role = "ignore"
        return
    if var.role == "multi":
        raise EditError("a multi-select can only be ignored (splitting/joining arrives later)")
    if not var.name:
        var.name = _spss_name(var.column.strip(), _used_names(cb))
    column = next((c for c in df.columns if str(c) == var.column), None)
    if column is None:
        raise EditError(f"column '{var.column}' is not in this file")
    series = df[column]
    manual = Inferred(rule="manual", reason=f"Set to {role} by a reviewer")
    if role == "text":
        var.role, var.measure, var.codes, var.missing, var.value_labels = "text", "nominal", [], [], None
        var.source = var.source if var.source in ("number", "datetime", "bool") else "text"
        var.inferred = manual
    elif role == "numeric":
        var.role, var.measure, var.codes, var.missing, var.value_labels = "numeric", "scale", [], [], None
        var.source = "number" if pd.api.types.is_numeric_dtype(series) else "text"
        var.inferred = manual
    else:  # single: code the distinct answers in natural order
        if pd.api.types.is_numeric_dtype(series):
            values = sorted(series.dropna().unique())
            if len(values) > MAX_CATEGORIES:
                raise EditError(f"{len(values)} distinct values: too many to code (max {MAX_CATEGORIES})")
            var.codes = [Code(code=float(v), label=f"{v:g}") for v in values]
            var.source = "number"
        else:
            raw_text = clean_text(series)
            text = _merge_case_variants(raw_text)
            categories = sorted(text.dropna().unique(), key=_natural_key)
            if len(categories) > MAX_CATEGORIES:
                raise EditError(f"{len(categories)} different answers: too many to code (max {MAX_CATEGORIES})")
            spellings: dict[str, set[str]] = {}
            for spelling, canonical in zip(raw_text, text):
                if isinstance(spelling, str):
                    spellings.setdefault(canonical, set()).add(spelling)
            var.codes = [Code(code=float(i + 1), label=c, match=sorted(spellings.get(c, {c})))
                         for i, c in enumerate(categories)]
            var.source = "text"
        var.role, var.measure, var.missing, var.value_labels, var.inferred = "single", "nominal", [], None, manual


def _relabel_code(cb, op, df):
    var = _var(cb, op["var"])
    _needs_codes(var)
    code = _code(var, op["code"])
    _pin(var, code)  # keep matching the raw answer after renaming the label
    code.label = str(op["label"]).strip() or code.label
    if var.value_labels is not None:
        var.value_labels[repr(code.code)] = code.label


def _set_missing(cb, op, df):
    var = _var(cb, op["var"])
    _needs_codes(var)
    code = _code(var, op["code"])
    make_missing = bool(op.get("missing", True))
    if make_missing and _holds(var.codes, code):
        var.codes = [c for c in var.codes if c is not code]
        var.missing.append(code)
        _remap_nets(var, {code.code: None})  # out of the base, so out of its nets
    elif not make_missing and _holds(var.missing, code):
        var.missing = [c for c in var.missing if c is not code]
        var.codes.append(code)
    var.codes.sort(key=lambda c: c.code)
    var.missing.sort(key=lambda c: c.code)


def _merge_codes(cb, op, df):
    var = _var(cb, op["var"])
    _needs_codes(var)
    target = _code(var, op["into"])
    _pin(var, target)
    for value in op["codes"]:
        code = _code(var, value)
        if code is target:
            continue
        _pin(var, code)
        target.match = sorted({*target.match, *code.match})
        _remap_nets(var, {code.code: target.code})
        var.codes = [c for c in var.codes if c is not code]
        var.missing = [c for c in var.missing if c is not code]


def _reorder_codes(cb, op, df):
    var = _var(cb, op["var"])
    _needs_codes(var)
    ordered = [_code(var, v) for v in op["order"]]
    if {id(c) for c in ordered} != {id(c) for c in var.codes}:
        raise EditError("order must list every (non-missing) code exactly once")
    used = {m.code for m in var.missing}
    mapping = {}
    for i, code in enumerate(ordered):
        _pin(var, code)
        new = float(i + 1)
        if new in used:
            raise EditError(f"code {new:g} is already used by a missing code")
        mapping[code.code] = new
        code.code = new
    _remap_nets(var, mapping)
    var.codes = ordered


def _set_codes(cb, op, df):
    """Give answers new values (codes): reverse a scale, mid-points for averages, a custom order."""
    var = _var(cb, op["var"])
    _needs_codes(var)
    pairs = []
    for old, new in op["map"]:
        try:
            new = float(new)
        except (TypeError, ValueError):
            raise EditError(f"'{new}' is not a number") from None
        if not new == new or new in (float("inf"), float("-inf")):
            raise EditError(f"'{new}' is not a valid value")
        pairs.append((_code(var, old), new))
    final = {id(c): c.code for c in [*var.codes, *var.missing]}
    for code, new in pairs:
        final[id(code)] = new
    values = list(final.values())
    dupes = sorted({v for v in values if values.count(v) > 1})
    if dupes:
        raise EditError(f"two answers would share the value {', '.join(f'{d:g}' for d in dupes)}")
    _remap_nets(var, {code.code: new for code, new in pairs})
    for code, new in pairs:
        _pin(var, code)
        if var.value_labels is not None:
            var.value_labels.pop(repr(code.code), None)
            var.value_labels[repr(new)] = code.label
        code.code = new
    var.codes.sort(key=lambda c: c.code)
    var.missing.sort(key=lambda c: c.code)


def _net_target(cb: Codebook, ref: str) -> "Variable | Derived":
    """The variable or derived variable a net belongs to; it must have categories."""
    d = cb.find_derived(ref)
    if d is not None:
        if not d.codes:
            raise EditError(f"'{d.name}' has no categories to net")
        return d
    var = _var(cb, ref)
    _needs_codes(var)
    return var


def _net(var: "Variable | Derived", spec: dict) -> Net:
    label = str(spec.get("label") or "").strip()
    if not label:
        raise EditError("a net needs a label")
    codes = []
    for value in spec.get("codes") or []:
        code = _code(var, value) if isinstance(var, Variable) else _derived_code(var, value)
        if not _holds(var.codes, code):
            raise EditError(f"'{code.label}' is excluded from the base, so it can't be in a net")
        codes.append(code.code)
    if not codes:
        raise EditError(f"net '{label}' needs at least one answer")
    return Net(label=label, codes=list(dict.fromkeys(codes)))


def _derived_code(d: Derived, value: Any) -> Code:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        match = next((c for c in d.codes if c.code == float(value)), None)
    else:
        match = next((c for c in d.codes if str(value).casefold() == c.label.casefold()), None)
    if match is None:
        raise EditError(f"'{value}' is not a category of '{d.name}'")
    return match


def _check_net_labels(var: "Variable | Derived") -> None:
    labels = [n.label.casefold() for n in var.nets]
    dupes = sorted({n.label for n in var.nets if labels.count(n.label.casefold()) > 1})
    if dupes:
        raise EditError(f"two nets are called {', '.join(dupes)}")


def _set_nets(cb, op, df):
    var = _net_target(cb, op["var"])
    var.nets = [_net(var, n) for n in op["nets"]]
    _check_net_labels(var)


def _add_net(cb, op, df):
    var = _net_target(cb, op["var"])
    var.nets.append(_net(var, op))
    _check_net_labels(var)


def _set_data_workbook(cb, op, df):
    """The respondent-level data sheets (services.data_workbook); null switches them off."""
    settings = op.get("settings")
    if settings is None:
        cb.data_workbook = None
        return
    try:
        cb.data_workbook = DataWorkbook.model_validate(settings)
    except Exception as e:
        raise EditError(f"invalid data workbook settings: {e}") from None
    for tab in cb.data_workbook.tabs:
        if tab.when is None and (tab.var is None or tab.code is None):
            raise EditError(f"tab '{tab.title}' needs a variable and a category (or a condition)")


def _remove_net(cb, op, df):
    var = cb.find_derived(op["var"]) or _var(cb, op["var"])
    label = str(op["label"]).casefold()
    if not any(n.label.casefold() == label for n in var.nets):
        raise EditError(f"no net '{op['label']}' on '{var.name or var.column}'")
    var.nets = [n for n in var.nets if n.label.casefold() != label]


def _build_derived(cb: Codebook, spec: dict, df: pd.DataFrame, name: str | None = None) -> Derived:
    spec = dict(spec)
    label = str(spec.get("label") or "").strip()
    if not label:
        raise EditError("a derived variable needs a label")
    if not name:
        name = spec.get("name") or _spss_name(label, _used_names(cb))
    spec["name"] = name
    spec.setdefault("codes", [])
    spec.setdefault("inferred", {"rule": "manual", "reason": f"Added by a reviewer ({spec.get('rule')})"})
    try:
        d = Derived.model_validate({k: v for k, v in spec.items() if k != "outputs"})
    except Exception as e:
        raise EditError(f"invalid derived variable: {e}") from None
    if not d.codes:
        # Categories from the rule definition, so bands/groups/combos needn't repeat them
        for key in ("bands", "groups", "combos"):
            items = d.params.get(key) or []
            d.codes = [Code(code=float(i["code"]), label=str(i["label"])) for i in items
                       if isinstance(i, dict) and "code" in i and "label" in i]
            if d.codes:
                break
        fallback = d.params.get("else")
        if isinstance(fallback, dict) and "code" in fallback:
            d.codes.append(Code(code=float(fallback["code"]), label=str(fallback["label"])))
    if d.rule in ("coalesce", "flags"):
        coded = apply_codebook(df, cb)
        ctx = Context(cb, coded.columns, pd.RangeIndex(len(next(iter(coded.columns.values()), []))))
        used = _used_names(cb)
        try:
            labels = multi_output_labels(d, ctx)
            singles = d.rule == "coalesce" and not coalesce_refs(d, ctx)[1]
        except RuleError as e:
            raise EditError(str(e)) from None
        d.outputs = [Option(label=lab, name=_spss_name(f"{d.name}_{lab}", used)) for lab in labels]
        if singles and not d.codes:
            _inherit_categories(cb, d)
    return d


def _inherit_categories(cb: Codebook, d: Derived) -> None:
    """A combined single question keeps its sources' answers (first source's label wins)."""
    codes: dict[float, Code] = {}
    measure = None
    for ref in d.params.get("from") or [d.source]:
        src = cb.find(ref) or cb.find_derived(ref)
        for c in (src.codes if src else []):
            codes.setdefault(c.code, Code(code=c.code, label=c.label))
        measure = measure or (src.measure if src else None)
    d.codes = [codes[k] for k in sorted(codes)]
    if measure in ("nominal", "ordinal"):
        d.measure = measure


def _add_derived(cb, op, df):
    d = _build_derived(cb, op["derived"], df)
    if d.name.lower() in _used_names(cb):
        raise EditError(f"name '{d.name}' is already used")
    cb.derived.append(d)


def _update_derived(cb, op, df):
    current = cb.find_derived(op["name"])
    if current is None:
        raise EditError(f"no derived variable '{op['name']}'")
    index = cb.derived.index(current)
    spec = dict(op["derived"])
    spec.setdefault("after", current.after)  # an edit keeps the variable where it was
    spec.setdefault("source", current.source)
    spec.setdefault("inferred", {"rule": "manual", "reason": f"Edited by a reviewer ({spec.get('rule')})"})
    cb.derived.pop(index)
    try:
        cb.derived.insert(index, _build_derived(cb, spec, df, name=spec.get("name") or current.name))
    except EditError:
        cb.derived.insert(index, current)
        raise


def _remove_derived(cb, op, df):
    current = cb.find_derived(op["name"])
    if current is None:
        raise EditError(f"no derived variable '{op['name']}'")
    cb.derived.remove(current)


_OPS = {
    "set_label": _set_label, "set_role": _set_role, "set_measure": _set_measure,
    "relabel_code": _relabel_code, "set_missing": _set_missing, "merge_codes": _merge_codes,
    "reorder_codes": _reorder_codes, "set_codes": _set_codes, "set_nets": _set_nets, "add_net": _add_net,
    "remove_net": _remove_net, "set_data_workbook": _set_data_workbook, "add_derived": _add_derived, "update_derived": _update_derived,
    "remove_derived": _remove_derived,
}
