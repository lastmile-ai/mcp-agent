"""
Stock Analyzer with Orchestrator and EvaluatorOptimizerLLM Workflow
------------------------------------------------------------
An integrated financial analysis tool using the latest orchestrator implementation
that now supports AugmentedLLM components directly.
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
MAX_ITERATIONS = 3

# Initialize app
app = MCPApp(name="unified_stock_analyzer", human_input_callback=None)


@app.tool
async def analyze_stock(company_name: str = "Apple") -> str:
    """Analyze a stock and generate a comprehensive financial report."""
    # Create output directory and set up file paths (COMMENTED OUT - NOW PRINTING RESULTS)
    # os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # output_file = f"{company_name.lower().replace(' ', '_')}_report_{timestamp}.md"
    output_path = os.path.join(OUTPUT_DIR, f"{company_name.lower().replace(' ', '_')}_report_{timestamp}.md")

    # Access the running app context directly
    # context = app.context  # Not needed when filesystem is commented out
    logger = app.logger

    # Configure filesystem server to use current directory (COMMENTED OUT - NOW PRINTING RESULTS)
    # if "filesystem" in context.config.mcp.servers:
    #     context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])
    #     logger.info("Filesystem server configured")
    # else:
    #     logger.warning("Filesystem server not configured - report saving may fail")

    # --- DEFINE AGENTS ---

    # Research agent: Collects data using Google Search
    research_agent = Agent(
        name="search_finder",
        instruction=f"""You are a comprehensive financial data collector for {company_name}.
        
        Your job is to gather ALL required financial information using Google Search and fetch tools.
        
        **REQUIRED DATA TO COLLECT:**
        
        1. **Current Market Data**:
           Search: "{company_name} stock price today current"
           Search: "{company_name} trading volume market data"
           Extract: Current price, daily change ($ and %), trading volume, 52-week range
        
        2. **Latest Earnings Information**:
           Search: "{company_name} latest quarterly earnings results"
           Search: "{company_name} earnings vs estimates beat miss"
           Extract: EPS actual vs estimate, revenue actual vs estimate, beat/miss percentages
        
        3. **Recent Financial News**:
           Search: "{company_name} financial news latest week"
           Search: "{company_name} analyst ratings upgrade downgrade"
           Extract: 3-5 recent headlines with dates, sources, and impact assessment
        
        4. **Financial Metrics**:
           Search: "{company_name} PE ratio market cap financial metrics"
           Extract: P/E ratio, market cap, key financial ratios
        
        **OUTPUT FORMAT:**
        Organize your findings in these exact sections:
        
        ## CURRENT MARKET DATA
        - Stock Price: $XXX.XX (±X.XX, ±X.X%)
        - Trading Volume: X.X million (vs avg X.X million)
        - 52-Week Range: $XXX.XX - $XXX.XX
        - Market Cap: $XXX billion
        - Source: [URL and date]
        
        ## LATEST EARNINGS
        - EPS: $X.XX actual vs $X.XX estimate (beat/miss by X%)
        - Revenue: $XXX billion actual vs $XXX billion estimate (beat/miss by X%)
        - Year-over-Year Growth: X%
        - Quarter: QX YYYY
        - Source: [URL and date]
        
        ## RECENT NEWS (Last 7 Days)
        1. [Headline] - [Date] - [Source] - [Impact: Positive/Negative/Neutral]
        2. [Headline] - [Date] - [Source] - [Impact: Positive/Negative/Neutral]
        3. [Continue for 3-5 items]
        
        ## KEY FINANCIAL METRICS
        - P/E Ratio: XX.X
        - Market Cap: $XXX billion
        - [Other available metrics]
        - Source: [URL and date]
        
        **CRITICAL REQUIREMENTS:**
        - Use EXACT figures, not approximations
        - Include source URLs for verification
        - Note data timestamps/dates
        - If any section is missing data, explicitly state what couldn't be found. """,
        server_names=["fetch"],
    )

    # Research evaluator: Evaluates the quality of research (ORIGINAL - UNCHANGED)
    research_evaluator = Agent(
        name="research_evaluator",
        instruction=f"""You are a strict financial data quality evaluator for {company_name} research.
        
        **EVALUATION CRITERIA:**
        
        1. **COMPLETENESS CHECK** (Must have ALL of these):
           ✓ Current stock price with exact dollar amount and percentage change
           ✓ Latest quarterly EPS with actual vs estimate comparison
           ✓ Latest quarterly revenue with actual vs estimate comparison  
           ✓ At least 3 recent financial news items with dates and sources
           ✓ Key financial metrics (P/E ratio, market cap)
           ✓ All data has proper source citations with URLs
        
        2. **ACCURACY CHECK**:
           ✓ Numbers are specific (not "around" or "approximately")
           ✓ Dates are recent and clearly stated
           ✓ Sources are credible financial websites
           ✓ No conflicting information without explanation
        
        3. **CURRENCY CHECK**:
           ✓ Stock price data is from today or latest trading day
           ✓ Earnings data is from most recent quarter
           ✓ News items are from last 7 days (or most recent available)
        
        **RATING GUIDELINES:**
        
        - **EXCELLENT**: All criteria met perfectly, comprehensive data, multiple source verification
        - **GOOD**: All required data present, good quality sources, minor gaps acceptable
        - **FAIR**: Most required data present but missing some elements or has quality issues
        - **POOR**: Missing critical data (stock price, earnings, or major sources), unreliable sources
        
        **EVALUATION OUTPUT FORMAT:**
        
        COMPLETENESS: [EXCELLENT/GOOD/FAIR/POOR]
        - Stock price data: [Present/Missing] - [Details]
        - Earnings data: [Present/Missing] - [Details]  
        - News coverage: [Present/Missing] - [Details]
        - Financial metrics: [Present/Missing] - [Details]
        - Source quality: [Excellent/Good/Fair/Poor] - [Details]
        
        ACCURACY: [EXCELLENT/GOOD/FAIR/POOR]
        - Data specificity: [Comments]
        - Source credibility: [Comments]
        - Data consistency: [Comments]
        
        CURRENCY: [EXCELLENT/GOOD/FAIR/POOR]
        - Stock data recency: [Comments]
        - Earnings recency: [Comments]
        - News recency: [Comments]
        
        OVERALL RATING: [EXCELLENT/GOOD/FAIR/POOR]
        
        **IMPROVEMENT FEEDBACK:**
        [Specific instructions for what needs to be improved, added, or fixed]
        [If rating is below GOOD, provide exact search queries needed]
        [List any missing data points that must be found]
        
        **CRITICAL RULE**: If ANY of these are missing, overall rating cannot exceed FAIR:
        - Exact current stock price with change
        - Latest quarterly EPS actual vs estimate  
        - Latest quarterly revenue actual vs estimate
        - At least 2 credible news sources from recent period
        """,
        server_names=["fetch"],
    )

    # Create the research EvaluatorOptimizerLLM component (ORIGINAL - UNCHANGED)
    research_quality_controller = EvaluatorOptimizerLLM(
        optimizer=research_agent,
        evaluator=research_evaluator,
        llm_factory=OpenAIAugmentedLLM,
        min_rating=QualityRating.EXCELLENT,
    )

    # Analyst agent: Analyzes the research data
    analyst_agent = Agent(
        name="financial_analyst",
        instruction=f"""You are a senior financial analyst providing investment analysis for {company_name}.
        
        Based on the verified, high-quality data provided, create a comprehensive analysis:
        
        **1. STOCK PERFORMANCE ANALYSIS**
        - Analyze current price movement and trading patterns
        - Compare to historical performance and volatility
        - Assess volume trends and market sentiment indicators
        
        **2. EARNINGS ANALYSIS** 
        - Evaluate earnings beat/miss significance
        - Analyze revenue growth trends and sustainability
        - Compare to guidance and analyst expectations
        - Identify key performance drivers
        
        **3. NEWS IMPACT ASSESSMENT**
        - Synthesize how recent news affects investment outlook
        - Identify market sentiment shifts
        - Highlight potential catalysts or risk factors
        
        **4. INVESTMENT THESIS DEVELOPMENT**
        
        **BULL CASE (Top 3 Strengths)**:
        1. [Strength with supporting data and metrics]
        2. [Strength with supporting data and metrics]
        3. [Strength with supporting data and metrics]
        
        **BEAR CASE (Top 3 Concerns)**:
        1. [Risk with supporting evidence and impact assessment]
        2. [Risk with supporting evidence and impact assessment] 
        3. [Risk with supporting evidence and impact assessment]
        
        **5. VALUATION PERSPECTIVE**
        - Current valuation metrics analysis (P/E, etc.)
        - Historical valuation context
        - Fair value assessment based on fundamentals
        
        **6. RISK ASSESSMENT**
        - Company-specific operational risks
        - Market/sector risks and headwinds
        - Regulatory or competitive threats
        
        **OUTPUT REQUIREMENTS:**
        - Support all conclusions with specific data points
        - Use exact numbers and percentages from the research
        - Maintain analytical objectivity
        - Include confidence levels for key assessments
        - Cite data sources for major claims.""",
        server_names=["fetch"],
    )

    # Report writer: Creates the final report
    report_writer = Agent(
        name="report_writer",
        instruction=f"""Create a comprehensive, institutional-quality financial report for {company_name}.
        
        **REPORT STRUCTURE** (Use exactly this format):
        
        # {company_name} - Comprehensive Financial Analysis
        **Report Date:** {datetime.now().strftime('%B %d, %Y at %I:%M %p EST')}
        **Analyst:** AI Financial Research Team
        
        ## Executive Summary
        **Current Price:** $XXX.XX (±$X.XX, ±X.X% today)
        **Market Cap:** $XXX.X billion  
        **Investment Thesis:** [2-3 sentence summary of key investment outlook]
        **Recommendation:** [Overall assessment with confidence level: High/Medium/Low]
        
        ---
        
        ## Current Market Performance
        
        ### Trading Metrics
        - **Stock Price:** $XXX.XX (±$X.XX, ±X.X% today)
        - **Trading Volume:** X.X million shares (vs X.X million avg)
        - **52-Week Range:** $XXX.XX - $XXX.XX  
        - **Current Position:** XX% of 52-week range
        - **Market Capitalization:** $XXX.X billion
        
        ### Technical Analysis
        [Analysis of price trends, volume patterns, momentum indicators]
        
        ---
        
        ## Financial Performance
        
        ### Latest Quarterly Results
        - **Earnings Per Share:** $X.XX actual vs $X.XX estimated (beat/miss by X.X%)
        - **Revenue:** $XXX.X billion actual vs $XXX.X billion estimated (beat/miss by X.X%)
        - **Year-over-Year Growth:** Revenue +/-X.X%, EPS +/-X.X%
        - **Quarter:** QX YYYY results
        
        ### Key Financial Metrics
        - **Price-to-Earnings Ratio:** XX.X
        - **Market Valuation:** [Analysis of current valuation vs historical/peers]
        
        ---
        
        ## Recent Developments
        
        ### Market-Moving News (Last 7 Days)
        [List 3-5 key news items with dates, sources, and impact analysis]
        
        ### Analyst Activity
        [Recent upgrades/downgrades, price target changes, consensus outlook]
        
        ---
        
        ## Investment Analysis
        
        ### Bull Case - Key Strengths
        1. **[Strength Title]:** [Detailed explanation with supporting data]
        2. **[Strength Title]:** [Detailed explanation with supporting data]  
        3. **[Strength Title]:** [Detailed explanation with supporting data]
        
        ### Bear Case - Key Concerns  
        1. **[Risk Title]:** [Detailed explanation with potential impact]
        2. **[Risk Title]:** [Detailed explanation with potential impact]
        3. **[Risk Title]:** [Detailed explanation with potential impact]
        
        ### Valuation Assessment
        [Current valuation analysis, fair value estimate, historical context]
        
        ---
        
        ## Risk Factors
        
        ### Company-Specific Risks
        - [Operational, competitive, management risks]
        
        ### Market & Sector Risks  
        - [Economic, industry, regulatory risks]
        
        ---
        
        ## Investment Conclusion
        
        ### Summary Assessment
        [Balanced summary of key investment points]
        
        ### Overall Recommendation
        [Clear recommendation with rationale and confidence level]
        
        ### Price Target/Fair Value
        [If sufficient data available for valuation estimate]
        
        ---
        
        ## Data Sources & Methodology
        
        ### Sources Used
        [List all data sources with URLs and timestamps]
        
        ### Data Quality Notes  
        [Any limitations, assumptions, or data quality considerations]
        
        ### Report Disclaimers
        *This report is for informational purposes only and should not be considered as personalized investment advice. Past performance does not guarantee future results. Please consult with a qualified financial advisor before making investment decisions.*
        
        ---
        
        **FORMATTING REQUIREMENTS:**
        - Use clean markdown formatting with proper headers
        - Include exact dollar amounts ($XXX.XX) and percentages (XX.X%)
        - Bold key metrics and important findings
        - Maintain professional, objective tone
        - Length: 1200-1800 words
        # - Save to file: {output_path} (COMMENTED OUT - NOW PRINTING RESULTS)
        
        **OUTPUT INSTRUCTIONS:** Return the complete report as formatted text. Do NOT save to a file - just return the full report content as a string.
        
        **CRITICAL:** Ensure all data comes directly from the verified research. Do not add speculative information not supported by the collected data.
        .""",
        server_names=["fetch"],  # Changed from "filesystem" to "fetch"
    )

    # --- CREATE THE ORCHESTRATOR ---
    logger.info(f"Initializing stock analysis workflow for {company_name}")

    # The updated Orchestrator can now take AugmentedLLM instances directly
    orchestrator = Orchestrator(
        llm_factory=OpenAIAugmentedLLM,
        available_agents=[
            # We can now pass the EvaluatorOptimizerLLM directly as a component
            research_quality_controller,
            analyst_agent,
            report_writer,
        ],
        plan_type="full",
    )

    # Define the task for the orchestrator
    task = f"""Create a high-quality stock analysis report for {company_name} by following these steps:

    1. Use the EvaluatorOptimizerLLM component (named 'research_quality_controller') to gather high-quality 
       financial data about {company_name}. This component will automatically evaluate 
       and improve the research until it reaches EXCELLENT quality.
       
       Ask for:
       - Current stock price and recent movement
       - Latest quarterly earnings results and performance vs expectations
       - Recent news and developments
    
    2. Use the financial_analyst to analyze this research data and identify key insights.
    
    3. Use the report_writer to create a comprehensive stock report as formatted text output.
       # (File saving removed - now returning formatted text results)
    
    The final report should be professional, fact-based, and include all relevant financial information."""

    # Run the orchestrator
    logger.info("Starting the stock analysis workflow")
    try:
        result = await orchestrator.generate_str(
            message=task, request_params=RequestParams(model="gpt-4o")
        )

        # Return the report content directly (CHANGED FROM FILE SAVING)
        # if os.path.exists(output_path):
        #     logger.info(f"Report successfully generated: {output_path}")
        #     return f"✅ Stock analysis complete! Report saved to: {output_path}"
        # else:
        #     logger.error(f"Failed to create report at {output_path}")
        #     return f"❌ Failed to create report at {output_path}"
        
        logger.info("Stock analysis complete - returning results")
        return f"✅ Stock Analysis Complete for {company_name}!\n\n" + "="*60 + "\n" + result

    except Exception as e:
        logger.error(f"Error during workflow execution: {str(e)}")
        return f"💥 Error during workflow execution: {str(e)}"


async def main():
    """Main function to run the stock analyzer as a standalone application."""
    async with app.run():
        # Get company name from command line args
        company = "Apple" if len(sys.argv) <= 1 else sys.argv[1]
        result = await analyze_stock(company)
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
