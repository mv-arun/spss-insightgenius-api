# Variables + Crosstabs: implementation plan

Status: proposal, not built. Preview: [variables-crosstabs-preview.html](variables-crosstabs-preview.html), with sample data and nothing saved.

## Goal

Turn the 7-step Tabulation flow into 5 steps:

| Today | Proposed |
|---|---|
| Upload → Review data → Banners + filter → Tables → Options → Custom groups → Generate | **Dataset** → **Variables** → **Crosstabs** → Options → Generate |

## App layout: no sidebar

The app does one job (transformations and tabulation), so the sidebar is replaced by a single top bar:

- **Left:** brand. Clicking it goes back to the Dataset step.
- **Centre:** the 5 steps as pills. The current step is filled, finished steps show ✓, and later steps stay locked until a dataset is chosen. On a phone, only the current step shows its name and the bar scrolls sideways.
- **Right:** help and the account menu. **Settings** moves into the account menu.
- **Under the bar:** a strip naming the open file ("derm_patient_survey_w2.sav · 420 respondents · 20 columns · Change"), so you always know which data you're working on.
- Without the 232px sidebar, Crosstabs gets that width back for the table.

What happens to today's pages:

| Today | Proposed |
|---|---|
| Home (`/home`) | Removed: `/` after sign-in opens the Dataset step |
| Datasets (`/datasets`, `/datasets/upload`, `/datasets/{id}`) | Becomes step 1. With `ENABLE_DATASETS` off (no Supabase), step 1 shows only the upload card |
| Transformations (`/review`) | Becomes step 2, Variables |
| Workflows (`/workflows`, `/express`, `/wizard`, `/export-mcp`) | Off the nav. Routes stay for now, hidden like the AI chat flag |
| Settings | Account menu |

Front-end impact:

- `ic.js`: `<ic-sidebar>` and `<ic-topbar>` are replaced by one `<ic-appbar>` that takes the steps. Pages that still use the old pair keep working until they're removed.
- `ic.css`: `.ic-app` becomes a single column, and `.ic-appbar` / `.ic-appbar-step` are added. No new colours.
- `main.py`: `/home` and `/workflows` redirect to `/app` (the stepped flow). `/upload`, `/privacy`, `/docs/mcp` and sign-in are unchanged.

- **Variables** is a variable-view grid with no data preview. It edits the codebook.
- **Crosstabs** is a drag-and-drop builder. The table updates as you build it, and what you see is what the Excel will contain.
- The UI says **Rows** and **Columns** instead of stubs and banners.
- No colour or design-system changes. Everything uses `ic.css` and `ic.js`.
- No AI in this round.

## What we took from the reference deck

| Product | Pattern | Use it? |
|---|---|---|
| MarketSight | Columns, Rows and Filters tabs; "Include all variables"; per-variable "Hide or omit unchecked values"; auto-update results | Yes: category checkboxes on each chip, "Add all", live update |
| Webix pivot | Four zones: Fields, Filters, Columns, Rows, Values | Yes: same zones. No: we drop the modal and the Apply button |
| Displayr / Q | Rows/Columns shelves, "Swap", Live view toggle, nets and stats under each row | Yes: Swap, live view, Top 2 Box and mean added automatically |
| Displayr drop overlay | Drop targets appear while dragging ("X as Rows", "Mean as cell value") | Later: nice, but more work than the plain drop zones |
| dejuice Table Builder | Variable list on the left; Banner, Stub and Table panels | Yes: the left variable list. No: the separate "Calculate table" button |
| SurveyMonkey | Rows (Stub) / Columns (Banner) drop areas; pick categories per question | Yes: picking categories per variable |
| Tabx / Survey Report | Letter significance, delta and row % rows, a list of calculation types | Partly: Column %, Counts, Row % and significance as "Values". We skip the delta rows |
| Crosstab Report (slide 5) | Shared settings bar: base, filter, stat levels | Yes: the result bar shows who is counted and the stat levels |

## Technical decision: stay on the current stack

We don't adopt React, AG Grid, PivotTable.js or MUI.

- **The numbers must come from the server.** PivotTable.js and AG Grid pivot compute in the browser. They know nothing about significance letters, weights, multi-select bases, nets or the low-base rules that are tested against the R golden file. If the preview were computed in the browser, it would disagree with the Excel.
- **One design system.** CLAUDE.md says not to add a second one. MUI or AntD would bring their own styles, and a React build step would split the codebase.
- **The work is small.** Native HTML5 drag and drop, a `+` menu as the keyboard and touch fallback, and popovers come to about 300 lines of plain JS. The preview already does all of it in one file.
- Only optional: SortableJS (about 10 KB, from a CDN) if reordering chips by drag needs to feel smoother than native drag and drop.

## Step 1: Dataset (replaces "Upload" and the Datasets pages)

- **Your datasets:** a table with name, format, respondents, columns and last update, plus search. "Use" opens the file and moves to Variables. It's built from the existing `public/ui/datasets.js` library calls.
- **Upload a new file:** today's drop zone (.sav, Excel, CSV/TSV). The uploaded file is saved to the library when Datasets is on.
- **Next wave of a study?** A hint pointing to Setup on the Variables step.

## Step 2: Variables (replaces "Review data")

The grid is one row per variable:

| Column | Behaviour |
|---|---|
| ☐ | Multi-select for bulk actions: change type, add to Rows, hide from tables |
| **Type** | Glyph chip: `1·2` Coded, ☑ Multi-select, `1–5` Rating, `123` Number, `Aa` Open text, 📅 Date, ⦸ Not used. Click it to open a menu → `set_role` op |
| Name | Monospace and read-only for source columns. Derived variables can be renamed (op already exists) |
| **Label** | Double-click or F2 edits in place. Enter saves, Esc cancels → `set_label` op |
| Values | "N categories" opens today's recode drawer (values, merges, missing, nets). Numbers show their range |
| Missing | Summary of missing codes |
| Base | n answered |
| ⋯ | Edit values and nets, create a variable from this one, add to Rows, hide |

Other details:

- Grids and multi-selects collapse into one parent row (for example `Q12_1…20`) and expand to show their items. Today these show as 112 loose "numeric" rows in example3.
- Type filter pills with counts, search, Undo, and "New variable" (today's builder).
- There's no crosstab preview on this step. Today's "Showing X by Y" preview moves to Crosstabs.
- Every edit goes through the existing `POST /v1/codebook` `edits` ops. **No new backend is needed for this step.**

## Step 3: Crosstabs (replaces "Banners", "Tables" and "Custom groups")

The layout is the variable list on the left, with Columns, Rows, Filter and Values shelves and the live result on the right.

| Shelf | Maps to `/v1/tabulate` spec |
|---|---|
| **Columns**: across the top, shared by every table | `banners` (custom groups stay a choice inside the Columns chip menu → `custom_groups`) |
| **Rows**: one table each, in order | `stubs` + `table_order`. A multi-select or grid parent → `mrs_groups` / `grid_groups` |
| **Filter**: who is counted | `filters`, today's respondent conditions |
| **Values**: Column %, Counts, Row %, Significance and level | `show_percentages`, `show_counts`, `significance_levels`. Row % is new |
| Sort (Survey order / Total high→low / A→Z) | `sort_rows` (A→Z is new) |
| Chip ▾ → choose categories | New: `hide_codes: {var: [codes]}` |
| Chip ▾ → Nets & groups | `nets`, same drawer as on Variables |

How it behaves:

- Drag from the list, drop on a shelf, or drop on a chip to insert before it. Double-click adds the variable to Rows, and `+` opens Rows / Columns / Filter.
- A variable sits on one shelf at a time. Numbers can't go in Columns: the app suggests banding them on Variables first.
- "⇅ Swap with rows", "Add all" (one table per usable variable) and "Clear".
- The live result redraws on every change. Requests are debounced by 250 ms, and an `AbortController` cancels any request that's out of date.
- The result shows each Rows variable as a table: Total, then a column group for each Columns variable, with letters, bases, low-base `**`, nets, means and significance letters.
- Click the row header to cycle the sort. "Hide empty rows" is a toggle. Chart view reuses today's Chart.js preview.
- When you change a type on Variables, the Crosstabs list updates at once. Variables that can't be tabulated (text, date, not used) are greyed out and explain why.

## Backend changes

1. **`POST /v1/tabulate/preview`** returns JSON.
   - It takes the same spec as `/v1/tabulate`, plus `tables: [stub…]` (only the tables currently on screen).
   - It runs `build_tabulation()` and serialises its `TabulationResult` (`services/tabulation_builder.py:261`) instead of calling `_build_excel`.
   - The preview and the Excel then share one code path, so their numbers can't drift.
   - Tests: preview JSON against the golden numbers in `test_tabulation_real.py`.
2. **Parsed-data cache.** A live preview sends many requests, and each one re-parses the `.sav` from Redis (CLAUDE.md: "no parsed cache yet").
   - Add a small in-process LRU of `SPSSData`, keyed by `(file_id or sha256(bytes), codebook hash)`, with a TTL that matches the Redis session.
   - Without the cache, the live preview is too slow on large files.
3. **New spec fields:**
   - `hide_codes` (categories hidden per variable)
   - `show_row_pct`
   - `sort_rows: "az"`
   - These are all small changes in `banner_workbook.py` and `tabulation_builder.py`.
4. No change to auth, the response envelope or middleware. The endpoint uses `require_scope("process")` like `/v1/tabulate`.

## Front-end structure

- `public/app.html`: stepper drops to 5 steps. The Banners, Tables and Custom groups sections are replaced by `#crosstabs-section`. The Review iframe is replaced by `#variables-section`.
- `public/ui/variables.js` (new): the grid, type chip, inline label edit and bulk bar. It reuses the recode drawer and builder from `review.html`. Move them into the module rather than copying them.
- `public/ui/crosstabs.js` (new): the variable list, shelves, drag and drop, popovers, result renderer and spec builder.
- `public/ui/ic.css`: new generic components `.ic-chip`, `.ic-shelf`, `.ic-pop` and `.ic-type-glyph`. Type glyphs are added to `ICONS` in `ic.js`. No new colours.
- `/review` (Transformations in the sidebar) keeps working on its own. It renders the same Variables grid, plus its current preview panel, until we decide to retire it.
- State: one `project` object (`{codebook, spec}`) shared by the steps, so carry-over is automatic. It's saved to `sessionStorage` (wrapped in try/catch), so a refresh doesn't lose the shelves.

## Phases

| # | Scope | Size | Depends on |
|---|---|---|---|
| 0 | App bar instead of sidebar, Dataset step, page redirects | ~2 days | none |
| 1 | Variables grid in `app.html` (and `/review`), grouped grids and multi-selects, type chip, inline label edit, bulk actions | ~3 days | 0 for the layout; the grid itself can start right away |
| 2 | Backend: `/v1/tabulate/preview` + parsed-data cache + tests | ~2–3 days | none (can run in parallel with 1) |
| 3 | Crosstabs builder wired to the preview endpoint; replaces Banners, Tables and Custom groups; spec → `/v1/tabulate` | ~4 days | 2 |
| 4 | Extras: `hide_codes`, Row %, A→Z sort, chart view, `sessionStorage` restore | ~2 days | 3 |
| 5 | Clean-up: remove the old steps' code, update CLAUDE.md and the docs, browser QA on example3 + the CX Pulse jobs | ~1 day | 3 |

Done means:

- Every existing tabulate test passes.
- New tests cover the preview endpoint's JSON and spec mapping.
- The Excel for a given Crosstabs setup matches the preview cell for cell on example3 and one reference job.

## Out of scope now / later

- AI suggestions ("show satisfaction by age"). The shelf model makes this easy later: the AI only has to fill in a spec.
- Nested columns (Age within Gender). `nested_banners` already exists in the spec, so this could later be done by dropping a chip onto another chip.
- Displayr-style drop overlays, a saved-crosstab library, and comparing waves inside the builder.

## Open questions

1. ~~Should `/review` keep its own page?~~ Decided: it becomes step 2. Datasets becomes step 1, and the sidebar is replaced by a top bar.
2. Row %, A→Z sort and hiding categories need small engine changes. Are they wanted in v1, or should v1 ship with what the engine already supports?
3. Should Columns stay shared by every table (as today), or should each table be allowed its own columns? Today the Excel has one banner set.
