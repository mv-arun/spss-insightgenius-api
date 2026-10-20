# Indico Crosstab — Product Roadmap

> Last updated: 2026-04-05

## Vision

The **Stripe of market research** — a deterministic statistical engine that developers integrate to build their own tabulation products. The product IS the API. Frontends are convenience wrappers and starter templates.

---

## Current State (Post-Enterprise Audit — Apr 5 2026)

### What's Live

| Feature | Status | Endpoint |
|---------|--------|----------|
| SPSS .sav/.por/.zsav/.csv/.xlsx upload + metadata | Production | `/v1/files/upload`, `/v1/metadata` |
| Auto-detect question types (QuantipyMRX) | Production | in metadata response |
| Smart metadata: suggested_banners, detected_groups, preset_nets | Production | in metadata response |
| Frequency tables (weighted/unweighted, mean/std/median) | Production | `/v1/frequency` |
| Single crosstab with sig letters + chi2 p-value | Production | `/v1/crosstab` |
| Full tabulation → Excel (multi/single-sheet) | Production | `/v1/tabulate` |
| Async tabulation with webhooks | Production | `/v1/tabulate` + `webhook_url` → 202 |
| Job status polling | Production | `/v1/jobs/{job_id}` |
| Means with T-test significance (Bonferroni) | Production | in tabulate |
| Multiple banners side-by-side (A/B + C/D/E) | Production | in tabulate |
| Nested banners (cross-product: parent × child) | Production | in tabulate |
| MRS groups (select-all-that-apply) | Production | in tabulate |
| Grid/Battery summary (T2B/Mean compact table) | Production | in tabulate |
| Custom groups (custom breaks with AND conditions) | Production | in tabulate |
| Stub filters (per-stub conditional bases) | Production | in tabulate |
| Total column as first column | Production | in tabulate |
| Nets (Top 2 Box, Bottom 2 Box, custom) | Production | in tabulate |
| Weight support (Kish effective-n, dual bases) | Production | in tabulate |
| Correlation matrix (Pearson/Spearman/Kendall) | Production | `/v1/correlation` |
| One-way ANOVA with Tukey HSD post-hoc | Production | `/v1/anova` |
| Importance-Performance gap analysis | Production | `/v1/gap-analysis` |
| Satisfaction summary (T2B/B2B/Mean compact) | Production | `/v1/satisfaction-summary` |
| Auto-analyze (zero-config → complete Excel) | Production | `/v1/auto-analyze` |
| Wave comparison (z-test/t-test between waves) | Production | `/v1/wave-compare` |
| Format conversion (.sav → xlsx/csv/dta/parquet) | Production | `/v1/convert` |
| Smart Spec Generator (Sonnet → TabulateSpec) | Production | `/v1/smart-spec` |
| Reporting Ticket .docx parsing (Sonnet) | Production | `/v1/parse-ticket` |
| Conversational analysis (Sonnet + engine) | Production | `/v1/chat`, `/v1/chat-stream` |
| RIM weighting | Production | `/v1/weight/preview`, `/v1/weight/compute` |
| Persistent file library (Supabase) | Production | `/v1/library/*` |
| Self-service API key management | Production | `/v1/keys` |
| API key auth + scope-based authorization | Production | middleware |
| Clerk OAuth JWT validation | Production | middleware |
| Per-plan rate limiting (Redis + in-memory fallback) | Production | middleware |
| Idempotency keys (Redis + in-memory fallback) | Production | middleware |
| Security headers (HSTS, nosniff, X-Frame-Options) | Production | middleware |
| Usage metering (fire-and-forget to Supabase) | Production | middleware |
| MCP server (13 tools, SSE transport) | Production | `/mcp/sse` |
| Embedded web UI: export, express, wizard, chat | Production | `/export`, `/express`, `/wizard`, `/export-mcp` |
| Landing page with competitive comparison | Production | `/` |
| Developer portal | Production | `/developers` |
| Privacy policy | Production | `/privacy` |
| API docs (Swagger) | Production | `/docs` |
| MCP docs | Production | `/docs/mcp` |
| npm SDK (@indicolabs/crosstab-sdk) | Built | `indico-crosstab-sdk/` repo |

### Key Metrics

| Metric | Value |
|--------|-------|
| Total REST endpoints | 29 |
| MCP tools | 13 |
| Tests (backend) | 114 |
| Tests (SDK) | 13 |
| Analysis types | 9 (frequency, crosstab, correlation, ANOVA, gap, satisfaction, auto, wave, RIM) |
| AI services | 3 (smart-spec generator, ticket parser, chat) |
| Tabulate features | 14 (sig, means, nets, MRS, grids, nested banners, stub filters, custom groups, Total, multi/single-sheet, dual bases, ticket, webhooks, async jobs) |
| Enterprise score | 7.5/10 (post-audit fixes) |

---

## Completed Sprints

### Sprint 1-6 (Mar 18-23): Foundation
7→14 endpoints, QuantipyMRX engine, MCP server (12 tools), embedded UI, 68 tests.

### Sprint 7: Enterprise Hardening (Mar 28)
Bonferroni significance, idempotency middleware, error standardization, key management, usage metering, concurrency controls.

### Sprint 8: MCP v2 + API v2 (Mar 28)
22 MCP tools, 52 REST endpoints (v1+v2), shared `executeCodingPipeline()`, deployed.

### Sprint 9: Nested Banners + Wave Compare + Stub Filters (Mar-Apr)
Nested banners (cross-product), wave comparison (z/t-test), stub filters, CI pipeline, OpenAPI spec.

### Sprint 10: 4 CRITICAL Security Fixes (Apr 5)
1. Library IDOR → auth + ownership on all 8 endpoints
2. PyJWT fallback bypass → removed unverified decode
3. CORS wildcard → restricted to explicit origins
4. MCP anonymous access → auth_required on empty key

### Sprint 11: Enterprise Audit + Quick Wins (Apr 5)
7-agent audit (Security, API, Performance, Dead Code, Test Coverage, Playwright E2E, MCP Live).
Score: 6.5/10 → 7.5/10 after fixes:
- Auth on file upload, ownership on 3 library endpoints
- Error boundaries on wave_compare + smart_spec
- PostgREST query sanitization
- Security headers (HSTS, nosniff, X-Frame-Options, Referrer-Policy)
- Dead code cleanup (-1830 lines, deleted schemas/, smart_labeler, request_id)
- BaseHTTPMiddleware → pure ASGI (fixed Railway deploy crashes)
- python-pptx restored (transitive dependency of quantipymrx)

### Sprint A: Developer Experience (Apr 5, in progress)
- npm SDK (`@indicolabs/crosstab-sdk`) — 13 types, all 28 methods, MSW tests
- Async webhooks — job store, `/v1/jobs/{id}`, webhook delivery
- Next.js template (pending)
- Developer portal page (pending)

---

## Next Up

### Sprint A Remaining (This Week)
| Item | Status |
|------|--------|
| Next.js starter template (upload → crosstab → Excel) | Pending |
| Developer portal page (`/developers`) | Pending |
| Publish SDK to npm | Pending |
| Push SDK to GitHub | Pending |

### Sprint B: Trust (Next Week)
| Item | Impact | Effort |
|------|--------|--------|
| Test coverage 40% → 70% (Clerk JWT, significance.py, untested endpoints) | High | 3-4 days |
| Status page (uptimerobot) | Medium | 1 hour |
| Security whitepaper (based on audit) | Medium | 1 day |
| Usage-based billing via Stripe metered | High | 2 days |
| Redis connection pool | Medium | 1 day |
| Parsed data cache for MCP sessions | High | 1 day |

### Sprint C: Growth (Week After)
| Item | Impact |
|------|--------|
| Template marketplace (3-5 pre-built templates) | High |
| "Built with Indico Crosstab" badge program | Medium |
| Open-source frontends as starter kits | High |
| Landing page for developers (not end-users) | High |
| Partner program for agencies | Medium |

---

## Pricing

| Plan | Price | Calls/min | Max file | AI features |
|------|-------|-----------|----------|-------------|
| Free | $0 | 10 | 5 MB | No |
| Growth | $29/mo | 60 | 50 MB | No |
| Business | $99/mo | 200 | 200 MB | Yes |
| Enterprise | Custom | Unlimited | 500 MB | Yes + SLA |

---

## Competitive Position

> "Desktop tabulation tools charge per seat. WinCross charges $3-5K/year. SPSS $99/mo per seat. All are closed monoliths. We are the **Stripe of market research** — an API that anyone can integrate. A developer with Lovable builds their own tabulation product in a weekend using our engine."
