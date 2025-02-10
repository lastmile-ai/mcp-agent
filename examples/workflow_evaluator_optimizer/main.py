import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)
from rich import print

# To illustrate an evaluator-optimizer workflow, we will build a job cover letter refinement system,
# which generates a draft based on job description, company information, and candidate details.
# Then the evaluator reviews the letter, provides a quality rating, and offers actionable feedback.
# The cycle continues until the letter meets a predefined quality standard.
app = MCPApp(name="cover_letter_writer")


async def example_usage():
    async with app.run() as cover_letter_app:
        context = cover_letter_app.context
        logger = cover_letter_app.logger

        logger.info("Current config:", data=context.config.model_dump())

        optimizer = Agent(
            name="optimizer",
            instruction="""You are a career coach specializing in cover letter writing.
            You are tasked with generating a compelling cover letter given the job posting,
            candidate details, and company information. Tailor the response to the company and job requirements.
            """,
            server_names=["fetch"],
        )

        evaluator = Agent(
            name="evaluator",
            instruction="""Evaluate the following response based on the criteria below:
            1. Clarity: Is the language clear, concise, and grammatically correct?
            2. Specificity: Does the response include relevant and concrete details tailored to the job description?
            3. Relevance: Does the response align with the prompt and avoid unnecessary information?
            4. Tone and Style: Is the tone professional and appropriate for the context?
            5. Persuasiveness: Does the response effectively highlight the candidate's value?
            6. Grammar and Mechanics: Are there any spelling or grammatical issues?
            7. Feedback Alignment: Has the response addressed feedback from previous iterations?

            For each criterion:
            - Provide a rating (EXCELLENT, GOOD, FAIR, or POOR).
            - Offer specific feedback or suggestions for improvement.

            Summarize your evaluation as a structured response with:
            - Overall quality rating.
            - Specific feedback and areas for improvement.""",
        )

        evaluator_optimizer = EvaluatorOptimizerLLM(
            optimizer=optimizer,
            evaluator=evaluator,
            llm_factory=OpenAIAugmentedLLM,
            min_rating=QualityRating.EXCELLENT,
        )

        job_posting = (
            "Software Engineer at LastMile AI. Responsibilities include developing AI systems, "
            "collaborating with cross-functional teams, and enhancing scalability. Skills required: "
            "Python, distributed systems, and machine learning."
        )
        candidate_details = (
            "Alex Johnson, 3 years in machine learning, contributor to open-source AI projects, "
            "proficient in Python and TensorFlow. Motivated by building scalable AI systems to solve real-world problems."
        )

        # This should trigger a 'fetch' call to get the company information
        company_information = (
            "Look up from the LastMile AI About page: https://lastmileai.dev/about"
        )

        result = await evaluator_optimizer.generate_str(
            message=f"Write a cover letter for the following job posting: {job_posting}\n\nCandidate Details: {candidate_details}\n\nCompany information: {company_information}",
            request_params=RequestParams(model="gpt-4o"),
        )

        logger.info(f"{result}")


if __name__ == "__main__":
    import time

    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
