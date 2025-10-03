# Import required libraries
import asyncio
import time
import argparse
import os
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from rich import print

# Initialize MCP application
app = MCPApp(name="linkedin_to_filesystem")


# Main function that handles LinkedIn scraping and CSV export
async def linkedin_to_filesystem(
    search_criteria: str, max_results: int, output_path: str
):
    """
    Automated workflow to search LinkedIn for candidates matching specific criteria,
    evaluate their fit, and output the candidate details in CSV format to a file.

    Args:
        search_criteria: Search string for finding candidates.
        max_results: Maximum number of candidates to retrieve.
        output_path: Path where the CSV file should be saved.
    """

    # Start MCP application context
    async with app.run() as agent_app:
        context = agent_app.context

        # Initialize connection to MCP servers
        async with MCPConnectionManager(context.server_registry):
            # Create LinkedIn scraper agent with instructions
            linkedin_scraper_agent = Agent(
                name="linkedin_scraper_agent",
                instruction=f"""You are an agent that searches LinkedIn for candidates based on specific criteria.

Your tasks are:
1. Use Playwright to navigate LinkedIn, log in, and search for candidates matching: {search_criteria}
2. For each candidate, extract their profile details including:
   - Name
   - Current Role and Company
   - Location
   - Profile URL
   - Key skills or experience summary
3. Evaluate if the candidate meets the criteria.
4. Output all qualified candidate details in CSV format.
   The CSV should have a header row with the following columns:
      Name,Role_Company,Location,Profile_URL,Skills_Experience,Notes
5. Write the CSV data to a file using the filesystem MCP server.

Each candidate should occupy one row. Make sure to collect MULTIPLE candidates, up to {max_results}.
""",
                server_names=["playwright", "filesystem"],
            )

            try:
                # Attach OpenAI LLM to the agent
                llm = await linkedin_scraper_agent.attach_llm(OpenAIAugmentedLLM)

                # Define the workflow prompt for the LLM
                prompt = f"""Complete the following workflow and output CSV data (with header) for qualified candidates.
1. Log in to LinkedIn using Playwright.
2. Search for candidates matching: {search_criteria}
   - Apply filters and scroll through at least {max_results} candidates, navigating multiple result pages if needed.
   - Do not stop after the first result or page. Ensure a diverse set of profiles.
3. For each candidate:
   - Extract: Name, Current Role/Company, Location, Profile URL, and key details on Skills/Experience.
   - Evaluate whether the candidate meets the criteria.
   - Prepare a brief note on why they are a fit.
4. Combine all results into a single CSV with header row:
   Name,Role_Company,Location,Profile_URL,Skills_Experience,Notes
5. Use the filesystem server to write the CSV to the following path:
   {output_path}

You must include at least {max_results} profiles unless LinkedIn returns fewer.
Do not stop after the first match or page. Confirm when saved.
"""

                # Execute the workflow
                print(
                    "🚀 Executing LinkedIn candidate search workflow and saving results as CSV..."
                )
                result = await llm.generate_str(prompt)
                print("LLM Output:", result)

                print("✅ Agent finished execution. Verifying file save...")

                # Verify the output file was created
                if os.path.exists(output_path):
                    print(f"📁 File saved successfully: {output_path}")
                else:
                    print("⚠️ File save not confirmed. Check filesystem server setup.")

            finally:
                # Clean up agent resources
                await linkedin_scraper_agent.close()


# Command line argument parsing
def parse_args():
    parser = argparse.ArgumentParser(description="LinkedIn Candidate CSV Exporter")
    parser.add_argument(
        "--criteria",
        required=True,
        help="Search criteria string for LinkedIn candidates",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum number of candidates to find",
    )
    parser.add_argument(
        "--output", default="candidates.csv", help="Output CSV file path"
    )
    return parser.parse_args()


# Main execution block
if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()

    # Track execution time and handle errors
    start = time.time()
    try:
        asyncio.run(
            linkedin_to_filesystem(args.criteria, args.max_results, args.output)
        )
    except KeyboardInterrupt:
        print("\n🛑 Received keyboard interrupt, shutting down gracefully...")
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        raise
    finally:
        end = time.time()
        print(f"⏱ Total run time: {end - start:.2f}s")
