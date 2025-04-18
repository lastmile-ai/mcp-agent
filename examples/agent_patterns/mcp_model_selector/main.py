import asyncio

from mcp.types import ModelHint, ModelPreferences

from mcp_agent.app import MCPApp
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.llm_selector import ModelSelector
from rich import print

app = MCPApp(name="llm_selector")


async def example_usage(model_selector: ModelSelector):
    logger = get_logger("llm_selector.example_usage")

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


if __name__ == "__main__":
    import time

    async def main():
        try:
            await app.initialize()

            # Load model selector
            start = time.time()
            model_selector = ModelSelector()
            end = time.time()
            model_selector_setup_time = end - start

            print(f"Loaded model selector: {model_selector_setup_time:.5f}s")

            start = time.time()
            await example_usage(model_selector)
            end = time.time()
            model_selector_usage_time = end - start

            print(f"ModelSelector usage time: {model_selector_usage_time:.5f}s")
        finally:
            await app.cleanup()

    asyncio.run(main())
