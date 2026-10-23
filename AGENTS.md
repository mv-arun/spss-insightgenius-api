# Indico Crosstab API — AGENTS.md

## What this project is

REST API + MCP server for deterministic market research data analysis. Processes SPSS files and generates professional Excel tabulations with significance testing. The product IS the API — frontends are convenience wrappers.

**URL:** https://crosstab.indicolabs.io
**GitHub:** quack2025/spss-insightgenius-api
**Deploy:** Railway (auto-deploy from `master`, 4 replicas)
**Engine:** QuantipyMRX (Python 3.11 + pandas + scipy)

## Stack

- **Backend:** FastAPI + Gunicorn + UvicornWorker
- **Engine:** QuantipyMRX fork (quantipy for Python 3.11+)
- **AI:** Anthropic Claude (Sonnet for smart-spec/chat, Haiku for labeling)
- **Cache/Sessions:** Redis (file sessions 30min TTL, rate limiting, idempotency)
- **Auth:** SHA-256 hashed API keys + Clerk OAuth JWT
- **Storage:** Supabase (API keys, usage, library)
- **MCP:** FastMCP SSE transport at `/mcp/sse`

## Key Architecture Decisions

### Middleware: Pure ASGI only
**NEVER use Starlette `BaseHTTPMiddleware`** — it causes `AssertionError` on streaming/empty responses and blocks Railway deploys. All middleware uses raw ASGI `send_wrapper` pattern. See `middleware/response_headers.py` and `middleware/idempotency.py`.

### Auth pattern
```python
# Endpoints use dependency injection:
key: KeyConfig = Depends(require_auth)       # any valid key
key: KeyConfig = Depends(require_scope("process"))  # key with specific scope
```
User identity = `key.name`. NEVER accept user_id from client input.

### File flow
1. Upload via `/v1/files/upload` (multipart), `/v1/files/upload-base64` (JSON) or MCP `spss_upload_file` → stored in Redis with 30min sliding TTL
2. Returns `file_id` (UUID); `GET`/`DELETE /v1/files/{file_id}` show / end the session
3. All analysis endpoints accept `file_id` parameter
4. Parsed once per worker per file + codebook (`services/data_cache.py`, `PARSED_CACHE_MB`, default 512; used by /v1/tabulate, /v1/tabulate/preview, /v1/crosstab). Callers get their own copy: tabulation adds columns to the data it's given.

### Response envelope
```json
{"success": true, "data": {...}, "meta": {"request_id": "abc", "processing_time_ms": 123}}
{"success": false, "error": {"code": "VARIABLE_NOT_FOUND", "message": "..."}, "detail": {...}}
```
- Errors: keep raising `HTTPException(status, detail={"code", "message"})`; the handlers in `main.py` wrap every error (and 422s) in the envelope, keeping FastAPI's `detail` for older callers.
- File outputs (`/v1/tabulate`, `/v1/auto-analyze`, `/v1/convert`, `/v1/exports/data-workbook`) take `response_format`: `file` (bytes) / `url` (download link, 15 min) / `base64`. Use `shared/file_output.py`.
- Async: `/v1/tabulate` + `webhook_url` → 202 + job; jobs are written through to Redis (`shared/job_store.py`) so any worker can answer `/v1/jobs/{id}`.
- Integration guide for other apps: `/docs/api` (`public/api-docs.html`; its endpoint reference renders `/openapi.json`, so keep summaries / descriptions / Form descriptions accurate).

## Endpoints (32 REST + MCP)

| Category | Endpoints |
|----------|-----------|
| System | GET /v1/health, GET /v1/usage |
| Files | POST /v1/files/upload, POST /v1/files/upload-base64, GET/DELETE /v1/files/{file_id}, GET /downloads/{token} |
| Library | POST/GET/PATCH/DELETE /v1/library/*, GET /v1/library/{id}/file (original bytes), GET /v1/library/search/files |
| Metadata | POST /v1/metadata |
| Analysis | /v1/frequency, /v1/crosstab, /v1/anova, /v1/correlation, /v1/gap-analysis, /v1/satisfaction-summary |
| Tabulation | POST /v1/tabulate (sync + async webhook; `output_mode: "pages"` + `pages: [{name, tables}]` = one sheet per page; `table_specs` = per-table columns / filters / custom groups, tables with the same setup tabulated together; `output_mode: "banner_sheets"` = Total / By banner / Stat sheets, `services/banner_workbook.py`), POST /v1/tabulate/preview (the banner workbook's tables as JSON, `tables: [...]` ≤ 50, for live previews), POST /v1/auto-analyze |
| Export | POST /v1/convert, POST /v1/exports/data-workbook (FULL DATA + category sheets from the codebook) |
| AI | POST /v1/smart-spec, /v1/parse-ticket, /v1/chat, /v1/chat-stream |
| Weighting | POST /v1/weight/preview, /v1/weight/compute |
| Wave | POST /v1/wave-compare |
| Setups | GET /v1/setups, POST /v1/setups/match, POST /v1/setups/apply (client rules as data, `presets/`) |
| Jobs | GET /v1/jobs/{job_id} |
| Keys | POST/GET/DELETE /v1/keys |
| MCP | 13 tools at /mcp/sse |

## Web UI

Static pages in `public/`, routed in `main.py`. One design system for every page:
- `public/ui/ic.css`: tokens and component classes (`.ic-btn`, `.ic-card`, `.ic-table`, `.ic-stepper`, `.ic-dropzone`, `.ic-option`, `.ic-result`, `.ic-modal`…).
- `public/ui/ic.js`: `<ic-appbar>` (brand, steps via `IC.appbarSteps`, API docs, user menu) and `<ic-icon>`, plus the `window.IC` helpers (`popMenu` / `popover` for pop-ups).
- `public/ui/tw.js`: Tailwind theme for pages whose scripts still build utility-class markup.
- `public/ui/datasets.js`: the library calls the Dataset step uses.
- New pages use `<div class="ic-app ic-app--bar"><ic-appbar></ic-appbar><div class="ic-main"><main class="ic-page">` (see `settings.html`). Don't add new colours or a second style system.

Optional features (off by default; `ENABLE_DATASETS`, `ENABLE_AI_CHAT`):
- Off, their API routes (`/v1/library/*`, `/v1/chat*`) and `/export-mcp` aren't served.
- `/static/config.js` sets `window.__INDICO_FEATURES__`, and the pages hide what needs them (`IC.FEATURES`).
- Datasets is the only part of the app that needs Supabase.

Navigation: no sidebar. The app is one stepped flow at `/app` (also `/export`), with its steps in the app bar:
- Dataset (library table when Datasets is on + upload) → Variables (`/review?embed=1` in a frame: the Variables grid) → Crosstabs → Options → Generate
- Crosstabs: first asks "a table for every question" or "start with no tables" (the questions stay listed either way). Views (tabs on the top line, with Back / Next mirroring the view's footer): Build tables (variables on the left; above the editor, the report's tables (`xtTables`, output order; + New table) and its sheets (drop a table on one); the open table's Rows, Columns, Filter (its own, sent as `table_specs`), Values (every table) and live preview), Arrange pages (a board: one column per sheet, tables stacked in order), Review all (every table, sheet by sheet, before Options).
- Values: Column %, Row %, Counts, T2B/B2B, answer order (file / Total / A→Z), significance. Chip menu → "Choose answers…" hides answers or columns (`hide_codes`; bases unchanged). Order, Row % (`show_row_pct`: a "(Row %)" sheet per banner) and hidden answers are written by `output_mode: "banner_sheets"` only, like the preview.
- A refresh picks up where the analyst left off: the file, its reviewed coding and every choice are kept in IndexedDB (`indico-crosstab`; ≤ 100 MB, 7 days, cleared on sign-out).
- Plan and what's left: `docs/proposals/variables-crosstabs-plan.md`
- `/home`, `/workflows` (and `/datasets*` when Datasets is on) redirect to `/app` (their pages were removed).
- Off the bar but served: `/review` (standalone Variables), `/express`, `/wizard`, `/export-mcp`, `/settings` (account menu)

Sign-in:
- `/` is the split-screen sign-in; signed in, it goes to `/app`.
- App pages need the `ic_session` cookie (`routers/ui_auth.py`). Without it they redirect to `/?next=…`.
- There is one account, set by `UI_LOGIN_EMAIL` / `UI_LOGIN_PASSWORD` (`UI_LOGIN_NAME` is optional). Sign-in is refused while either is unset.
- `/upload` (MCP uploader), `/privacy`, `/docs/api` and `/docs/mcp` stay public.
- The pages still call the API with the demo key from `/static/config.js`.

## Testing

```bash
python -m pytest tests/ -x -q --tb=short  # 298 tests, ~45s
```

- `tests/test_tabulation_real.py` — golden standard tests vs R export
- `tests/fixtures/` — example3_raw.sav + example3_golden.xlsx
- `tests/test_mcp.py` — MCP tool tests (direct function calls)
- `tests/test_jobs.py` — async job lifecycle + HTTP integration

## Deployment

- Push to `master` → Railway auto-deploys
- Dockerfile: multi-stage, non-root user, gunicorn 4 workers
- Healthcheck: `GET /v1/health`
- `python-pptx` is required (quantipymrx imports it internally)
- Security headers injected via ASGI middleware (not BaseHTTPMiddleware)

## npm SDK

`@indicolabs/crosstab-sdk` at `C:\Users\jorge\proyectos_python\indico-crosstab-sdk`

```typescript
const ig = new IndicoCrosstab("sk_test_...");
const { file_id } = await ig.upload(file, "survey.sav");
const meta = await ig.getMetadata(file_id);
const ct = await ig.crosstab(file_id, { row: "Q1", col: "Gender" });
const excel = await ig.tabulate(file_id, { banners: ["Gender"], stubs: ["_all_"] });
```

## Enterprise Standards

See `~/.claude/projects/C--Users-jorge/memory/enterprise_api_standards.md` for the full checklist that this project and all Indico Labs API products must follow.
