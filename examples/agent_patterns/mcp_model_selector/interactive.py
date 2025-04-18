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
    cost: float, speed: float, intelligence: float, provider: str
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

    return table


async def display_model_result(model: ModelInfo, preferences: dict, provider: str):
    result_table = Table(show_header=True, header_style="bold blue")
    result_table.add_column("Parameter", style="cyan")
    result_table.add_column("Value", style="green")

    result_table.add_row(
        "Selected Model", model.model_dump_json(indent=2, exclude_none=True)
    )
    result_table.add_row("Provider", provider)
    result_table.add_row("Cost Priority", f"{preferences['cost']:.2f}")
    result_table.add_row("Speed Priority", f"{preferences['speed']:.2f}")
    result_table.add_row("Intelligence Priority", f"{preferences['intelligence']:.2f}")

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

        # Provider selection
        console.print("\n[bold cyan]Available Providers:[/bold cyan]")
        for i, provider in enumerate(providers, 1):
            console.print(f"{i}. {provider}")

        provider_choice = Prompt.ask("\nSelect provider", default="1")

        selected_provider = providers[int(provider_choice) - 1]

        # Display current preferences
        preferences_table = create_preferences_table(
            cost_priority, speed_priority, intelligence_priority, selected_provider
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
                        model_preferences=model_preferences
                    )
                else:
                    model = model_selector.select_best_model(
                        model_preferences=model_preferences, provider=selected_provider
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
