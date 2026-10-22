"""Codebook pipeline (IMPLEMENTATION_PLAN.md M2): infer → apply, codebook API, wave reuse."""

import asyncio
import base64
import io
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from services.codebook.apply import apply_codebook
from services.codebook.infer import infer_codebook
from services.codebook.model import Codebook
from services.data_loader import describe_file, load_data, load_with_codebook
from services.ingest.readers import read_raw
from tests.conftest import TEST_KEY

FIXTURE = Path(__file__).parent / "fixtures" / "exports" / "hubspot_cx_sample.xlsx"
SNAPSHOT = Path(__file__).parent / "snapshots" / "codebook_hubspot_cx_sample.json"
SAV = Path(__file__).parent / "fixtures" / "example3_raw.sav"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(scope="module")
def raw():
    return read_raw(FIXTURE.read_bytes(), FIXTURE.name)


@pytest.fixture(scope="module")
def codebook(raw):
    return infer_codebook(raw)


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """Don't spend the shared test key's per-minute budget other test modules rely on."""
    from middleware import rate_limiter
    yield
    rate_limiter._windows.clear()


def test_inferred_codebook_snapshot(codebook):
    """Any change to inference shows up here as a readable JSON diff."""
    actual = codebook.model_dump(mode="json")
    if os.environ.get("UPDATE_GOLDEN"):
        SNAPSHOT.write_text(json.dumps(actual, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        pytest.skip(f"codebook snapshot rewritten: {SNAPSHOT}")
    assert actual == json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_every_decision_has_a_reason(codebook):
    assert all(v.inferred and v.inferred.reason for v in codebook.variables)
    assert all(d.inferred and d.inferred.reason for d in codebook.derived)


def test_saved_codebook_reproduces_data_exactly(codebook):
    """Apply is driven only by the codebook: JSON round-trip → identical coded data."""
    restored = Codebook.model_validate_json(codebook.model_dump_json())
    inferred = load_data(FIXTURE.read_bytes(), FIXTURE.name)
    from_saved = load_data(FIXTURE.read_bytes(), FIXTURE.name, codebook=restored)
    pd.testing.assert_frame_equal(inferred.df, from_saved.df)
    assert inferred.meta.variable_value_labels == from_saved.meta.variable_value_labels
    assert inferred.meta.column_names_to_labels == from_saved.meta.column_names_to_labels


def test_next_wave_keeps_codes_and_reports_new_answers(raw, codebook):
    """Wave 2 lacks a category and has a new answer: codes don't shift, the new answer is reported."""
    wave2 = raw.df.copy()
    exam = "Exam Results Alternative"
    wave2 = wave2[wave2[exam] != "Strongly Disagree"].copy()
    wave2.loc[wave2.index[:3], exam] = "Somewhat agree (new wording)"

    coded = apply_codebook(wave2, codebook)
    var = codebook.variable("Exam_Results_Alternative")
    agree = next(c.code for c in var.codes if c.label == "Agree")
    assert agree == 4.0  # same code as wave 1 although "Strongly Disagree" (1) is absent
    assert (coded.columns["Exam_Results_Alternative"] == agree).sum() == (wave2[exam] == "Agree").sum()
    assert coded.unmatched["Exam_Results_Alternative"] == ["Somewhat agree (new wording)"]

    # A fresh inference on wave 2 alone would also keep the full-scale codes
    assert infer_codebook(read_raw(_xlsx(wave2), "w2.xlsx")).variable("Exam_Results_Alternative") \
        .codes[3].code == agree


def test_missing_column_is_an_error(raw, codebook):
    with pytest.raises(ValueError, match="not in this file"):
        apply_codebook(raw.df.drop(columns=["Job role"]), codebook)


def test_describe_counts(raw):
    result = describe_file(FIXTURE.read_bytes(), FIXTURE.name)
    variables = {v["column"]: v for v in result["codebook"]["variables"]}
    exam = variables["Exam Results Alternative"]
    counts = {c["label"]: c["count"] for c in exam["codes"] + exam["missing"]}
    assert counts == raw.df["Exam Results Alternative"].value_counts().to_dict()
    assert exam["base"] == sum(c["count"] for c in exam["codes"])  # missing codes excluded
    roles = variables["Job role"]
    assert roles["role"] == "multi" and roles["base"] == raw.df["Job role"].notna().sum()
    assert result["summary"]["by_role"]["multi"] == 5
    assert result["summary"]["output_variables"] == len(load_data(FIXTURE.read_bytes(), FIXTURE.name).df.columns)


def test_describe_spss_file_uses_metadata():
    result = describe_file(SAV.read_bytes(), SAV.name)
    variables = result["codebook"]["variables"]
    assert result["codebook"]["source"]["format"] == "sav"
    assert all(v["inferred"]["rule"] == "spss:metadata" for v in variables)
    labelled = [v for v in variables if v["role"] == "single"]
    assert labelled and all(c["count"] is not None for v in labelled for c in v["codes"])


def test_load_with_codebook_returns_applied_codebook():
    data, cb = load_with_codebook(FIXTURE.read_bytes(), FIXTURE.name)
    assert cb.output_names() == list(data.df.columns)


def _xlsx(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


# ── API ──────────────────────────────────────────────────────────────────────

def test_codebook_endpoint_excel(client, auth_headers):
    response = client.post("/v1/codebook", headers=auth_headers,
                           files={"file": (FIXTURE.name, FIXTURE.read_bytes(), XLSX_MIME)})
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["summary"]["columns"] == 37
    assert body["codebook"]["source"]["format"] == "xlsx"


def test_codebook_endpoint_spss(client, auth_headers):
    response = client.post("/v1/codebook", headers=auth_headers,
                           files={"file": (SAV.name, SAV.read_bytes(), "application/octet-stream")})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["codebook"]["source"]["format"] == "sav"


def test_codebook_endpoint_requires_key(client):
    response = client.post("/v1/codebook", files={"file": (FIXTURE.name, FIXTURE.read_bytes(), XLSX_MIME)})
    assert response.status_code == 401


def test_mcp_get_codebook():
    from mcp_server.tools.metadata import get_codebook
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(get_codebook(
            api_key=TEST_KEY, file_base64=base64.b64encode(FIXTURE.read_bytes()).decode(),
            filename=FIXTURE.name))
    finally:
        loop.close()
    assert "codebook" in json.dumps(result)


def test_review_page_served(client):
    response = client.get("/review")
    assert response.status_code == 200
    html = response.text
    assert "/v1/codebook" in html and 'id="var-grid"' in html  # the Variables grid (its preview moved to Crosstabs)
    assert "innerHTML" not in html  # file-derived labels are only ever set as text
