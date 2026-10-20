# Indico Crosstab API

**Professional SPSS processing API + MCP server for market research.** Upload .sav files, get crosstabs with significance testing, auto-detected question types, and publication-ready Excel exports. Includes AI-powered zero-config analysis.

**Live**: [crosstab.indicolabs.io](https://crosstab.indicolabs.io) | **API Docs**: [crosstab.indicolabs.io/docs](https://crosstab.indicolabs.io/docs) | **MCP**: `crosstab.indicolabs.io/mcp/sse`

---

## Quick Start

### Option 1: Web UI (no code needed)

1. Open [crosstab.indicolabs.io](https://crosstab.indicolabs.io)
2. Drag & drop your `.sav` file
3. Click **Auto-Analyze** for instant results, or configure manually:
   - Select banner variables (demographics for columns)
   - Choose stubs (questions for rows)
   - Enable Top 2 Box / Means
4. Click **Generate Excel** → download your tabulation

### Review how a file was read

In the web app (`/app`) this is **Step 2 — Review data**, right after upload; the following steps (banners, stubs, tabulation, one-click analysis) use the reviewed coding. Standalone: open `/review`, drop any SPSS / Excel / CSV file and see the codebook — how every column was coded, with
counts and reasons — next to a live crosstab and chart. Fix anything that was misread (rename, change type,
exclude "Don't know" from bases, merge or reorder answers) and build derived variables (bands, groups,
Single/Dual/Triple counts, priority groups…) with a live preview. Approve to run the full analysis.

### Option 2: Auto-Analyze (zero config)

```bash
curl -X POST https://crosstab.indicolabs.io/v1/auto-analyze \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@survey.sav" \
  -o auto_analysis.xlsx
```

AI auto-detects banners, groups variables into MRS/Grid, applies nets, and generates a complete Excel.

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

### Option 4: Python

```python
import requests, json

resp = requests.post(
    "https://crosstab.indicolabs.io/v1/tabulate",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    files={"file": open("survey.sav", "rb")},
    data={"spec": json.dumps({
        "banners": ["gender", "region"],
        "stubs": ["_all_"],
        "include_means": True,
        "significance_level": 0.95,
    })}
)
with open("tabulation.xlsx", "wb") as f:
    f.write(resp.content)
print(f"Done: {resp.headers['X-Stubs-Success']} tables generated")
```

### Option 5: MCP (for AI agents)

Connect to `https://crosstab.indicolabs.io/mcp/sse` and use any of the 12 tools. Files are passed as base64.

---

## Endpoints (14)

| Method | Endpoint | Description |
|--------|----------|-------------|
| **POST** | `/v1/auto-analyze` | **Zero-config** — upload .sav, get complete Excel (AI-detected banners, MRS, grids, nets) |
| **POST** | `/v1/tabulate` | **Full tabulation → Excel** with sig letters, nets, means, MRS, grids, custom groups. Accepts optional .docx Reporting Ticket. |
| POST | `/v1/metadata` | Variable metadata + suggested banners + detected groups + preset nets |
| POST | `/v1/codebook` | How each column is coded: codes + raw answers + counts, missing codes, multi-selects, derived variables, reasons (also `GET /v1/files/{file_id}/codebook`). Send `edits` to change it (rename, recode, exclude from base, merge, derived variables: bands / recode / priority / count / combination / coalesce / flags); `PATCH /v1/files/{file_id}/codebook` saves edits with the file session. Analysis endpoints accept the edited `codebook` |
| POST | `/v1/frequency` | Frequency table (counts, %, mean, std, median) |
| POST | `/v1/crosstab` | Single crosstab with sig letters (A/B/C) + chi-square p-value |
| POST | `/v1/correlation` | Correlation matrix (Pearson/Spearman/Kendall) with p-values |
| POST | `/v1/anova` | One-way ANOVA with Tukey HSD post-hoc comparisons |
| POST | `/v1/gap-analysis` | Importance-Performance gap analysis with quadrants |
| POST | `/v1/satisfaction-summary` | Compact T2B/B2B/Mean for multiple scale variables |
| POST | `/v1/process` | Multi-operation pipeline (auto-detect or manual) |
| POST | `/v1/convert` | Convert .sav → xlsx, csv, parquet, dta |
| POST | `/v1/parse-ticket` | Parse Reporting Ticket .docx → tab plan (Haiku AI) |
| GET | `/v1/health` | Health check + engine status |
| GET | `/v1/usage` | Usage stats for your API key |

## MCP Tools (12)

| Tool | Description |
|------|-------------|
| `get_spss_metadata` | Variable metadata + auto-detect |
| `get_variable_info` | Single variable detail |
| `analyze_frequencies` | Frequency table |
| `analyze_crosstabs` | Crosstab with sig letters |
| `analyze_correlation` | Correlation matrix |
| `analyze_anova` | ANOVA + Tukey HSD |
| `analyze_gap` | Gap analysis with quadrants |
| `summarize_satisfaction` | Satisfaction summary |
| `create_tabulation` | Full tabulation → Excel (base64) |
| `auto_analyze` | Zero-config → Excel (base64) |
| `export_data` | Format conversion |
| `list_files` | Available tools |

---

## Tabulate Spec

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `banners` | string[] | *required* | Demographics for columns (e.g., `["gender", "region"]`) |
| `stubs` | string[] | `["_all_"]` | Questions for rows (`_all_` = auto-select all) |
| `significance_level` | float | `0.95` | 0.90, 0.95, or 0.99 |
| `weight` | string | `null` | Weight variable name |
| `include_means` | bool | `false` | Add Mean row with T-test sig letters |
| `include_total_column` | bool | `true` | Total as first column |
| `output_mode` | string | `"multi_sheet"` | `"multi_sheet"`, `"single_sheet"`, or `"banner_sheets"` (Total / By banner / Stat) |
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

| Plan | Requests/min | Max file | Price |
|------|-------------|----------|-------|
| Free | 10 | 5 MB | $0 |
| Growth | 60 | 50 MB | $29/mo |
| Business | 200 | 200 MB | $99/mo |
| Enterprise | Unlimited | 500 MB | Custom |

### Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `UNAUTHORIZED` | 401 | Missing/invalid API key |
| `FORBIDDEN` | 403 | Valid key, wrong scope |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INVALID_FILE_FORMAT` | 400 | Not a .sav file |
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
| AI | Claude Haiku (ticket parsing, smart labels, executive summary) |
| Auth | API keys (SHA256, no DB) |
| Rate Limiting | Redis (fallback: in-memory) |
| MCP | FastMCP with SSE transport |
| Deploy | Railway (Docker, Gunicorn, 4 replicas, auto-deploy) |

Built by [Indico Labs](https://indicolabs.io).
