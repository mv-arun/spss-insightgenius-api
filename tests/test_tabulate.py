"""Tests for POST /v1/tabulate endpoint — including Tier 1 features."""

import json

import pytest
import io
from openpyxl import load_workbook


def test_tabulate_basic(client, auth_headers, test_sav_bytes):
    """Tabulate satisfaction x gender -> Excel with 1 sheet."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": ["satisfaction"],
        "significance_level": 0.95,
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert resp.headers["X-Stubs-Total"] == "1"
    assert resp.headers["X-Stubs-Success"] == "1"

    wb = load_workbook(io.BytesIO(resp.content))
    assert "Summary" in wb.sheetnames
    assert "satisfaction" in wb.sheetnames

    ws_ct = wb["satisfaction"]
    assert "satisfaction" in ws_ct.cell(row=1, column=1).value


def test_tabulate_all_stubs(client, auth_headers, test_sav_bytes):
    """Tabulate with stubs=_all_ auto-selects variables with value labels."""
    spec = json.dumps({"banner": "gender", "stubs": ["_all_"]})
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    total = int(resp.headers["X-Stubs-Total"])
    assert total >= 2


def test_tabulate_with_nets(client, auth_headers, test_sav_bytes):
    """Tabulate with net definitions (Top 2 Box)."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": ["satisfaction"],
        "nets": {"satisfaction": {"Top 2 Box": [4, 5], "Bottom 2 Box": [1, 2]}},
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb["satisfaction"]
    nets_found = any(row[0].value == "Nets" for row in ws.iter_rows(min_col=1, max_col=1))
    assert nets_found, "Nets section not found in Excel"


def test_tabulate_with_weight(client, auth_headers, test_sav_bytes):
    """T1-4: Tabulate with weight shows dual bases."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": ["satisfaction"],
        "weight": "weight_var",
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb["satisfaction"]
    # Check for dual bases
    found_weighted = False
    found_unweighted = False
    for row in ws.iter_rows(min_col=1, max_col=1, max_row=10):
        val = row[0].value or ""
        if "weighted" in val.lower():
            found_weighted = True
        if "unweighted" in val.lower():
            found_unweighted = True
    assert found_weighted, "Weighted base row not found"
    assert found_unweighted, "Unweighted base row not found"


def test_tabulate_means(client, auth_headers, test_sav_bytes):
    """T1-1: Means row with T-test."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": ["satisfaction"],
        "include_means": True,
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb["satisfaction"]
    # Find "Mean" label
    mean_found = False
    for row in ws.iter_rows(min_col=1, max_col=1):
        if row[0].value == "Mean":
            mean_found = True
            break
    assert mean_found, "Mean row not found in Excel"


def test_tabulate_multiple_banners(client, auth_headers, test_sav_bytes):
    """T1-2: Multiple banners side-by-side."""
    spec = json.dumps({
        "banners": ["gender", "age_group"],
        "stubs": ["satisfaction"],
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))

    # Summary should mention both banners
    ws_sum = wb["Summary"]
    banners_cell = None
    for row in ws_sum.iter_rows(min_col=1, max_col=2, max_row=15):
        if row[0].value == "Banners":
            banners_cell = row[1].value
            break
    assert banners_cell is not None
    assert "gender" in banners_cell
    assert "age_group" in banners_cell

    # Data sheet should have columns for both banners (2 gender + 3 age = 5 + Total = 6 data cols)
    ws = wb["satisfaction"]
    # Check letters row — should have A,B (gender) + C,D,E (age_group)
    letters = []
    for col in range(2, 10):
        val = ws.cell(row=5, column=col).value  # Letters row (row 5 with banner group header)
        if val and len(str(val)) <= 2 and str(val).isalpha():
            letters.append(str(val))
    assert len(letters) >= 5, f"Expected 5+ column letters, got {letters}"
    assert "A" in letters and "E" in letters


def test_tabulate_mrs(client, auth_headers, test_sav_bytes_with_mrs):
    """T1-3: MRS groups as crosstab rows."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": [],
        "mrs_groups": {"Brand Awareness": ["AWARE_A", "AWARE_B", "AWARE_C"]},
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test_mrs.sav", test_sav_bytes_with_mrs, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    assert int(resp.headers["X-Stubs-Success"]) >= 1
    wb = load_workbook(io.BytesIO(resp.content))
    assert "Brand Awareness" in wb.sheetnames


def test_tabulate_total_first_column(client, auth_headers, test_sav_bytes):
    """T2-5: Total appears as first column before banners."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": ["satisfaction"],
        "include_total_column": True,
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb["satisfaction"]
    # First data column (B) should be "Total"
    # Find the column value labels row
    for r in range(3, 8):
        val = ws.cell(row=r, column=2).value
        if val == "Total":
            break
    else:
        assert False, "Total not found as first column"


def test_tabulate_single_sheet(client, auth_headers, test_sav_bytes):
    """Single-sheet mode: all stubs stacked in one sheet."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": ["satisfaction", "age_group"],
        "output_mode": "single_sheet",
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    assert "Tabulation" in wb.sheetnames
    # Should NOT have individual sheets for each stub
    assert "satisfaction" not in wb.sheetnames
    assert "age_group" not in wb.sheetnames
    # The Tabulation sheet should contain both stubs
    ws = wb["Tabulation"]
    found_sat = False
    found_age = False
    for row in ws.iter_rows(min_col=1, max_col=1):
        val = str(row[0].value or "")
        if "satisfaction" in val.lower():
            found_sat = True
        if "age_group" in val.lower():
            found_age = True
    assert found_sat, "satisfaction stub not found in single sheet"
    assert found_age, "age_group stub not found in single sheet"


def test_tabulate_grid_summary(client, auth_headers, test_sav_bytes):
    """Grid/Battery summary: T2B + Mean for multiple scale variables in one sheet."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": [],
        "grid_mode": "summary",
        "grid_groups": {
            "Satisfaction Battery": {
                "variables": ["satisfaction", "recommend"],
                "show": ["t2b", "mean"]
            }
        },
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    assert int(resp.headers["X-Stubs-Success"]) >= 1
    wb = load_workbook(io.BytesIO(resp.content))
    assert "Satisfaction Battery" in wb.sheetnames
    ws = wb["Satisfaction Battery"]
    # Should have "Top 2 Box %" and "Mean" metric headers
    found_t2b = False
    found_mean = False
    for row in ws.iter_rows(min_col=1, max_col=1):
        val = str(row[0].value or "")
        if "Top 2 Box" in val:
            found_t2b = True
        if val == "Mean":
            found_mean = True
    assert found_t2b, "T2B metric header not found"
    assert found_mean, "Mean metric header not found"


def test_tabulate_custom_groups(client, auth_headers, test_sav_bytes):
    """Custom groups: virtual banner columns defined by conditions."""
    spec = json.dumps({
        "banner": "gender",
        "stubs": ["satisfaction"],
        "custom_groups": [
            {"name": "Young Males", "conditions": [
                {"variable": "gender", "operator": "eq", "value": 1.0},
                {"variable": "age_group", "operator": "eq", "value": 1.0}
            ]},
            {"name": "Young Females", "conditions": [
                {"variable": "gender", "operator": "eq", "value": 2.0},
                {"variable": "age_group", "operator": "eq", "value": 1.0}
            ]},
        ],
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb["satisfaction"]
    # Find "Young Males" in header rows
    found_custom = False
    for row in ws.iter_rows(min_row=1, max_row=8, min_col=2, max_col=10):
        for cell in row:
            if cell.value and "Young Males" in str(cell.value):
                found_custom = True
                break
    assert found_custom, "Custom group 'Young Males' not found in Excel headers"


def test_tabulate_custom_groups_only(client, auth_headers, test_sav_bytes):
    """Custom groups without regular banners."""
    spec = json.dumps({
        "stubs": ["satisfaction"],
        "custom_groups": [
            {"name": "Satisfied (4-5)", "conditions": [
                {"variable": "satisfaction", "operator": "gte", "value": 4.0}
            ]},
            {"name": "Neutral (3)", "conditions": [
                {"variable": "satisfaction", "operator": "eq", "value": 3.0}
            ]},
            {"name": "Dissatisfied (1-2)", "conditions": [
                {"variable": "satisfaction", "operator": "lte", "value": 2.0}
            ]},
        ],
    })
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    assert int(resp.headers["X-Stubs-Success"]) >= 1


def test_tabulate_total_only(client, auth_headers, test_sav_bytes):
    """Total-only export (no banners) should succeed with just the Total column."""
    spec = json.dumps({"stubs": ["satisfaction"]})
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_tabulate_invalid_banner(client, auth_headers, test_sav_bytes):
    spec = json.dumps({"banner": "NONEXISTENT", "stubs": ["satisfaction"]})
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "VARIABLE_NOT_FOUND"


def test_tabulate_invalid_stub(client, auth_headers, test_sav_bytes):
    spec = json.dumps({"banner": "gender", "stubs": ["Q999"]})
    resp = client.post(
        "/v1/tabulate",
        headers=auth_headers,
        files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
        data={"spec": spec},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "VARIABLE_NOT_FOUND"


def _crosstab_rows(ws):
    """{row label: [cell values]} for one tabulation sheet, plus the column header labels."""
    all_rows = list(ws.iter_rows(values_only=True))
    base_at = next(i for i, r in enumerate(all_rows) if r[0] == "Base (N)")
    rows = {str(r[0]): list(r[1:]) for r in all_rows if r[0] is not None}
    return rows, list(all_rows[base_at - 2][1:])  # value labels sit above the letters row


def test_tabulate_overlapping_custom_groups_keep_their_bases(client, auth_headers, test_sav_bytes, tmp_path):
    """A respondent in two custom groups counts in both (groups used to overwrite each other)."""
    import pyreadstat
    path = tmp_path / "t.sav"
    path.write_bytes(test_sav_bytes)
    df, _ = pyreadstat.read_sav(str(path))
    spec = json.dumps({
        "banner": "gender",
        "stubs": ["satisfaction"],
        "custom_groups": [
            {"name": "Males", "conditions": [{"variable": "gender", "operator": "eq", "value": 1.0}]},
            {"name": "Young", "conditions": [{"variable": "age_group", "operator": "eq", "value": 1.0}]},
        ],
    })
    resp = client.post("/v1/tabulate", headers=auth_headers,
                       files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
                       data={"spec": spec})
    assert resp.status_code == 200
    rows, headers = _crosstab_rows(load_workbook(io.BytesIO(resp.content))["satisfaction"])
    bases = dict(zip(headers, rows["Base (N)"]))
    assert bases["Males"] == (df["gender"] == 1).sum() > 0
    assert bases["Young"] == (df["age_group"] == 1).sum() > 0


def test_tabulate_custom_groups_only_shows_answer_rows(client, auth_headers, test_sav_bytes):
    """With custom groups as the only banner, stub tables keep their answer rows."""
    spec = json.dumps({
        "stubs": ["satisfaction"],
        "custom_groups": [
            {"name": "Males", "conditions": [{"variable": "gender", "operator": "eq", "value": 1.0}]},
            {"name": "Females", "conditions": [{"variable": "gender", "operator": "eq", "value": 2.0}]},
        ],
    })
    for mode in ("multi_sheet", "single_sheet"):
        resp = client.post("/v1/tabulate", headers=auth_headers,
                           files={"file": ("test.sav", test_sav_bytes, "application/octet-stream")},
                           data={"spec": json.dumps({**json.loads(spec), "output_mode": mode})})
        assert resp.status_code == 200
        wb = load_workbook(io.BytesIO(resp.content))
        ws = wb["satisfaction"] if mode == "multi_sheet" else wb[wb.sheetnames[-1]]
        labels = {str(r[0]) for r in ws.iter_rows(values_only=True)}
        assert {"Very dissatisfied", "Neutral", "Very satisfied"} <= labels, mode


def _sav(tmp_path, df, value_labels=None):
    """Write a small .sav and return its bytes."""
    import pyreadstat
    path = tmp_path / "t.sav"
    pyreadstat.write_sav(df, str(path), variable_value_labels=value_labels or {})
    return path.read_bytes()


def _tabulate(client, auth_headers, sav_bytes, spec):
    resp = client.post("/v1/tabulate", headers=auth_headers,
                       files={"file": ("t.sav", sav_bytes, "application/octet-stream")},
                       data={"spec": json.dumps(spec)})
    assert resp.status_code == 200, resp.text
    return resp, load_workbook(io.BytesIO(resp.content))


def _three_groups_df():
    """Three cuts of 30. 'barrier' is picked by 4/30, 11/30 and 8/30: B vs A gives p ≈ 0.037,
    significant at 95% but not after Bonferroni over three pairs (alpha 0.0167)."""
    import pandas as pd
    cut = [1.0] * 30 + [2.0] * 30 + [3.0] * 30
    barrier = [1.0] * 4 + [0.0] * 26 + [1.0] * 11 + [0.0] * 19 + [1.0] * 8 + [0.0] * 22
    only_b = [None] * 30 + [1.0, 2.0] * 15 + [None] * 30          # asked of cut 2 only
    return pd.DataFrame({"cut": cut, "barrier": barrier, "only_b": only_b})


_THREE_GROUPS = [
    {"name": f"Cut {i}", "conditions": [{"variable": "cut", "operator": "eq", "value": float(i)}]}
    for i in (1, 2, 3)
]
_LABELS = {"barrier": {0.0: "No", 1.0: "Yes"}, "only_b": {1.0: "One", 2.0: "Two"}}


def test_tabulate_exclusive_custom_groups_are_tested_against_each_other(client, auth_headers, tmp_path):
    """Non-overlapping custom groups share one banner, so their columns get sig letters."""
    sav = _sav(tmp_path, _three_groups_df(), _LABELS)
    _, wb = _tabulate(client, auth_headers, sav, {
        "stubs": ["barrier"], "custom_groups": _THREE_GROUPS, "bonferroni": False})
    rows, headers = _crosstab_rows(wb["barrier"])
    yes = dict(zip(headers, rows["Yes"]))
    assert yes["Cut 2"].endswith(" A"), yes          # 36.7% beats Cut 1's 13.3%
    assert dict(zip(headers, rows["Base (N)"]))["Cut 1"] == 30


def test_tabulate_bonferroni_switch(client, auth_headers, tmp_path):
    """p ≈ 0.037 is significant without correction and not with Bonferroni (the default)."""
    sav = _sav(tmp_path, _three_groups_df(), _LABELS)
    for bonferroni, expect_letter in ((True, False), (False, True)):
        _, wb = _tabulate(client, auth_headers, sav, {
            "stubs": ["barrier"], "custom_groups": _THREE_GROUPS, "bonferroni": bonferroni})
        rows, headers = _crosstab_rows(wb["barrier"])
        cell = dict(zip(headers, rows["Yes"]))["Cut 2"]
        assert cell.endswith(" A") is expect_letter, (bonferroni, cell)
        assert ("no multiple-comparison correction" in wb["barrier"].cell(row=2, column=1).value) is not bonferroni


def test_tabulate_question_asked_of_one_group_keeps_its_table(client, auth_headers, tmp_path):
    """A banner column with nobody answering shows '-' instead of failing the whole table."""
    sav = _sav(tmp_path, _three_groups_df(), _LABELS)
    resp, wb = _tabulate(client, auth_headers, sav, {"stubs": ["only_b"], "custom_groups": _THREE_GROUPS})
    assert resp.headers["X-Stubs-Success"] == "1"
    rows, headers = _crosstab_rows(wb["only_b"])
    bases = dict(zip(headers, rows["Base (N)"]))
    assert (bases["Cut 1"], bases["Cut 2"], bases["Cut 3"]) == (0, 30, 0)
    assert dict(zip(headers, rows["One"]))["Cut 1"] == "-"


def test_tabulate_unlabelled_codes_print_as_whole_numbers(client, auth_headers, tmp_path):
    """A ranking item without value labels shows rows '1', '2', not '1.0', '2.0'."""
    import pandas as pd
    df = pd.DataFrame({"g": [1.0, 2.0] * 10, "rank_a": [1.0, 2.0, 3.0, 2.0] * 5})
    sav = _sav(tmp_path, df, {"g": {1.0: "M", 2.0: "F"}})
    _, wb = _tabulate(client, auth_headers, sav, {"banner": "g", "grid_groups": {"Rank": {"variables": ["rank_a"], "show": ["rank"]}}, "stubs": ["g"]})
    rows, _ = _crosstab_rows(wb["rank_a"])
    assert {"1", "2", "3"} <= set(rows), list(rows)


def _block(ws, title):
    """Rows of one table in a Displayr-style sheet, from its title to its footer."""
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    start = next(i for i, r in enumerate(rows) if r[0] == title)
    end = next(i for i in range(start + 1, len(rows)) if rows[i][0] in (title, f"{title} SUMMARY"))  # Total: "… SUMMARY"
    return rows[start:end + 2]


def test_tabulate_displayr_layout(client, auth_headers, tmp_path):
    """Total / By <banner> / Stat sheets; fractions, NET, Column Sample Size, letters, empty columns."""
    sav = _sav(tmp_path, _three_groups_df(), _LABELS)
    _, wb = _tabulate(client, auth_headers, sav, {
        "stubs": ["barrier", "only_b"], "custom_groups": _THREE_GROUPS, "bonferroni": False,
        "output_mode": "displayr", "custom_groups_label": "Data Cut"})
    assert wb.sheetnames == ["Total", "By Data Cut", "By Data Cut (Stat)"]

    block = _block(wb["By Data Cut"], "barrier by Data Cut")
    assert block[1][:5] == ["Column %", "Cut 1", "Cut 2", "Cut 3", "Total"]
    rows = {r[0]: r[1:5] for r in block[2:] if r[0]}
    assert rows["Yes"] == pytest.approx([4 / 30, 11 / 30, 8 / 30, 23 / 90])   # fractions, not "13.3%"
    assert rows["NET"] == [1, 1, 1, 1]
    assert rows["Column Sample Size"] == [30, 30, 30, 90]
    assert block[-1][0] == "sample size = 90"

    empty = {r[0]: r[1:5] for r in _block(wb["By Data Cut"], "only_b by Data Cut")[2:] if r[0]}
    assert empty["One"][0] is None and empty["Column Sample Size"] == [0, 30, 0, 30]

    stat = _block(wb["By Data Cut (Stat)"], "barrier by Data Cut")
    yes = next(i for i, r in enumerate(stat) if r[0] == "Yes")
    assert [v or "" for v in stat[yes + 1][1:5]] == ["", "A", "", "-"]   # Cut 2 > Cut 1; Total untested
    assert any(r[0] == "Column Names" for r in stat)

    total = {r[0]: r[1] for r in _block(wb["Total"], "barrier")[2:] if r[0]}
    assert total["Yes"] == pytest.approx(23 / 90) and total["NET"] == 1


def test_tabulate_displayr_merged_nets_and_grids(client, auth_headers, tmp_path):
    """Nets that split every answer replace the answers; a grid group is one table with its items side by side."""
    import pandas as pd
    df = _three_groups_df().assign(r1=[1.0, 2.0, 3.0] * 30, r2=[3.0, 3.0, 1.0] * 30)
    labels = {**_LABELS, "r1": {1.0: "Low", 2.0: "Mid", 3.0: "High"}, "r2": {1.0: "Low", 2.0: "Mid", 3.0: "High"}}
    sav = _sav(tmp_path, df, labels)
    _, wb = _tabulate(client, auth_headers, sav, {
        "stubs": ["barrier"], "custom_groups": _THREE_GROUPS, "output_mode": "displayr",
        "grid_groups": {"Ratings": {"variables": ["r1", "r2"], "show": []}},
        "nets": {"r1": {"Low + Mid": [1, 2], "High": [3]}, "r2": {"Low + Mid": [1, 2], "High": [3]}}})
    block = _block(wb["By Custom Groups"], "Ratings by Custom Groups")
    labels_col = [r[0] for r in block]
    assert "Low + Mid" in labels_col and "High" in labels_col and "Low" not in labels_col   # merge
    header_items = [v for v in block[1][1:] if v]
    assert len(header_items) == 2                                       # r1 and r2 as column groups
    low_mid = next(r for r in block if r[0] == "Low + Mid")
    assert low_mid[4] == pytest.approx(2 / 3) and low_mid[8] == pytest.approx(1 / 3)   # Total of r1, r2


def test_tabulate_displayr_table_order_and_titles(client, auth_headers, tmp_path):
    """Tables follow table_order (variables and group names) and take table_titles."""
    sav = _sav(tmp_path, _three_groups_df(), _LABELS)
    _, wb = _tabulate(client, auth_headers, sav, {
        "stubs": ["barrier", "only_b"], "custom_groups": _THREE_GROUPS, "output_mode": "displayr",
        "table_order": ["only_b", "barrier"], "table_titles": {"barrier": "Q10: Barriers"}})
    titles = [r[0] for r in wb["Total"].iter_rows(values_only=True)
              if r[0] and r[1] is None and not str(r[0]).startswith(("sample size", "Total")) and "SUMMARY" not in str(r[0])]
    assert titles == ["only_b", "Q10: Barriers"]
