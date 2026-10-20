# Sprint A: Developer Experience Sprint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A developer goes from zero to working crosstab with significance testing in 15 minutes, using a typed npm SDK and a Next.js starter template.

**Architecture:** Three independent subsystems built in sequence: (1) TypeScript npm SDK wrapping all 28 REST endpoints with full type safety, (2) async webhook system on the backend for long-running jobs like tabulation, (3) Next.js template + developer portal demonstrating the SDK. The SDK is the critical path — everything else depends on it.

**Tech Stack:** TypeScript (SDK), FastAPI (webhooks), Next.js 15 App Router + shadcn/ui (template), npm (publishing)

---

## Scope & Subsystem Breakdown

| # | Subsystem | Deliverable | Depends On |
|---|-----------|-------------|------------|
| 1 | **npm SDK** | `@indicolabs/crosstab-sdk` — typed TS client | Nothing |
| 2 | **Async Webhooks** | `POST /v1/tabulate` returns 202 + webhook callback | Nothing (backend only) |
| 3 | **Next.js Template** | `create-indico-crosstab-app` starter + developer portal page | SDK |

Each subsystem is independently deployable and testable.

---

## File Structure

### Subsystem 1: npm SDK (`indico-crosstab-sdk/`)

New repo: `C:\Users\jorge\proyectos_python\indico-crosstab-sdk`

```
indico-crosstab-sdk/
├── package.json
├── tsconfig.json
├── vitest.config.ts
├── src/
│   ├── index.ts                  # Public API: export { IndicoCrosstab } + all types
│   ├── client.ts                 # Indico Crosstab class — HTTP client, auth, error handling
│   ├── types.ts                  # All request/response types (TabulateSpec, Metadata, etc.)
│   ├── errors.ts                 # IndicoCrosstabError, RateLimitError, AuthError classes
│   ├── endpoints/
│   │   ├── files.ts              # upload(), download(), listLibrary()
│   │   ├── metadata.ts           # getMetadata(), describeVariable()
│   │   ├── analysis.ts           # frequency(), crosstab(), anova(), correlation(), etc.
│   │   ├── tabulation.ts         # tabulate(), autoAnalyze() — returns Buffer
│   │   └── keys.ts               # createKey(), listKeys(), revokeKey()
│   └── utils/
│       ├── fetch.ts              # Wrapper around fetch with retry, timeout, error parsing
│       └── form-data.ts          # Multipart form-data builder for file uploads
├── tests/
│   ├── client.test.ts            # Constructor, auth, base URL
│   ├── files.test.ts             # Upload, download
│   ├── metadata.test.ts          # Metadata extraction
│   ├── analysis.test.ts          # Frequency, crosstab, anova
│   ├── tabulation.test.ts        # Tabulate, auto-analyze (binary response)
│   ├── errors.test.ts            # Error parsing, retry logic
│   └── helpers/
│       └── mock-server.ts        # MSW mock server for all endpoints
└── README.md
```

### Subsystem 2: Async Webhooks (backend changes)

Modified files in `C:\Users\jorge\proyectos_python\quantipro-api`:

```
quantipro-api/
├── routers/
│   ├── tabulate.py               # MODIFY: add webhook_url param, return 202
│   └── jobs.py                   # CREATE: GET /v1/jobs/{job_id} — poll job status
├── services/
│   └── job_runner.py             # CREATE: background job execution + webhook delivery
├── shared/
│   └── job_store.py              # CREATE: Redis-backed job state (pending/running/done/failed)
└── tests/
    ├── test_jobs.py              # CREATE: job lifecycle tests
    └── test_webhook.py           # CREATE: webhook delivery tests
```

### Subsystem 3: Next.js Template

New repo: `C:\Users\jorge\proyectos_python\indico-crosstab-nextjs-template`

```
indico-crosstab-nextjs-template/
├── package.json
├── next.config.ts
├── .env.example                  # INDICO_CROSSTAB_API_KEY=sk_test_...
├── app/
│   ├── layout.tsx
│   ├── page.tsx                  # Landing: "Your tables, your rules"
│   ├── upload/
│   │   └── page.tsx              # File upload → metadata display
│   ├── analyze/
│   │   └── page.tsx              # Crosstab builder UI
│   └── api/
│       ├── upload/route.ts       # Server action: proxy upload to Indico Crosstab
│       ├── metadata/route.ts     # Server action: get metadata
│       ├── crosstab/route.ts     # Server action: run crosstab
│       └── tabulate/route.ts     # Server action: generate Excel
├── components/
│   ├── file-uploader.tsx         # Drag & drop + progress
│   ├── variable-picker.tsx       # Select banner/stub variables
│   ├── crosstab-table.tsx        # Render crosstab with sig letters
│   └── sig-letter-cell.tsx       # Colored significance letter (A/B/C)
└── lib/
    └── indico-crosstab.ts         # SDK instance (server-side singleton)
```

---

## Subsystem 1: npm SDK

### Task 1: Project scaffolding + client skeleton

**Files:**
- Create: `indico-crosstab-sdk/package.json`
- Create: `indico-crosstab-sdk/tsconfig.json`
- Create: `indico-crosstab-sdk/vitest.config.ts`
- Create: `indico-crosstab-sdk/src/index.ts`
- Create: `indico-crosstab-sdk/src/client.ts`
- Create: `indico-crosstab-sdk/src/errors.ts`
- Create: `indico-crosstab-sdk/src/types.ts`
- Test: `indico-crosstab-sdk/tests/client.test.ts`

- [ ] **Step 1: Create project directory and initialize**

```bash
mkdir -p C:/Users/jorge/proyectos_python/indico-crosstab-sdk
cd C:/Users/jorge/proyectos_python/indico-crosstab-sdk
npm init -y
```

- [ ] **Step 2: Install dev dependencies**

```bash
npm install -D typescript vitest @types/node tsup
```

- [ ] **Step 3: Write `package.json`**

```json
{
  "name": "@indicolabs/crosstab-sdk",
  "version": "0.1.0",
  "description": "TypeScript SDK for Indico Crosstab — deterministic survey data analysis API",
  "main": "dist/index.js",
  "module": "dist/index.mjs",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.mjs",
      "require": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsup src/index.ts --format cjs,esm --dts",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "tsc --noEmit"
  },
  "keywords": ["spss", "survey", "market-research", "crosstab", "significance-testing", "indicolabs"],
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "https://github.com/quack2025/insightgenius-sdk"
  },
  "engines": {
    "node": ">=18"
  }
}
```

- [ ] **Step 4: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

- [ ] **Step 5: Write `vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
  },
});
```

- [ ] **Step 6: Write `src/errors.ts`**

```typescript
export class IndicoCrosstabError extends Error {
  public readonly code: string;
  public readonly statusCode: number;
  public readonly docUrl?: string;

  constructor(message: string, code: string, statusCode: number, docUrl?: string) {
    super(message);
    this.name = "IndicoCrosstabError";
    this.code = code;
    this.statusCode = statusCode;
    this.docUrl = docUrl;
  }
}

export class AuthenticationError extends IndicoCrosstabError {
  constructor(message = "Invalid or missing API key") {
    super(message, "UNAUTHORIZED", 401);
    this.name = "AuthenticationError";
  }
}

export class RateLimitError extends IndicoCrosstabError {
  public readonly retryAfterMs: number;

  constructor(retryAfterMs: number) {
    super(`Rate limit exceeded. Retry after ${retryAfterMs}ms`, "RATE_LIMITED", 429);
    this.name = "RateLimitError";
    this.retryAfterMs = retryAfterMs;
  }
}

export class ValidationError extends IndicoCrosstabError {
  constructor(message: string) {
    super(message, "VALIDATION_ERROR", 400);
    this.name = "ValidationError";
  }
}
```

- [ ] **Step 7: Write `src/types.ts` — core types**

```typescript
// ── File & Session ──────────────────────────────────────────────

export interface UploadResult {
  file_id: string;
  filename: string;
  format: string;
  size_bytes: number;
  n_cases: number;
  n_variables: number;
  session_ttl_seconds: number;
}

// ── Metadata ────────────────────────────────────────────────────

export interface VariableInfo {
  name: string;
  label: string;
  type: "numeric" | "string" | "date";
  value_labels: Record<string, string>;
  n_valid: number;
  n_missing: number;
  measure?: string;
}

export interface DetectedGroup {
  name: string;
  type: "mrs" | "grid_single" | "grid_multi" | "awareness" | "scale";
  members: string[];
  label?: string;
}

export interface Metadata {
  filename: string;
  n_cases: number;
  n_variables: number;
  variables: VariableInfo[];
  detected_groups: DetectedGroup[];
  suggested_banners: string[];
  suggested_nets: Record<string, Record<string, number[]>>;
}

// ── Analysis ────────────────────────────────────────────────────

export interface FrequencyResult {
  variable: string;
  label: string;
  n_valid: number;
  n_missing: number;
  counts: Record<string, number>;
  percentages: Record<string, number>;
  mean?: number;
  std?: number;
  median?: number;
}

export interface CrosstabResult {
  row_variable: string;
  col_variable: string;
  table: Record<string, Record<string, number>>;
  percentages: Record<string, Record<string, number>>;
  significance_letters: Record<string, Record<string, string>>;
  col_bases: Record<string, number>;
  chi2?: number;
  p_value?: number;
}

export interface AnovaResult {
  dependent: string;
  factor: string;
  f_statistic: number;
  p_value: number;
  significant: boolean;
  group_means: Record<string, number>;
  group_ns: Record<string, number>;
  post_hoc_tukey?: Array<{
    group1: string;
    group2: string;
    mean_diff: number;
    p_value: number;
    significant: boolean;
  }>;
}

export interface CorrelationResult {
  variables: string[];
  method: "pearson" | "spearman" | "kendall";
  matrix: Record<string, Record<string, number>>;
  p_values: Record<string, Record<string, number>>;
  significant_pairs: Array<{
    var1: string;
    var2: string;
    r: number;
    p_value: number;
  }>;
}

export interface SatisfactionItem {
  variable: string;
  label: string;
  n_valid: number;
  mean: number;
  std: number;
  median: number;
  t2b_pct: number;
  b2b_pct: number;
}

export interface GapAnalysisItem {
  item: string;
  importance: number;
  performance: number;
  gap: number;
  quadrant: "Concentrate Here" | "Keep Up" | "Possible Overkill" | "Low Priority";
}

export interface WaveComparisonItem {
  variable: string;
  wave1_value: number;
  wave2_value: number;
  delta: number;
  p_value: number;
  significant: boolean;
}

// ── Tabulation ──────────────────────────────────────────────────

export interface NetDefinition {
  [netName: string]: number[];
}

export interface GridGroup {
  variables: string[];
  show?: Array<"t2b" | "b2b" | "mean" | "median">;
}

export interface TabulateSpec {
  banners?: string[];
  stubs?: string[];
  weight?: string;
  significance_level?: number;
  include_means?: boolean;
  include_total_column?: boolean;
  output_mode?: "multi_sheet" | "single_sheet";
  title?: string;
  nets?: Record<string, NetDefinition>;
  mrs_groups?: Record<string, string[]>;
  grid_groups?: Record<string, GridGroup>;
  filters?: Record<string, unknown>;
}

// ── API Response Envelope ───────────────────────────────────────

export interface ApiResponse<T> {
  success: true;
  data: T;
  meta?: {
    request_id?: string;
    processing_time_ms?: number;
    [key: string]: unknown;
  };
}

export interface ApiError {
  success: false;
  error: {
    code: string;
    message: string;
    doc_url?: string;
  };
}

// ── Client Options ──────────────────────────────────────────────

export interface IndicoCrosstabOptions {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
  maxRetries?: number;
}

// ── Keys ────────────────────────────────────────────────────────

export interface ApiKeyInfo {
  id: string;
  name: string;
  prefix: string;
  plan: string;
  scopes: string[];
  created_at: string;
  last_used?: string;
}

export interface CreatedKey {
  raw_key: string;
  key_hash: string;
  created_at: string;
}
```

- [ ] **Step 8: Write `src/client.ts` — the main Indico Crosstab class**

```typescript
import { IndicoCrosstabError, AuthenticationError, RateLimitError, ValidationError } from "./errors";
import type {
  IndicoCrosstabOptions,
  ApiResponse,
  ApiError,
  UploadResult,
  Metadata,
  FrequencyResult,
  CrosstabResult,
  AnovaResult,
  CorrelationResult,
  SatisfactionItem,
  GapAnalysisItem,
  WaveComparisonItem,
  TabulateSpec,
  ApiKeyInfo,
  CreatedKey,
} from "./types";

const DEFAULT_BASE_URL = "https://crosstab.indicolabs.io";
const DEFAULT_TIMEOUT = 120_000;
const DEFAULT_MAX_RETRIES = 2;

export class IndicoCrosstab {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeout: number;
  private readonly maxRetries: number;

  constructor(options: IndicoCrosstabOptions | string) {
    const opts = typeof options === "string" ? { apiKey: options } : options;
    if (!opts.apiKey) throw new Error("apiKey is required");
    this.apiKey = opts.apiKey;
    this.baseUrl = (opts.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    this.timeout = opts.timeout ?? DEFAULT_TIMEOUT;
    this.maxRetries = opts.maxRetries ?? DEFAULT_MAX_RETRIES;
  }

  // ── Internal HTTP ───────────────────────────────────────────

  private async request<T>(
    method: string,
    path: string,
    body?: FormData | Record<string, unknown>,
    options?: { rawResponse?: boolean },
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
    };

    let fetchBody: BodyInit | undefined;
    if (body instanceof FormData) {
      fetchBody = body;
    } else if (body) {
      headers["Content-Type"] = "application/json";
      fetchBody = JSON.stringify(body);
    }

    let lastError: Error | undefined;
    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      if (attempt > 0) {
        await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** attempt, 8000)));
      }

      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeout);

      try {
        const res = await fetch(url, {
          method,
          headers,
          body: fetchBody,
          signal: controller.signal,
        });
        clearTimeout(timer);

        if (options?.rawResponse) {
          if (!res.ok) {
            throw await this.parseError(res);
          }
          return res as unknown as T;
        }

        if (res.status === 429) {
          const retryAfter = parseInt(res.headers.get("Retry-After") ?? "5", 10) * 1000;
          if (attempt < this.maxRetries) {
            await new Promise((r) => setTimeout(r, retryAfter));
            continue;
          }
          throw new RateLimitError(retryAfter);
        }

        if (!res.ok) {
          throw await this.parseError(res);
        }

        const json = await res.json();
        if (json.success === false) {
          throw new IndicoCrosstabError(
            json.error?.message ?? "Unknown error",
            json.error?.code ?? "UNKNOWN",
            res.status,
            json.error?.doc_url,
          );
        }

        return (json.data ?? json) as T;
      } catch (err) {
        clearTimeout(timer);
        if (err instanceof IndicoCrosstabError) throw err;
        lastError = err as Error;
        if (attempt === this.maxRetries) break;
      }
    }

    throw lastError ?? new Error("Request failed after retries");
  }

  private async parseError(res: Response): Promise<IndicoCrosstabError> {
    try {
      const json = await res.json();
      const err = json.error ?? json;
      if (res.status === 401) return new AuthenticationError(err.message);
      if (res.status === 400) return new ValidationError(err.message ?? "Validation error");
      return new IndicoCrosstabError(
        err.message ?? res.statusText,
        err.code ?? `HTTP_${res.status}`,
        res.status,
        err.doc_url,
      );
    } catch {
      return new IndicoCrosstabError(res.statusText, `HTTP_${res.status}`, res.status);
    }
  }

  private formData(fields: Record<string, string | Blob | undefined>): FormData {
    const fd = new FormData();
    for (const [key, value] of Object.entries(fields)) {
      if (value !== undefined) {
        fd.append(key, value);
      }
    }
    return fd;
  }

  // ── Files ───────────────────────────────────────────────────

  async upload(file: Blob | Buffer, filename = "upload.sav"): Promise<UploadResult> {
    const blob = file instanceof Blob ? file : new Blob([file]);
    const fd = new FormData();
    fd.append("file", blob, filename);
    return this.request<UploadResult>("POST", "/v1/files/upload", fd);
  }

  // ── Metadata ────────────────────────────────────────────────

  async getMetadata(fileId: string): Promise<Metadata> {
    const fd = this.formData({ file_id: fileId });
    return this.request<Metadata>("POST", "/v1/metadata", fd);
  }

  // ── Analysis ────────────────────────────────────────────────

  async frequency(
    fileId: string,
    variable: string,
    options?: { weight?: string },
  ): Promise<FrequencyResult> {
    const fd = this.formData({
      file_id: fileId,
      variable,
      weight: options?.weight,
    });
    return this.request<FrequencyResult>("POST", "/v1/frequency", fd);
  }

  async crosstab(
    fileId: string,
    spec: { row: string; col: string; weight?: string; significance_level?: number },
  ): Promise<CrosstabResult> {
    const fd = this.formData({
      file_id: fileId,
      spec: JSON.stringify(spec),
    });
    return this.request<CrosstabResult>("POST", "/v1/crosstab", fd);
  }

  async anova(
    fileId: string,
    spec: { dependent: string; factor: string; weight?: string },
  ): Promise<AnovaResult> {
    const fd = this.formData({
      file_id: fileId,
      spec: JSON.stringify(spec),
    });
    return this.request<AnovaResult>("POST", "/v1/anova", fd);
  }

  async correlation(
    fileId: string,
    spec: { variables: string[]; method?: "pearson" | "spearman" | "kendall" },
  ): Promise<CorrelationResult> {
    const fd = this.formData({
      file_id: fileId,
      spec: JSON.stringify(spec),
    });
    return this.request<CorrelationResult>("POST", "/v1/correlation", fd);
  }

  async satisfactionSummary(
    fileId: string,
    spec: { variables: string[]; weight?: string },
  ): Promise<SatisfactionItem[]> {
    const fd = this.formData({
      file_id: fileId,
      spec: JSON.stringify(spec),
    });
    const result = await this.request<{ summaries: SatisfactionItem[] }>(
      "POST",
      "/v1/satisfaction-summary",
      fd,
    );
    return result.summaries;
  }

  async gapAnalysis(
    fileId: string,
    spec: { importance_vars: string[]; performance_vars: string[]; weight?: string },
  ): Promise<GapAnalysisItem[]> {
    const fd = this.formData({
      file_id: fileId,
      spec: JSON.stringify(spec),
    });
    const result = await this.request<{ items: GapAnalysisItem[] }>(
      "POST",
      "/v1/gap-analysis",
      fd,
    );
    return result.items;
  }

  async waveCompare(
    fileId1: string,
    fileId2: string,
    options?: { variables?: string[]; weight?: string; significance_level?: number },
  ): Promise<WaveComparisonItem[]> {
    const fd = this.formData({
      file1_id: fileId1,
      file2_id: fileId2,
      variables: options?.variables ? JSON.stringify(options.variables) : undefined,
      weight: options?.weight,
      significance_level: options?.significance_level?.toString(),
    });
    const result = await this.request<{ comparisons: WaveComparisonItem[] }>(
      "POST",
      "/v1/wave-compare",
      fd,
    );
    return result.comparisons;
  }

  // ── Tabulation & Export ─────────────────────────────────────

  async tabulate(fileId: string, spec: TabulateSpec): Promise<ArrayBuffer> {
    const fd = this.formData({
      file_id: fileId,
      spec: JSON.stringify(spec),
    });
    const res = await this.request<Response>("POST", "/v1/tabulate", fd, {
      rawResponse: true,
    });
    return res.arrayBuffer();
  }

  async autoAnalyze(fileId: string, options?: Record<string, unknown>): Promise<ArrayBuffer> {
    const fd = this.formData({
      file_id: fileId,
      options: options ? JSON.stringify(options) : undefined,
    });
    const res = await this.request<Response>("POST", "/v1/auto-analyze", fd, {
      rawResponse: true,
    });
    return res.arrayBuffer();
  }

  async convert(
    fileId: string,
    format: "xlsx" | "csv" | "dta" | "parquet",
  ): Promise<ArrayBuffer> {
    const fd = this.formData({
      file_id: fileId,
      target_format: format,
    });
    const res = await this.request<Response>("POST", "/v1/convert", fd, {
      rawResponse: true,
    });
    return res.arrayBuffer();
  }

  // ── API Keys ────────────────────────────────────────────────

  async createKey(name: string): Promise<CreatedKey> {
    return this.request<CreatedKey>("POST", "/v1/keys", { name });
  }

  async listKeys(): Promise<ApiKeyInfo[]> {
    const result = await this.request<{ keys: ApiKeyInfo[] }>("GET", "/v1/keys");
    return result.keys;
  }

  async revokeKey(keyId: string): Promise<void> {
    await this.request<unknown>("DELETE", `/v1/keys/${keyId}`);
  }
}
```

- [ ] **Step 9: Write `src/index.ts`**

```typescript
export { IndicoCrosstab } from "./client";
export { IndicoCrosstabError, AuthenticationError, RateLimitError, ValidationError } from "./errors";
export type {
  IndicoCrosstabOptions,
  UploadResult,
  Metadata,
  VariableInfo,
  DetectedGroup,
  FrequencyResult,
  CrosstabResult,
  AnovaResult,
  CorrelationResult,
  SatisfactionItem,
  GapAnalysisItem,
  WaveComparisonItem,
  TabulateSpec,
  NetDefinition,
  GridGroup,
  ApiKeyInfo,
  CreatedKey,
  ApiResponse,
  ApiError,
} from "./types";
```

- [ ] **Step 10: Write the failing test**

Create `tests/client.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { IndicoCrosstab, AuthenticationError, IndicoCrosstabError } from "../src";

describe("Indico Crosstab constructor", () => {
  it("accepts string API key", () => {
    const ig = new IndicoCrosstab("sk_test_abc123");
    expect(ig).toBeInstanceOf(Indico Crosstab);
  });

  it("accepts options object", () => {
    const ig = new IndicoCrosstab({
      apiKey: "sk_test_abc123",
      baseUrl: "http://localhost:8000",
      timeout: 5000,
    });
    expect(ig).toBeInstanceOf(Indico Crosstab);
  });

  it("throws if apiKey is empty", () => {
    expect(() => new IndicoCrosstab("")).toThrow("apiKey is required");
  });

  it("throws if apiKey is missing from options", () => {
    expect(() => new IndicoCrosstab({ apiKey: "" })).toThrow("apiKey is required");
  });
});

describe("Error classes", () => {
  it("IndicoCrosstabError has code and statusCode", () => {
    const err = new IndicoCrosstabError("test", "TEST_CODE", 400);
    expect(err.message).toBe("test");
    expect(err.code).toBe("TEST_CODE");
    expect(err.statusCode).toBe(400);
    expect(err).toBeInstanceOf(Error);
  });

  it("AuthenticationError defaults to 401", () => {
    const err = new AuthenticationError();
    expect(err.statusCode).toBe(401);
    expect(err.code).toBe("UNAUTHORIZED");
  });
});
```

- [ ] **Step 11: Run test to verify it passes**

```bash
cd C:/Users/jorge/proyectos_python/indico-crosstab-sdk
npx vitest run
```

Expected: all 5 tests PASS.

- [ ] **Step 12: Build and verify**

```bash
npx tsup src/index.ts --format cjs,esm --dts
ls dist/
```

Expected: `index.js`, `index.mjs`, `index.d.ts`, `index.d.mts` exist.

- [ ] **Step 13: Commit**

```bash
git init
git add -A
git commit -m "feat: initial SDK scaffold — Indico Crosstab client, types, errors"
```

---

### Task 2: HTTP integration tests with mock server

**Files:**
- Create: `indico-crosstab-sdk/tests/helpers/mock-server.ts`
- Create: `indico-crosstab-sdk/tests/files.test.ts`
- Create: `indico-crosstab-sdk/tests/metadata.test.ts`
- Create: `indico-crosstab-sdk/tests/analysis.test.ts`
- Create: `indico-crosstab-sdk/tests/tabulation.test.ts`
- Create: `indico-crosstab-sdk/tests/errors.test.ts`

- [ ] **Step 1: Install MSW for mocking**

```bash
cd C:/Users/jorge/proyectos_python/indico-crosstab-sdk
npm install -D msw
```

- [ ] **Step 2: Write `tests/helpers/mock-server.ts`**

```typescript
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const BASE = "http://localhost:8000";

const handlers = [
  // Health
  http.get(`${BASE}/v1/health`, () =>
    HttpResponse.json({ status: "ok", version: "1.0.0" }),
  ),

  // Upload
  http.post(`${BASE}/v1/files/upload`, async ({ request }) => {
    const auth = request.headers.get("Authorization");
    if (!auth?.startsWith("Bearer sk_")) {
      return HttpResponse.json(
        { success: false, error: { code: "UNAUTHORIZED", message: "Invalid API key" } },
        { status: 401 },
      );
    }
    return HttpResponse.json({
      file_id: "test-file-id-123",
      filename: "survey.sav",
      format: "sav",
      size_bytes: 1024,
      n_cases: 500,
      n_variables: 42,
      session_ttl_seconds: 1800,
    });
  }),

  // Metadata
  http.post(`${BASE}/v1/metadata`, () =>
    HttpResponse.json({
      success: true,
      data: {
        filename: "survey.sav",
        n_cases: 500,
        n_variables: 42,
        variables: [
          { name: "Q1", label: "Satisfaction", type: "numeric", value_labels: { "1": "Low", "5": "High" }, n_valid: 480, n_missing: 20 },
        ],
        detected_groups: [],
        suggested_banners: ["Gender"],
        suggested_nets: {},
      },
    }),
  ),

  // Frequency
  http.post(`${BASE}/v1/frequency`, () =>
    HttpResponse.json({
      success: true,
      data: {
        variable: "Q1",
        label: "Satisfaction",
        n_valid: 480,
        n_missing: 20,
        counts: { "1": 50, "2": 80, "3": 120, "4": 130, "5": 100 },
        percentages: { "1": 10.4, "2": 16.7, "3": 25.0, "4": 27.1, "5": 20.8 },
        mean: 3.3,
        std: 1.2,
        median: 3.0,
      },
    }),
  ),

  // Crosstab
  http.post(`${BASE}/v1/crosstab`, () =>
    HttpResponse.json({
      success: true,
      data: {
        row_variable: "Q1",
        col_variable: "Gender",
        table: { "1": { A: 25, B: 25 }, "5": { A: 60, B: 40 } },
        percentages: { "1": { A: 10, B: 10 }, "5": { A: 24, B: 16 } },
        significance_letters: { "5": { A: "B" } },
        col_bases: { A: 250, B: 250 },
        chi2: 12.5,
        p_value: 0.014,
      },
    }),
  ),

  // Tabulate (binary response)
  http.post(`${BASE}/v1/tabulate`, () => {
    const bytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04]); // PK zip header
    return new HttpResponse(bytes, {
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "X-Processing-Time-Ms": "1234",
      },
    });
  }),

  // Rate limited endpoint
  http.post(`${BASE}/v1/rate-limited`, () =>
    new HttpResponse(null, {
      status: 429,
      headers: { "Retry-After": "1" },
    }),
  ),
];

export const mockServer = setupServer(...handlers);
```

- [ ] **Step 3: Write `tests/files.test.ts`**

```typescript
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { IndicoCrosstab, AuthenticationError } from "../src";
import { mockServer } from "./helpers/mock-server";

beforeAll(() => mockServer.listen({ onUnhandledRequest: "error" }));
afterEach(() => mockServer.resetHandlers());
afterAll(() => mockServer.close());

const ig = new IndicoCrosstab({ apiKey: "sk_test_abc", baseUrl: "http://localhost:8000" });

describe("files", () => {
  it("upload returns file_id and metadata", async () => {
    const blob = new Blob([new Uint8Array(100)]);
    const result = await ig.upload(blob, "test.sav");
    expect(result.file_id).toBe("test-file-id-123");
    expect(result.n_cases).toBe(500);
    expect(result.n_variables).toBe(42);
    expect(result.session_ttl_seconds).toBe(1800);
  });
});
```

- [ ] **Step 4: Write `tests/metadata.test.ts`**

```typescript
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { IndicoCrosstab } from "../src";
import { mockServer } from "./helpers/mock-server";

beforeAll(() => mockServer.listen({ onUnhandledRequest: "error" }));
afterEach(() => mockServer.resetHandlers());
afterAll(() => mockServer.close());

const ig = new IndicoCrosstab({ apiKey: "sk_test_abc", baseUrl: "http://localhost:8000" });

describe("metadata", () => {
  it("returns structured metadata", async () => {
    const meta = await ig.getMetadata("test-file-id");
    expect(meta.n_cases).toBe(500);
    expect(meta.variables).toHaveLength(1);
    expect(meta.variables[0].name).toBe("Q1");
    expect(meta.suggested_banners).toContain("Gender");
  });
});
```

- [ ] **Step 5: Write `tests/analysis.test.ts`**

```typescript
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { IndicoCrosstab } from "../src";
import { mockServer } from "./helpers/mock-server";

beforeAll(() => mockServer.listen({ onUnhandledRequest: "error" }));
afterEach(() => mockServer.resetHandlers());
afterAll(() => mockServer.close());

const ig = new IndicoCrosstab({ apiKey: "sk_test_abc", baseUrl: "http://localhost:8000" });

describe("frequency", () => {
  it("returns frequency table with stats", async () => {
    const freq = await ig.frequency("test-file-id", "Q1");
    expect(freq.variable).toBe("Q1");
    expect(freq.n_valid).toBe(480);
    expect(freq.mean).toBe(3.3);
    expect(Object.keys(freq.counts)).toHaveLength(5);
  });
});

describe("crosstab", () => {
  it("returns crosstab with significance letters", async () => {
    const ct = await ig.crosstab("test-file-id", { row: "Q1", col: "Gender" });
    expect(ct.row_variable).toBe("Q1");
    expect(ct.significance_letters["5"]["A"]).toBe("B");
    expect(ct.chi2).toBeCloseTo(12.5);
    expect(ct.col_bases["A"]).toBe(250);
  });
});
```

- [ ] **Step 6: Write `tests/tabulation.test.ts`**

```typescript
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { IndicoCrosstab } from "../src";
import { mockServer } from "./helpers/mock-server";

beforeAll(() => mockServer.listen({ onUnhandledRequest: "error" }));
afterEach(() => mockServer.resetHandlers());
afterAll(() => mockServer.close());

const ig = new IndicoCrosstab({ apiKey: "sk_test_abc", baseUrl: "http://localhost:8000" });

describe("tabulate", () => {
  it("returns Excel binary (ArrayBuffer)", async () => {
    const buffer = await ig.tabulate("test-file-id", {
      banners: ["Gender"],
      stubs: ["Q1"],
      significance_level: 0.95,
    });
    expect(buffer).toBeInstanceOf(ArrayBuffer);
    expect(buffer.byteLength).toBeGreaterThan(0);
    // Verify PK zip magic bytes
    const view = new Uint8Array(buffer);
    expect(view[0]).toBe(0x50); // P
    expect(view[1]).toBe(0x4b); // K
  });
});
```

- [ ] **Step 7: Write `tests/errors.test.ts`**

```typescript
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { IndicoCrosstab, AuthenticationError } from "../src";
import { mockServer } from "./helpers/mock-server";
import { http, HttpResponse } from "msw";

beforeAll(() => mockServer.listen({ onUnhandledRequest: "error" }));
afterEach(() => mockServer.resetHandlers());
afterAll(() => mockServer.close());

describe("error handling", () => {
  it("throws AuthenticationError on 401", async () => {
    const ig = new IndicoCrosstab({ apiKey: "bad_key", baseUrl: "http://localhost:8000" });
    const blob = new Blob([new Uint8Array(10)]);
    await expect(ig.upload(blob)).rejects.toThrow(AuthenticationError);
  });

  it("throws IndicoCrosstabError with code on API error", async () => {
    mockServer.use(
      http.post("http://localhost:8000/v1/metadata", () =>
        HttpResponse.json(
          { success: false, error: { code: "VARIABLE_NOT_FOUND", message: "Q99 not found" } },
          { status: 400 },
        ),
      ),
    );
    const ig = new IndicoCrosstab({ apiKey: "sk_test_abc", baseUrl: "http://localhost:8000" });
    await expect(ig.getMetadata("test-id")).rejects.toThrow("Q99 not found");
  });
});
```

- [ ] **Step 8: Run all tests**

```bash
npx vitest run
```

Expected: all tests pass (constructor tests + integration tests).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "test: integration tests with MSW mock server"
```

---

### Task 3: README with quickstart

**Files:**
- Create: `indico-crosstab-sdk/README.md`

- [ ] **Step 1: Write README**

```markdown
# @indicolabs/crosstab-sdk

TypeScript SDK for [Indico Crosstab](https://crosstab.indicolabs.io) — deterministic survey data analysis with significance testing.

## Install

```bash
npm install @indicolabs/crosstab-sdk
```

## Quick Start

```typescript
import { IndicoCrosstab } from "@indicolabs/crosstab-sdk";
import { readFileSync, writeFileSync } from "fs";

const ig = new IndicoCrosstab("sk_test_your_key_here");

// 1. Upload a .sav file
const file = readFileSync("survey.sav");
const { file_id } = await ig.upload(new Blob([file]), "survey.sav");

// 2. See what's in it
const meta = await ig.getMetadata(file_id);
console.log(`${meta.n_cases} respondents, ${meta.n_variables} variables`);
console.log("Suggested banners:", meta.suggested_banners);

// 3. Run a crosstab with significance testing
const ct = await ig.crosstab(file_id, {
  row: "Q1_Satisfaction",
  col: "Gender",
  significance_level: 0.95,
});
console.log("Significance letters:", ct.significance_letters);
// → { "5": { "A": "B" } } means column A is significantly higher than B

// 4. Generate a full Excel report
const excel = await ig.tabulate(file_id, {
  banners: ["Gender", "AgeGroup"],
  stubs: ["_all_"],          // all variables
  significance_level: 0.95,
  include_means: true,
  nets: {
    Q1_Satisfaction: { "Top 2 Box": [4, 5], "Bottom 2 Box": [1, 2] },
  },
});
writeFileSync("report.xlsx", Buffer.from(excel));
```

## API Reference

### Constructor

```typescript
// Simple
const ig = new IndicoCrosstab("sk_test_...");

// With options
const ig = new IndicoCrosstab({
  apiKey: "sk_live_...",
  baseUrl: "https://crosstab.indicolabs.io",  // default
  timeout: 120_000,                           // 2 min default
  maxRetries: 2,                              // default
});
```

### Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `upload(file, filename)` | Upload .sav/.csv/.xlsx | `UploadResult` |
| `getMetadata(fileId)` | Variables, types, detected groups | `Metadata` |
| `frequency(fileId, variable)` | Frequency table with stats | `FrequencyResult` |
| `crosstab(fileId, spec)` | Crosstab with sig letters (A/B/C) | `CrosstabResult` |
| `anova(fileId, spec)` | One-way ANOVA + Tukey HSD | `AnovaResult` |
| `correlation(fileId, spec)` | Correlation matrix | `CorrelationResult` |
| `satisfactionSummary(fileId, spec)` | T2B/B2B/Mean summary | `SatisfactionItem[]` |
| `gapAnalysis(fileId, spec)` | Importance-Performance gaps | `GapAnalysisItem[]` |
| `waveCompare(fileId1, fileId2)` | Compare two survey waves | `WaveComparisonItem[]` |
| `tabulate(fileId, spec)` | Full Excel with sig testing | `ArrayBuffer` |
| `autoAnalyze(fileId)` | Zero-config Excel report | `ArrayBuffer` |
| `convert(fileId, format)` | Convert to xlsx/csv/dta/parquet | `ArrayBuffer` |

### Error Handling

```typescript
import { IndicoCrosstab, AuthenticationError, RateLimitError, ValidationError } from "@indicolabs/crosstab-sdk";

try {
  const meta = await ig.getMetadata(fileId);
} catch (err) {
  if (err instanceof AuthenticationError) {
    // Invalid API key → redirect to settings
  } else if (err instanceof RateLimitError) {
    // Wait and retry
    await new Promise(r => setTimeout(r, err.retryAfterMs));
  } else if (err instanceof ValidationError) {
    // Bad input → show message to user
    console.error(err.message);
  }
}
```

## Get an API Key

1. Go to [crosstab.indicolabs.io/app/keys](https://crosstab.indicolabs.io/app/keys)
2. Create a key
3. Use it: `new IndicoCrosstab("sk_live_...")`

## Build Your Own Tabulation Product

See the [Next.js template](https://github.com/quack2025/insightgenius-nextjs-template) for a complete example of building a survey analysis platform using this SDK.

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with quickstart and API reference"
```

---

## Subsystem 2: Async Webhooks

### Task 4: Job store (Redis-backed)

**Files:**
- Create: `quantipro-api/shared/job_store.py`
- Test: `quantipro-api/tests/test_jobs.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_jobs.py`:

```python
"""Tests for async job lifecycle."""
import pytest
from shared.job_store import JobStore, JobStatus


def test_create_job():
    store = JobStore()
    job_id = store.create(user_id="demo", endpoint="/v1/tabulate", webhook_url=None)
    assert job_id
    assert len(job_id) == 36  # UUID


def test_get_job_initial_status():
    store = JobStore()
    job_id = store.create(user_id="demo", endpoint="/v1/tabulate", webhook_url=None)
    job = store.get(job_id)
    assert job is not None
    assert job["status"] == JobStatus.PENDING
    assert job["endpoint"] == "/v1/tabulate"
    assert job["result"] is None


def test_update_status():
    store = JobStore()
    job_id = store.create(user_id="demo", endpoint="/v1/tabulate", webhook_url=None)
    store.update(job_id, status=JobStatus.RUNNING)
    job = store.get(job_id)
    assert job["status"] == JobStatus.RUNNING


def test_complete_with_result():
    store = JobStore()
    job_id = store.create(user_id="demo", endpoint="/v1/tabulate", webhook_url=None)
    store.complete(job_id, download_url="https://example.com/dl/abc123")
    job = store.get(job_id)
    assert job["status"] == JobStatus.DONE
    assert job["result"]["download_url"] == "https://example.com/dl/abc123"


def test_fail_with_error():
    store = JobStore()
    job_id = store.create(user_id="demo", endpoint="/v1/tabulate", webhook_url=None)
    store.fail(job_id, error_code="TIMEOUT", error_message="Processing exceeded 120s")
    job = store.get(job_id)
    assert job["status"] == JobStatus.FAILED
    assert job["result"]["error"]["code"] == "TIMEOUT"


def test_get_nonexistent_returns_none():
    store = JobStore()
    assert store.get("nonexistent-uuid") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:/Users/jorge/proyectos_python/quantipro-api
python -m pytest tests/test_jobs.py -v
```

Expected: `ModuleNotFoundError: No module named 'shared.job_store'`

- [ ] **Step 3: Write `shared/job_store.py`**

```python
"""In-memory job store with optional Redis persistence.

Jobs track async processing requests (tabulation, auto-analyze).
Each job has: id, status, endpoint, user_id, webhook_url, result, timestamps.
"""

import json
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# In-memory store (per-worker). Redis upgrade in a follow-up task.
_jobs: dict[str, dict] = {}


class JobStore:
    """Manages async job lifecycle. In-memory with Redis fallback."""

    def create(
        self,
        user_id: str,
        endpoint: str,
        webhook_url: Optional[str] = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {
            "id": job_id,
            "status": JobStatus.PENDING,
            "endpoint": endpoint,
            "user_id": user_id,
            "webhook_url": webhook_url,
            "result": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        return _jobs.get(job_id)

    def update(self, job_id: str, status: JobStatus) -> None:
        if job_id in _jobs:
            _jobs[job_id]["status"] = status
            _jobs[job_id]["updated_at"] = time.time()

    def complete(self, job_id: str, download_url: str) -> None:
        if job_id in _jobs:
            _jobs[job_id]["status"] = JobStatus.DONE
            _jobs[job_id]["result"] = {"download_url": download_url}
            _jobs[job_id]["updated_at"] = time.time()

    def fail(self, job_id: str, error_code: str, error_message: str) -> None:
        if job_id in _jobs:
            _jobs[job_id]["status"] = JobStatus.FAILED
            _jobs[job_id]["result"] = {
                "error": {"code": error_code, "message": error_message},
            }
            _jobs[job_id]["updated_at"] = time.time()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_jobs.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add shared/job_store.py tests/test_jobs.py
git commit -m "feat: in-memory job store for async processing"
```

---

### Task 5: Job status endpoint + webhook delivery

**Files:**
- Create: `quantipro-api/routers/jobs.py`
- Create: `quantipro-api/services/job_runner.py`
- Modify: `quantipro-api/main.py` (register router)
- Modify: `quantipro-api/routers/tabulate.py` (add webhook_url param)
- Test: `quantipro-api/tests/test_jobs.py` (extend)

- [ ] **Step 1: Write the failing test for job status endpoint**

Append to `tests/test_jobs.py`:

```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
HEADERS = {"Authorization": "Bearer sk_test_quantipro_test_key_abc123"}


def test_get_job_status_not_found():
    resp = client.get("/v1/jobs/nonexistent-uuid", headers=HEADERS)
    assert resp.status_code == 404


def test_get_job_status_returns_job():
    from shared.job_store import JobStore, JobStatus
    store = JobStore()
    job_id = store.create(user_id="test_key", endpoint="/v1/tabulate")
    store.complete(job_id, download_url="https://example.com/dl/abc")

    resp = client.get(f"/v1/jobs/{job_id}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "done"
    assert data["data"]["result"]["download_url"] == "https://example.com/dl/abc"
```

- [ ] **Step 2: Write `routers/jobs.py`**

```python
"""GET /v1/jobs/{job_id} — Poll async job status."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth import require_auth, KeyConfig
from shared.job_store import JobStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Jobs"])

_store = JobStore()


@router.get("/v1/jobs/{job_id}", summary="Get async job status")
async def get_job(job_id: str, key: KeyConfig = Depends(require_auth)):
    job = _store.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={
            "success": False,
            "error": {"code": "NOT_FOUND", "message": f"Job {job_id} not found"},
        })
    return {"success": True, "data": job}
```

- [ ] **Step 3: Register router in `main.py`**

Add to the router imports section in `main.py`:

```python
from routers.jobs import router as jobs_router
```

And add to the `app.include_router(...)` calls:

```python
app.include_router(jobs_router)
```

- [ ] **Step 4: Write `services/job_runner.py`**

```python
"""Background job runner — executes tabulation async + delivers webhook."""

import asyncio
import logging
import time

import httpx

from shared.job_store import JobStore, JobStatus

logger = logging.getLogger(__name__)
_store = JobStore()


async def run_tabulation_job(
    job_id: str,
    tabulate_fn,
    *args,
    **kwargs,
) -> None:
    """Run tabulation in background, store result, fire webhook."""
    _store.update(job_id, JobStatus.RUNNING)
    job = _store.get(job_id)
    webhook_url = job.get("webhook_url") if job else None

    try:
        result = await tabulate_fn(*args, **kwargs)
        # result is (excel_bytes, download_url)
        excel_bytes, download_url = result
        _store.complete(job_id, download_url=download_url)
        logger.info("[JOB] %s completed → %s", job_id, download_url)
    except Exception as e:
        _store.fail(job_id, error_code="PROCESSING_ERROR", error_message=str(e))
        logger.error("[JOB] %s failed: %s", job_id, e, exc_info=True)

    # Fire webhook if configured
    if webhook_url:
        await _deliver_webhook(job_id, webhook_url)


async def _deliver_webhook(job_id: str, url: str, max_retries: int = 3) -> None:
    """POST job result to webhook URL with retries."""
    job = _store.get(job_id)
    if not job:
        return

    payload = {
        "event": "job.completed" if job["status"] == JobStatus.DONE else "job.failed",
        "job_id": job_id,
        "status": job["status"],
        "result": job["result"],
        "timestamp": time.time(),
    }

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code < 400:
                    logger.info("[WEBHOOK] %s → %s (%d)", job_id, url, resp.status_code)
                    return
                logger.warning("[WEBHOOK] %s → %s returned %d", job_id, url, resp.status_code)
        except Exception as e:
            logger.warning("[WEBHOOK] %s attempt %d failed: %s", job_id, attempt + 1, e)

        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)

    logger.error("[WEBHOOK] %s → %s failed after %d attempts", job_id, url, max_retries)
```

- [ ] **Step 5: Add `webhook_url` parameter to tabulate endpoint**

In `routers/tabulate.py`, add to the endpoint signature:

```python
webhook_url: str | None = Form(None, description="URL to POST job result when processing completes. If provided, returns 202 with job_id instead of blocking."),
```

Add at the beginning of the function body (before processing), after auth/rate-limit:

```python
# Async mode: return 202 + job_id, process in background
if webhook_url:
    from shared.job_store import JobStore
    from services.job_runner import run_tabulation_job
    store = JobStore()
    job_id = store.create(user_id=key.name, endpoint="/v1/tabulate", webhook_url=webhook_url)

    async def _do_tabulate():
        # existing tabulation logic here — returns (excel_bytes, download_url)
        file_bytes, filename = await resolve_file(file=file, file_id=file_id)
        # ... (the existing processing)
        # store result in download and return URL
        from routers.downloads import store_download
        token, download_url = await store_download(excel_bytes, f"{spec_obj.title or 'tabulation'}.xlsx")
        return excel_bytes, download_url

    asyncio.create_task(run_tabulation_job(job_id, _do_tabulate))
    return JSONResponse(status_code=202, content={
        "success": True,
        "data": {
            "job_id": job_id,
            "status": "pending",
            "poll_url": f"/v1/jobs/{job_id}",
            "webhook_url": webhook_url,
            "message": "Processing started. Poll the job URL or wait for webhook callback.",
        },
    })
```

NOTE: The exact integration depends on the current structure of the tabulate endpoint. The implementing engineer should read `routers/tabulate.py` fully and extract the processing logic into a callable async function. The key change is: if `webhook_url` is provided, wrap the existing logic in `run_tabulation_job` and return 202 immediately.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_jobs.py -v
```

Expected: 8 passed (6 unit + 2 integration).

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/ -x -q --tb=short
```

Expected: all tests pass (106 + new job tests).

- [ ] **Step 8: Commit**

```bash
git add routers/jobs.py services/job_runner.py shared/job_store.py tests/test_jobs.py main.py routers/tabulate.py
git commit -m "feat: async webhooks — job store, status endpoint, webhook delivery"
```

---

## Subsystem 3: Next.js Template

### Task 6: Next.js project scaffold with SDK integration

**Files:**
- Create: `indico-crosstab-nextjs-template/package.json`
- Create: `indico-crosstab-nextjs-template/next.config.ts`
- Create: `indico-crosstab-nextjs-template/.env.example`
- Create: `indico-crosstab-nextjs-template/lib/indico-crosstab.ts`
- Create: `indico-crosstab-nextjs-template/app/layout.tsx`
- Create: `indico-crosstab-nextjs-template/app/page.tsx`

- [ ] **Step 1: Create Next.js project**

```bash
cd C:/Users/jorge/proyectos_python
npx create-next-app@latest indico-crosstab-nextjs-template --typescript --tailwind --eslint --app --src-dir=false --import-alias="@/*" --use-npm
```

- [ ] **Step 2: Install SDK and shadcn/ui**

```bash
cd C:/Users/jorge/proyectos_python/indico-crosstab-nextjs-template
npm install @indicolabs/crosstab-sdk
npx shadcn@latest init -d
npx shadcn@latest add button card input label table tabs badge
```

- [ ] **Step 3: Write `.env.example`**

```
# Get your key at https://crosstab.indicolabs.io/app/keys
INDICO_CROSSTAB_API_KEY=sk_test_your_key_here
```

- [ ] **Step 4: Write `lib/indico-crosstab.ts`**

```typescript
import { IndicoCrosstab } from "@indicolabs/crosstab-sdk";

if (!process.env.INDICO_CROSSTAB_API_KEY) {
  throw new Error("INDICO_CROSSTAB_API_KEY is required. Get one at https://crosstab.indicolabs.io/app/keys");
}

export const ig = new IndicoCrosstab({
  apiKey: process.env.INDICO_CROSSTAB_API_KEY,
});
```

- [ ] **Step 5: Write `app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Survey Analyzer — Built with Indico Crosstab",
  description: "Professional survey analysis with significance testing",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="min-h-screen bg-gray-50">
          <header className="border-b bg-white px-6 py-4">
            <div className="mx-auto flex max-w-5xl items-center justify-between">
              <h1 className="text-lg font-semibold">Survey Analyzer</h1>
              <span className="text-xs text-gray-400">
                Powered by{" "}
                <a href="https://crosstab.indicolabs.io" className="underline" target="_blank">
                  Indico Crosstab
                </a>
              </span>
            </div>
          </header>
          <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
```

- [ ] **Step 6: Write `app/page.tsx` — landing with upload**

```tsx
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  return (
    <div className="space-y-8">
      <div className="text-center space-y-4 py-12">
        <h2 className="text-4xl font-bold tracking-tight">Your surveys. Your platform.</h2>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          Upload an SPSS file and get professional crosstabs with significance testing in seconds.
          Built with the Indico Crosstab API.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>1. Upload</CardTitle>
            <CardDescription>Drag & drop your .sav file</CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/upload">
              <Button className="w-full">Upload File</Button>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>2. Analyze</CardTitle>
            <CardDescription>Pick variables, run crosstabs</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Automatic significance testing with industry-standard A/B/C letter notation.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>3. Export</CardTitle>
            <CardDescription>Download client-ready Excel</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Professional formatting with nets, means, and bases — ready for presentation.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Commit**

```bash
git init
git add -A
git commit -m "feat: Next.js template scaffold with Indico Crosstab SDK"
```

---

### Task 7: Upload page + metadata display

**Files:**
- Create: `indico-crosstab-nextjs-template/app/upload/page.tsx`
- Create: `indico-crosstab-nextjs-template/app/api/upload/route.ts`
- Create: `indico-crosstab-nextjs-template/app/api/metadata/route.ts`
- Create: `indico-crosstab-nextjs-template/components/file-uploader.tsx`

- [ ] **Step 1: Write `app/api/upload/route.ts` — server action**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { ig } from "@/lib/indico-crosstab";

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const file = formData.get("file") as File | null;
  if (!file) {
    return NextResponse.json({ error: "No file provided" }, { status: 400 });
  }

  const buffer = Buffer.from(await file.arrayBuffer());
  const result = await ig.upload(new Blob([buffer]), file.name);
  return NextResponse.json(result);
}
```

- [ ] **Step 2: Write `app/api/metadata/route.ts`**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { ig } from "@/lib/indico-crosstab";

export async function POST(req: NextRequest) {
  const { file_id } = await req.json();
  if (!file_id) {
    return NextResponse.json({ error: "file_id required" }, { status: 400 });
  }

  const metadata = await ig.getMetadata(file_id);
  return NextResponse.json(metadata);
}
```

- [ ] **Step 3: Write `components/file-uploader.tsx`**

```tsx
"use client";

import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  onUploaded: (fileId: string, filename: string) => void;
}

export function FileUploader({ onUploaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Upload failed");
      }
      const data = await res.json();
      onUploaded(data.file_id, data.filename);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [onUploaded]);

  return (
    <Card
      className={`border-2 border-dashed transition-colors ${
        dragging ? "border-blue-500 bg-blue-50" : "border-gray-300"
      }`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
    >
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <p className="text-lg font-medium mb-2">
          {uploading ? "Uploading..." : "Drop your .sav file here"}
        </p>
        <p className="text-sm text-muted-foreground mb-4">
          Supports .sav, .csv, .xlsx (max 50MB)
        </p>
        {error && <p className="text-sm text-red-500 mb-4">{error}</p>}
        <Button variant="outline" disabled={uploading} asChild>
          <label className="cursor-pointer">
            Browse files
            <input
              type="file"
              className="hidden"
              accept=".sav,.csv,.xlsx,.xls,.tsv"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
          </label>
        </Button>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Write `app/upload/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileUploader } from "@/components/file-uploader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface Variable {
  name: string;
  label: string;
  type: string;
  n_valid: number;
}

interface Metadata {
  filename: string;
  n_cases: number;
  n_variables: number;
  variables: Variable[];
  suggested_banners: string[];
}

export default function UploadPage() {
  const router = useRouter();
  const [fileId, setFileId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [loading, setLoading] = useState(false);

  const handleUploaded = async (id: string, filename: string) => {
    setFileId(id);
    setLoading(true);
    try {
      const res = await fetch("/api/metadata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: id }),
      });
      const data = await res.json();
      setMetadata(data);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Upload & Inspect</h2>

      {!metadata && <FileUploader onUploaded={handleUploaded} />}

      {loading && <p className="text-center text-muted-foreground">Analyzing file...</p>}

      {metadata && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{metadata.filename}</CardTitle>
            </CardHeader>
            <CardContent className="flex gap-4">
              <Badge variant="secondary">{metadata.n_cases} respondents</Badge>
              <Badge variant="secondary">{metadata.n_variables} variables</Badge>
              <Badge variant="outline">
                Suggested banners: {metadata.suggested_banners.join(", ") || "none"}
              </Badge>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Variables</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-96 overflow-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="py-2 pr-4 font-medium">Name</th>
                      <th className="py-2 pr-4 font-medium">Label</th>
                      <th className="py-2 pr-4 font-medium">Type</th>
                      <th className="py-2 font-medium">Valid N</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metadata.variables.map((v) => (
                      <tr key={v.name} className="border-b">
                        <td className="py-2 pr-4 font-mono text-xs">{v.name}</td>
                        <td className="py-2 pr-4">{v.label}</td>
                        <td className="py-2 pr-4">
                          <Badge variant="outline" className="text-xs">{v.type}</Badge>
                        </td>
                        <td className="py-2">{v.n_valid}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <Button onClick={() => router.push(`/analyze?file_id=${fileId}`)}>
            Analyze this file
          </Button>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: upload page with drag-drop and metadata display"
```

---

### Task 8: Crosstab analysis page with significance letters

**Files:**
- Create: `indico-crosstab-nextjs-template/app/analyze/page.tsx`
- Create: `indico-crosstab-nextjs-template/app/api/crosstab/route.ts`
- Create: `indico-crosstab-nextjs-template/app/api/tabulate/route.ts`
- Create: `indico-crosstab-nextjs-template/components/variable-picker.tsx`
- Create: `indico-crosstab-nextjs-template/components/crosstab-table.tsx`
- Create: `indico-crosstab-nextjs-template/components/sig-letter-cell.tsx`

- [ ] **Step 1: Write `components/sig-letter-cell.tsx`**

```tsx
interface Props {
  value: number;
  letter?: string;
}

export function SigLetterCell({ value, letter }: Props) {
  return (
    <td className="px-3 py-2 text-right tabular-nums">
      {value.toFixed(1)}%
      {letter && (
        <span className="ml-1 text-xs font-bold text-red-600">{letter}</span>
      )}
    </td>
  );
}
```

- [ ] **Step 2: Write `components/variable-picker.tsx`**

```tsx
"use client";

import { Label } from "@/components/ui/label";

interface Variable {
  name: string;
  label: string;
}

interface Props {
  label: string;
  variables: Variable[];
  value: string;
  onChange: (value: string) => void;
}

export function VariablePicker({ label, variables, value, onChange }: Props) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      <select
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Select variable...</option>
        {variables.map((v) => (
          <option key={v.name} value={v.name}>
            {v.name} — {v.label}
          </option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 3: Write `components/crosstab-table.tsx`**

```tsx
import { SigLetterCell } from "./sig-letter-cell";

interface CrosstabResult {
  row_variable: string;
  col_variable: string;
  percentages: Record<string, Record<string, number>>;
  significance_letters: Record<string, Record<string, string>>;
  col_bases: Record<string, number>;
}

interface Props {
  data: CrosstabResult;
}

export function CrosstabTable({ data }: Props) {
  const columns = Object.keys(data.col_bases);
  const rows = Object.keys(data.percentages);

  // Assign letters A, B, C... to columns
  const colLetters = Object.fromEntries(
    columns.map((col, i) => [col, String.fromCharCode(65 + i)]),
  );

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-100 border-b">
            <th className="px-3 py-2 text-left font-medium">{data.row_variable}</th>
            {columns.map((col) => (
              <th key={col} className="px-3 py-2 text-right font-medium">
                {col}
                <span className="ml-1 text-xs text-gray-400">({colLetters[col]})</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row} className="border-b hover:bg-gray-50">
              <td className="px-3 py-2 font-medium">{row}</td>
              {columns.map((col) => (
                <SigLetterCell
                  key={col}
                  value={data.percentages[row]?.[col] ?? 0}
                  letter={data.significance_letters[row]?.[col]}
                />
              ))}
            </tr>
          ))}
          <tr className="bg-gray-50 font-medium">
            <td className="px-3 py-2">Base (n)</td>
            {columns.map((col) => (
              <td key={col} className="px-3 py-2 text-right tabular-nums">
                {data.col_bases[col]}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Write `app/api/crosstab/route.ts`**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { ig } from "@/lib/indico-crosstab";

export async function POST(req: NextRequest) {
  const { file_id, row, col } = await req.json();
  if (!file_id || !row || !col) {
    return NextResponse.json({ error: "file_id, row, and col required" }, { status: 400 });
  }

  const result = await ig.crosstab(file_id, { row, col, significance_level: 0.95 });
  return NextResponse.json(result);
}
```

- [ ] **Step 5: Write `app/api/tabulate/route.ts`**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { ig } from "@/lib/indico-crosstab";

export async function POST(req: NextRequest) {
  const { file_id, spec } = await req.json();
  if (!file_id || !spec) {
    return NextResponse.json({ error: "file_id and spec required" }, { status: 400 });
  }

  const buffer = await ig.tabulate(file_id, spec);
  return new NextResponse(buffer, {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="${spec.title || "tabulation"}.xlsx"`,
    },
  });
}
```

- [ ] **Step 6: Write `app/analyze/page.tsx`**

```tsx
"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { VariablePicker } from "@/components/variable-picker";
import { CrosstabTable } from "@/components/crosstab-table";

interface Variable { name: string; label: string; type: string; }

function AnalyzeContent() {
  const params = useSearchParams();
  const fileId = params.get("file_id");

  const [variables, setVariables] = useState<Variable[]>([]);
  const [row, setRow] = useState("");
  const [col, setCol] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fileId) return;
    fetch("/api/metadata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: fileId }),
    })
      .then((r) => r.json())
      .then((data) => setVariables(data.variables ?? []));
  }, [fileId]);

  const runCrosstab = async () => {
    if (!row || !col) return;
    setLoading(true);
    try {
      const res = await fetch("/api/crosstab", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: fileId, row, col }),
      });
      setResult(await res.json());
    } finally {
      setLoading(false);
    }
  };

  const downloadExcel = async () => {
    const res = await fetch("/api/tabulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_id: fileId,
        spec: { banners: [col], stubs: [row], significance_level: 0.95 },
      }),
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "analysis.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!fileId) return <p>No file selected. Go to /upload first.</p>;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Analyze</h2>

      <Card>
        <CardHeader><CardTitle>Crosstab Builder</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <VariablePicker label="Row (stub)" variables={variables} value={row} onChange={setRow} />
          <VariablePicker label="Column (banner)" variables={variables} value={col} onChange={setCol} />
          <div className="flex items-end gap-2">
            <Button onClick={runCrosstab} disabled={!row || !col || loading}>
              {loading ? "Running..." : "Run Crosstab"}
            </Button>
            {result && (
              <Button variant="outline" onClick={downloadExcel}>
                Download Excel
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>
              {result.row_variable} × {result.col_variable}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CrosstabTable data={result} />
            {result.chi2 != null && (
              <p className="mt-2 text-xs text-muted-foreground">
                Chi-squared: {result.chi2.toFixed(2)}, p = {result.p_value.toFixed(4)}
                {result.p_value < 0.05 && " (significant)"}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function AnalyzePage() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <AnalyzeContent />
    </Suspense>
  );
}
```

- [ ] **Step 7: Verify it runs**

```bash
cp .env.example .env.local
# Edit .env.local with a real sk_test_ key
npm run dev
```

Open `http://localhost:3000`. Upload a .sav → see metadata → run crosstab → see significance letters → download Excel.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: crosstab analysis page with significance letters + Excel export"
```

---

### Task 9: Developer portal page on the API

**Files:**
- Create: `quantipro-api/public/developers.html`
- Modify: `quantipro-api/main.py` (add route)

- [ ] **Step 1: Write `public/developers.html`**

This is a single-page developer portal with interactive code samples. The implementing engineer should:

1. Read the existing `public/index.html` (landing page) for style/layout patterns
2. Create `developers.html` with sections:
   - **Quickstart** (5-step code sample: install → init → upload → analyze → export)
   - **Interactive playground** (paste API key, upload file, try endpoints live)
   - **SDK install** (npm, Python pip, curl)
   - **Authentication** (how API keys work, where to get one)
   - **Code samples** (JavaScript, Python, curl) for the 5 most common operations
   - **Webhooks** (how async works, callback format)
   - **Rate limits** (per-plan table)

3. Add route in `main.py`:
```python
@app.get("/developers", include_in_schema=False)
async def developers_page():
    return FileResponse("public/developers.html")
```

- [ ] **Step 2: Commit**

```bash
git add public/developers.html main.py
git commit -m "feat: developer portal page with quickstart and code samples"
```

---

## Verification Checklist

After completing all tasks:

- [ ] **SDK**: `cd indico-crosstab-sdk && npm test` — all tests pass
- [ ] **SDK**: `npm run build` — produces dist/ with types
- [ ] **Backend**: `cd quantipro-api && python -m pytest tests/ -x -q` — all tests pass (including job tests)
- [ ] **Template**: `cd indico-crosstab-nextjs-template && npm run build` — builds without errors
- [ ] **E2E**: Upload .sav via template → see metadata → run crosstab → see sig letters → download Excel
- [ ] **Webhook**: `POST /v1/tabulate` with `webhook_url` → returns 202 → `GET /v1/jobs/{id}` → status=done → webhook received
- [ ] **Developer portal**: `https://crosstab.indicolabs.io/developers` loads with quickstart code

---

## Deployment Notes

1. **SDK**: Publish to npm with `npm publish --access public` (requires npm account with `@indicolabs` scope)
2. **Backend**: Push to `master` → Railway auto-deploys
3. **Template**: Push to GitHub `quack2025/insightgenius-nextjs-template` → reference in SDK README
4. **Developer portal**: Included in backend deploy (static HTML)
