# Indico Crosstab — Strategic Next Steps

**Date:** 2026-04-05 (updated)
**Status:** Active — Pivoting to Platform/Engine strategy

---

## Core Positioning (Agreed)

### The Product Claim

> **Statistical Precision Guaranteed.**
> Same data + same spec = same results. Every time.
> No prompt variability. No hallucinated statistics. No rounding differences between runs.
> Powered by QuantipyMRX — a deterministic statistical engine, not an LLM.

### The Positioning Statement

> **Claude analyzes. Indico Crosstab certifies.**
> Use Claude to explore your data. Use Indico Crosstab when the numbers need to be right.

### The Platform Vision (NEW — Apr 2026)

> **The Stripe of market research.**
> Desktop tabulation tools charge per seat. We charge per API call.
> A developer with Lovable builds their own tabulation product in a weekend using our engine.
> Our customer is the BUILDER, not the end-user.

---

## Strategic Pivot: End-User Tool → Platform Engine

### Before (Mar 2026)
- Product: web app where researchers upload .sav files
- Customer: market researcher
- Monetization: SaaS subscription per seat
- Ceiling: ~$100K ARR (niche tool)

### After (Apr 2026)
- Product: API + SDK + templates that developers integrate
- Customer: developer / agency building research tools
- Monetization: usage-based (per API call / per export)
- Ceiling: ~$10M+ ARR (platform)

### Why This Works
1. **npm SDK exists** (`@indicolabs/crosstab-sdk`) — typed TypeScript client
2. **Async webhooks exist** — `webhook_url` → 202 + callback
3. **13 MCP tools** — Claude.ai native integration
4. **Deterministic engine** — the moat. Hard to replicate without statisticians.
5. **No-code builders (Lovable, Bolt)** are creating massive demand for backend APIs

---

## Immediate Priorities (Apr 2026)

### 1. Developer Experience (Sprint A — in progress)
- [x] npm SDK with types, errors, retry
- [x] Async webhooks + job polling
- [ ] Next.js starter template
- [ ] Developer portal page
- [ ] Publish to npm

### 2. Trust (Sprint B — next week)
- [ ] Test coverage 40% → 70%
- [ ] Status page
- [ ] Security whitepaper
- [ ] Stripe metered billing
- [ ] Redis connection pool + parsed data cache

### 3. Growth (Sprint C — week after)
- [ ] Template marketplace
- [ ] "Built with Indico Crosstab" badge
- [ ] Open-source frontends
- [ ] Developer landing page
- [ ] Partner program

---

## Enterprise Standards

All Indico Labs API products must pass the enterprise checklist:
- See `~/.claude/projects/C--Users-jorge/memory/enterprise_api_standards.md`
- 10 sections, ~60 checkpoints
- Audit process: 7 agents in parallel (Security, API, Performance, Dead Code, Test Coverage, Playwright, MCP)

---

## Key Metrics to Track

| Metric | Current | Target (Q2 2026) |
|--------|---------|-------------------|
| Enterprise score | 7.5/10 | 9/10 |
| Test coverage | ~45% | 80% |
| REST endpoints | 29 | 32+ |
| SDK downloads (npm) | 0 | 100+ |
| External integrations | 0 | 5+ |
| Developer signups | 0 | 50+ |
