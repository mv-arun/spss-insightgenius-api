# Plan: Recoding in Review data + configurable survey rules

> Status: proposal · 2026-10-15 · builds on IMPLEMENTATION_PLAN.md (M4 rule engine, M5 saved codebooks, M7 data workbook)

## 1. Goal

1. Give analysts a **proper recode tool** in *Review data*, matching what they know from
   Forsta Reportal and Datasmoothie: change a question's coding, or build a new variable from it,
   without writing rules by hand.
2. Make the **hard-coded HubSpot / CX rules configurable in the UI**: job-role group, NPS groups,
   product counts and mixes, drivers, score columns, the FULL DATA tabs. They become ordinary
   recodes that are visible, editable and saved, instead of Python code.

## 2. What the reference tools do

| Tool | How recoding works | What we take from it |
|---|---|---|
| **Typical tabulation UI** — *Recode into existing or new variables* | **Into existing:** change Structure (e.g. Nominal → Numeric) and the **Values** in *Values & Labels* to get a mean (reverse a scale, mid-points); **merge categories** by dragging one onto another (undo = *Split*); **add Top/Bottom K NET** categories to tables without changing values; turn a grid into **Binary** with a *Count this value* column (Top 2 Box). **Into new:** one-click scripts — *Top/Bottom K Box*, *Recode NPS*, *numeric from mid-points*, *capping*; anything else via R / JavaScript | Two clear modes (**edit this question** vs **create a new variable**); one-click **quick recodes**; **nets** as table categories; editable **values** (scores) separate from labels |
| **Forsta Reportal** — *Recoding a Variable* | Right-click a question → *Recode Variable* → page with **Categories** (name, ID) on the right and **Answers** on the left; select answers, click **»** to assign; *Add / Remove* categories; *Clear selected*; question gets a **(1R)** badge; a question can be recoded several times (rec0, rec1…). **Numeric:** *From / To* ranges, **“N equal categories”** + *Go*, change operators, no gaps allowed, **Mask** a category | The **category builder** (answers → new categories) is the core UI; **badge** showing a question has recodes; several recodes per question; numeric **ranges with equal-split**, **mask** |
| **Datasmoothie** (video, Quantipy-based like our engine) | Datasources → dataset → variable list (Name / Type / Label / Values) → click a variable → panel with a **Missing** tab: every answer with a checkbox; tick *Don't know* → it disappears from charts | A visible **“Exclude from base”** checkbox column per answer — clearer than our hover-icon |

## 3. What we already have (M4) and the gaps

**Have:** rule engine with 7 rule types (`recode`, `bands`, `priority`, `count`, `combination`,
`coalesce`, `flags`), edit ops (`set_label`, `set_role`, `set_measure`, `relabel_code`,
`set_missing`, `merge_codes`, `reorder_codes`, `add/update/remove_derived`), server-side validation,
Undo, a “+ New variable” builder (forms for bands / group answers / count / flags / combine; JSON
for priority & combination), codebook sent with every analysis.

**Gaps vs the reference tools:**

| Gap | Why it matters |
|---|---|
| No **Recode** entry point on a question — editing is scattered (hover icons, “Treat as”, a separate builder) | Analysts expect *Recode Variable* on the question, as in Forsta |
| No **category builder** (answers → named categories, drag or »), only a text-field “group name” form | The single most used recode; must be fast and visual |
| **Existing derived variables can't be edited** in the UI (only removed) | NPS bands, job-role priority etc. can't be changed → the core of "make rules configurable" |
| No **values / scores** separate from codes (reverse a scale, mid-points for means) | The main “recode into existing” use |
| No **nets** (Top 2 Box / “Any agree” categories in tables without a new variable) | Standard tables expect them; today only auto T2B on grids |
| Priority / combination rules only as **JSON** | Not usable by an analyst |
| **Missing** is a hover icon | Datasmoothie / SPSS show it as a visible checkbox column |
| No **quick recodes** (Top 2 Box, NPS, reverse scale, mid-points, quantiles) | One click instead of a form |
| Hard-coded client rules (§5) | Not visible, not editable, not reusable for other surveys |
| Edits **lost on reload**; no saved setups | Recodes must survive and repeat every wave (M5) |

## 4. Proposed UX

### 4.1 Entry point: a **Recode** button on every question

In *Review data*, an opened question shows **[Recode]** next to *Rename* / *Treat as*. Questions with
recodes get a **badge** (“2 recodes”, like Forsta's *(2R)*). Recode opens a side **drawer** with two tabs:

```
┌ Recode · Exam Results Alternative ───────────────────────────────── ✕ ┐
│ [ Edit this question ]  [ Create new variable ]                      │
├───────────────────────────────────────────────────────────────────────┤
│ Code  Answer                       Value*  Count   Exclude from base │
│  1    Strongly Disagree             1       59      ☐                │
│  2    Disagree                      2      121      ☐                │
│  3    Neither agree or disagree     3      190      ☐                │
│  4    Agree                         4      880      ☐                │
│  5    Strongly Agree                5      416      ☐                │
│ 98    I do not know                 —       35      ☑                │
│ 99    Not applicable                —       38      ☑                │
│  ⠿ drag to reorder · select rows → [Merge] [Rename]                  │
│ Quick: [Reverse values] [Top 2 Box net] [Bottom 2 Box net]           │
│ Nets (table rows only): Agree (T2B) = 4+5   [+ net]                  │
│ * Value = score used for means; codes/labels stay the same           │
└──────────────────────────────────────────── [Cancel] [Apply] ────────┘
```

- **Edit this question** (“into existing” + Datasmoothie “Missing”): one table with
  drag-to-reorder, multi-select rows → *Merge* / *Rename*, an editable **Value** (score) column, a
  visible **Exclude from base** checkbox column, **nets**, quick actions. Changes are staged in the
  drawer and applied together (one Undo step).

```
│ [ Edit this question ]  [ Create new variable ]                      │
│ Name: Exam results (3 groups)                                        │
│ ┌ Answers ──────────────── ┐   ┌ New categories ─────────────────┐   │
│ │ ☐ Strongly Disagree  59  │ » │ 1 Disagree   ← Strongly Disagree │   │
│ │ ☐ Disagree          121  │   │               Disagree           │   │
│ │ ☐ Neither …         190  │ » │ 2 Neutral    ← Neither …         │   │
│ │ ☐ Agree             880  │ » │ 3 Agree      ← Agree, Strongly…  │   │
│ │ ☐ Strongly Agree    416  │   │ [+ category]                     │   │
│ └──────────────────────────┘   └──────────────────────────────────┘   │
│ Unassigned answers: (•) missing  ( ) “Other” category                │
│ Preview: Disagree 180 · Neutral 190 · Agree 1,296                    │
```

- **Create new variable** (Forsta's category builder): pick answers (checkboxes or drag) and press
  **»** to put them in a category; add / rename / remove categories; choose what happens to
  unassigned answers; live count preview. The source can be:
  - **Coded question** → category builder (rule `recode`)
  - **Number / rating** → **From / To** ranges, “**N equal groups**” + Go, presets (NPS 0-6/7-8/9-10,
    quartiles), **mask** a range (rule `bands`)
  - **Multi-select** → three builders: **Count ticked** (bands), **Priority groups** (§4.2),
    **Exact combinations** (§4.3)
  - **Several multi-selects** → **Combine** (rule `coalesce`)
  - **Any coded question** → **One column per answer** (rule `flags`)

### 4.2 Priority groups without JSON (job role)

```
Groups — first match wins (drag to change priority)
 1  Exams Officer   if ticked [Exams Officer ×]
 2  Leader          if ticked [School Leader ×] [School Group/District Leader ×]
                    or ticked [Head of Department ×] and NOT ticked [Teacher ×]   [+ or…]
 3  Teacher         if ticked [Teacher ×]
 Everyone else →    [Other]   ( ) leave missing
```
Each condition row = *ticked any of / ticked all of / not ticked* + option chips (and *score
between* for numeric questions). Maps 1:1 to the existing `priority` conditions (`any / all / none
/ and / or / between`).

### 4.3 Exact combinations (product mix)

A list of combinations, each a set of option chips + “exactly these” or “only from these”, and
“ignore when checking: [Other ×]”. Maps to `combination`.

### 4.4 Editing an existing derived variable

Every derived variable (NPS group, Job role group, anything a user built) gets **[Edit]**: the same
drawer, pre-filled (`update_derived`). This is what makes the client rules configurable.

### 4.5 Visible “Exclude from base”

The expanded question in the list also shows a small checkbox column instead of the hover ⊘ icon.

## 5. Hard-coded rules → configurable

| Hard-coded today | Where | Becomes |
|---|---|---|
| Job role group (EO > Leader > Teacher > Other) | `codebook/heuristics.py` `_job_role_group`, `codebook/infer.py` | A **priority-groups recode** in the *HubSpot CX* setup (§6), editable in §4.2 |
| NPS group 0-6 / 7-8 / 9-10 | `codebook/infer.py` `NPS_BANDS` | Stays auto-suggested (generic), but **editable** as a **number-bands recode** |
| “(##)” role flag columns | `respondent_sheet.py` `ROLE_FLAGS` | **One column per answer** of the role group (data workbook setting, §7) |
| Number of products, Single / Dual / Triple | `respondent_sheet.py` `_product_columns` | **Count ticked** recode on Customer type (bands) |
| Product mix (Resources only … Programmes AND/OR exams) | `respondent_sheet.py` `_PRODUCTS`, `_PRODUCT_MIX` | **Exact combinations** recode(s) |
| Promoters / Passives / Detractors flags | `respondent_sheet.py` | **One column per answer** of NPS group |
| DRIVERS + driver flags, driver order | `respondent_sheet.py` `_driver_columns`, `_DRIVER_ORDER` | **Combine** recode of the 3 driver questions; order = the order of its columns (drag) |
| Score columns 1–5 | `respondent_sheet.py` | **One column per answer** per rating |
| HubSpot bookkeeping columns dropped | `respondent_sheet.py` `HUBSPOT_SYSTEM_COLUMNS` | **Not used** role on those columns in the setup |
| FULL DATA title, tabs (Detractors, Promoters, Single, Dual, Triple, Exam officers, Teachers, Leaders) | `respondent_sheet.py` `CATEGORY_SHEETS` | **Data workbook** settings (§7) |
| The on/off switch | `config.py` `CLIENT_RULES_LEGACY` | Removed once the setup reproduces the output |

The rule content already exists as data: `tests/fixtures/codebooks/cx_client_rules.json`, proven
identical to the code.

## 6. Setups (saved, reusable recodes)

A **setup** = a named list of codebook edits + which columns it expects. Examples: *HubSpot CX
Pulse*, *HubSpot CX Exam Stage*.

- **Apply:** on upload, if the columns match a saved setup → banner “*Looks like a HubSpot CX
  Pulse export — apply your saved setup?* [Apply] [Not now]”. Applied recodes appear as normal,
  editable recodes (badges, Edit buttons).
- **Save:** “Save as setup…” stores the current edits (name, client). Later waves: one click.
- **Partial matches:** edits referring to missing columns/options are skipped and listed
  (“2 recodes couldn't be applied: option *Exams Officer* not found in *Job role*”) — never silent.
- **Storage:** first as JSON files shipped with the app (`presets/hubspot_cx_pulse.json`, from the
  fixture) + **Import / Export setup** buttons; then Supabase with versions in **M5**
  (per organisation, decision pending).

## 7. Data workbook (FULL DATA + tabs), configurable

A small **Data workbook** panel (Step 2 or Options): which recodes become **flag columns** next to
their source, which variables get **one tab per category** (e.g. NPS group → Detractors / Passives /
Promoters tabs), tab names, sheet title, the % / count rows on/off. Defaults come from the setup.
Implementation = IMPLEMENTATION_PLAN.md **M7** (generic `data_workbook.py` driven by the codebook);
`respondent_sheet.py` is deleted after.

## 8. Backend changes

| Change | Notes |
|---|---|
| `set_values` op: score per code (reverse, mid-points) | New `Code.value` (defaults to code); means / t-tests use values; labels & codes unchanged |
| **Nets** in the codebook: `Variable.nets = [{label, codes}]`; ops `add_net / remove_net` | Tabulation picks them up as table nets (replaces auto T2B guessing where set) |
| `recode` rule: `else` (unassigned → *Other* or missing) and `copy` (keep unassigned with original labels) | Category builder needs both |
| `bands` helper: equal-width / quantile splits; `mask` flag per band | Forsta's “N equal categories”, masking |
| `apply_edits` reports **skipped** edits (missing column/option) instead of failing | For setups on new waves |
| Setup format + `GET /v1/setups`, `POST /v1/setups/match` (fingerprint), import/export | JSON files first; Supabase in M5 |
| Codebook JSON gets `recodes` metadata (source var, created_by setup/user) for badges | Purely descriptive |
| Remove `_job_role_group`, product/driver code, `CLIENT_RULES_LEGACY` | After R4 golden test passes |

## 9. Phases

| # | Phase | Delivers | Done when |
|---|---|---|---|
| **R1** | Recode drawer — *Edit this question* | Recode button + badge; table with drag reorder, multi-row merge/rename, **Exclude from base** checkboxes, **Values** column, quick *Reverse values*; staged apply (one Undo) | Every existing edit op reachable from one place; hover icons removed |
| **R2** | Recode drawer — *Create new variable* | Category builder (answers » categories, else Other/missing), number ranges (+ N equal groups, presets, mask), count-ticked, flags, combine — all with live preview | Analyst can build Top 2 Box, age bands, Single/Dual/Triple without JSON |
| **R3** | Priority & combination builders + **Edit existing** | §4.2 / §4.3 condition UI; Edit on every derived variable (pre-filled) | Job role group and product mix built/edited entirely in the UI; NPS bands editable |
| **R4** | Setups (files) + retire hard-coded rules | `presets/hubspot_cx_pulse.json`, `…exam_stage.json`; match banner; apply/skip report; import/export; delete legacy code + flag | Golden test passes with the setup instead of `CLIENT_RULES_LEGACY`; `grep` finds no client rules in `services/` |
| **R5** | Nets + values in tables | `nets` + `values` in codebook and tabulation; Top/Bottom K net quick actions | Tables show user nets; means use values (reverse-scaled mean verified) |
| **R6** | Data workbook settings (M7) | Generic data workbook from the codebook + settings panel | FULL DATA + tabs for CX Pulse reproduced from the setup; any survey can get its own tabs |
| **R7** | Saved setups in Supabase (M5) | Versions, per-org sharing, auto-apply on next wave | October wave: upload → “apply setup?” → identical coding, new options reported |

Suggested order: **R1 → R2 → R3 → R4** (makes the HubSpot rules configurable), then R5, R6, R7.

**Status (Oct 2026):** R1–R6 done. R4 notes: the job-role group, product count / mix and DRIVERS are
setups (`presets/hubspot_cx_pulse.json`, `presets/hubspot_cx_exam_stage.json`) and inference has no
client rules; the golden output with the setup equals the old output plus three new tables (Number
of products, Product mix, Drivers), and the real W3 Pulse / Exam Stage files give identical groups.
A setup whose columns are all present is applied automatically (keeps the old "it just works"
behaviour; Undo takes it off); partial matches are offered. Answers a wave doesn't have are left
out of a setup's rules with a note instead of skipping the recode. Still client-specific until R6:
`respondent_sheet.py` (FULL DATA + tabs) and `CLIENT_RULES_LEGACY`, which now only gates it.

R5 notes: nets live on the question (`Variable.nets`, ops `set_nets / add_net / remove_net`), follow
merges / new values / exclusions, show in the review preview, and replace the guessed nets in
/v1/tabulate and /v1/auto-analyze (a request's own `nets` still win). "Values" needed no separate
`Code.value`: the drawer's Value column (`set_codes`, R1) already is the number means use — a
reversed scale gives 6 − mean with the nets still on the same answers (tests/test_nets.py).

R6 notes: `services/data_workbook.py` builds FULL DATA + category sheets from `Codebook.data_workbook`
(op `set_data_workbook`; extra columns after a given column — flags per answer, var + code, a
condition, number ticked, first answered of several columns — score flags per rating, dropped
columns, tabs). The HubSpot setups carry the analysts' layout; on the sample and on the real W3 Pulse
and Exam Stage files every cell of all 9 sheets equals the old `respondent_sheet.py` output (the
sample's sheet is now named FULL DATA PULSE, as the real Pulse file's was). `respondent_sheet.py` and
`CLIENT_RULES_LEGACY` are deleted: no client rules remain in code. Review page: *Data sheets* panel
(title, flag columns, score columns, category tabs, columns left out; Save / Download now).
Not done from M7: the coded .sav / CSV export with the full codebook (M7.3).
R1–R3 are front-end heavy on top of the existing rule engine; R4 is mostly moving data out of code.

## 10. Testing

- Unit: each new op (`set_values`, nets, recode `else`/`copy`, equal-split bands, skipped edits).
- Golden: CX Pulse / Exam Stage synthetic fixtures — output with the **setup** equals today's output
  (then the legacy code can go).
- Browser (Playwright, on demand): build Top 2 Box via category builder; edit NPS bands; edit job-role
  priority (move Leader above Exams Officer → counts change); apply setup to a second wave.
- Real-file check (local, not committed): W3 CX Pulse and Exam Stage exports.

## 11. Open questions

1. **Recode into existing vs new by default?** Forsta always creates a new recoded variable;
   some tools edit in place. Proposal: *Edit this question* for cleanup, *Create new variable* for
   analysis groupings (keeps the original question intact).
2. **Setup scope:** per client, per survey (Pulse vs Exam Stage), or per organisation?
3. **Auto-apply** a matching setup or always ask? (Proposal: ask, with “always apply for this
   survey” option.)
4. The analysts' 3 open questions (col BZ, “Programmes AND/OR exams”, Triple with “Other”) decide the
   defaults in the HubSpot setups.
