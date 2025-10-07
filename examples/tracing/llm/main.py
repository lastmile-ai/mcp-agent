import asyncio
import time
from typing import Dict

from pydantic import BaseModel

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_anthropic import MessageParam
from mcp_agent.workflows.llm.augmented_llm_azure import AzureAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


# Settings loaded from mcp_agent.config.yaml/mcp_agent.secrets.yaml
app = MCPApp(name="llm_tracing_example")


class CountryRecord(BaseModel):
    """Single country's structured data."""

    capital: str
    population: int


class CountryInfo(BaseModel):
    """Structured response containing multiple countries."""

    countries: Dict[str, CountryRecord]

    def summary(self) -> str:
        return ", ".join(
            f"{country}: {info.capital} (pop {info.population:,})"
            for country, info in self.countries.items()
        )


async def llm_tracing():
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Current config:", data=context.config.model_dump())

        async def _trace_openai():
            # Direct LLM usage (OpenAI)
            openai_llm = OpenAIAugmentedLLM(
                name="openai_llm",
                default_request_params=RequestParams(maxTokens=1024),
            )

            result = await openai_llm.generate(
                message="What is the capital of France?",
            )
            logger.info(f"openai_llm result: {result}")

            await openai_llm.select_model(RequestParams(model="gpt-4"))
            result_str = await openai_llm.generate_str(
                message="What is the capital of Belgium?",
            )
            logger.info(f"openai_llm result: {result_str}")

            result_structured = await openai_llm.generate_structured(
                MessageParam(
                    role="user",
                    content=(
                        "Return JSON under a top-level `countries` object. "
                        "Within `countries`, each key should be the country name (France, Ireland, Italy) "
                        "with values containing `capital` and `population`."
                    ),
                ),
                response_model=CountryInfo,
            )
            logger.info(
                "openai_llm structured result",
                data=result_structured.model_dump(mode="json"),
            )

        async def _trace_anthropic():
            # Agent-integrated LLM (Anthropic)
            llm_agent = Agent(name="llm_agent")
            async with llm_agent:
                llm = await llm_agent.attach_llm(AnthropicAugmentedLLM)
                result = await llm.generate("What is the capital of Germany?")
                logger.info(f"llm_agent result: {result}")

                result_str = await llm.generate_str(
                    message="What is the capital of Italy?",
                )
                logger.info(f"llm_agent result: {result_str}")

                result_structured = await llm.generate_structured(
                    MessageParam(
                        role="user",
                        content=(
                            "Return JSON under a top-level `countries` object. "
                            "Within `countries`, each key should be the country name (France, Germany, Belgium) "
                            "with values containing `capital` and `population`."
                        ),
                    ),
                    response_model=CountryInfo,
                )
                logger.info(
                    "llm_agent structured result",
                    data=result_structured.model_dump(mode="json"),
                )

        async def _trace_azure():
            # Azure
            azure_llm = AzureAugmentedLLM(name="azure_llm")
            result = await azure_llm.generate("What is the capital of Spain?")
            logger.info(f"azure_llm result: {result}")

            result_str = await azure_llm.generate_str(
                message="What is the capital of Portugal?",
            )
            logger.info(f"azure_llm result: {result_str}")

            result_structured = await azure_llm.generate_structured(
                MessageParam(
                    role="user",
                    content=(
                        "Return JSON under a top-level `countries` object. "
                        "Within `countries`, each key should be the country name (Spain, Portugal, Italy) "
                        "with values containing `capital` and `population`."
                    ),
                ),
                response_model=CountryInfo,
            )
            logger.info(
                "azure_llm structured result",
                data=result_structured.model_dump(mode="json"),
            )

        await asyncio.gather(
            _trace_openai(),
            _trace_anthropic(),
            # _trace_azure(),
        )
        logger.info("All LLM tracing completed.")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(llm_tracing())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
