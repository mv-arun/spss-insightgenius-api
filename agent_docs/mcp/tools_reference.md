# MCP Tools Reference — 14 Tools

> All tools require `api_key` parameter (or `Authorization: Bearer` header on Streamable HTTP).

---

## System Tools

### spss_get_server_info
**No auth required.** Returns engine status, available tools, plan limits.

```json
// Response
{
  "server": "spss_mcp",
  "version": "1.0.0",
  "quantipymrx_available": true,
  "file_sessions_enabled": true,
  "supported_formats": [".sav", ".csv", ".xlsx", ...],
  "tools_available": ["spss_upload_file", ...],
  "tools_unavailable": [],
  "plan_limits": { "free": {...}, "pro": {...}, "business": {...} }
}
```

### spss_upload_file
Upload a data file to create a reusable session.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | yes | API key |
| file_base64 | string | yes | Base64-encoded file |
| filename | string | no | Filename with extension (default: upload.sav) |

```json
// Response
{
  "file_id": "abc123",
  "format_detected": "sav",
  "metadata_inferred": false,
  "n_cases": 1000,
  "n_variables": 19,
  "ttl_seconds": 1800
}
```

---

## Exploration Tools

### spss_get_metadata
Full dataset metadata including AI-detected smart fields.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id | string | no* | File session ID |
| file_base64 | string | no* | Base64 file (alternative) |
| response_format | string | no | "json" or "markdown" |

*One of file_id or file_base64 required.

Returns: variables list, suggested_banners, detected_groups, preset_nets, detected_weights.

### spss_describe_variable
Deep profile of a single variable.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| variable | string | yes | Variable name |

Returns: name, label, type, value_labels, distribution, n_valid, n_missing, mean/std/median (if numeric).

---

## Analysis Tools

### spss_analyze_frequencies
Frequency tables for 1-50 variables (batch).

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| variables | string[] | yes | 1-50 variable names |
| weight | string | no | Weight variable |

### spss_analyze_crosstab
Cross-tabulation with significance letters (A/B/C) and chi-square.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| row | string | yes | Row variable (stub) |
| col | string or string[] | yes | Banner variable(s) |
| weight | string | no | Weight variable |
| significance_level | float | no | 0.90, 0.95, or 0.99 (default: 0.95) |
| nets | object | no | Net definitions |
| include_means | bool | no | Include mean row with T-test |

### spss_analyze_correlation *(requires QuantipyMRX)*
Correlation matrix between numeric variables.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| variables | string[] | yes | 2-20 numeric variables |
| method | string | no | "pearson", "spearman", or "kendall" |

### spss_analyze_anova *(requires QuantipyMRX)*
One-way ANOVA with Tukey HSD post-hoc.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| dependent | string | yes | Dependent numeric variable |
| factor | string | yes | Grouping categorical variable |
| post_hoc | bool | no | Include Tukey comparisons (default: true) |

### spss_analyze_gap *(requires QuantipyMRX)*
Importance-Performance gap analysis with quadrant classification.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| importance_vars | string[] | yes | Importance variables |
| performance_vars | string[] | yes | Performance variables (same order) |

### spss_summarize_satisfaction *(requires QuantipyMRX)*
Compact T2B/B2B/Mean summary for multiple scale variables.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| variables | string[] | yes | Scale variables |
| top_box | int[] | no | Top Box values (default: [4,5]) |
| bottom_box | int[] | no | Bottom Box values (default: [1,2]) |

---

## Output Tools

### spss_auto_analyze
Zero-config: AI detects banners, groups, nets → complete Excel.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| significance_level | float | no | Default 0.95 |
| include_means | bool | no | Default true |

Returns: `download_url` + `tables_summary[]` + `content_blocks` with slides.

### spss_create_tabulation
Full professional Excel with sig, nets, means, MRS, grids.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| banners | string[] | yes | Banner variables |
| stubs | string[] | no | Default ["_all_"] |
| significance_level | float | no | Default 0.95 |
| weight | string | no | Weight variable |
| include_means | bool | no | Default false |
| output_mode | string | no | "multi_sheet", "single_sheet", or "banner_sheets" |
| nets | object | no | Net definitions |
| mrs_groups | object | no | MRS groups |
| grid_groups | object | no | Grid groups |
| custom_groups | array | no | Custom break groups |

### spss_export_data
Convert file to another format.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| file_id / file_base64 | | yes | File reference |
| format | string | yes | "xlsx", "csv", "parquet", or "dta" |

Returns: `download_url` for the converted file.

---

## Annotations

All tools declare MCP annotations for LLM reasoning:

| Tool | readOnly | destructive | idempotent | openWorld |
|------|----------|-------------|------------|-----------|
| spss_upload_file | false | false | true | false |
| spss_get_server_info | true | false | true | false |
| spss_get_metadata | true | false | true | false |
| spss_describe_variable | true | false | true | false |
| spss_analyze_* | true | false | true | false |
| spss_auto_analyze | true | false | true | false |
| spss_create_tabulation | true | false | true | false |
| spss_export_data | true | false | true | false |

---

## Conditional Registration

Tools 7-10 require QuantipyMRX engine:
- `spss_analyze_correlation`
- `spss_analyze_anova`
- `spss_analyze_gap`
- `spss_summarize_satisfaction`

If QuantipyMRX is not installed, these tools are NOT registered (LLMs won't see them).
Check `spss_get_server_info.tools_unavailable` for details.
