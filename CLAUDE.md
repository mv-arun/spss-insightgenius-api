# Indico Crosstab API — CLAUDE.md

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
1. Upload via `/v1/files/upload` or MCP `spss_upload_file` → stored in Redis with 30min sliding TTL
2. Returns `file_id` (UUID)
3. All analysis endpoints accept `file_id` parameter
4. File re-parsed from Redis bytes on each request (no parsed cache yet)

### Response envelope
```json
{"success": true, "data": {...}, "meta": {"request_id": "abc", "processing_time_ms": 123}}
{"success": false, "error": {"code": "VARIABLE_NOT_FOUND", "message": "..."}}
```

## Endpoints (29 REST + MCP)

| Category | Endpoints |
|----------|-----------|
| System | GET /v1/health, GET /v1/usage |
| Files | POST /v1/files/upload, GET /downloads/{token} |
| Library | POST/GET/PATCH/DELETE /v1/library/*, GET /v1/library/search/files |
| Metadata | POST /v1/metadata |
| Analysis | /v1/frequency, /v1/crosstab, /v1/anova, /v1/correlation, /v1/gap-analysis, /v1/satisfaction-summary |
| Tabulation | POST /v1/tabulate (sync + async webhook; `output_mode: "displayr"` = Total / By banner / Stat sheets, `services/displayr_workbook.py`), POST /v1/auto-analyze |
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
- `public/ui/ic.js`: `<ic-sidebar>`, `<ic-topbar>` and `<ic-icon>`, plus the `window.IC` helpers.
- `public/ui/tw.js`: Tailwind theme for pages whose scripts still build utility-class markup.
- `public/ui/datasets.js`: library calls and the shared datasets table.
- New pages copy the skeleton in `home.html`. Don't add new colours or a second style system.

Optional features (off by default; `ENABLE_DATASETS`, `ENABLE_AI_CHAT`):
- Off, their API routes (`/v1/library/*`, `/v1/chat*`) and pages (`/datasets*`, `/export-mcp`) aren't served.
- `/static/config.js` sets `window.__INDICO_FEATURES__`, and the pages hide their links (`IC.FEATURES`).
- Datasets is the only part of the app that needs Supabase.

Sidebar sections and the pages behind them:
- Home: `/home`
- Datasets: `/datasets`, `/datasets/upload`, `/datasets/{id}`
- Transformations: `/review`
- Workflows: `/workflows` → `/export` (tabulation: Upload → Review data → Banners + respondent filter → Tables → Options → Custom groups → Generate), `/express`, `/wizard`, `/export-mcp` (AI chat)
- Settings: `/settings`

Sign-in:
- `/` is the split-screen sign-in.
- App pages need the `ic_session` cookie (`routers/ui_auth.py`). Without it they redirect to `/?next=…`.
- There is one account, set by `UI_LOGIN_EMAIL` / `UI_LOGIN_PASSWORD` (`UI_LOGIN_NAME` is optional). Sign-in is refused while either is unset.
- `/upload` (MCP uploader), `/privacy` and `/docs/mcp` stay public.
- The pages still call the API with the demo key from `/static/config.js`.

## Testing

```bash
python -m pytest tests/ -x -q --tb=short  # 114 tests, ~22s
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
