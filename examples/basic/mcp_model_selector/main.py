import asyncio

from mcp.types import ModelHint, ModelPreferences

from mcp_agent.app import MCPApp
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.llm_selector import ModelSelector
from rich import print

app = MCPApp(name="llm_selector")
model_selector = ModelSelector()


@app.tool
async def example_usage() -> str:
    """
    An example function/tool that demonstrates MCP's ModelPreferences type
    to select a model based on speed, cost, and intelligence priorities.
    """
    logger = get_logger("llm_selector.example_usage")
    result = ""

    # Select the smartest OpenAI model:
    model_preferences = ModelPreferences(
        costPriority=0, speedPriority=0, intelligencePriority=1.0
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences,
        provider="OpenAI",
    )
    logger.info(
        "Smartest OpenAI model:",
        data={"model_preferences": model_preferences, "model": model},
    )
    result += "Smartest OpenAI model: " + model.name

    model_preferences = ModelPreferences(
        costPriority=0.25, speedPriority=0.25, intelligencePriority=0.5
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences,
        provider="OpenAI",
    )
    logger.info(
        "Most balanced OpenAI model:",
        data={"model_preferences": model_preferences, "model": model},
    )
    result += "\nMost balanced OpenAI model: " + model.name

    model_preferences = ModelPreferences(
        costPriority=0.3, speedPriority=0.6, intelligencePriority=0.1
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences,
        provider="OpenAI",
    )
    logger.info(
        "Fastest and cheapest OpenAI model:",
        data={"model_preferences": model_preferences, "model": model},
    )
    result += "\nFastest and cheapest OpenAI model: " + model.name

    model_preferences = ModelPreferences(
        costPriority=0.1, speedPriority=0.1, intelligencePriority=0.8
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences,
        provider="Anthropic",
    )
    logger.info(
        "Smartest Anthropic model:",
        data={"model_preferences": model_preferences, "model": model},
    )
    result += "\nSmartest Anthropic model: " + model.name

    model_preferences = ModelPreferences(
        costPriority=0.8, speedPriority=0.1, intelligencePriority=0.1
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences,
        provider="Anthropic",
    )
    logger.info(
        "Cheapest Anthropic model:",
        data={"model_preferences": model_preferences, "model": model},
    )
    result += "\nCheapest Anthropic model: " + model.name

    model_preferences = ModelPreferences(
        costPriority=0.1,
        speedPriority=0.8,
        intelligencePriority=0.1,
        hints=[
            ModelHint(name="gpt-4o"),
            ModelHint(name="gpt-4o-mini"),
            ModelHint(name="claude-3.5-sonnet"),
            ModelHint(name="claude-3-haiku"),
        ],
    )
    model = model_selector.select_best_model(model_preferences=model_preferences)
    logger.info(
        "Select fastest model between gpt-4o/mini/sonnet/haiku:",
        data={"model_preferences": model_preferences, "model": model},
    )
    result += "\nSelect fastest model between gpt-4o/mini/sonnet/haiku: " + model.name

    model_preferences = ModelPreferences(
        costPriority=0.15,
        speedPriority=0.15,
        intelligencePriority=0.7,
        hints=[
            ModelHint(name="gpt-4o"),
            ModelHint(name="gpt-4o-mini"),
            ModelHint(name="claude-sonnet"),  # Fuzzy name matching
            ModelHint(name="claude-haiku"),  # Fuzzy name matching
        ],
    )
    model = model_selector.select_best_model(model_preferences=model_preferences)
    logger.info(
        "Most balanced model between gpt-4o/mini/sonnet/haiku:",
        data={"model_preferences": model_preferences, "model": model},
    )
    result += "\nMost balanced model between gpt-4o/mini/sonnet/haiku: " + model.name

    # Examples showcasing new filtering capabilities
    print("\n[bold cyan]Testing new filtering capabilities:[/bold cyan]")

    # Example 1: Models with large context windows (> 100k tokens)
    model_preferences = ModelPreferences(
        costPriority=0.2, speedPriority=0.3, intelligencePriority=0.5
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences, min_tokens=100000
    )
    logger.info(
        "Best model with context window > 100k tokens:",
        data={
            "model_preferences": model_preferences,
            "model": model,
            "context_window": model.context_window,
        },
    )
    result += "\nBest model with context window >100k tokens: " + model.name

    # Example 2: Models with tool calling support
    model_preferences = ModelPreferences(
        costPriority=0.3, speedPriority=0.3, intelligencePriority=0.4
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences, tool_calling=True
    )
    logger.info(
        "Best model with tool calling support:",
        data={
            "model_preferences": model_preferences,
            "model": model,
            "tool_calling": model.tool_calling,
        },
    )
    result += "\nBest model with tool calling support: " + model.name

    # Example 3: Models with structured outputs (JSON mode)
    model_preferences = ModelPreferences(
        costPriority=0.4, speedPriority=0.3, intelligencePriority=0.3
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences, structured_outputs=True
    )
    logger.info(
        "Best model with structured outputs support:",
        data={
            "model_preferences": model_preferences,
            "model": model,
            "structured_outputs": model.structured_outputs,
        },
    )
    result += "\nBest model with structured outputs support: " + model.name

    # Example 4: Models with medium context window (50k-150k tokens) and tool calling
    model_preferences = ModelPreferences(
        costPriority=0.25, speedPriority=0.25, intelligencePriority=0.5
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences,
        min_tokens=50000,
        max_tokens=150000,
        tool_calling=True,
    )
    logger.info(
        "Best model with 50k-150k context window and tool calling:",
        data={
            "model_preferences": model_preferences,
            "model": model,
            "context_window": model.context_window,
            "tool_calling": model.tool_calling,
        },
    )
    result += (
        "\nBest model with 50k-150k context window and tool calling: " + model.name
    )

    # Example 5: Fast models with both tool calling and structured outputs
    model_preferences = ModelPreferences(
        costPriority=0.2, speedPriority=0.7, intelligencePriority=0.1
    )
    model = model_selector.select_best_model(
        model_preferences=model_preferences, tool_calling=True, structured_outputs=True
    )
    logger.info(
        "Fastest model with both tool calling and structured outputs:",
        data={
            "model_preferences": model_preferences,
            "model": model,
            "tool_calling": model.tool_calling,
            "structured_outputs": model.structured_outputs,
            "speed": model.metrics.speed.tokens_per_second,
        },
    )
    result += (
        "\nFastest model with both tool calling and structured outputs: " + model.name
    )

    return result


if __name__ == "__main__":
    import time

    async def main():
        try:
            await app.initialize()

            start = time.time()
            await example_usage()
            end = time.time()
            model_selector_usage_time = end - start

            print(f"ModelSelector usage time: {model_selector_usage_time:.5f}s")
        finally:
            await app.cleanup()

    asyncio.run(main())
