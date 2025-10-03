"""
Example of using Temporal as the execution engine for MCP Agent workflows.
This example demonstrates how to create a workflow using the app.workflow and app.workflow_run
decorators, and how to run it using the Temporal executor.
"""

import asyncio

from mcp_agent.agents.agent import Agent
from mcp_agent.executor.temporal import TemporalExecutor
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)

from main import app


@app.workflow
class EvaluatorOptimizerWorkflow(Workflow[str]):
    """
    A simple workflow that demonstrates the basic structure of a Temporal workflow.
    """

    @app.workflow_run
    async def run(self, input: str) -> WorkflowResult[str]:
        """
        Run the workflow, processing the input data.

        Args:
            input_data: The data to process

        Returns:
            A WorkflowResult containing the processed data
        """

        context = app.context
        logger = app.logger

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
            context=app.context,
        )

        result = await evaluator_optimizer.generate_str(
            message=input,
            request_params=RequestParams(model="gpt-4o"),
        )

        return WorkflowResult(value=result)


async def main():
    async with app.run() as orchestrator_app:
        executor: TemporalExecutor = orchestrator_app.executor

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

        task = f"Write a cover letter for the following job posting: {job_posting}\n\nCandidate Details: {candidate_details}\n\nCompany information: {company_information}"

        handle = await executor.start_workflow(
            "EvaluatorOptimizerWorkflow",
            task,
        )
        a = await handle.result()
        print(a)


if __name__ == "__main__":
    asyncio.run(main())
