"""
RentSpider Client Agents
------------------------
Agents that interact with the RentSpider MCP server for real estate analysis.
This replaces the inline API client from the original real estate analyzer.
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.human_input.console_handler import console_input_callback
from mcp_agent.elicitation.handler import console_elicitation_callback
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)

# Configuration
OUTPUT_DIR = "property_reports"
LOCATION = "Austin, TX" if len(sys.argv) <= 1 else " ".join(sys.argv[1:])
PROPERTY_TYPE = "single family homes"

# Initialize app with elicitation support
app = MCPApp(
    name="rentspider_real_estate_analyzer",
    human_input_callback=console_input_callback,
    elicitation_callback=console_elicitation_callback,
)


async def main():
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{LOCATION.lower().replace(' ', '_').replace(',', '')}_property_report_{timestamp}.md"
    output_path = os.path.join(OUTPUT_DIR, output_file)

    async with app.run() as analyzer_app:
        context = analyzer_app.context
        logger = analyzer_app.logger

        # Configure filesystem server
        if "filesystem" in context.config.mcp.servers:
            context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])
            logger.info("Filesystem server configured")

        # Check for required servers
        required_servers = ["rentspider_api", "g-search", "filesystem"]
        missing_servers = []

        for server in required_servers:
            if server not in context.config.mcp.servers:
                missing_servers.append(server)

        if missing_servers:
            logger.error(f"Missing required servers: {missing_servers}")
            logger.info("Required servers:")
            logger.info("- rentspider_api: The RentSpider MCP server")
            logger.info("- g-search: Google search MCP server")
            logger.info("- filesystem: File system operations")
            return False

        # --- DEFINE AGENTS ---

        # RentSpider Market Research Agent
        rentspider_market_agent = Agent(
            name="rentspider_market_researcher",
            instruction=f"""You are a world-class real estate market researcher specializing in {LOCATION}.

            You have access to the RentSpider API through MCP tools that include automatic elicitation.
            
            IMPORTANT: 
            - Do NOT ask for human input or user preferences manually
            - Call each RentSpider tool ONLY ONCE - the elicitation will handle user preferences
            - If RentSpider API fails (data_source: "API_FAILED"), supplement with web search immediately
            - Do NOT repeat elicitation calls

            Your research process (call each tool only once):
            1. Call get_market_statistics for {LOCATION} (elicitation will handle user preferences)
            2. Call search_properties for {LOCATION} (elicitation will handle search criteria)  
            3. Call get_rental_trends for {LOCATION} (elicitation will handle trend preferences)
            4. If any API calls fail, use web search to supplement the data

            Web search fallback queries if RentSpider fails:
            - "{LOCATION} real estate market data 2025"
            - "{LOCATION} median home prices current"
            - "{LOCATION} rental rates 2025"
            - "{LOCATION} property market trends"

            Extract and analyze:
            - Current median prices and trends
            - Rental rates and yields
            - Market inventory levels
            - Days on market statistics
            - Investment potential metrics

            Present findings with specific numbers, percentages, and data sources.
            Always indicate if data came from RentSpider API or web search fallback.
            """,
            server_names=["rentspider_api", "g-search", "fetch"],
        )

        # Supplementary Web Research Agent
        web_research_agent = Agent(
            name="web_market_researcher",
            instruction=f"""            You supplement RentSpider API data with additional web research for {LOCATION}.
            
            IMPORTANT: Do NOT ask for human input. Focus on web research only.

            Use web search to find information that complements the RentSpider data:
            1. "{LOCATION} real estate market forecast 2025"
            2. "{LOCATION} new construction development projects"
            3. "{LOCATION} economic indicators employment growth"  
            4. "{LOCATION} infrastructure improvements transportation"
            5. "Zillow {LOCATION} market insights" OR "Realtor.com {LOCATION} trends"

            Focus on:
            - Market forecasts and expert predictions
            - New developments and infrastructure projects
            - Economic factors affecting real estate
            - Comparative data from other sources
            - Local market news and developments

            Cross-reference web findings with RentSpider data to provide comprehensive analysis.
            Cite all sources with URLs and note any discrepancies between data sources.
            """,
            server_names=["g-search", "fetch"],
        )

        # Market Research Evaluator
        market_research_evaluator = Agent(
            name="market_research_evaluator",
            instruction=f"""You evaluate the quality of market research data for {LOCATION}.

            Evaluate based on these criteria:

            1. Data Collection: Did the agent successfully gather market data?
               - RentSpider API results are preferred but not required
               - Web search fallback is acceptable if API fails
               - Data source should be clearly indicated

            2. Data Completeness: Is essential information present?
               - Market statistics (prices, trends, inventory)
               - Property search results (even if from web search)
               - Rental market data (API or web fallback)

            3. Elicitation Usage: Did the agent use elicitation appropriately?
               - Should have called RentSpider tools to trigger elicitation
               - Should NOT have repeated elicitation unnecessarily

            4. Fallback Handling: If RentSpider API failed, was web search used?

            Rate each criterion:
            - EXCELLENT: All data collected successfully (API or web fallback)
            - GOOD: Most required data present, some gaps acceptable
            - FAIR: Basic data present but missing key elements
            - POOR: Critical failure to collect any meaningful data

            IMPORTANT: If RentSpider API fails but web search provides fallback data, 
            this should still rate as GOOD or EXCELLENT depending on completeness.
            Do NOT penalize for API failures if agent handled them properly.
            """,
        )

        # Create the market research EvaluatorOptimizerLLM component (more lenient)
        market_research_controller = EvaluatorOptimizerLLM(
            optimizer=rentspider_market_agent,
            evaluator=market_research_evaluator,
            llm_factory=OpenAIAugmentedLLM,
            min_rating=QualityRating.FAIR,  # More lenient to avoid loops
        )

        # Neighborhood Analysis Agent
        neighborhood_agent = Agent(
            name="neighborhood_researcher",
            instruction=f"""            You research neighborhood factors for {LOCATION}.
            
            IMPORTANT: Do NOT ask for human input. Use web search to gather comprehensive neighborhood data.

            Use web search to gather neighborhood information:
            1. "{LOCATION} school ratings district quality"
            2. "{LOCATION} crime statistics safety data"
            3. "{LOCATION} walkability transportation access"
            4. "{LOCATION} amenities shopping dining parks"
            5. "{LOCATION} demographics income levels"

            Focus on providing comprehensive neighborhood analysis covering:
            - School quality and ratings
            - Safety and crime statistics  
            - Transportation and walkability
            - Local amenities and quality of life
            - Demographics and community characteristics
            - Future development plans

            Provide specific ratings, scores, and statistics where available.
            """,
            server_names=["g-search", "fetch"],
        )

        # Investment Analysis Agent
        investment_analyst = Agent(
            name="investment_analyst",
            instruction=f"""            You analyze investment potential for {LOCATION} real estate.

            IMPORTANT: Do NOT manually ask for user input. The RentSpider tools will automatically 
            elicit investment criteria when you call them.

            Call the RentSpider tools to get user-customized analysis:
            - The tools will automatically elicit investment budget, risk tolerance, timeline, etc.
            - Use the elicited preferences along with market data to provide analysis

            Analyze the RentSpider and web research data to provide:

            1. Investment Attractiveness Assessment:
               - Overall market conditions (buyer's vs seller's market)
               - Price trends and market timing
               - Rental yield potential from RentSpider data

            2. Financial Analysis:
               - Cash flow calculations using RentSpider rental data
               - ROI projections based on user's elicited budget
               - Cash-on-cash return estimates
               - Break-even analysis

            3. Risk Assessment:
               - Market volatility indicators
               - Economic risk factors
               - Rental market stability

            4. Personalized Recommendations:
               - Property types matching elicited criteria
               - Neighborhood recommendations
               - Optimal investment strategy
               - Entry and exit timing
            """,
            server_names=["rentspider_api"],
        )

        # Report Writer Agent
        report_writer = Agent(
            name="real_estate_report_writer",
            instruction=f"""            Create a comprehensive real estate analysis report for {LOCATION}.

            IMPORTANT: Do NOT ask for human input about report preferences. 
            The previous agents will have already gathered all user preferences through elicitation.
            
            Create a professional report using all the data gathered by previous agents.

            Structure the report:

            1. **Executive Summary**
               - Key findings and recommendations
               - Investment attractiveness rating
               - Personalized action items

            2. **RentSpider Market Data Analysis**
               - Property search results and pricing
               - Market statistics and trends
               - Rental market analysis and yields

            3. **Supplementary Market Research**
               - Web research findings
               - Market forecasts and expert opinions
               - Comparative market data

            4. **Neighborhood Analysis**
               - Quality of life factors
               - Safety and school ratings
               - Transportation and amenities

            5. **Personalized Investment Analysis**
               - Financial projections based on user criteria
               - Risk assessment for their situation
               - Tailored recommendations and strategy

            6. **Action Plan**
               - Next steps based on user timeline
               - Key metrics to monitor
               - Decision-making framework

            7. **Data Sources**
               - RentSpider API data summary
               - Web research citations
               - Elicitation responses summary

            Save the report to: "{output_path}"
            Format as clean markdown with tables and specific numbers.
            Highlight personalized recommendations prominently.
            """,
            server_names=["filesystem"],
        )

        # --- CREATE THE ORCHESTRATOR ---
        logger.info(
            f"Initializing RentSpider-powered real estate analysis for {LOCATION}"
        )

        orchestrator = Orchestrator(
            llm_factory=OpenAIAugmentedLLM,
            available_agents=[
                market_research_controller,
                web_research_agent,
                neighborhood_agent,
                investment_analyst,
                report_writer,
            ],
            plan_type="full",  # Changed back to "full" - only valid options are "full" or "iterative"
        )

        # Define the orchestration task
        task = f"""Create a comprehensive real estate market analysis for {LOCATION} using RentSpider API data and web research.

        Execute these steps in order:

        1. Use the 'market_research_controller' to gather market data for {LOCATION}:
           - This component uses RentSpider API tools with automatic elicitation
           - It will call get_market_statistics, search_properties, and get_rental_trends
           - Each tool automatically handles user preference elicitation
           - If RentSpider API fails, it will use web search as fallback

        2. Use the 'web_research_agent' to supplement with additional market information:
           - Market forecasts and expert analysis
           - New developments and infrastructure projects  
           - Economic indicators and comparative data

        3. Use the 'neighborhood_agent' for local area analysis:
           - Schools, safety, amenities, transportation
           - Demographics and quality of life metrics

        4. Use the 'investment_analyst' for investment evaluation:
           - Can use RentSpider tools if needed for additional data
           - Analyze financial potential using collected data
           - Provide investment recommendations

        5. Use the 'report_writer' to create final report:
           - Integrate all data from previous agents
           - Create comprehensive markdown report
           - Save to: "{output_path}"

        The RentSpider API tools use elicitation to gather user preferences automatically.
        If API calls fail, agents should use web search for backup data.

        Final deliverable: Professional markdown report with comprehensive real estate analysis for {LOCATION}."""

        # Run the orchestrator
        logger.info("Starting RentSpider-powered real estate analysis workflow")
        print("\n🎯 This analysis uses RentSpider API with interactive customization.")
        print("💬 You'll be asked questions to personalize your analysis.\n")

        start_time = time.time()

        try:
            await orchestrator.generate_str(
                message=task, request_params=RequestParams(model="gpt-4o")
            )

            # Check if report was created
            if os.path.exists(output_path):
                end_time = time.time()
                total_time = end_time - start_time
                logger.info(f"Report successfully generated: {output_path}")
                print("\n✅ RentSpider-powered analysis completed!")
                print(f"📁 Report location: {output_path}")
                print(f"🏠 Market analyzed: {LOCATION}")
                print(f"⏱️  Total time: {total_time:.2f}s")
                print("🔥 Enhanced with RentSpider API data and elicitation")
                return True
            else:
                logger.error(f"Failed to create report at {output_path}")
                return False

        except Exception as e:
            logger.error(f"Error during workflow execution: {str(e)}")
            return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(f"🏡 Analyzing real estate market for: {' '.join(sys.argv[1:])}")
    else:
        print(f"🏡 Analyzing real estate market for: {LOCATION} (default)")

    print("🤖 RentSpider API Real Estate Analysis with Elicitation")
    print("💬 Interactive analysis personalized to your needs")
    print("⏳ Starting RentSpider-powered analysis...\n")

    start = time.time()
    success = asyncio.run(main())
    end = time.time()
    total_time = end - start

    if success:
        print(f"\n🎉 RentSpider analysis completed in {total_time:.2f}s!")
        print("📊 Check your personalized report for detailed insights.")
        print("🔥 Powered by RentSpider API with interactive elicitation")
    else:
        print(f"\n❌ Analysis failed after {total_time:.2f}s. Check logs.")
        print("💡 Ensure RentSpider MCP server is running and API key is configured.")
