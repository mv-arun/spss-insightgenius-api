# Indico Crosstab API

**Market research tables as an API + MCP server.** Send a survey data file (.sav, .csv, .tsv, .xlsx, .xls), get crosstabs with significance letters, nets, weighting and publication-ready Excel tabulations.

**Live**: [crosstab.indicolabs.io](https://crosstab.indicolabs.io) | **API guide**: [/docs/api](https://crosstab.indicolabs.io/docs/api) | **Try it**: [/docs](https://crosstab.indicolabs.io/docs) (Swagger) | **OpenAPI**: [/openapi.json](https://crosstab.indicolabs.io/openapi.json) | **MCP**: [/docs/mcp](https://crosstab.indicolabs.io/docs/mcp)

---

## Quick Start

### Option 1: Web app (no code needed)

Sign in at [crosstab.indicolabs.io](https://crosstab.indicolabs.io); the app (`/app`) is one stepped flow:
**Dataset** (upload) → **Variables** (how every column was read; fix labels, types, bases, build derived
variables) → **Crosstabs** (build the tables: rows, columns, filters, live preview) → **Options** → **Generate** (Excel).

The Variables step is also served on its own at `/review`.

### Option 2: Auto-Analyze (zero config)

```bash
curl -X POST https://crosstab.indicolabs.io/v1/auto-analyze \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@survey.sav" \
  -o auto_analysis.xlsx
```

Auto-detects banners, groups variables into MRS/Grid, applies nets, and generates a complete Excel.

### Option 3: Full Control

```bash
curl -X POST https://crosstab.indicolabs.io/v1/tabulate \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@survey.sav" \
  -F 'spec={
    "banners": ["gender", "region", "age_group"],
    "stubs": ["_all_"],
    "significance_level": 0.95,
    "include_means": true,
    "nets": {"sat_overall": {"Top 2 Box": [4,5], "Bottom 2 Box": [1,2]}},
    "mrs_groups": {"Brand_Awareness": ["AWARE_A","AWARE_B","AWARE_C"]}
  }' -o tabulation.xlsx
```

### Option 4: From another app

Upload once, reuse the `file_id`, and choose how files come back (`response_format`: `file`, `url` or `base64`):

```python
import requests, json

API, H = "https://crosstab.indicolabs.io", {"Authorization": "Bearer YOUR_API_KEY"}

file_id = requests.post(f"{API}/v1/files/upload", headers=H,
                        files={"file": open("survey.sav", "rb")}).json()["file_id"]

resp = requests.post(f"{API}/v1/tabulate", headers=H, data={
    "file_id": file_id,
    "spec": json.dumps({"banners": ["gender", "region"], "stubs": ["_all_"]}),
    "response_format": "url",
})
resp.raise_for_status()
print(resp.json()["data"]["download_url"])   # valid 15 minutes
```

JSON-only callers can upload with `POST /v1/files/upload-base64`; long jobs can run in the background
with `webhook_url` (poll `GET /v1/jobs/{job_id}`). Errors are always
`{"success": false, "error": {"code", "message"}}`. Everything is in the [API guide](https://crosstab.indicolabs.io/docs/api).

### Option 5: MCP (for AI agents)

Connect to `https://crosstab.indicolabs.io/mcp/sse` (setup: [/docs/mcp](https://crosstab.indicolabs.io/docs/mcp)).
Upload with `spss_upload_file` (or the `/upload` page) and pass the `file_id` to the other tools.

---

## Endpoints

The full, always-current list with every field is the [API guide](https://crosstab.indicolabs.io/docs/api) (generated from the OpenAPI schema).

| Area | Endpoints |
|------|-----------|
| Files | `POST /v1/files/upload`, `POST /v1/files/upload-base64`, `GET`/`DELETE /v1/files/{file_id}`, `GET /downloads/{token}` |
| Metadata & coding | `POST /v1/metadata`, `POST /v1/codebook`, `GET`/`PATCH /v1/files/{file_id}/codebook` |
| Analysis (JSON) | `/v1/frequency`, `/v1/crosstab`, `/v1/correlation`, `/v1/anova`, `/v1/gap-analysis`, `/v1/satisfaction-summary`, `/v1/wave-compare`, `/v1/process` |
| Tabulation (Excel) | `/v1/tabulate` (sync, or async with `webhook_url`), `/v1/tabulate/preview` (JSON), `/v1/auto-analyze` |
| Export | `/v1/convert` (xlsx, csv, dta, parquet), `/v1/exports/data-workbook` |
| Weighting | `/v1/weight/preview`, `/v1/weight/compute` |
| Setups | `GET /v1/setups`, `POST /v1/setups/match`, `POST /v1/setups/apply` |
| AI | `/v1/smart-spec`, `/v1/parse-ticket` (plus `/v1/chat*` when `ENABLE_AI_CHAT`) |
| Jobs & keys | `GET /v1/jobs/{job_id}`, `/v1/keys` |
| System | `GET /v1/health`, `GET /v1/usage` |

## MCP Tools

| Tool | Description |
|------|-------------|
| `spss_get_started` | How to use the tools |
| `spss_upload_file` | Start a file session → `file_id` |
| `spss_get_metadata` | Variable metadata + auto-detect |
| `spss_get_codebook` | How each column is coded |
| `spss_describe_variable` | Single variable detail |
| `spss_analyze_frequencies` | Frequency table |
| `spss_analyze_crosstab` | Crosstab with sig letters |
| `spss_analyze_correlation` | Correlation matrix |
| `spss_analyze_anova` | ANOVA + Tukey HSD |
| `spss_analyze_gap` | Gap analysis with quadrants |
| `spss_summarize_satisfaction` | Satisfaction summary |
| `spss_create_tabulation` | Full tabulation → Excel (download link) |
| `spss_auto_analyze` | Zero-config → Excel (download link) |
| `spss_export_data` | Format conversion |
| `spss_get_server_info` | Server version and limits |

---

## Tabulate Spec

The main fields (all of them: [API guide → Tabulation spec](https://crosstab.indicolabs.io/docs/api#spec)):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `banners` | string[] | none (Total only) | Demographics for columns (e.g., `["gender", "region"]`) |
| `stubs` | string[] | `["_all_"]` | Questions for rows (`_all_` = auto-select all) |
| `significance_level` | float | `0.95` | 0.90, 0.95, or 0.99 |
| `weight` | string | `null` | Weight variable name |
| `include_means` | bool | `false` | Add Mean row with T-test sig letters |
| `include_total_column` | bool | `true` | Total as first column |
| `output_mode` | string | `"multi_sheet"` | `"multi_sheet"`, `"single_sheet"`, `"banner_sheets"` (Total / By banner / Stat) or `"pages"` (with `pages`) |
| `nets` | object | `null` | Per-variable net definitions |
| `mrs_groups` | object | `null` | MRS groups: `{"name": ["var1", "var2"]}` |
| `grid_groups` | object | `null` | Grid groups: `{"name": {"variables": [...], "show": ["t2b","mean"]}}` |
| `custom_groups` | array | `null` | Custom breaks with AND conditions |
| `title` | string | `""` | Report title |

### Excel Output

- **Summary sheet**: file info, column legend (A=London, B=South East...), stub index
- **One sheet per stub**: headers → letters → base (N) → data with `pct% SIG_LETTERS` → nets → means
- **MRS sheets**: one per group, percentages can exceed 100%
- **Grid sheets**: compact T2B/B2B/Mean summary
- Significance letters in red, nets in green rows
- Freeze panes for scrolling

---

## Significance Testing

Column proportion z-test with letter notation (A/B/C):
- Each banner category gets a letter (e.g., Male=A, Female=B, London=C, North=D)
- Each cell tested vs every other column
- Significantly higher → other column's letter appears (e.g., `68.6% E` means sig higher than column E)
- Supports weighted (Kish effective-n) and unweighted
- Means tested with independent T-test
- Confidence levels: 90%, 95%, 99%
- Two levels (Decipher style, default for auto-analyze): `"significance_levels": [0.95, 0.90]` shows
  CAPITAL letters at 95% and lowercase at 90% only (e.g. `58.6% ACd`). JSON adds
  `significance_letters_secondary` per cell
- Low-base markers on the Base row: `*` base < 100, `**` base < 30 (`low_base_warn` / `low_base_flag`,
  0 = off); the base stays numeric in Excel. `/v1/crosstab` returns `column_bases` and `low_base`

---

## Authentication

All endpoints require: `Authorization: Bearer sk_live_...` or `sk_test_...`

### Rate Limits

| Plan | Requests/min | Max file (/v1/tabulate) |
|------|-------------|----------|
| Free | 10 | 5 MB |
| Pro | 60 | 50 MB |
| Business | 200 | 200 MB |

### Error Codes

Every error: `{"success": false, "error": {"code": "...", "message": "..."}}` (full list in the [API guide](https://crosstab.indicolabs.io/docs/api#errors)).

| Code | HTTP | Meaning |
|------|------|---------|
| `UNAUTHORIZED` | 401 | Missing/invalid API key |
| `FORBIDDEN` | 403 | Valid key, wrong scope |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INVALID_FILE_FORMAT` | 400 | The file can't be read |
| `FILE_NOT_FOUND` | 404 | `file_id` unknown or expired |
| `FILE_TOO_LARGE` | 413 | Exceeds plan limit |
| `VARIABLE_NOT_FOUND` | 400 | Variable doesn't exist |
| `PROCESSING_FAILED` | 500 | Engine error |
| `PROCESSING_TIMEOUT` | 504 | Exceeded time limit |

---

## Local Development

```bash
git clone https://github.com/quack2025/spss-insightgenius-api.git
cd spss-insightgenius-api
pip install -r requirements.txt
cp .env.example .env  # Edit with your API key hash
python main.py        # → http://localhost:8000
python -m pytest tests/ -q
```

Testing locally without API keys: set `AUTH_DISABLED=true` (requests without a key run as an
anonymous user; never use in production), e.g.
`AUTH_DISABLED=true python -m uvicorn main:app --port 8000`.

Survey exports (Excel/CSV) are covered by a golden test on a **synthetic** HubSpot-style file
(`tests/fixtures/exports/`, generated by `make_hubspot_cx_sample.py`; never commit real client
data, this repo is public). After an intended output change, regenerate and review the snapshot:
`UPDATE_GOLDEN=1 python -m pytest tests/test_cx_pulse_golden.py`.

Client rules are **setups**, not code: named lists of codebook edits in `presets/` (e.g. the
HubSpot CX job-role priority groups, Single / Dual / Triple product, product mix, DRIVERS).
`GET /v1/setups`, `POST /v1/setups/match` and `POST /v1/setups/apply` (built-in `setup_id`, or an
exported `setup` JSON); edits that don't fit a file are skipped and reported. The review page applies
a setup whose columns are all present automatically, offers partial matches, and can save the user's
own changes as a setup file for the next wave. See [RECODING_PLAN.md](RECODING_PLAN.md) §6.

Respondent **data sheets** (FULL DATA with 1/blank flag columns + one sheet per category, with % and
count rows) come from the codebook's `data_workbook` setting (`services/data_workbook.py`): set it in
the review page's *Data sheets* panel or with a setup (the HubSpot setups reproduce the analysts'
workbook). Auto-analyze appends them when the codebook has the setting;
`POST /v1/exports/data-workbook` returns them on their own.

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Pydantic v2 |
| Engine | QuantipyMRX (crosstab, sig testing, auto-detect, MRS, NPS) |
| AI | Claude Sonnet (smart-spec, chat), Haiku (ticket parsing, labels, executive summary) |
| Auth | API keys (SHA-256 hashes) + Clerk OAuth for MCP |
| Storage | Redis (file sessions, downloads, jobs, rate limits); Supabase (keys, usage, library) |
| Rate Limiting | Redis (fallback: in-memory) |
| MCP | FastMCP with SSE transport |
| Deploy | Railway (Docker, Gunicorn, 4 replicas, auto-deploy) |

Built by [Indico Labs](https://indicolabs.io).
