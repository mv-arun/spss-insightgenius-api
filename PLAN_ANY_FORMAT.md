# Plan: Any-Format Survey Input with Codebook Review

> Status: proposal · Owner: Arun MV · Date: 2026-10-14
> Supersedes the HubSpot-specific work in `services/respondent_sheet.py` and the
> client rules in `services/data_loader.py` (built in Phase 1, uncommitted).
> The older `PLAN.md` (QuantipyMRX integration) is unrelated and stays as is.

## 1. Goal

A user uploads **any** survey data file, **sees how the system understood it**
(the codebook and a live crosstab), fixes anything that's wrong, and **moves on**
to tables, exports, and wave comparisons.

- **Any format:** SPSS, CSV/TSV, Excel, and the exports of common survey platforms
  (HubSpot, SurveyMonkey, Qualtrics, Typeform, Google Forms, Alchemer, Decipher).
- **No file-specific rules in code.** Nothing in `services/` may mention a client,
  a question wording or an answer option. Anything specific to one survey
  (e.g. "Exams Officer outranks Teacher") lives in that survey's **codebook**, which
  the user edits and saves.
- **Visible decisions.** Every inference ("this column is a 5-point agreement
  scale", "these 6 columns are one multi-select question") is shown with its
  reason and can be changed.
- **Same results every run.** Re-running a file with the same codebook gives
  identical numbers. AI may *suggest*, but a person approves, and the decision is saved.

### Non-goals
- Coding open-ended comments into themes (explicitly out of scope).
- A full drag-and-drop table designer. The review screen is
  for checking and correcting the data, not for building reports.

## 2. Where we are (Phase 1, uncommitted)

| Keep in core (generic) | Move out of code → becomes codebook / user rules |
|---|---|
| Rating-scale lexicon (agree/satisfied/likely/…), ordered coding | `_job_role_group` (Exams Officer > Leader > Teacher) |
| "Don't know / N/A / Prefer not to say" → user-missing | `respondent_sheet.py` product rules (Single/Dual/Triple, mixes) |
| Numeric-prefix codes ("10 - Extremely likely") | `HUBSPOT_SYSTEM_COLUMNS` list |
| Delimited multi-select detection ("A; B") | client driver order, `CATEGORY_SHEETS`, "FULL DATA PULSE" title |
| Constant / empty / free-text detection | Header regexes for "Job role", "Customer type", "Drivers" |
| NPS group suggestion (0-10 + recommend/NPS header) | |
| Mean-row fix, T2B ignores DK codes, .xls calamine fallback | |

The client behaviour isn't lost. It becomes a **saved codebook** (a JSON
fixture), and reproducing the September Pulse workbook from that codebook alone is
an acceptance test (§9).

## 3. Architecture

```
 Upload (any format)
   │
 ① INGEST         readers + platform adapters → RawTable
   │               (cells, header rows, sheet, delimiter, encoding)
   │
 ② STRUCTURE      detect header layout, question→option grouping, ID/date/weight columns
   │               user can override: header rows, sheet, delimiter
   │
 ③ INFER          → Codebook draft (every decision has type, reason, confidence)
   │
 ④ REVIEW  ◀──── user: visual codebook + live crosstab; edit, derive, approve
   │               (or: apply a saved codebook → change report)
   │
 ⑤ APPLY          RawTable + Codebook → coded dataset (.sav in memory, full metadata)
   │
 ⑥ OUTPUTS        tables (sig 95/90, low-base flags) · data export with segment tabs
                   · .sav / .csv / .xlsx export · wave compare · charts · MCP / chat
```

Today, steps ②, ③ and ⑤ are merged into `data_loader._tabular_to_sav`. They get
split into separate, testable functions. Everything after ⑤ already exists and
stays unchanged: the rest of the system still sees a normal `SPSSData`.

### New/changed modules

| Module | Responsibility |
|---|---|
| `services/ingest/readers.py` | sav/zsav/por, csv/tsv (sniffing, encodings), xlsx/xls (openpyxl → calamine fallback) → `RawTable` |
| `services/ingest/adapters/*.py` | One per platform: `detect(raw) -> confidence`, `normalize(raw) -> RawTable`. `generic` is the fallback |
| `services/codebook/model.py` | Pydantic models: `Codebook`, `Variable`, `Group`, `Derived`, `Output` (§4) |
| `services/codebook/infer.py` | RawTable → draft Codebook. Generic heuristics only (moved from `data_loader`) |
| `services/codebook/apply.py` | RawTable + Codebook → coded DataFrame + SPSS meta + `ApplyReport` (unmatched answers, new options, dropped columns) |
| `services/codebook/derive.py` | Generic rule engine for derived variables (§5) |
| `services/codebook/store.py` | Supabase persistence, versions, fingerprint matching |
| `services/exports/data_workbook.py` | Generic successor to `respondent_sheet.py`: full data + one tab per chosen segment |
| `services/data_loader.py` | Thin wrapper: `ingest → infer (or load saved) → apply`. Keeps the `load_data()` signature, so every existing endpoint keeps working |

## 4. The codebook

One versioned JSON document per survey. Inferred automatically, edited by the
user, saved, and reused for every wave.

```json
{
  "id": "cb_8f2…", "name": "CX Pulse", "version": 4,
  "source": {"adapter": "hubspot", "header_rows": 1, "sheet": "Sheet1", "delimiter": ";"},
  "fingerprint": {"columns": ["Record ID", "Job role", "…"], "min_overlap": 0.8},

  "variables": [
    {"column": "Record ID", "name": "record_id", "role": "id"},
    {"column": "Email", "role": "pii", "export": false},
    {"column": "Source", "role": "ignore", "reason": "same value in every row"},
    {"column": "Exam Results Alternative", "name": "exam_results", "role": "single",
     "measure": "ordinal", "label": "Exam results are a fair reflection",
     "codes": [{"code": 1, "label": "Strongly Disagree", "match": ["Strongly Disagree"]},
               {"code": 5, "label": "Strongly Agree",    "match": ["Strongly Agree"]}],
     "missing": [{"code": 98, "label": "I do not know"}],
     "inferred": {"rule": "scale:agreement-5", "confidence": 0.97}},
    {"column": "Job role", "name": "job_role", "role": "multi", "storage": "delimited",
     "delimiter": ";", "options": [{"code": 1, "label": "Teacher"}, "…"]},
    {"column": "CX Pulse Overall NPS", "name": "nps", "role": "numeric", "range": [0, 10],
     "tags": ["nps"]}
  ],

  "groups": [
    {"name": "cx_principles", "role": "grid", "members": ["ease", "quality", "accessible"],
     "show": ["t2b", "b2b", "mean"]}
  ],

  "derived": [
    {"name": "nps_group", "label": "NPS group", "rule": "bands", "from": "nps",
     "bands": [{"code": 1, "label": "Detractors", "min": 0, "max": 6},
               {"code": 2, "label": "Passives", "min": 7, "max": 8},
               {"code": 3, "label": "Promoters", "min": 9, "max": 10}]}
  ],

  "outputs": {
    "banners": ["role_group", "nps_group"],
    "data_workbook": {"segment_tabs": ["nps_group", "role_group", "product_count"],
                      "header_rows": ["percent", "count"]},
    "significance": {"levels": [0.95, 0.90]}, "low_base": {"warn": 100, "suppress_hint": 30}
  }
}
```

Rules:
- **Variable roles:** `id`, `pii`, `date`, `weight`, `single`, `multi`, `numeric`,
  `text`, `ignore`. Plus `groups` for multi-select sets stored as separate columns,
  and for grids.
- **`match`** lists the raw text that maps to each code, so spelling variants and
  translations map to the same code.
- **Codes never change between versions.** A new answer option gets the next free code
  and is reported. It is never renumbered.
- **Saved codebooks are applied, not re-inferred.** Inference only runs for columns
  the codebook doesn't know, and those show up as "new" in the review.
- The **Excel "Value Labels" / "Variable Labels" sheets** stay supported, as a spreadsheet
  way to import and export a codebook's variables.

## 5. Derived variables: generic rule types

These replace the hard-coded client logic. Users build them in the review UI
(form per rule type, with a live count preview), and they're stored in `derived`.

| Rule | What it does | Client example (becomes data, not code) |
|---|---|---|
| `recode` | Map codes → new codes (merge categories) | Top-2-box variable |
| `bands` | Numeric ranges → categories | NPS 0-6 / 7-8 / 9-10 |
| `priority` | First matching condition wins; `else` bucket | Role: Exams Officer > Leader > Teacher > Other |
| `count` | Number of options selected, optionally banded | Number of products → Single / Dual / Triple |
| `combination` | Exact (or subset) set of selected options | "Resources + Exams", "Programmes only" |
| `coalesce` | First non-empty of several columns | DRIVERS = detractor/passive/promoter drivers |
| `flags` | One 0/1 variable per option or value | Driver flags, score 1–5 columns |

Conditions use a small, safe expression format (no `eval`):
`{"any": [...]}`, `{"all": [...]}`, `{"none": [...]}`, `{"and"|"or": [...]}`,
`{"var": "nps", "between": [0, 6]}`. Derived variables can refer to other
derived variables (checked for cycles).

**AI assist (optional, approved by a person):** "Describe the rule" → Claude drafts the
rule JSON from text like the analyst's note ("Leader if not an exams officer and
selected school leader, or HoD but not a teacher") → it's shown as a filled-in form
with a count preview → the user approves. The draft is never applied unreviewed.

## 6. Format support

### Readers (step ①)
| Format | Reader | Notes |
|---|---|---|
| .sav / .zsav / .por | pyreadstat | Codebook comes straight from SPSS metadata (labels, missing values) |
| .csv / .tsv / .txt | pandas + sniffer | Encodings utf-8-sig / cp1252 / latin-1; delimiter sniffing |
| .xlsx / .xlsm | openpyxl | Sheet picker when there are several |
| .xls | xlrd → calamine fallback | Handles loosely written files (HubSpot re-saves) |
| .json / .ndjson | pandas | Array of respondent objects (Typeform/API dumps) |
| .parquet | pyarrow | Cheap to add; data-team exports |

### Platform adapters (step ②)
Each adapter recognises its layout and turns it into "one header row, one row per
respondent, multi-selects identified". If nothing matches, the `generic` adapter is used.

| Platform | How it's detected | What's normalised |
|---|---|---|
| **Generic** | fallback | One header row; delimited multi-selects; `Q5_1`, `Q5_2` / `Q5 - Option` column families grouped |
| **HubSpot** | `Record ID` + `Submission Name`/`Survey ID` columns | `;` multi-selects; system columns suggested as `ignore` |
| **SurveyMonkey** | Row 2 is "Response"/option text, row 1 has merged question headers | 2 header rows → question + option; one-column-per-option multi-selects → group |
| **Qualtrics** | Row 3 is `{"ImportId": …}` JSON | 3 header rows; `QID` names; "Choice Text" vs "Numeric Values" exports both supported |
| **Typeform / Google Forms** | `#`, `Submit Date`, `Network ID` / `Timestamp` columns | Comma-separated checkboxes; one column per option |
| **Alchemer** | `Response ID`, `Time Started` | `:`-joined option columns |
| **Decipher** | `record`, `uuid`, `qtime`, `status` | Datamap-style `q1r1` names → groups |

Every structural decision (header rows, sheet, delimiter, adapter) is shown in the
review and can be overridden: `POST /v1/files/{id}/structure`.

### Generic inference (step ③)
The current heuristics, generalised and with a reason attached to each:
- **ID:** unique per row plus an ID-like name/pattern. **PII:** email/phone/name patterns
  (excluded from exports by default). **Date:** parseable datetimes.
  **Weight:** numeric, positive, name like weight/wt/pond.
- **Ignore:** constant, entirely empty, or export bookkeeping (generic patterns, not lists of
  vendor column names).
- **Single vs text:** distinct-value count, uniqueness ratio, answer length (as today).
- **Multi:** delimited answers (`;` `,` `|`, chosen by testing each), or column families
  with 0/1 / option-text / blank values.
- **Scale order:** built-in scale lexicon (multilingual: EN/ES/PT/FR/DE), then numeric
  prefixes, then natural order. Ambiguous cases are flagged "needs review" instead of
  being guessed silently.
- **Grids:** consecutive variables with the same codes and a shared label prefix.
- **NPS:** 0–10 range plus a recommend/NPS header → suggests a `bands` derived variable,
  which is shown in the UI as a suggestion, not created silently.

## 7. Review UI: "see it, fix it, move on"

A new step in the web app (`public/review.html`, reached from upload, wizard and express)
between upload and analysis. All logic stays in the API (the product *is* the API),
so MCP/SDK users get the same review data as JSON.

```
┌ survey_wave3.xls · HubSpot export · 1,200 respondents · 37 columns ────────── [Approve & continue] ┐
│ Structure: 1 header row · delimiter ";" · sheet "Sheet1"                                 [change] │
├─ Codebook ──────────────────────────────────────────┬─ Preview ──────────────────────────────────┤
│ ⚠ 2 need review   ✚ 1 new since v3   ⊘ 9 ignored    │ Row:    [Exam results ▾]                  │
│                                                     │ Banner: [NPS group ▾]   ☐ weight          │
│ ● Exam results   single · ordinal · 5 codes  98% ✓  │                                           │
│   1 Strongly Disagree ▇ 40                          │            Total  Detr.  Pass.  Prom.     │
│   2 Disagree          ▇▇ 90                         │            1150   28**   400    722       │
│   …                                                 │ Agree      50.0%  30.0%  58.0%A 48.0%a    │
│   98 I do not know    (missing) 30      [drag ⇅]    │ Top 2 box  75.0%  40.0%  70.0%A 82.0%AB   │
│ ● Job role       multi · ";" · 6 options      ✓     │ Mean       3.80   2.80   3.60A  4.10AB    │
│ ● Customer type  multi · 4 options            ⚠ new │ [table | bar | stacked]  ** base < 30     │
│ ● Sentiment      ignore · constant                  │                                           │
│ ＋ Add derived variable  (bands · priority · count…)│ Derived preview: Role group  1/110 2/300… │
└─────────────────────────────────────────────────────┴───────────────────────────────────────────┘
```

**Codebook panel**
- One row per variable: type chip, label, base, a small distribution bar per code,
  missing codes, confidence, and a reason tooltip ("matched 5-point agreement scale").
- Filters: *needs review*, *new since last version*, *ignored*, *derived*.
- Inline edits (each a codebook patch):
  - change role or measure; rename; edit labels;
  - drag codes to reorder; merge categories; mark as missing;
  - split or join multi-selects; group columns into a multi-select set or grid;
  - exclude a column; mark it as PII.
- "Add derived variable" opens the form for a rule type (§5), with a live count preview.
  Optionally, "describe it" asks Claude for a draft rule.

**Preview panel**
- Pick any row and banner variable, including derived ones. It renders the real crosstab
  from `/v1/crosstab`: column %, two-level sig letters, low-base markers, T2B and mean.
- Chart toggle (Chart.js, already used in `chat.html`): bars, stacked bars, and diverging
  bars for scales.
- **Updates on every codebook edit,** using the draft codebook. Nothing is saved until the
  user approves.

**Approve & continue**
- Saves a new codebook version, re-codes the file, and continues to auto-analyze, tabulate,
  the data workbook, or export.
- On a later wave the codebook is matched automatically. If nothing new is found the user
  can skip review entirely ("Nothing changed since v4: continue").

## 8. API

All endpoints use the standard envelope and `require_scope`. Identity comes from `key.name`.

| Endpoint | Purpose |
|---|---|
| `POST /v1/files/upload` | (existing) now also returns `structure` + `codebook_summary` + `matched_codebook` |
| `GET  /v1/files/{id}/structure` · `POST …/structure` | Detected layout; override header rows / sheet / delimiter / adapter |
| `GET  /v1/files/{id}/codebook` | Current draft or applied codebook, with reasons, confidence, distributions |
| `PATCH /v1/files/{id}/codebook` | Apply a list of edits (JSON Patch-style) → returns the updated codebook + affected variables |
| `POST /v1/files/{id}/codebook/apply` | Apply a saved codebook (`codebook_id`, `version`) → `ApplyReport` (new options, unmatched answers, missing columns) |
| `POST /v1/files/{id}/derived/preview` | Test a derived rule → counts per category, without saving |
| `POST /v1/codebooks` · `GET /v1/codebooks` · `GET /v1/codebooks/{id}[/versions/{v}]` | Save / list / fetch (versions are immutable) |
| `POST /v1/codebooks/{id}/describe-rule` | (optional AI) text → draft derived rule, never auto-applied |
| `POST /v1/crosstab`, `/v1/frequency`, `/v1/tabulate`, `/v1/auto-analyze`, `/v1/wave-compare`, `/v1/convert` | Accept the file's applied codebook automatically, or `codebook_id` explicitly |
| `POST /v1/exports/data-workbook` | Generic full-data + segment-tabs workbook, driven by `outputs.data_workbook` |
| MCP | `spss_get_codebook`, `spss_patch_codebook`, `spss_apply_codebook`, `spss_preview_derived` |

Redis keeps `{file_id}:raw`, `{file_id}:codebook` and `{file_id}:coded` (the coded .sav,
so endpoints stop re-parsing on every request), all with the same 30-minute TTL.

## 9. Delivery milestones

Sizes: S = days, M = 1–2 weeks, L = 2–4 weeks (one engineer). Each milestone ships on its own.

| # | Milestone | Size | Done when |
|---|---|---|---|
| **M0** | **Land Phase 1 safely.** Commit the generic parts. Put the client-specific code behind a feature flag until M4 replaces it | S | PR merged; tests green; Sept Pulse output unchanged |
| **M1** | **Decipher-style tables:** 95% capitals / 90% lowercase sig letters; low-base markers `*` <100, `**` <30 plus legend | S | Golden tests updated; markers in Excel and JSON |
| **M2** | **Split the pipeline:** `ingest → infer → apply` modules, `Codebook` model, `GET /codebook` (read-only), cached coded .sav in Redis | M | All existing tests pass unchanged; codebook JSON for every fixture snapshot-tested |
| **M3** | **Review UI v1:** `review.html` with codebook panel (read-only), live crosstab preview, charts, approve → continue | M | A user can upload any fixture, see every variable's interpretation, and preview crosstabs |
| **M4** | **Edit + derived rules:** `PATCH /codebook`, the 7 rule types, rule forms with live counts; client rules re-expressed as a codebook fixture; remove client-specific code | L | Sept Pulse workbook reproduced **only** from `fixtures/codebooks/cx_pulse.json`; grep test: no client strings in `services/` |
| **M5** | **Save + reuse across waves:** Supabase `codebooks` table, versions, fingerprint auto-match, `ApplyReport`, wave-compare uses the shared codebook | M | Oct wave applied with v-Sept codebook: identical codes, new options reported; skip-review path works |
| **M6** | **Platform adapters:** SurveyMonkey, Qualtrics, Typeform/Google Forms, Alchemer, Decipher + structure override UI | M–L | Real sample export per platform → correct codebook with no manual edits on the golden sample |
| **M7** | **Generic data workbook + exports:** segment tabs chosen in the codebook; %/count header rows; .sav export with full codebook metadata | S–M | Analyst-style workbook for any survey, configured in the UI |
| **M8** | **AI rule drafting (optional):** describe-a-rule → draft → approve | S | Analyst's job-role note produces the correct rule draft; never applied without approval |

Suggested order: M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8.
M3 (seeing the codebook) comes before M4 (editing it), so users get value early and we
learn which edits matter most.

## 10. Testing

- **Fixture corpus** (`tests/fixtures/exports/`): at least one real, anonymised export per
  platform, plus synthetic HubSpot-style exports. Each has a golden codebook JSON
  and golden crosstabs. **Needed from the team:** sample exports from each platform.
- **Snapshot tests:** inferred codebook per fixture. Any change to inference shows up as a
  readable diff.
- **Wave stability:** apply codebook v(n) to wave n+1 (with an added option, a removed
  option, and a renamed column) → codes unchanged, report correct.
- **Rule engine:** unit tests per rule type, plus property tests (priority groups are
  mutually exclusive; every answered respondent gets exactly one group).
- **No client-specific code:** a test greps `services/` for known client strings
  (client name, "Exams Officer", "Customer type", …) and fails if any are found.
- **Regression:** existing 152 tests plus the `example3` golden tabulation stay green
  throughout.
- **UI:** Playwright smoke test: upload → review → edit label → preview updates → approve.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Inference gets it wrong silently | Confidence + reasons shown; anything below the threshold is flagged "needs review"; approval step before outputs |
| Codes drift between waves | Saved codebooks are applied rather than re-inferred; codes never change; the report lists anything new |
| Platform export formats change | Adapters detect with a confidence score and fall back to `generic`; the user can override the structure |
| Performance on large files (100k+ rows) | Cached coded .sav in Redis; derived-rule preview runs on a sample, then the full set on approve |
| Rule language grows into a programming language | Fixed set of 7 rule types plus a small condition format; no `eval`; anything else is a feature request |
| PII leaking into exports | `pii` role detected by default and excluded from exports unless explicitly included |

## 12. Decisions needed

1. **Who can edit codebooks:** every user, or only an "analyst" role? Shared per organisation
   or per API key? (The current identity model is per key.)
2. **Auto-match:** apply a matching saved codebook automatically (with a banner saying so), or
   always ask?
3. **Which platforms first in M6:** need real sample exports to prioritise.
4. **The review step for API-only users:** optional (`auto_approve=true`), or required on first
   upload of a new survey?
5. **The client analyst's open questions** (col BZ, "Programmes AND/OR exams", Triple with
   "Other") are still needed, to make the `cx_pulse` codebook fixture correct in M4.
