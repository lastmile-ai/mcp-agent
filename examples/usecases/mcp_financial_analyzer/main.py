"""
Unified Stock Analyzer with Orchestrator and Evaluator-Optimizer
------------------------------------------------------------
An integrated financial analysis tool that uses the orchestrator to manage the entire 
workflow, including the evaluator-optimizer pattern for quality assurance.
"""

import asyncio
import os
import sys
from datetime import datetime
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)

# Configuration values
OUTPUT_DIR = "company_reports"
COMPANY_NAME = "Apple" if len(sys.argv) <= 1 else sys.argv[1]

# Initialize app
app = MCPApp(name="unified_stock_analyzer")

async def main():
    # Create output directory and set up file paths
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{COMPANY_NAME.lower().replace(' ', '_')}_report_{timestamp}.md"
    output_path = os.path.join(OUTPUT_DIR, output_file)
    
    async with app.run() as analyzer_app:
        context = analyzer_app.context
        logger = analyzer_app.logger
        
        # Configure filesystem server to use current directory
        if "filesystem" in context.config.mcp.servers:
            context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])
            logger.info("Filesystem server configured")
        
        # --- DEFINE AGENTS ---
        
        # 1. RESEARCH AGENT: Collects data using Google Search
        research_agent = Agent(
            name="search_finder",
            instruction=f"""Use Google Search to find information about {COMPANY_NAME} in the current month of May 2025:
            You are a world class research analyst.
            Execute these exact search queries:
            1. "{COMPANY_NAME} stock price today"
            2. "{COMPANY_NAME} latest quarterly earnings"
            3. "{COMPANY_NAME} financial news"
            
            Extract the most relevant information about:
            - Current stock price and recent movement
            - Latest earnings report data
            - Any significant recent news
            
            Keep responses short and focused on facts.""",
            server_names=["g-search", "fetch", "filesystem"],
        )

        # 2. RESEARCH EVALUATOR: Evaluates the quality of research
        research_evaluator = Agent(
            name="research_evaluator",
            instruction="""Evaluate the following research data based on the criteria below:
            1. Clarity: Is the language clear, concise, and grammatically correct?
            2. Specificity: Does the response include relevant and concrete details tailored to the query?
            3. Quality: Is the financial data accurate and current?
            4. Completeness: Is the data sufficient to generate a good report on company financials?

            For each criterion:
            - Provide a rating (EXCELLENT, GOOD, FAIR, or POOR).
            - Offer specific feedback or suggestions for improvement.

            Summarize your evaluation as a structured response with:
            - Overall quality rating.
            - Specific feedback and areas for improvement.""",
        )

        # 3. RESEARCH OPTIMIZER: Improves research based on evaluation
        research_optimizer = Agent(
            name="research_optimizer",
            instruction=f"""You are an expert financial researcher. Based on the evaluation feedback provided, 
            improve the research data about {COMPANY_NAME}. Make sure to address all the concerns raised 
            in the evaluation while maintaining factual accuracy. Use Google Search if necessary to fill gaps.
            
            The result should be comprehensive and high-quality financial research that covers:
            - Current stock price and recent movement
            - Latest earnings report data
            - Significant recent news
            
            Keep responses concise and fact-focused.""",
            server_names=["g-search", "fetch"],
        )
        
        # 4. ANALYST AGENT: Analyzes the research 
        analyst_agent = Agent(
            name="financial_analyst",
            instruction=f"""Analyze the key financial data for {COMPANY_NAME}:
            You are a world class financial analyst.
            1. Note if stock is up or down and by how much
            2. Check if earnings beat or missed expectations
            3. List 1-2 main strengths and concerns
            
            Be very concise but thorough in your analysis.""",
            server_names=["fetch"],
        )
        
        # 5. REPORT WRITER AGENT: Creates the final report
        report_writer_agent = Agent(
            name="report_writer",
            instruction=f"""Create a comprehensive stock report for {COMPANY_NAME}:
            You are a world class financial report writer.

            1. Start with a brief company description
            2. Include current stock price and performance analysis
            3. Summarize latest earnings results with key metrics
            4. List relevant news articles from the past month
            5. Add a data-backed outlook on how the company is performing
            
            Format as professional markdown and keep under 600 words total.
            Save the report to "{output_path}".""",
            server_names=["filesystem"],
        )
        
        # 6. REPORT EVALUATOR: Ensures report quality
        report_evaluator = Agent(
            name="report_evaluator",
            instruction=f"""Evaluate the stock report for {COMPANY_NAME} based on these criteria:
            1. Accuracy: Does the report accurately reflect the financial data?
            2. Completeness: Does it cover all key aspects (price, earnings, news, outlook)?
            3. Clarity: Is it well-organized and easy to understand?
            4. Insight: Does it provide valuable perspectives beyond raw data?
            
            For each criterion:
            - Provide a rating (EXCELLENT, GOOD, FAIR, or POOR)
            - Offer specific feedback for improvement
            
            Conclude with an overall quality rating.""",
        )
        
        # --- CREATE THE UNIFIED ORCHESTRATOR ---
        logger.info(f"Initializing unified stock analysis workflow for {COMPANY_NAME}")
        
        # Create the evaluator-optimizer for research quality
        EvaluatorOptimizerLLM(
            optimizer=research_optimizer,
            evaluator=research_evaluator,
            llm_factory=OpenAIAugmentedLLM,
            min_rating=QualityRating.EXCELLENT,
        )
        
        # Define the comprehensive task for the orchestrator
        task = f"""Create a high-quality stock analysis report for {COMPANY_NAME} by following these steps:

        1. Research Stage:
           - Use the search_finder agent to gather current financial data about {COMPANY_NAME}
           - Evaluate the research quality with the research_evaluator agent
           - If quality is not EXCELLENT, improve the research with the research_optimizer agent
           - Repeat until research quality reaches EXCELLENT
        
        2. Analysis Stage:
           - Use the financial_analyst agent to analyze the high-quality research data
           - Identify key strengths, concerns, and performance indicators
        
        3. Report Generation:
           - Use the report_writer agent to create a comprehensive stock report
           - Save the report to "{output_file}" in the "{OUTPUT_DIR}" directory
        
        4. Quality Control:
           - Evaluate the report with the report_evaluator agent
           - If quality is not at least GOOD, improve the report
        
        The final report should be factual, concise, and provide valuable insights."""
        
        # Create unified orchestrator with all agents
        orchestrator = Orchestrator(
            llm_factory=OpenAIAugmentedLLM,
            available_agents=[
                research_agent,
                research_evaluator,
                research_optimizer,
                analyst_agent, 
                report_writer_agent,
                report_evaluator,
            ],
            # Enable the orchestrator to dynamically decide the execution steps
            plan_type="full",
        )
        
        # Run the orchestrator to manage the entire workflow
        logger.info("Starting unified workflow for stock analysis")
        orchestrator_result = await orchestrator.generate_str(
            message=task, 
            request_params=RequestParams(model="gpt-4o")
        )
        
        # Check if report was successfully created
        if os.path.exists(output_path):
            logger.info(f"Report successfully generated: {output_path}")
            # Display brief summary of the result
            logger.info(f"Workflow summary: {orchestrator_result}")
            return True
        else:
            logger.error("Failed to create report")
            return False

if __name__ == "__main__":
    asyncio.run(main())