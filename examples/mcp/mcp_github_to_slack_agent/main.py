import asyncio
import time
import argparse
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from rich import print

app = MCPApp(name="github_to_slack")


async def github_to_slack(github_owner: str, github_repo: str, slack_channel: str):
    async with app.run() as agent_app:
        context = agent_app.context

        async with MCPConnectionManager(context.server_registry):
            github_to_slack_agent = Agent(
                name="github_to_slack_agent",
                instruction=f"""You are an agent that monitors GitHub pull requests and provides summaries to Slack.
                Your tasks are:
                1. Use the GitHub server to retrieve information about the latest pull requests for the repository {github_owner}/{github_repo}
                2. Analyze and prioritize the pull requests based on their importance, urgency, and impact
                3. Format a concise summary of high-priority items
                4. Submit this summary to the Slack server in the channel {slack_channel}
                
                For prioritization, consider:
                - PRs marked as high priority or urgent
                - PRs that address security vulnerabilities
                - PRs that fix critical bugs
                - PRs that are blocking other work
                - PRs that have been open for a long time
                
                Your Slack summary should be professional, concise, and highlight the most important information.""",
                server_names=["github", "slack"],
            )

            try:
                llm = await github_to_slack_agent.attach_llm(AnthropicAugmentedLLM)

                prompt = f"""Complete the following workflow:

                1. Retrieve the latest pull requests from the GitHub repository {github_owner}/{github_repo}.
                   Use the GitHub server to get this information.
                   Gather details such as PR title, author, creation date, status, and description.

                2. Analyze the pull requests you've retrieved and prioritize them.
                   Identify high-priority items based on:
                   - PRs marked as high priority or urgent in their title or description
                   - PRs that address security vulnerabilities
                   - PRs that fix critical bugs
                   - PRs that are blocking other work
                   - PRs that have been open for a long time
                   Create a list of high-priority PRs with brief explanations of why they are prioritized.

                3. Format a professional and concise summary of the high-priority pull requests
                   to share on Slack. The summary should:
                   - Start with a brief overview of what's included
                   - List each high-priority PR with its key details
                   - Include links to the PRs
                   - End with any relevant action items or recommendations
                
                4. Use the Slack server to post this summary to the channel {slack_channel}.
                """

                # Execute the workflow
                print("Executing GitHub to Slack workflow...")
                await llm.generate_str(prompt)

                print("Workflow completed successfully!")

            finally:
                # Clean up the agent
                await github_to_slack_agent.close()


def parse_args():
    parser = argparse.ArgumentParser(description="GitHub to Slack PR Summary Tool")
    parser.add_argument("--owner", required=True, help="GitHub repository owner")
    parser.add_argument("--repo", required=True, help="GitHub repository name")
    parser.add_argument("--channel", required=True, help="Slack channel to post to")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start = time.time()
    try:
        asyncio.run(github_to_slack(args.owner, args.repo, args.channel))
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down gracefully...")
    except Exception as e:
        print(f"Error during execution: {e}")
        raise
    finally:
        end = time.time()
        t = end - start
        print(f"Total run time: {t:.2f}s")
