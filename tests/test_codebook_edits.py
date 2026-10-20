"""Codebook editing + derived-variable rules (IMPLEMENTATION_PLAN.md M4)."""

import io
import json
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from services.codebook.apply import apply_codebook
from services.codebook.infer import infer_codebook
from services.codebook.patch import EditError, apply_ops
from services.data_loader import load_data
from services.ingest.readers import read_raw

FIXTURE = Path(__file__).parent / "fixtures" / "exports" / "hubspot_cx_sample.xlsx"
CLIENT_RULES = Path(__file__).parent / "fixtures" / "codebooks" / "cx_client_rules.json"
SAV = Path(__file__).parent / "fixtures" / "example3_raw.sav"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXAM = "Exam_Results_Alternative"


@pytest.fixture(scope="module")
def raw():
    return read_raw(FIXTURE.read_bytes(), FIXTURE.name)


@pytest.fixture(scope="module")
def cb(raw):
    return infer_codebook(raw)


def coded(raw, cb, edits):
    edited = apply_ops(cb, edits, raw.df)
    return edited, apply_codebook(raw.df, edited).columns


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    from middleware import rate_limiter
    yield
    rate_limiter._windows.clear()


# ── variable edits ───────────────────────────────────────────────────────────

def test_set_label_and_measure(raw, cb):
    edited, _ = coded(raw, cb, [{"op": "set_label", "var": EXAM, "label": "Results were fair"},
                                {"op": "set_measure", "var": EXAM, "measure": "ordinal"}])
    var = edited.variable(EXAM)
    assert (var.label, var.measure) == ("Results were fair", "ordinal")
    assert cb.variable(EXAM).label != "Results were fair"  # original untouched


def test_set_missing_moves_code_out_of_base(raw, cb):
    edited, cols = coded(raw, cb, [{"op": "set_missing", "var": EXAM, "code": "Neither agree or disagree"}])
    var = edited.variable(EXAM)
    assert 3.0 in [m.code for m in var.missing] and 3.0 not in [c.code for c in var.codes]
    data = load_data(FIXTURE.read_bytes(), FIXTURE.name, codebook=edited)
    assert 3.0 not in set(data.df[EXAM].dropna())  # user-missing → excluded on load
    assert (cols[EXAM] == 3.0).sum() == (raw.df["Exam Results Alternative"] == "Neither agree or disagree").sum()


def test_merge_codes_keeps_target_code(raw, cb):
    edited, cols = coded(raw, cb, [{"op": "merge_codes", "var": EXAM, "codes": ["Agree", "Strongly Agree"], "into": 4}])
    agree_raw = raw.df["Exam Results Alternative"].isin(["Agree", "Strongly Agree"]).sum()
    assert (cols[EXAM] == 4.0).sum() == agree_raw
    assert 5.0 not in [c.code for c in edited.variable(EXAM).codes]


def test_relabel_keeps_matching_raw_answer(raw, cb):
    edited, cols = coded(raw, cb, [{"op": "relabel_code", "var": EXAM, "code": 4, "label": "Agree (net)"}])
    assert (cols[EXAM] == 4.0).sum() == (raw.df["Exam Results Alternative"] == "Agree").sum()
    assert edited.variable(EXAM).codes[3].label == "Agree (net)"


def test_reorder_codes_renumbers(raw, cb):
    order = ["Strongly Agree", "Agree", "Neither agree or disagree", "Disagree", "Strongly Disagree"]
    edited, cols = coded(raw, cb, [{"op": "reorder_codes", "var": EXAM, "order": order}])
    assert [c.label for c in edited.variable(EXAM).codes] == order
    assert (cols[EXAM] == 1.0).sum() == (raw.df["Exam Results Alternative"] == "Strongly Agree").sum()


def test_set_role_ignore_and_text_and_single(raw, cb):
    edited, cols = coded(raw, cb, [{"op": "set_role", "var": "Source", "role": "ignore"},
                                   {"op": "set_role", "var": EXAM, "role": "text"},
                                   {"op": "set_role", "var": "Sentiment", "role": "single"}])
    assert "Source" not in cols and cols[EXAM].iloc[0] in set(raw.df["Exam Results Alternative"])
    assert [c.label for c in edited.variable("Sentiment").codes] == ["Not Applicable"]
    assert (cols["Sentiment"] == 1.0).all()


def test_set_role_single_refuses_open_text(raw, cb):
    with pytest.raises(EditError, match="too many to code"):
        apply_ops(cb, [{"op": "set_role", "var": "Centre_Name", "role": "single"}], raw.df)


def test_unknown_variable_and_op_rejected(raw, cb):
    with pytest.raises(EditError, match="no variable"):
        apply_ops(cb, [{"op": "set_label", "var": "Nope", "label": "x"}], raw.df)
    with pytest.raises(EditError, match="unknown operation"):
        apply_ops(cb, [{"op": "explode"}], raw.df)


# ── rules ────────────────────────────────────────────────────────────────────

def test_recode_and_bands(raw, cb):
    edits = [
        {"op": "add_derived", "derived": {"label": "Exam T2B", "rule": "recode", "params": {
            "from": EXAM, "groups": [{"code": 1, "label": "Agree (T2B)", "values": ["Agree", "Strongly Agree"]},
                                     {"code": 2, "label": "Other", "values": [1, 2, 3]}]}}},
        {"op": "add_derived", "derived": {"label": "NPS bands", "rule": "bands", "params": {
            "from": "CX_Pulse_Overall_NPS", "bands": [{"code": 1, "label": "Low", "min": 0, "max": 6},
                                                      {"code": 2, "label": "High", "min": 7, "max": 10}]}}},
    ]
    edited, cols = coded(raw, cb, edits)
    t2b = raw.df["Exam Results Alternative"].isin(["Agree", "Strongly Agree"]).sum()
    assert (cols["Exam_T2B"] == 1.0).sum() == t2b
    assert cols["Exam_T2B"].isna().sum() == raw.df["Exam Results Alternative"].str.contains("know|applicable").sum()
    assert (cols["NPS_bands"] == 2.0).sum() == (raw.df["CX Pulse Overall NPS"] >= 7).sum()
    assert [c.label for c in edited.find_derived("NPS_bands").codes] == ["Low", "High"]


def test_count_without_bands_is_numeric(raw, cb):
    _, cols = coded(raw, cb, [{"op": "add_derived", "derived": {
        "label": "Roles ticked", "rule": "count", "params": {"from": "Job role"}}}])
    expected = raw.df["Job role"].map(lambda v: len(v.split(";")))
    assert cols["Roles_ticked"].tolist() == expected.astype(float).tolist()


def test_invalid_rule_reference_rejected(raw, cb):
    with pytest.raises(EditError, match="not an option"):
        apply_ops(cb, [{"op": "add_derived", "derived": {"label": "x", "rule": "priority", "params": {
            "base": "Job role", "groups": [{"code": 1, "label": "a", "when": {"var": "Job role", "any": ["Pilot"]}}]}}}],
            raw.df)
    with pytest.raises(EditError, match="needs a label"):
        apply_ops(cb, [{"op": "add_derived", "derived": {"rule": "bands", "params": {}}}], raw.df)


def test_remove_and_update_derived(raw, cb):
    nps = cb.derived[-1].name
    edited, cols = coded(raw, cb, [{"op": "remove_derived", "name": nps}])
    assert nps not in cols
    edited, cols = coded(raw, cb, [{"op": "update_derived", "name": nps, "derived": {
        "label": "NPS 2 groups", "rule": "bands", "params": {
            "from": "CX_Pulse_Overall_NPS", "bands": [{"code": 1, "label": "0-8", "min": 0, "max": 8},
                                                      {"code": 2, "label": "9-10", "min": 9, "max": 10}]}}}])
    assert set(cols[nps].dropna()) == {1.0, 2.0}
    before, after = cb.find_derived(nps), edited.find_derived(nps)
    assert after.after == before.after and after.source == before.source  # stays in place
    assert after.inferred.reason.startswith("Edited")


def test_priority_and_combination_rules_built_in_the_ui(raw, cb):
    # The shape the review page's priority builder sends: OR of AND-ed condition rows
    role = "Job role"
    edited, cols = coded(raw, cb, [
        {"op": "add_derived", "derived": {"label": "Role (UI)", "rule": "priority", "params": {"base": role, "groups": [
            {"code": 1, "label": "Exams Officer", "when": {"var": role, "any": ["Exams Officer"]}},
            {"code": 2, "label": "Leader", "when": {"or": [
                {"var": role, "any": ["School Leader", "School Group/School District Leader"]},
                {"and": [{"var": role, "any": ["Head of Department"]}, {"var": role, "none": ["Teacher"]}]}]}},
            {"code": 3, "label": "Teacher", "when": {"var": role, "any": ["Teacher"]}}],
            "else": {"code": 4, "label": "Other"}}}},
        {"op": "add_derived", "derived": {"label": "Mix (UI)", "rule": "combination", "params": {
            "from": "Customer type", "ignore": [], "combos": [
                {"code": 1, "label": "Exams only", "exact": ["Exams or qualifications"]},
                {"code": 2, "label": "Programmes / exams", "within": ["Programmes or curriculum", "Exams or qualifications"]}]}}},
    ])
    client = json.loads(CLIENT_RULES.read_text(encoding="utf-8"))
    _, legacy = coded(raw, cb, client["edits"])
    role_ui = cols[edited.derived[-2].name]
    assert role_ui.fillna(-1).equals(legacy["Role_group"].fillna(-1))
    mix = cols[edited.derived[-1].name]
    assert set(mix.dropna()) <= {1.0, 2.0} and (mix == 1).sum() > 0


def test_name_collision_rejected(raw, cb):
    with pytest.raises(EditError, match="already used"):
        apply_ops(cb, [{"op": "add_derived", "derived": {"name": EXAM, "label": "dup", "rule": "flags",
                                                          "params": {"from": EXAM}}}], raw.df)


# ── the client rules, as data ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client_coded(raw, cb):
    edits = json.loads(CLIENT_RULES.read_text(encoding="utf-8"))["edits"]
    edited = apply_ops(cb, edits, raw.df)
    return edited, apply_codebook(raw.df, edited).columns


def _ticked(series: pd.Series) -> list[set[str]]:
    return [{o.strip() for o in str(v).split(";") if o.strip()} if pd.notna(v) else set() for v in series]


def _analyst_role(roles: set[str]) -> float | None:
    """The analysts' written rule: EO > Leader (incl. HoD who isn't a Teacher) > Teacher > Other."""
    if not roles:
        return None
    if "Exams Officer" in roles:
        return 1.0
    if roles & {"School Leader", "School Group/School District Leader"} or ("Head of Department" in roles and "Teacher" not in roles):
        return 2.0
    return 3.0 if "Teacher" in roles else 4.0


PRODUCTS = {"Resources": "Teaching and learning resources such as textbooks, digital tools, or curriculum support",
            "Programmes": "Programmes or curriculum", "Exams": "Exams or qualifications"}


def test_client_role_rule_matches_the_analysts_rule(raw, client_coded):
    _, cols = client_coded
    expected = [_analyst_role(r) for r in _ticked(raw.df["Job role"])]
    assert cols["Role_group"].tolist() == pytest.approx(expected, nan_ok=True)


def test_client_product_and_driver_rules_match_the_analysts_rules(raw, client_coded):
    edited, cols = client_coded
    customer = _ticked(raw.df["Customer type"])
    count = [min(len(t), 3) or None for t in customer]  # every listed answer counts (their LEN formula)
    assert cols["Product_count"].tolist() == pytest.approx([float(c) if c else None for c in count], nan_ok=True)
    named = {v: k for k, v in PRODUCTS.items()}
    sets = [{named.get(a, a) for a in t} for t in customer]  # non-product answers rule a mix out
    for code, mix in [(1.0, {"Resources"}), (3.0, {"Exams"}), (6.0, {"Resources", "Exams"})]:
        assert ((cols["Product_mix"] == code).tolist()) == [s == mix for s in sets], mix
    either = [bool(s) and s <= {"Programmes", "Exams"} for s in sets]
    assert (cols["Programmes_or_exams"] == 1.0).tolist() == either
    first = raw.df["Detractors Drivers"].combine_first(raw.df["Passive Drivers"]).combine_first(raw.df["Promoter Drivers"])
    for opt, given in [(o, _ticked(first)) for o in edited.find_derived("DRIVERS").outputs]:
        assert (cols[opt.name] == 1).tolist() == [opt.label in g for g in given], opt.label


def test_client_rules_place_role_group_after_job_role(client_coded):
    edited, _ = client_coded
    names = edited.output_names()
    assert names.index("Role_group") == names.index("Job_role_Other") + 1


# ── API ──────────────────────────────────────────────────────────────────────

def _post(client, auth_headers, path, data, file=FIXTURE, mime=XLSX_MIME):
    return client.post(path, headers=auth_headers, files={"file": (file.name, file.read_bytes(), mime)}, data=data)


def test_edit_endpoint_and_crosstab_with_edited_codebook(client, auth_headers):
    edits = [{"op": "merge_codes", "var": EXAM, "codes": ["Agree", "Strongly Agree"], "into": "Agree"},
             {"op": "relabel_code", "var": EXAM, "code": 4, "label": "Agree (any)"}]
    response = _post(client, auth_headers, "/v1/codebook", {"edits": json.dumps(edits)})
    assert response.status_code == 200, response.text
    codebook = response.json()["data"]["codebook"]
    exam = next(v for v in codebook["variables"] if v["name"] == EXAM)
    assert [c["label"] for c in exam["codes"]][-1] == "Agree (any)" and exam["codes"][-1]["count"] > 0

    spec = {"row": EXAM, "col": "CX_Pulse_Overall_NPS_group"}
    xtab = _post(client, auth_headers, "/v1/crosstab", {"spec": json.dumps(spec), "codebook": json.dumps(codebook)})
    assert xtab.status_code == 200, xtab.text
    labels = [r["row_label"] for r in xtab.json()["data"]["table"]]
    assert "Agree (any)" in labels and "Strongly Agree" not in labels


def test_edit_endpoint_rejects_bad_edits(client, auth_headers):
    bad = _post(client, auth_headers, "/v1/codebook", {"edits": json.dumps([{"op": "set_label", "var": "Nope", "label": "x"}])})
    assert bad.status_code == 400 and "no variable" in bad.json()["detail"]["message"]
    malformed = _post(client, auth_headers, "/v1/codebook", {"edits": "{not json"})
    assert malformed.status_code == 400


# Job 3 edits on an SPSS file: the age question was asked per condition (Q_16 / Q_17 / Q_18)
SPSS_EDITS = [
    {"op": "add_derived", "derived": {"name": "AGE", "label": "Age", "rule": "coalesce",
                                      "params": {"from": ["Q_16", "Q_17", "Q_18"]}}},
    {"op": "set_nets", "var": "AGE", "nets": [{"label": "Under 41", "codes": [1, 2]}]},
    {"op": "set_nets", "var": "Q_27_1", "nets": [{"label": "3 + 4 + 5", "codes": [3, 4, 5]}]},
    {"op": "set_label", "var": "Q_11", "label": "Severity"},
]


def test_edit_endpoint_spss_file(client, auth_headers):
    """SPSS files are editable: combined questions, nets (also on derived variables), labels."""
    response = _post(client, auth_headers, "/v1/codebook", {"edits": json.dumps(SPSS_EDITS)},
                     file=SAV, mime="application/octet-stream")
    assert response.status_code == 200, response.text
    codebook = response.json()["data"]["codebook"]
    age = next(d for d in codebook["derived"] if d["name"] == "AGE")
    assert [c["label"] for c in age["codes"]][0] == "30 years or younger"   # categories of the sources
    assert age["nets"] == [{"label": "Under 41", "codes": [1.0, 2.0]}]
    assert next(v for v in codebook["variables"] if v["name"] == "Q_11")["label"] == "Severity"


def test_tabulate_spss_with_edited_codebook(client, auth_headers):
    codebook = _post(client, auth_headers, "/v1/codebook", {"edits": json.dumps(SPSS_EDITS)},
                     file=SAV, mime="application/octet-stream").json()["data"]["codebook"]
    spec = {"banner": "Q_10", "stubs": ["AGE", "Q_27_1", "Q_11"]}
    response = _post(client, auth_headers, "/v1/tabulate",
                     {"spec": json.dumps(spec), "codebook": json.dumps(codebook)},
                     file=SAV, mime="application/octet-stream")
    assert response.status_code == 200, response.text
    wb = load_workbook(io.BytesIO(response.content))
    rows = {r[0]: r[1:] for r in wb["AGE"].iter_rows(values_only=True) if r[0]}
    assert rows["Base (N)"][0] == 85                       # everyone answered one of the three
    assert "30 years or younger" in rows and "Under 41" in rows
    assert "3 + 4 + 5" in {r[0] for r in wb["Q_27_1"].iter_rows(values_only=True)}
    assert wb["Q_11"].cell(row=1, column=1).value.startswith("Q_11: Severity")


def test_combining_single_and_multi_questions_is_refused():
    from services.codebook.patch import EditError, apply_ops
    from services.data_loader import QuantiProEngine, codebook_from_spss
    raw = SAV.read_bytes()
    data = QuantiProEngine.load_spss(raw, SAV.name)
    cb = codebook_from_spss(raw, data, SAV.name)
    cb.variables[0].role = "multi"  # pretend cf_1 is a multi-select
    with pytest.raises(EditError, match="mixes multi-select and single"):
        apply_ops(cb, [{"op": "add_derived", "derived": {"label": "X", "rule": "coalesce",
                                                         "params": {"from": ["cf_1", "Q_16"]}}}], data.df)


def test_invalid_codebook_rejected(client, auth_headers):
    spec = {"row": EXAM, "col": "CX_Pulse_Overall_NPS_group"}
    response = _post(client, auth_headers, "/v1/crosstab", {"spec": json.dumps(spec), "codebook": '{"variables": 3}'})
    assert response.status_code == 400


def test_metadata_and_frequency_use_edited_codebook(client, auth_headers):
    """A derived variable added by an edit is a real variable for every analysis endpoint."""
    edits = [{"op": "add_derived", "derived": {"name": "Product_count", "label": "Number of products",
              "rule": "count", "params": {"from": "Customer type", "bands": [
                  {"code": 1, "label": "Single", "min": 1, "max": 1},
                  {"code": 2, "label": "Multiple", "min": 2, "max": None}]}}}]
    codebook = _post(client, auth_headers, "/v1/codebook", {"edits": json.dumps(edits)}).json()["data"]["codebook"]
    meta = _post(client, auth_headers, "/v1/metadata", {"codebook": json.dumps(codebook)})
    assert meta.status_code == 200, meta.text
    assert "Product_count" in [v["name"] for v in meta.json()["data"]["variables"]]
    freq = _post(client, auth_headers, "/v1/frequency", {"variable": "Product_count", "codebook": json.dumps(codebook)})
    assert freq.status_code == 200, freq.text
    assert {f["label"] for f in freq.json()["data"]["frequencies"]} == {"Single", "Multiple"}


def test_review_page_has_editing():
    html = (Path(__file__).parent.parent / "public" / "review.html").read_text(encoding="utf-8")
    assert "add_derived" in html and "set_role" in html and "set_codes" in html and "innerHTML" not in html
    assert "openRecoder" in html and "Exclude from base" in html


def test_review_page_frameable_only_by_same_origin(client):
    review = client.get("/review?embed=1")
    assert review.headers["x-frame-options"] == "SAMEORIGIN"
    assert review.headers["content-security-policy"] == "frame-ancestors 'self'"
    assert client.get("/app").headers["x-frame-options"] == "DENY"  # everything else unchanged


def test_app_has_review_step():
    html = (Path(__file__).parent.parent / "public" / "app.html").read_text(encoding="utf-8")
    assert 'src="/review?embed=1"' in html and "appendData(" in html
    assert "append('file', savFile)" not in html.replace("form.append('file', savFile);\n  if (reviewedCodebook)", "")
    assert ".xlsx" in html and ".csv" in html  # Step 1 accepts Excel / CSV too


def test_crosstab_multi_select_rows(client, auth_headers, cb):
    """A multi-select previewed as one table: % of respondents ticking each option."""
    rows = [o.name for o in cb.find("Job role").options]
    spec = {"rows": rows, "col": "CX_Pulse_Overall_NPS_group", "significance_levels": [0.95, 0.90]}
    r = _post(client, auth_headers, "/v1/crosstab", {"spec": json.dumps(spec)})
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["is_mrs"] and [t["row_label"] for t in body["table"]] == [o.label for o in cb.find("Job role").options]
    assert sum(body["column_bases"].values()) == 400
    bad = _post(client, auth_headers, "/v1/crosstab", {"spec": json.dumps({"rows": ["Job_role_not_listed"], "col": EXAM})})
    assert bad.status_code == 400


def test_pages_are_revalidated(client):
    for path in ("/app", "/review"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path


# ── R1: values (set_codes) and recoding questions that were numbers in the file ──

def test_set_codes_reverses_a_scale(raw, cb):
    reverse = [[1, 5], [2, 4], [4, 2], [5, 1]]
    edited, cols = coded(raw, cb, [{"op": "set_codes", "var": EXAM, "map": reverse}])
    assert [(c.code, c.label) for c in edited.variable(EXAM).codes][:2] == [(1.0, "Strongly Agree"), (2.0, "Agree")]
    answers = raw.df["Exam Results Alternative"]
    assert (cols[EXAM] == 1.0).sum() == (answers == "Strongly Agree").sum()
    assert (cols[EXAM] == 5.0).sum() == (answers == "Strongly Disagree").sum()


def test_set_codes_midpoints_and_duplicates_rejected(raw, cb):
    edited, cols = coded(raw, cb, [{"op": "set_codes", "var": EXAM, "map": [[1, 0.5], [5, 9.5]]}])
    assert {0.5, 9.5} <= set(cols[EXAM].dropna())
    with pytest.raises(EditError, match="share the value"):
        apply_ops(cb, [{"op": "set_codes", "var": EXAM, "map": [[1, 2]]}], raw.df)
    with pytest.raises(EditError, match="not a number"):
        apply_ops(cb, [{"op": "set_codes", "var": EXAM, "map": [[1, "high"]]}], raw.df)


def test_recoding_a_numeric_rating_changes_the_data(raw, cb):
    """Ratings stored as numbers (1-5) used to pass through unchanged after a merge or new values."""
    ease = "CX_Principle_Ease"
    edited, cols = coded(raw, cb, [{"op": "merge_codes", "var": ease, "codes": [5], "into": 4},
                                   {"op": "relabel_code", "var": ease, "code": 4, "label": "4-5 (agree)"},
                                   {"op": "set_codes", "var": ease, "map": [[1, 10], [2, 20]]}])
    raw_ease = raw.df["CX Principle - Ease"]
    assert 5.0 not in set(cols[ease]) and (cols[ease] == 4.0).sum() == raw_ease.isin([4, 5]).sum()
    assert (cols[ease] == 10.0).sum() == (raw_ease == 1).sum()
    # labels are the answers; only their values changed (rows sort by value)
    assert [(c.code, c.label) for c in edited.variable(ease).codes] == [(3.0, "3"), (4.0, "4-5 (agree)"), (10.0, "1"), (20.0, "2")]


def test_recode_else_collects_unassigned_answers(raw, cb):
    edited, cols = coded(raw, cb, [{"op": "add_derived", "derived": {"label": "Agree vs rest", "rule": "recode", "params": {
        "from": EXAM, "groups": [{"code": 1, "label": "Agree", "values": ["Agree", "Strongly Agree"]}],
        "else": {"code": 2, "label": "Everyone else"}}}}])
    answers = raw.df["Exam Results Alternative"]
    assert (cols["Agree_vs_rest"] == 2.0).sum() == answers.isin(["Strongly Disagree", "Disagree", "Neither agree or disagree"]).sum()
    assert cols["Agree_vs_rest"].isna().sum() == answers.isin(["I do not know", "Not applicable - No results received"]).sum()
    assert [c.label for c in edited.find_derived("Agree_vs_rest").codes] == ["Agree", "Everyone else"]


# ── numbers are code values, even when labels are numbers too ────────────────

def _numeric_labelled_scale():
    """Codes 1..6 whose labels are numbers ("1", "4", …) that don't match the codes."""
    from services.codebook.model import Code, Codebook, Source, Variable
    labels = ["1", "4", "5", "6", "7", "MISSING"]
    var = Variable(column="Q5", name="Q5", label="Scale", role="single", measure="ordinal", source="number",
                   codes=[Code(code=float(i + 1), label=label) for i, label in enumerate(labels)])
    return Codebook(source=Source(format="csv"), variables=[var]), pd.DataFrame({"Q5": [1.0, 2, 3, 4, 5, 6, 4, 6]})


def test_set_missing_by_code_ignores_numeric_labels():
    cb, df = _numeric_labelled_scale()
    var = apply_ops(cb, [{"op": "set_missing", "var": "Q5", "code": 6}], df).variable("Q5")
    assert [(m.code, m.label) for m in var.missing] == [(6.0, "MISSING")]
    assert [c.label for c in var.codes] == ["1", "4", "5", "6", "7"]


def test_set_codes_by_code_ignores_numeric_labels():
    cb, df = _numeric_labelled_scale()
    edited = apply_ops(cb, [{"op": "set_codes", "var": "Q5", "map": [[4, 40]]}], df)
    assert (40.0, "6") in [(c.code, c.label) for c in edited.variable("Q5").codes]
    assert (apply_codebook(df, edited).columns["Q5"] == 40.0).sum() == 2  # the rows coded 4, not those labelled "4"
    # a string is still matched by label
    relabelled = apply_ops(cb, [{"op": "relabel_code", "var": "Q5", "code": "MISSING", "label": "No answer"}], df)
    assert relabelled.variable("Q5").codes[-1].label == "No answer"
