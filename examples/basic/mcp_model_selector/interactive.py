import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.prompt import FloatPrompt, Prompt
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from mcp.types import ModelPreferences
from mcp_agent.app import MCPApp
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.llm_selector import ModelInfo, ModelSelector

app = MCPApp(name="llm_selector")
console = Console()


async def get_valid_float_input(
    prompt_text: str, min_val: float = 0.0, max_val: float = 1.0
) -> Optional[float]:
    while True:
        try:
            value = FloatPrompt.ask(
                prompt_text, console=console, default=None, show_default=False
            )
            if value is None:
                return None
            if min_val <= value <= max_val:
                return value
            console.print(
                f"[red]Please enter a value between {min_val} and {max_val}[/red]"
            )
        except (ValueError, TypeError):
            return None


def create_preferences_table(
    cost: float,
    speed: float,
    intelligence: float,
    provider: str,
    min_tokens: Optional[int] = None,
    max_tokens: Optional[int] = None,
    tool_calling: Optional[bool] = None,
    structured_outputs: Optional[bool] = None,
) -> Table:
    table = Table(
        title="Current Preferences", show_header=True, header_style="bold magenta"
    )
    table.add_column("Priority", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Cost", f"{cost:.2f}")
    table.add_row("Speed", f"{speed:.2f}")
    table.add_row("Intelligence", f"{intelligence:.2f}")
    table.add_row("Provider", provider)

    if min_tokens is not None:
        table.add_row("Min Context Tokens", f"{min_tokens:,}")
    if max_tokens is not None:
        table.add_row("Max Context Tokens", f"{max_tokens:,}")
    if tool_calling is not None:
        table.add_row("Tool Calling", "Required" if tool_calling else "Not Required")
    if structured_outputs is not None:
        table.add_row(
            "Structured Outputs", "Required" if structured_outputs else "Not Required"
        )

    return table


async def display_model_result(model: ModelInfo, preferences: dict, provider: str):
    result_table = Table(show_header=True, header_style="bold blue")
    result_table.add_column("Parameter", style="cyan")
    result_table.add_column("Value", style="green")

    result_table.add_row("Model Name", model.name)
    result_table.add_row("Description", model.description or "N/A")
    result_table.add_row("Provider", model.provider)

    # Display new model properties
    if model.context_window is not None:
        result_table.add_row("Context Window", f"{model.context_window:,} tokens")
    if model.tool_calling is not None:
        result_table.add_row("Tool Calling", "✓" if model.tool_calling else "✗")
    if model.structured_outputs is not None:
        result_table.add_row(
            "Structured Outputs", "✓" if model.structured_outputs else "✗"
        )

    # Display metrics
    if model.metrics.cost.blended_cost_per_1m:
        result_table.add_row(
            "Cost (per 1M tokens)", f"${model.metrics.cost.blended_cost_per_1m:.2f}"
        )
    result_table.add_row(
        "Speed (tokens/sec)", f"{model.metrics.speed.tokens_per_second:.1f}"
    )
    if model.metrics.intelligence.quality_score:
        result_table.add_row(
            "Quality Score", f"{model.metrics.intelligence.quality_score:.1f}"
        )

    console.print(
        Panel(
            result_table,
            title="[bold green]Model Selection Result",
            border_style="green",
        )
    )


async def interactive_model_selection(model_selector: ModelSelector):
    logger = get_logger("llm_selector.interactive")
    providers = [
        "All",
        "AI21 Labs",
        "Amazon Bedrock",
        "Anthropic",
        "Cerebras",
        "Cohere",
        "Databricks",
        "DeepSeek",
        "Deepinfra",
        "Fireworks",
        "FriendliAI",
        "Google AI Studio",
        "Google Vertex",
        "Groq",
        "Hyperbolic",
        "Microsoft Azure",
        "Mistral",
        "Nebius",
        "Novita",
        "OpenAI",
        "Perplexity",
        "Replicate",
        "SambaNova",
        "Together.ai",
        "xAI",
    ]

    while True:
        console.clear()
        rprint("[bold blue]=== Model Selection Interface ===[/bold blue]")
        rprint("[yellow]Enter values between 0.0 and 1.0 for each priority[/yellow]")
        rprint("[yellow]Press Enter without input to exit[/yellow]\n")

        # Get priorities
        cost_priority = await get_valid_float_input("Cost Priority (0-1)")
        if cost_priority is None:
            break

        speed_priority = await get_valid_float_input("Speed Priority (0-1)")
        if speed_priority is None:
            break

        intelligence_priority = await get_valid_float_input(
            "Intelligence Priority (0-1)"
        )
        if intelligence_priority is None:
            break

        # Get additional filtering criteria
        console.print(
            "\n[bold cyan]Additional Filters (press Enter to skip):[/bold cyan]"
        )

        # Context window filters
        min_tokens = None
        min_tokens_input = Prompt.ask(
            "Minimum context window size (tokens)", default=""
        )
        if min_tokens_input:
            min_tokens = int(min_tokens_input)

        max_tokens = None
        max_tokens_input = Prompt.ask(
            "Maximum context window size (tokens)", default=""
        )
        if max_tokens_input:
            max_tokens = int(max_tokens_input)

        # Tool calling filter
        tool_calling = None
        tool_calling_input = Prompt.ask("Require tool calling? (y/n)", default="")
        if tool_calling_input.lower() in ["y", "yes"]:
            tool_calling = True
        elif tool_calling_input.lower() in ["n", "no"]:
            tool_calling = False

        # Structured outputs filter
        structured_outputs = None
        structured_outputs_input = Prompt.ask(
            "Require structured outputs? (y/n)", default=""
        )
        if structured_outputs_input.lower() in ["y", "yes"]:
            structured_outputs = True
        elif structured_outputs_input.lower() in ["n", "no"]:
            structured_outputs = False

        # Provider selection
        console.print("\n[bold cyan]Available Providers:[/bold cyan]")
        for i, provider in enumerate(providers, 1):
            console.print(f"{i}. {provider}")

        provider_choice = Prompt.ask("\nSelect provider", default="1")

        selected_provider = providers[int(provider_choice) - 1]

        # Display current preferences
        preferences_table = create_preferences_table(
            cost_priority,
            speed_priority,
            intelligence_priority,
            selected_provider,
            min_tokens,
            max_tokens,
            tool_calling,
            structured_outputs,
        )
        console.print(preferences_table)

        # Create model preferences
        model_preferences = ModelPreferences(
            costPriority=cost_priority,
            speedPriority=speed_priority,
            intelligencePriority=intelligence_priority,
        )

        # Select model with progress spinner
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Selecting best model...", total=None)

            try:
                if selected_provider == "All":
                    model = model_selector.select_best_model(
                        model_preferences=model_preferences,
                        min_tokens=min_tokens,
                        max_tokens=max_tokens,
                        tool_calling=tool_calling,
                        structured_outputs=structured_outputs,
                    )
                else:
                    model = model_selector.select_best_model(
                        model_preferences=model_preferences,
                        provider=selected_provider,
                        min_tokens=min_tokens,
                        max_tokens=max_tokens,
                        tool_calling=tool_calling,
                        structured_outputs=structured_outputs,
                    )

                # Display result
                await display_model_result(
                    model,
                    {
                        "cost": cost_priority,
                        "speed": speed_priority,
                        "intelligence": intelligence_priority,
                    },
                    selected_provider,
                )

                logger.info(
                    "Interactive model selection result:",
                    data={
                        "model_preferences": model_preferences,
                        "provider": selected_provider,
                        "model": model,
                    },
                )

            except Exception as e:
                console.print(f"\n[red]Error selecting model: {str(e)}[/red]")
                logger.error("Error in model selection", exc_info=e)

        if not Prompt.ask("\nContinue?", choices=["y", "n"], default="y") == "y":
            break


def main():
    async def run():
        try:
            await app.initialize()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    description="Loading model selector...", total=None
                )
                model_selector = ModelSelector()
                progress.update(task, description="Model selector loaded!")

            await interactive_model_selection(model_selector)

        finally:
            await app.cleanup()

    typer.run(lambda: asyncio.run(run()))


if __name__ == "__main__":
    main()
