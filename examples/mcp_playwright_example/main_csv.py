import asyncio
import time
import argparse
import os
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from rich import print

app = MCPApp(name="linkedin_to_slack")

async def linkedin_to_slack(search_criteria: str, slack_channel: str, max_results: int):
    """
    Automated workflow to search LinkedIn for candidates matching specific criteria,
    evaluate their fit, and output the candidate details in CSV format.
    
    Args:
        search_criteria: Search string for finding candidates.
        slack_channel: (Unused in this version)
        max_results: Maximum number of candidates to retrieve.
    """
    async with app.run() as agent_app:
        context = agent_app.context

        async with MCPConnectionManager(context.server_registry):
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

Each candidate should occupy one row. Do not output any extra text outside the CSV data.
""",
                server_names=["playwright", "slack"],  # Slack is still listed, but won’t be used.
            )

            try:
                llm = await linkedin_scraper_agent.attach_llm(OpenAIAugmentedLLM)

                prompt = f"""Complete the following workflow and output only CSV data (with header) for qualified candidates.
1. Log in to LinkedIn using Playwright.
2. Search for candidates matching: {search_criteria}
   - Apply necessary filters and limit to {max_results} candidates.
3. For each candidate:
   - Extract: Name, Current Role/Company, Location, Profile URL, and key details on Skills/Experience.
   - Evaluate whether the candidate meets the specified criteria.
   - Prepare a brief note on why they are a fit.
4. Finally, output only CSV text with a header row containing:
   Name,Role_Company,Location,Profile_URL,Skills_Experience,Notes

Do not include any additional formatting or explanations; output only the raw CSV text.
"""

                print("Executing LinkedIn candidate search workflow and saving results as CSV...")
                result = await llm.generate_str(prompt)

                # Write the result (CSV data) to a file.
                csv_filename = "candidate_summary.csv"
                absolute_path = os.path.abspath(csv_filename)
                with open(csv_filename, "w", newline="") as csv_file:
                    csv_file.write(result)

                print("Workflow completed successfully!")
                print("Candidate summary saved to:", absolute_path)

            finally:
                await linkedin_scraper_agent.close()

def parse_args():
    parser = argparse.ArgumentParser(description="LinkedIn Candidate CSV Exporter")
    parser.add_argument("--criteria", required=True, help="Search criteria string for LinkedIn candidates")
    parser.add_argument("--channel", required=True, help="(Unused) Slack channel")
    parser.add_argument("--max-results", type=int, default=10, help="Maximum number of candidates to find")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    start = time.time()
    try:
        asyncio.run(linkedin_to_slack(args.criteria, args.channel, args.max_results))
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down gracefully...")
    except Exception as e:
        print(f"Error during execution: {e}")
        raise
    finally:
        end = time.time()
        print(f"Total run time: {end - start:.2f}s")