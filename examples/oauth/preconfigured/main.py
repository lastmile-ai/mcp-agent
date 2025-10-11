"""
OAuth MCP Agent Example

This example demonstrates how to use an MCP agent with OAuth authentication
to access the GitHub MCP server and search for organizations.

Features demonstrated:
- OAuth flow setup and configuration
- Connecting to GitHub MCP server with OAuth
- Using the search_orgs tool
- Error handling and token refresh
"""

import asyncio
import json
import logging
from typing import Any, Dict, List

from mcp_agent.app import MCPApp
from mcp_agent.mcp.gen_client import gen_client

# Create the MCP app with OAuth configuration
app = MCPApp(name="oauth_github_example")


async def search_github_orgs(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for GitHub organizations using the GitHub MCP server with OAuth.

    Args:
        query: Search query (e.g., 'microsoft', 'location:california')
        limit: Maximum number of results to return

    Returns:
        List of organization data from GitHub
    """
    async with app.run() as github_app:
        context = github_app.context
        logger = github_app.logger

        logger.info(f"Searching GitHub organizations for: '{query}'")

        try:
            # Connect to the GitHub MCP server with OAuth
            async with gen_client(
                "github", server_registry=context.server_registry, context=context
            ) as github_client:
                logger.info("Connected to GitHub MCP server with OAuth")

                # List available tools to verify connection
                tools_result = await github_client.list_tools()
                logger.info(f"Available tools: {len(tools_result.tools)} tools found")

                # Find the search_orgs tool
                search_orgs_tool = None
                for tool in tools_result.tools:
                    if tool.name == "search_orgs":
                        search_orgs_tool = tool
                        break

                if not search_orgs_tool:
                    logger.error("search_orgs tool not found")
                    return []

                logger.info(f"Found search_orgs tool: {search_orgs_tool.description}")

                # Call the search_orgs tool
                result = await github_client.call_tool(
                    "search_orgs",
                    {
                        "query": query,
                        "perPage": min(limit, 100),  # GitHub API max is 100
                        "sort": "best-match",
                        "order": "desc",
                    },
                )

                logger.info("Search completed, processing results...")

                # Parse and return the results
                if result.content:
                    # The result content should contain the organization data
                    organizations = []
                    for content_item in result.content:
                        if hasattr(content_item, "text"):
                            try:
                                # Try to parse as JSON if it's structured data
                                data = json.loads(content_item.text)
                                if isinstance(data, dict) and "items" in data:
                                    organizations.extend(data["items"][:limit])
                                elif isinstance(data, list):
                                    organizations.extend(data[:limit])
                                else:
                                    organizations.append(data)
                            except json.JSONDecodeError:
                                # If not JSON, treat as text description
                                organizations.append({"description": content_item.text})

                    logger.info(f"Found {len(organizations)} organizations")
                    return organizations[:limit]

                return []

        except Exception as e:
            logger.error(f"Error searching GitHub organizations: {e}")
            # Check if it's an OAuth-related error
            if "authentication" in str(e).lower() or "oauth" in str(e).lower():
                logger.error(
                    "Authentication failed. Please check your OAuth configuration "
                    "and ensure your GitHub token is valid."
                )
            raise


async def demonstrate_org_search():
    """
    Demonstrate searching for different types of organizations.
    """
    search_queries = [
        "microsoft",
        # "location:california",
        # "created:>=2020-01-01",
        # "language:python",
        # "repositories:>100"
    ]

    for query in search_queries:
        print(f"\n{'=' * 50}")
        print(f"Searching for: {query}")
        print("=" * 50)

        try:
            orgs = await search_github_orgs(query, limit=3)

            if orgs:
                for i, org in enumerate(orgs, 1):
                    print(f"\n{i}. {org.get('login', 'Unknown')}")
                    if "description" in org and org["description"]:
                        print(f"   Description: {org['description']}")
                    if "html_url" in org:
                        print(f"   URL: {org['html_url']}")
                    if "public_repos" in org:
                        print(f"   Public repos: {org['public_repos']}")
                    if "location" in org and org["location"]:
                        print(f"   Location: {org['location']}")
            else:
                print("No organizations found.")

        except Exception as e:
            print(f"Error: {e}")
            continue


async def main():
    """
    Main function demonstrating various OAuth MCP agent usage patterns.
    """
    print("OAuth MCP Agent Example - GitHub Organization Search")
    print("=" * 60)

    try:
        # Demonstrate basic organization search
        await demonstrate_org_search()

    except Exception as e:
        print(f"\nExample failed with error: {e}")
        print("\nPlease ensure:")
        print("1. You have configured your GitHub OAuth app correctly")
        print("2. Your mcp_agent.secrets.yaml file contains valid OAuth credentials")
        print("3. The GitHub MCP server is properly installed and accessible")
        print("4. Your OAuth token has the required scopes (read:org)")

        # Log the full error for debugging
        logging.exception("Full error details:")


if __name__ == "__main__":
    # Set up logging to show detailed information
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    asyncio.run(main())
