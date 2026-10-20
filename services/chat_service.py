"""Chat service: Sonnet orchestrates analysis, engine executes, Sonnet interprets.

Flow:
1. User sends natural language query + file_id
2. Sonnet receives query + file metadata → decides which analyses to run
3. Backend executes analyses via QuantiProEngine (deterministic)
4. Sonnet receives results → generates interpretation + chart specs
5. Frontend renders charts + narrative

Cost: ~$0.01-0.03 per conversation turn (Sonnet input + output).
"""

import json
import logging
import math
from typing import Any

from anthropic import AsyncAnthropic

from config import get_settings
from services.quantipy_engine import QuantiProEngine, SPSSData
from shared.filenames import output_filename

logger = logging.getLogger(__name__)

# Tools that Sonnet can call (mapped to engine functions)
ANALYSIS_TOOLS = [
    {
        "name": "run_frequency",
        "description": "Run frequency analysis for one or more variables. Returns counts, percentages, mean, std, median. Supports filters for sub-population analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "variables": {"type": "array", "items": {"type": "string"}, "description": "Variable names to analyze"},
                "weight": {"type": "string", "description": "Weight variable name (optional)"},
                "filters": {"type": "array", "items": {"type": "object"}, "description": "Filters: [{variable, operator (eq/ne/gt/lt/gte/lte/in), value}]"},
            },
            "required": ["variables"],
        },
    },
    {
        "name": "run_crosstab",
        "description": "Run cross-tabulation with significance testing (Z-test, A/B/C letters). Best for comparing a question across demographics. Supports filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "row": {"type": "string", "description": "Row variable (the question)"},
                "col": {"type": "string", "description": "Column variable (the demographic/banner)"},
                "weight": {"type": "string", "description": "Weight variable (optional)"},
                "significance_level": {"type": "number", "default": 0.95},
                "filters": {"type": "array", "items": {"type": "object"}, "description": "Filters: [{variable, operator, value}]"},
            },
            "required": ["row", "col"],
        },
    },
    {
        "name": "run_correlation",
        "description": "Compute correlation matrix between numeric variables. Returns r-values and p-values.",
        "input_schema": {
            "type": "object",
            "properties": {
                "variables": {"type": "array", "items": {"type": "string"}, "description": "2+ numeric variables"},
                "method": {"type": "string", "enum": ["pearson", "spearman", "kendall"], "default": "pearson"},
            },
            "required": ["variables"],
        },
    },
    {
        "name": "run_anova",
        "description": "One-way ANOVA with Tukey HSD post-hoc. Tests if a numeric variable differs across groups.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dependent": {"type": "string", "description": "Numeric dependent variable"},
                "factor": {"type": "string", "description": "Grouping variable (categorical)"},
                "post_hoc": {"type": "boolean", "default": True},
            },
            "required": ["dependent", "factor"],
        },
    },
    {
        "name": "run_tabulate",
        "description": "Generate full Excel tabulation with multiple stubs crossed by banners. Returns a download URL. Use this when the user asks for an Excel, a tabulation, or a full report.",
        "input_schema": {
            "type": "object",
            "properties": {
                "banners": {"type": "array", "items": {"type": "string"}, "description": "Banner/demographic variables"},
                "stubs": {"type": "array", "items": {"type": "string"}, "description": "Stub variables to analyze (use ['_all_'] for all)"},
                "weight": {"type": "string", "description": "Weight variable (optional)"},
                "include_means": {"type": "boolean", "default": True},
                "significance_level": {"type": "number", "default": 0.95},
                "include_summary": {"type": "boolean", "default": False, "description": "Add AI executive summary as first Excel sheet"},
                "filters": {"type": "array", "items": {"type": "object"}, "description": "Filters: [{variable, operator, value}]"},
                "nets": {"type": "object", "description": "Nets per variable: {var: {net_name: [codes]}}"},
                "mrs_groups": {"type": "object", "description": "MRS groups: {group_name: [member_vars]}"},
                "output_mode": {"type": "string", "enum": ["multi_sheet", "single_sheet", "banner_sheets"], "default": "multi_sheet"},
            },
            "required": ["banners", "stubs"],
        },
    },
    {
        "name": "show_chart",
        "description": """Display a chart. Choose the RIGHT chart type for market research:
- nps_gauge: NPS score display. data: {score, promoters, passives, detractors}
- t2b_bar: Top 2 Box horizontal bars (sorted, color-coded). data: {labels, datasets:[{values}], sig_letters}
- correlation_heatmap: Correlation matrix. data: {labels, matrix: [[1.0, 0.8, ...], ...]}
- likert_diverging: Likert scale diverging bars. data: {labels, categories:['SD','D','N','A','SA'], values:[[10,20,30,25,15],...]}
- donut: Distribution (gender, region). data: {labels, datasets:[{values}]}
- bar/horizontal_bar/stacked_bar/line/scatter/pie: Standard charts. data: {labels, datasets:[{label, values, color}]}

RULES: Use nps_gauge for NPS, t2b_bar for satisfaction T2B comparisons, correlation_heatmap for correlation matrices, likert_diverging for Likert scale distributions, donut for simple distributions.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "horizontal_bar", "stacked_bar", "line", "scatter", "pie", "donut",
                             "nps_gauge", "t2b_bar", "correlation_heatmap", "likert_diverging"],
                },
                "title": {"type": "string"},
                "data": {
                    "type": "object",
                    "description": "Chart data — structure depends on chart_type (see tool description)",
                },
            },
            "required": ["chart_type", "title", "data"],
        },
    },
]


def _sanitize_for_json(obj: Any) -> Any:
    """Replace NaN/Inf with None for JSON serialization."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 4)
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _build_metadata_context(data: SPSSData) -> str:
    """Build a compact metadata summary for Sonnet's system prompt."""
    engine = QuantiProEngine()
    meta = engine.extract_metadata(data)

    lines = [
        f"File: {data.file_name} | {meta['n_cases']} cases x {meta['n_variables']} variables",
        "",
        "Variables (name: label [type, N categories]):",
    ]

    for v in meta.get("variables", [])[:100]:  # Cap at 100 vars for prompt
        vl = v.get("value_labels") or {}
        n_labels = len(vl)
        label = v.get("label", "")
        vtype = v.get("type", "")
        cats = f", {n_labels} cats" if n_labels > 0 else ""
        sample_labels = list(vl.values())[:4]
        sample_str = f" → {sample_labels}" if sample_labels else ""
        lines.append(f"  {v['name']}: {label} [{vtype}{cats}]{sample_str}")

    if len(meta.get("variables", [])) > 100:
        lines.append(f"  ... +{len(meta['variables']) - 100} more variables")

    # Suggested banners
    banners = meta.get("suggested_banners") or []
    if banners:
        lines.append(f"\nSuggested banners (demographics): {[b['variable'] for b in banners]}")

    # Detected groups
    groups = meta.get("detected_groups") or []
    if groups:
        lines.append(f"\nDetected groups ({len(groups)}):")
        for g in groups[:10]:
            lines.append(f"  [{g['question_type']}] {g['display_name'][:60]} ({len(g['variables'])} vars)")

    # Detected weights
    weights = meta.get("detected_weights") or []
    if weights:
        lines.append(f"\nDetected weight variables: {weights}")

    return "\n".join(lines)


async def _execute_tool(tool_name: str, tool_input: dict, data: SPSSData) -> dict:
    """Execute an analysis tool against the loaded data."""
    engine = QuantiProEngine()

    try:
        # Apply filters if provided (Story #2)
        filters = tool_input.get("filters")
        if filters and isinstance(filters, list) and len(filters) > 0:
            from services.tabulation_builder import _apply_group_mask
            mask = _apply_group_mask(data.df, filters)
            import pandas as pd
            filtered_df = data.df[mask].copy()
            data = type(data)(df=filtered_df, meta=data.meta, mrx_dataset=data.mrx_dataset, file_name=data.file_name)

        if tool_name == "run_frequency":
            results = []
            for var in tool_input["variables"]:
                try:
                    result = engine.frequency(data, var, weight=tool_input.get("weight"))
                    results.append(_sanitize_for_json(result))
                except Exception as e:
                    results.append({"variable": var, "error": str(e)})
            return {"frequencies": results}

        elif tool_name == "run_crosstab":
            result = engine.crosstab_with_significance(
                data,
                row=tool_input["row"],
                col=tool_input["col"],
                weight=tool_input.get("weight"),
                significance_level=tool_input.get("significance_level", 0.95),
            )
            return _sanitize_for_json(result)

        elif tool_name == "run_correlation":
            result = engine.correlation_matrix(
                data,
                variables=tool_input["variables"],
                method=tool_input.get("method", "pearson"),
            )
            return _sanitize_for_json(result)

        elif tool_name == "run_anova":
            result = engine.anova(
                data,
                dependent=tool_input["dependent"],
                factor=tool_input["factor"],
                post_hoc=tool_input.get("post_hoc", True),
            )
            return _sanitize_for_json(result)

        elif tool_name == "run_tabulate":
            from services.tabulation_builder import TabulateSpec, build_tabulation

            spec = TabulateSpec(
                banners=tool_input["banners"],
                stubs=tool_input.get("stubs", ["_all_"]),
                weight=tool_input.get("weight"),
                include_means=tool_input.get("include_means", True),
                significance_level=tool_input.get("significance_level", 0.95),
                include_summary=tool_input.get("include_summary", False),
                filters=tool_input.get("filters"),
                nets=tool_input.get("nets"),
                mrs_groups=tool_input.get("mrs_groups"),
                output_mode=tool_input.get("output_mode", "multi_sheet"),
            )
            result = build_tabulation(QuantiProEngine, data, spec)

            # Store the Excel for download
            from routers.downloads import store_download
            download_id, download_url = await store_download(
                result.excel_bytes,
                filename=output_filename("tables", data.file_name),
            )

            return {
                "download_url": download_url,
                "stubs_total": result.total_stubs,
                "stubs_success": result.successful,
                "stubs_failed": result.failed,
            }

        elif tool_name == "show_chart":
            # Charts are rendered by the frontend, we just pass through the spec
            return {"chart": tool_input, "rendered": True}

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error("Tool execution error [%s]: %s", tool_name, e, exc_info=True)
        return {"error": str(e)}


SYSTEM_PROMPT = """You are a senior market research analyst using Indico Crosstab.
You have access to a survey dataset and powerful analysis tools. Your job is to:

1. Understand the user's question
2. Decide which analyses to run (call tools)
3. Interpret the results with professional insight
4. Visualize key findings with charts (call show_chart)

RULES:
- Always use the analysis tools — NEVER invent or estimate numbers
- Run multiple analyses when needed to give a complete answer
- Use show_chart to visualize important findings (bar charts for comparisons, heatmaps for correlations)
- When showing crosstab results, highlight significant differences (sig letters)
- If the user asks for an Excel, tabulation, report, or "genera un Excel": use run_tabulate
- When using run_tabulate, include banners from the confirmed demographics, stubs from user request (or '_all_'), and include_means=true
- If user describes what they want in natural language, translate it to run_tabulate parameters (this is the "Prompt to Excel" feature)
- For filters: if user says "only women" or "filtered to London", add filters parameter
- Be concise but insightful. Lead with the key finding, then support with data
- Speak the language of market research: T2B, NPS, significance, base sizes
- If a variable doesn't exist, suggest similar ones from the metadata
- Answer in the same language as the user's question
- When generating tabulations, set include_summary=true for comprehensive reports

CHART TYPE GUIDE (use the most appropriate for each analysis):
- NPS analysis → nps_gauge: {score: 42, promoters: 55, passives: 25, detractors: 20}
- T2B comparison across items → t2b_bar: {labels: ["Speed","Price","Comfort"], datasets:[{values:[68,55,72]}], sig_letters:["AB","","C"]}
- Correlation matrix → correlation_heatmap: {labels: ["sat_speed","sat_price"], matrix: [[1.0, 0.65],[0.65, 1.0]]}
- Likert distributions → likert_diverging: {labels:["Speed","Price"], categories:["Very dissatisfied","Dissatisfied","Neutral","Satisfied","Very satisfied"], values:[[5,10,20,40,25],[8,15,25,35,17]]}
- Simple distribution (gender, region) → donut: {labels:["Male","Female"], datasets:[{values:[52,48]}]}
- Comparison across groups → bar or horizontal_bar: {labels:[...], datasets:[{label, values, color}]}
- Trends over time → line
- Standard bar for everything else → bar

ALWAYS choose the specialized chart type when it applies. Never use plain 'bar' for NPS, T2B comparisons, Likert scales, or correlations.
"""


class ChatService:
    """Orchestrates Sonnet + Engine for conversational analysis."""

    def __init__(self):
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY required for chat service")
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def chat(
        self,
        message: str,
        data: SPSSData,
        history: list[dict] | None = None,
        max_tool_rounds: int = 5,
        prep_context: dict | None = None,
    ) -> dict:
        """Process a chat message. Returns {response, charts, downloads, tool_calls}.

        Args:
            message: User's natural language query
            data: Loaded SPSSData from file session
            history: Previous messages [{role, content}] for context
            max_tool_rounds: Max Sonnet→tool→Sonnet loops
            prep_context: User-confirmed data structure {mrs_groups, grid_groups, demographics, weight}
        """
        metadata_context = _build_metadata_context(data)

        # Add prep context if available
        prep_section = ""
        if prep_context:
            lines = ["\n\nUSER-CONFIRMED DATA STRUCTURE:"]
            mrs = prep_context.get("mrs_groups", [])
            if mrs:
                lines.append(f"\nMRS Groups ({len(mrs)} — treat each as a single multi-response question, NOT individual variables):")
                for g in mrs:
                    lines.append(f"  - {g.get('name','?')}: {g.get('variables',[])} (% can exceed 100%)")
            grids = prep_context.get("grid_groups", [])
            if grids:
                lines.append(f"\nGrid Batteries ({len(grids)} — same scale, analyze as battery/summary table):")
                for g in grids:
                    lines.append(f"  - {g.get('name','?')}: {g.get('variables',[])}")
            demos = prep_context.get("demographics", [])
            if demos:
                lines.append(f"\nDemographics (use as banners/cross-tab columns): {demos}")
            wt = prep_context.get("weight")
            if wt:
                lines.append(f"\nWeight variable: {wt} (apply to all analyses unless user says otherwise)")
            study_ctx = prep_context.get("study_context")
            if study_ctx:
                lines.append(f"\n\nSTUDY BRIEF / OBJECTIVES (provided by user — use this to guide your analysis, prioritize relevant variables, and contextualize findings):\n{study_ctx}")
            prep_section = "\n".join(lines)

        system = SYSTEM_PROMPT + f"\n\nDATASET CONTEXT:\n{metadata_context}{prep_section}"

        # Build messages
        messages = []
        if history:
            for h in history[-10:]:  # Keep last 10 exchanges for context
                messages.append(h)
        messages.append({"role": "user", "content": message})

        charts = []
        downloads = []
        tool_calls_log = []

        # Sonnet tool-use loop
        for round_num in range(max_tool_rounds):
            response = await self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=system,
                tools=ANALYSIS_TOOLS,
                messages=messages,
            )

            # Collect text blocks and tool use blocks
            text_parts = []
            tool_uses = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            # If no tool calls, we're done
            if not tool_uses:
                break

            # Execute all tool calls
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_input = tool_use.input

                logger.info("Chat tool call: %s(%s)", tool_name, json.dumps(tool_input)[:200])
                tool_calls_log.append({"tool": tool_name, "input": tool_input})

                if tool_name == "show_chart":
                    charts.append(tool_input)
                    result_content = json.dumps({"rendered": True})
                else:
                    result = await _execute_tool(tool_name, tool_input, data)
                    if "download_url" in result:
                        downloads.append(result["download_url"])
                    result_content = json.dumps(result, default=str)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_content[:50000],  # Cap at 50K to avoid context overflow
                })

            messages.append({"role": "user", "content": tool_results})

        # Final text response
        final_text = ""
        if response.stop_reason == "end_turn":
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
        elif text_parts:
            final_text = "\n".join(text_parts)

        return {
            "response": final_text,
            "charts": charts,
            "downloads": downloads,
            "tool_calls": tool_calls_log,
            "model": "claude-sonnet-4-20250514",
            "rounds": round_num + 1 if 'round_num' in dir() else 1,
        }
