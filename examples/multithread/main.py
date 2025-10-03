import argparse
import asyncio
import concurrent.futures
import logging
import traceback

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

logger = logging.getLogger(__name__)


async def run() -> str:
    app = MCPApp(name="script_generation_fewshot_eval")
    async with app.run():
        optimizer = Agent(
            name="optimizer",
            instruction="""You are an expert script writer and optimizer. Your task is to generate a script based on the provided message.
            The story must adhere to the following rules:
            1. The story must be at least 100 words long.
            2. The story can be no longer than 150 words.
            """,
            server_names=[],
        )
        evaluator = Agent(
            name="evaluator",
            instruction="""Evaluate the script based on the following criteria:
            [Criteria]: Script Length (target is no less than 100 words and no more than 150 words)
            [Coherence]: The script should be coherent and follow a logical structure.
            [Creativity]: The script should be creative and engaging.
            For each criterion,
            - Provide a rating (EXCELLENT, GOOD, FAIR, or POOR)
            - Offer specific feedback or suggestions for improvement.

            Summarize your evaluation as a structured response with:
            - Overall quality rating
            - Specific feedback and areas for improvement.
            - Include concrete feedback about script length expressed in number of words. This is very important!
            """,
            server_names=["word_count"],
        )

        evaluator_optimizer = EvaluatorOptimizerLLM(
            optimizer=optimizer,
            evaluator=evaluator,
            llm_factory=OpenAIAugmentedLLM,
            min_rating=QualityRating.GOOD,
        )

        result = await evaluator_optimizer.generate_str(
            """
            Please write a story about a goblin that is a master of disguise.
            The goblin should be able to change its appearance and behavior to blend in with different environments and situations
            """,
            request_params=RequestParams(maxTokens=16384, max_iterations=3),
        )

        return result


def generate_step():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run())
        return result
    except Exception as e:
        logger.exception("Error during script generation", exc_info=e)
        return ""
    finally:
        # Close the loop
        loop.close()
        asyncio.set_event_loop(None)


def main(concurrency: int) -> list[str]:
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(generate_step): idx for idx in range(concurrency)}
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                print(f"[Thread {idx}] Result: {result}\n\n")
                results.append(result)
            except Exception as e:
                print(f"[Thread {idx}] Generated an exception: {e}")
                traceback.print_exc()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--concurrency", type=int, default=2, help="Number of concurrent requests"
    )

    args = parser.parse_args()

    results = main(args.concurrency)

    print("\n\n---\n\n")
    for idx, result in enumerate(results):
        print(f"Result {idx}: {result}\n")
