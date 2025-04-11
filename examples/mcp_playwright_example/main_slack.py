import asyncio
import time
import argparse
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from rich import print


app = MCPApp(name="linkedin_to_slack")


async def linkedin_to_slack(search_criteria: str, slack_channel: str, max_results: int):
    """
    Automated workflow to search LinkedIn for candidates matching specific criteria
    and send their profiles to Slack.
    
    Args:
        search_criteria: Search string for finding candidates
        slack_channel: Slack channel to send the notifications
        max_results: Max number of candidates to retrieve
    """
    async with app.run() as agent_app:
        context = agent_app.context

        async with MCPConnectionManager(context.server_registry):
            linkedin_scraper_agent = Agent(
                name="linkedin_scraper_agent",
                instruction=f"""You are an agent that searches LinkedIn for candidates based on specific criteria 
                and notifies Slack with matching profiles.
                
                Your tasks are:
                1. Use Playwright to search LinkedIn for candidates matching: {search_criteria}
                2. Extract key profile details for each candidate
                3. Evaluate their fit based on skills, experience, education, and location
                4. Notify the Slack channel {slack_channel} for every qualified candidate
                
                Guidelines:
                - Only notify Slack if a candidate genuinely matches the criteria
                - Include their name, role, company, skills, experience, location, and profile link
                - Be professional and concise in your Slack messages
                """,
                server_names=["playwright", "slack"],
            )

            try:
                llm = await linkedin_scraper_agent.attach_llm(OpenAIAugmentedLLM)

                prompt = f"""Complete the following workflow:

                1. Log in to LinkedIn using Playwright.

                2. Search for candidates based on: {search_criteria}
                   - Apply filters and narrow results
                   - Limit to {max_results} candidates

                3. For each candidate:
                   - Extract: Name, Headline, Current Role, Company, Location, Profile URL
                   - Evaluate: Skills, Experience, Education, Location
                   - If qualified → Prepare Slack message

                4. Post to Slack channel {slack_channel}:
                   - Name, Headline, Current Role, Company
                   - Matching Skills
                   - Relevant Experience
                   - Profile Link
                   - Brief note on why they’re a fit

                5. Repeat until {max_results} qualified candidates are found or search results are exhausted.

                Notes:
                - Respect LinkedIn rate limits (add random delays)
                - Be mindful of accurate evaluation
                """

                print("Executing LinkedIn to Slack workflow...")
                await llm.generate_str(prompt)
                print("Workflow completed successfully!")

            finally:
                await linkedin_scraper_agent.close()


def parse_args():
    parser = argparse.ArgumentParser(description="LinkedIn to Slack Candidate Matcher")
    parser.add_argument("--criteria", required=True, help="Search criteria string for LinkedIn candidates")
    parser.add_argument("--channel", required=True, help="Slack channel to send profiles to")
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