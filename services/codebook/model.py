"""The codebook: every decision about how a raw survey file becomes coded data.

Inferred automatically (services.codebook.infer), applied deterministically
(services.codebook.apply), and returned by the API so users can see — and later
edit — how each column was understood. See PLAN_ANY_FORMAT.md §4.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["id", "pii", "date", "weight", "single", "multi", "numeric", "text", "ignore"]
Measure = Literal["nominal", "ordinal", "scale"]


class Inferred(BaseModel):
    """Why the inference made a decision (shown in the review UI)."""
    rule: str
    reason: str
    confidence: float = 1.0


class Code(BaseModel):
    code: float
    label: str
    match: list[str] = Field(default_factory=list, description="Raw answers coded to this value")
    count: int | None = Field(None, description="Respondents with this code (filled for review)")


class Net(BaseModel):
    """A table row adding up several answers, e.g. Top 2 Box = 4 + 5 (no new variable)."""
    label: str
    codes: list[float]


class Option(BaseModel):
    """One option of a multi-select question, stored as a 0/1 variable."""
    label: str
    name: str
    count: int | None = None


class Variable(BaseModel):
    column: str = Field(description="Header in the uploaded file")
    name: str | None = Field(None, description="SPSS variable name (None when not output)")
    label: str
    role: Role
    measure: Measure | None = None
    codes: list[Code] = Field(default_factory=list, description="Valid codes (value labels)")
    missing: list[Code] = Field(default_factory=list, description="User-missing codes (excluded from bases)")
    value_labels: dict[str, str] | None = Field(
        None, description="Explicit value labels overriding `codes` (e.g. from a Value Labels sheet)")
    nets: list[Net] = Field(default_factory=list, description="Net rows shown in tables (e.g. Top 2 Box)")
    delimiter: str | None = None              # multi
    options: list[Option] = Field(default_factory=list)  # multi
    source: Literal["number", "text", "bool", "datetime"] | None = None
    tags: list[str] = Field(default_factory=list)
    inferred: Inferred | None = None
    status: Literal["ok", "needs_review", "new"] = "ok"
    base: int | None = Field(None, description="Respondents who answered (filled for review)")

    def anchor(self) -> str | None:
        """Last SPSS variable this column produces (derived variables can be placed after it)."""
        if self.role == "ignore":
            return None
        return self.options[-1].name if self.role == "multi" and self.options else self.name


DerivedRule = Literal["recode", "bands", "priority", "count", "combination", "coalesce", "flags"]


class Derived(BaseModel):
    """A variable computed from others by a rule (PLAN_ANY_FORMAT.md §5, services.codebook.rules)."""
    name: str
    label: str
    rule: DerivedRule
    source: str = Field("", description="Main input: a variable name, or a multi-select's column/label")
    after: str | None = Field(None, description="Output position: right after this variable (None = at the end)")
    params: dict[str, Any] = Field(default_factory=dict)
    codes: list[Code] = Field(default_factory=list, description="Categories of a single-variable result")
    outputs: list[Option] = Field(default_factory=list, description="0/1 variables of a multi-variable result")
    nets: list[Net] = Field(default_factory=list, description="Net rows shown in tables (single results only)")
    measure: Measure = "nominal"
    inferred: Inferred | None = None

    def output_names(self) -> list[str]:
        return [o.name for o in self.outputs] if self.outputs else [self.name]


class SheetColumn(BaseModel):
    """An extra column of the data workbook (services.data_workbook)."""
    header: str = ""
    var: str | None = Field(None, description="Variable / derived name: its value, or a flag with `code`")
    code: float | None = Field(None, description="1 where `var` has this code")
    when: dict[str, Any] | None = Field(None, description="1 where this condition holds (rule conditions)")
    flags_of: str | None = Field(None, description="One flag column per answer / option of this variable")
    headers: dict[str, str] = Field(default_factory=dict, description="flags_of: header per answer label or code")
    order: list[str] = Field(default_factory=list, description="flags_of: answers containing these words first, in order")
    last: list[str] = Field(default_factory=list, description="flags_of: these answers at the end")
    count: str | None = Field(None, description="Number of options ticked of this multi-select")
    exclude: list[str] = Field(default_factory=list, description="count: options not counted")
    first_of: list[str] | None = Field(None, description="The first answered of these file columns, as answered")
    total: Literal["SUM", "COUNT"] | None = None


class ColumnGroup(BaseModel):
    after: str = Field(description="File column the extra columns follow")
    columns: list[SheetColumn]


class SheetTab(BaseModel):
    """A sheet with just the respondents of one category."""
    title: str
    var: str | None = None
    code: float | None = None
    when: dict[str, Any] | None = None


class DataWorkbook(BaseModel):
    """Respondent-level FULL DATA sheet + category tabs (RECODING_PLAN.md §7)."""
    title: str = "FULL DATA"
    drop_columns: list[str] = Field(default_factory=list, description="File columns left out")
    groups: list[ColumnGroup] = Field(default_factory=list)
    score_flags: tuple[int, int] | None = Field(None, description="[lo, hi]: a flag per score after each rating")
    percent_row: bool = Field(True, description="A % row above the counts row")
    tabs: list[SheetTab] = Field(default_factory=list)


class Source(BaseModel):
    format: str
    adapter: str = "generic"
    rows: int = 0
    columns: int = 0


class Codebook(BaseModel):
    version: int = 0
    source: Source
    variables: list[Variable]
    derived: list[Derived] = Field(default_factory=list)
    data_workbook: DataWorkbook | None = Field(None, description="FULL DATA sheet + category tabs, if wanted")

    def variable(self, name: str) -> Variable | None:
        return next((v for v in self.variables if v.name == name), None)

    def output_names(self) -> list[str]:
        """SPSS variables produced, in file order."""
        names: list[str] = []
        for var in self.variables:
            anchor = var.anchor()
            if anchor is None:
                continue
            names += [o.name for o in var.options] if var.role == "multi" else [var.name]
            names += [n for d in self.derived if d.after == anchor for n in d.output_names()]
        names += [n for d in self.derived if d.after is None for n in d.output_names()]
        return names

    def find(self, ref: str) -> "Variable | None":
        """A variable by SPSS name, or a multi-select by its column or label."""
        for var in self.variables:
            if var.name == ref or (var.role == "multi" and ref in (var.column, var.column.strip(), var.label)):
                return var
        return None

    def table_nets(self, explicit: dict | None = None) -> dict[str, dict[str, list]]:
        """Nets for TabulateSpec.nets: {variable: {net label: [codes]}}; `explicit` (a request's own) wins."""
        nets = {v.name: {n.label: [int(c) if float(c).is_integer() else c for c in n.codes] for n in v.nets}
                for v in [*self.variables, *self.derived] if v.name and v.nets}
        return {**nets, **(explicit or {})}

    def find_derived(self, name: str) -> "Derived | None":
        return next((d for d in self.derived if d.name == name), None)
