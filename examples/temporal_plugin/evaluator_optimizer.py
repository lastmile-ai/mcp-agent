import asyncio
import os
from uuid import uuid4
from temporalio import workflow
from mcp_agent.core.context import get_current_context
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.agents.agent import Agent
from temporalio.client import Client
from mcp_agent.executor.temporal.plugin import MCPAgentPlugin
from mcp_agent.app import MCPApp
from temporalio.worker import Worker

app = MCPApp(name="mcp_basic_agent")


@workflow.defn
class BasicWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        context = get_current_context()
        logger = context.app.logger

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
            context=context,
        )

        result = await evaluator_optimizer.generate_str(
            message=input,
            request_params=RequestParams(model="gpt-4o"),
        )

        return result


async def main():
    async with app.run() as running_app:
        plugin = MCPAgentPlugin(running_app)

        client = await Client.connect(
            running_app.config.temporal.host,
            plugins=[plugin],
        )

        async with Worker(
            client,
            task_queue=running_app.config.temporal.task_queue,
            workflows=[BasicWorkflow],
        ):
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
                "Look up from the LastMile AI page: https://lastmileai.dev"
            )

            task = f"Write a cover letter for the following job posting: {job_posting}\n\nCandidate Details: {candidate_details}\n\nCompany information: {company_information}"

            output = await client.execute_workflow(
                BasicWorkflow.run,
                task,
                id=f"basic-workflow-{uuid4()}",
                task_queue=running_app.config.temporal.task_queue,
            )
            print(output)


if __name__ == "__main__":
    asyncio.run(main())
