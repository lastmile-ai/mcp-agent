# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "beautifulsoup4",
#     "pydantic",
#     "rich",
#     "typer",
# ]
# ///

import locale
import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field
import json
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import track
from pathlib import Path

locale.setlocale(locale.LC_ALL, "en_US.UTF-8")

app = typer.Typer()
console = Console()


class ModelBenchmarks(BaseModel):
    """
    Performance benchmarks for comparing different models.
    """

    __pydantic_extra__: dict[str, float] = Field(
        init=False
    )  # Enforces that extra fields are floats

    quality_score: float | None = None
    """A blended quality score for the model."""

    mmlu_score: float | None = None
    gsm8k_score: float | None = None
    bbh_score: float | None = None

    model_config = ConfigDict(extra="allow")


class ModelLatency(BaseModel):
    """
    Latency benchmarks for comparing different models.
    """

    time_to_first_token_ms: float = Field(gt=0)
    """ 
    Median Time to first token in milliseconds.
    """

    tokens_per_second: float = Field(gt=0)
    """
    Median output tokens per second.
    """


class ModelCost(BaseModel):
    """
    Cost benchmarks for comparing different models.
    """

    blended_cost_per_1m: float | None = None
    """
    Blended cost mixing input/output cost per 1M tokens.
    """

    input_cost_per_1m: float | None = None
    """
    Cost per 1M input tokens.
    """

    output_cost_per_1m: float | None = None
    """
    Cost per 1M output tokens.
    """

    model_config = ConfigDict(extra="allow")


class ModelMetrics(BaseModel):
    """
    Model metrics for comparing different models.
    """

    cost: ModelCost
    speed: ModelLatency
    intelligence: ModelBenchmarks


class ModelInfo(BaseModel):
    name: str
    description: str | None = None
    provider: str
    context_window: int | None = None
    tool_calling: bool | None = None
    structured_outputs: bool | None = None
    metrics: ModelMetrics

    model_config = ConfigDict(extra="allow")


def parse_context_window(context_str: str) -> int | None:
    """Parse context window strings like '131k', '1m', '128000' to integers."""
    if not context_str:
        return None

    context_str = context_str.strip().lower()
    try:
        # Handle k suffix (thousands)
        if context_str.endswith("k"):
            return int(float(context_str[:-1]) * 1000)
        # Handle m suffix (millions)
        elif context_str.endswith("m"):
            return int(float(context_str[:-1]) * 1000000)
        # Handle plain numbers
        else:
            return int(context_str.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_html_to_models(html_content: str) -> list[ModelInfo]:
    """
    Robustly parse Artificial Analysis model listings.

    Strategy:
    1) First, try to extract embedded JSON objects that the site now renders. These
       contain rich fields like provider, pricing, speed, and latency.
    2) If that fails, fall back to the legacy table-based parser.
    """

    def extract_json_object(text: str, start_index: int) -> tuple[Optional[str], int]:
        """Extract a balanced JSON object starting at text[start_index] == '{'.

        Returns (json_string, end_index_after_object) or (None, start_index + 1) if
        no valid object could be parsed.
        """
        if start_index < 0 or start_index >= len(text) or text[start_index] != "{":
            return None, start_index + 1

        brace_count = 0
        in_string = False
        escape = False
        i = start_index
        while i < len(text):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        # Include this closing brace
                        return text[start_index : i + 1], i + 1
            i += 1

        return None, start_index + 1

    def coalesce_bool(*values: Optional[bool | None]) -> Optional[bool]:
        for v in values:
            if isinstance(v, bool):
                return v
        return None

    def normalize_name_from_slug_or_id(
        slug: Optional[str], host_api_id: Optional[str], fallback: str
    ) -> str:
        # Prefer host_api_id if present
        candidate = host_api_id or slug or fallback
        if not candidate:
            return fallback
        # If looks like a path, take the basename
        if "/" in candidate:
            candidate = candidate.rsplit("/", 1)[-1]
        return str(candidate)

    def try_parse_from_embedded_json(text: str) -> list[ModelInfo]:
        models_from_json: list[ModelInfo] = []

        # Heuristic: the rich objects begin with '{"id":"' and include both
        # '"host":{' and '"model":{' blocks.
        for match in re.finditer(r"\{\s*\"id\"\s*:\s*\"", text):
            start = match.start()
            json_str, _end_pos = extract_json_object(text, start)
            if not json_str:
                continue

            # Quick filter before json.loads to avoid obvious mismatches
            if ('"host":' not in json_str) or ('"model":' not in json_str):
                continue

            try:
                data = json.loads(json_str)
            except Exception:
                continue

            # Validate minimal shape we care about
            # We expect fields at top-level like name, host_label, prices, timescaleData
            name = data.get("name") or ((data.get("model") or {}).get("name"))
            host_label = data.get("host_label") or (
                (data.get("host") or {}).get("short_name")
                or (data.get("host") or {}).get("name")
            )
            if not name or not host_label:
                continue

            # Identify API ID / slug and normalize to a usable name
            api_id_raw = (
                data.get("slug")
                or (data.get("model") or {}).get("slug")
                or name.lower().replace(" ", "-").replace("(", "").replace(")", "")
            )
            host_api_id = data.get("host_api_id")
            api_id = normalize_name_from_slug_or_id(api_id_raw, host_api_id, name)

            # Context window
            context_window = data.get("context_window_tokens") or (
                data.get("model") or {}
            ).get("context_window_tokens")
            if not context_window:
                # Try formatted fields like "33k" if tokens are missing
                formatted = data.get("context_window_formatted") or (
                    data.get("model") or {}
                ).get("contextWindowFormatted")
                context_window = parse_context_window(formatted) if formatted else None

            # Tool calling / JSON mode from various levels
            tool_calling = coalesce_bool(
                data.get("function_calling"),
                (data.get("host") or {}).get("function_calling"),
                (data.get("model") or {}).get("function_calling"),
            )
            structured_outputs = coalesce_bool(
                data.get("json_mode"),
                (data.get("host") or {}).get("json_mode"),
                (data.get("model") or {}).get("json_mode"),
            )

            # Pricing
            blended_cost = data.get("price_1m_blended_3_to_1")
            input_cost = data.get("price_1m_input_tokens")
            output_cost = data.get("price_1m_output_tokens")

            # Speed/latency
            timescale = data.get("timescaleData") or {}
            tokens_per_second = timescale.get("median_output_speed") or 0.0
            first_chunk_seconds = timescale.get("median_time_to_first_chunk") or 0.0
            # Ensure positive to satisfy validation
            if not tokens_per_second or tokens_per_second <= 0:
                tokens_per_second = 0.1
            if not first_chunk_seconds or first_chunk_seconds <= 0:
                first_chunk_seconds = 0.001

            # Intelligence/quality
            # Prefer estimated_intelligence_index if present, fallback to intelligence_index
            quality_score = (
                (data.get("model") or {}).get("estimated_intelligence_index")
                or (data.get("model") or {}).get("intelligence_index")
                or data.get("estimated_intelligence_index")
                or data.get("intelligence_index")
            )

            model_info = ModelInfo(
                name=str(api_id),
                description=str(name),
                provider=str(host_label),
                context_window=int(context_window) if context_window else None,
                tool_calling=tool_calling,
                structured_outputs=structured_outputs,
                metrics=ModelMetrics(
                    cost=ModelCost(
                        blended_cost_per_1m=blended_cost,
                        input_cost_per_1m=input_cost,
                        output_cost_per_1m=output_cost,
                    ),
                    speed=ModelLatency(
                        time_to_first_token_ms=float(first_chunk_seconds) * 1000.0,
                        tokens_per_second=float(tokens_per_second),
                    ),
                    intelligence=ModelBenchmarks(
                        quality_score=float(quality_score) if quality_score else None
                    ),
                ),
            )

            models_from_json.append(model_info)

        return models_from_json

    # 1) Try embedded JSON pathway first
    json_models = try_parse_from_embedded_json(html_content)
    if json_models:
        console.print(
            f"[bold blue]Parsed {len(json_models)} models from embedded JSON[/bold blue]"
        )

    # 2) Fallback: legacy/new table-based parsing
    soup = BeautifulSoup(html_content, "html.parser")
    models: list[ModelInfo] = []

    headers = [th.get_text(strip=True) for th in soup.find_all("th")]
    console.print(f"[bold blue]Found {len(headers)} headers[/bold blue]")

    # Cell index to header mapping:
    # 0: API Provider
    # 1: Model
    # 2: ContextWindow
    # 3: Function Calling
    # 4: JSON Mode
    # 5: License
    # 6: OpenAI Compatible
    # 7: API ID
    # 8: Footnotes
    # 9: Artificial AnalysisIntelligence Index
    # 10: MMLU-Pro (Reasoning & Knowledge)
    # 11: GPQA Diamond (Scientific Reasoning)
    # 12: Humanity's Last Exam (Reasoning & Knowledge)
    # 13: LiveCodeBench (Coding)
    # 14: SciCode (Coding)
    # 15: HumanEval (Coding)
    # 16: MATH-500 (Quantitative Reasoning)
    # 17: AIME 2024 (Competition Math)
    # 18: Chatbot Arena
    # 19: BlendedUSD/1M Tokens
    # 20: Input PriceUSD/1M Tokens
    # 21: Output PriceUSD/1M Tokens
    # 22: MedianTokens/s
    # 23: P5Tokens/s
    # 24: P25Tokens/s
    # 25: P75Tokens/s
    # 26: P95Tokens/s
    # 27: MedianFirst Chunk (s)
    # 28: First AnswerToken (s)
    # 29: P5First Chunk (s)
    # 30: P25First Chunk (s)
    # 31: P75First Chunk (s)
    # 32: P95First Chunk (s)
    # 33: TotalResponse (s)
    # 34: ReasoningTime (s)
    # 35: FurtherAnalysis

    # Find all table rows
    rows = soup.find_all("tr")

    # Heuristic: skip header-like rows by requiring at least, say, 6 <td> cells
    def is_data_row(tr) -> bool:
        tds = tr.find_all("td")
        return len(tds) >= 6

    rows = [r for r in rows if is_data_row(r)]

    console.print(f"[bold green]Processing {len(rows)} models...[/bold green]")

    def parse_price_tokens_latency(
        cells: list[str],
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        # Identify blended price: first cell containing a '$'
        price = None
        tokens_per_s = None
        latency_s = None
        price_idx = None
        for idx, txt in enumerate(cells):
            if "$" in txt:
                # remove $ and commas
                try:
                    price = float(txt.replace("$", "").replace(",", "").strip())
                    price_idx = idx
                    break
                except Exception:
                    continue
        if price_idx is not None:
            # The next two numeric cells are typically tokens/s and first chunk (s)
            # Be defensive: scan forward for first two parseable floats
            found = []
            for txt in cells[price_idx + 1 : price_idx + 6]:
                try:
                    val = float(txt.replace(",", "").strip())
                    found.append(val)
                except Exception:
                    continue
                if len(found) >= 2:
                    break
            if len(found) >= 2:
                tokens_per_s, latency_s = found[0], found[1]
        return price, tokens_per_s, latency_s

    for row in track(rows, description="Parsing models..."):
        cells_el = row.find_all("td")
        cells = [c.get_text(strip=True) for c in cells_el]
        if not cells:  # Ensure we have enough cells
            continue

        try:
            # Extract provider from first cell's <img alt>
            provider_img = cells_el[0].find("img")
            provider = (
                provider_img["alt"].replace(" logo", "") if provider_img else "Unknown"
            )

            # Extract model display name from second cell
            model_name_elem = cells_el[1].find("span")
            if model_name_elem:
                display_name = model_name_elem.text.strip()
            else:
                display_name = cells[1].strip()

            # Prefer href pointing to the model page to derive a stable slug
            href = None
            link = row.find("a", href=re.compile(r"/models/"))
            if link and link.has_attr("href"):
                href = link["href"]
            api_id = None
            if href:
                # Use the last path segment
                api_id = href.rstrip("/").rsplit("/", 1)[-1]
            if not api_id:
                # Fallback: slugify display name
                api_id = (
                    display_name.lower()
                    .replace(" ", "-")
                    .replace("(", "")
                    .replace(")", "")
                    .replace("/", "-")
                )

            # Extract context window from third cell
            context_window_text = cells[2]
            context_window = parse_context_window(context_window_text)

            # Newer tables often omit explicit tool/json icons in the list view
            tool_calling = None
            structured_outputs = None

            # Extract quality score if present (percentage-like cell anywhere)
            quality_score = None
            for txt in cells:
                if txt.endswith("%"):
                    try:
                        quality_score = float(txt.replace("%", "").strip())
                        break
                    except Exception:
                        pass

            # Extract price, tokens/s, latency with heuristics
            blended_cost, tokens_per_sec, latency_sec = parse_price_tokens_latency(
                cells
            )
            if tokens_per_sec is None:
                tokens_per_sec = 0.1
            if latency_sec is None:
                latency_sec = 0.001

            model_info = ModelInfo(
                name=api_id,
                description=display_name,
                provider=provider,
                context_window=context_window,
                tool_calling=tool_calling,
                structured_outputs=structured_outputs,
                metrics=ModelMetrics(
                    cost=ModelCost(blended_cost_per_1m=blended_cost),
                    speed=ModelLatency(
                        time_to_first_token_ms=float(latency_sec) * 1000.0,
                        tokens_per_second=float(tokens_per_sec),
                    ),
                    intelligence=ModelBenchmarks(quality_score=quality_score),
                ),
            )

            models.append(model_info)

        except Exception as e:
            console.print(f"[red]Error processing row: {e}[/red]")
            console.print(f"[yellow]Row content: {str(row)}[/yellow]")
            continue

    # 3) Merge JSON models (if any) with table models; prefer JSON values and add any missing
    if json_models:
        merged: dict[tuple[str, str], ModelInfo] = {}
        for m in json_models:
            merged[(m.provider.lower(), m.name.lower())] = m
        for m in models:
            key = (m.provider.lower(), m.name.lower())
            if key not in merged:
                merged[key] = m
        return list(merged.values())
    return models


def export_to_json(
    models: list[ModelInfo], output_file: str = "model_benchmarks5.json"
):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump([m.model_dump() for m in models], f, indent=2)


def display_summary(models: list[ModelInfo]):
    """Display a summary table of parsed models."""
    table = Table(title=f"Parsed Models Summary ({len(models)} models)")

    table.add_column("#", style="dim", width=3)
    table.add_column("Provider", style="cyan", no_wrap=True)
    table.add_column("Model", style="magenta", max_width=50)
    table.add_column("Context", justify="right", style="green")
    table.add_column("Tools", justify="center")
    table.add_column("JSON", justify="center")
    table.add_column("Quality", justify="right", style="yellow")
    table.add_column("Cost/1M", justify="right", style="red")
    table.add_column("Speed", justify="right", style="blue")

    for idx, model in enumerate(models, 1):
        # Truncate long model names
        model_name = model.description or model.name
        if len(model_name) > 50:
            model_name = model_name[:47] + "..."

        table.add_row(
            str(idx),
            model.provider,
            model_name,
            f"{model.context_window:,}" if model.context_window else "N/A",
            "✓" if model.tool_calling else "✗" if model.tool_calling is False else "?",
            "✓"
            if model.structured_outputs
            else "✗"
            if model.structured_outputs is False
            else "?",
            f"{model.metrics.intelligence.quality_score:.1f}%"
            if model.metrics.intelligence.quality_score
            else "N/A",
            f"${model.metrics.cost.blended_cost_per_1m:.2f}"
            if model.metrics.cost.blended_cost_per_1m
            else "N/A",
            f"{model.metrics.speed.tokens_per_second:.0f} t/s"
            if model.metrics.speed.tokens_per_second
            else "N/A",
        )

    console.print(table)


@app.command()
def main(
    input_file: Path = typer.Argument(
        ...,
        help="Path to the HTML file containing the benchmark table",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    output_file: Path = typer.Argument(
        "src/mcp_agent/data/artificial_analysis_llm_benchmarks.json",
        help="Path to the output JSON file",
        resolve_path=True,
    ),
):
    """
    Parse LLM benchmark HTML tables from Artificial Analysis and convert to JSON.
    """
    console.print(f"[bold]Reading HTML from:[/bold] {input_file}")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            html_content = f.read()

        models = parse_html_to_models(html_content)

        if not models:
            console.print("[red]No models found in the HTML file![/red]")
            raise typer.Exit(1)

        console.print(
            f"\n[bold green]Successfully parsed {len(models)} models![/bold green]\n"
        )

        display_summary(models)

        export_to_json(models, str(output_file))
        console.print(f"\n[bold]Output saved to:[/bold] {output_file}")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
