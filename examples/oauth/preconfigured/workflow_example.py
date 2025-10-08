"""
OAuth Workflow Pre-Authorization Example

This example demonstrates how to use the workflow_pre_auth endpoint to
pre-store OAuth tokens for a workflow, then execute the workflow to
access GitHub MCP server tools.

Features demonstrated:
- Using the workflow_pre_auth endpoint to store OAuth tokens
- Creating a workflow that uses pre-authorized tokens
- Accessing multiple MCP servers with different tokens
- Error handling for token expiration and OAuth issues
"""

import asyncio
import json
import time
from typing import Any, Dict, List

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.core.context import Context


class GitHubOrganizationAnalyzer(Agent):
    """
    An agent that analyzes GitHub organizations using pre-authorized OAuth tokens.
    """

    def __init__(self, context: Context):
        super().__init__(context=context)
        self.name = "github_org_analyzer"

    async def analyze_organizations(
        self, queries: List[str], detailed_analysis: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze multiple organizations based on search queries.

        Args:
            queries: List of search queries for organizations
            detailed_analysis: Whether to fetch detailed information

        Returns:
            Analysis results for all organizations
        """
        logger = self.context.logger
        results = {"organizations": [], "summary": {}, "errors": []}

        try:
            # The OAuth tokens should be pre-authorized for this workflow
            # and available through the context
            logger.info(f"Starting analysis of {len(queries)} organization queries")

            for query in queries:
                try:
                    orgs = await self._search_organizations(query)

                    for org in orgs:
                        org_analysis = {
                            "query": query,
                            "organization": org.get("login", "unknown"),
                            "description": org.get("description", ""),
                            "url": org.get("html_url", ""),
                            "public_repos": org.get("public_repos", 0),
                            "followers": org.get("followers", 0),
                            "location": org.get("location", ""),
                            "created_at": org.get("created_at", ""),
                        }

                        if detailed_analysis:
                            # Add more detailed analysis
                            org_analysis.update(
                                await self._analyze_organization_details(org)
                            )

                        results["organizations"].append(org_analysis)

                except Exception as e:
                    error_msg = f"Error processing query '{query}': {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

            # Generate summary
            results["summary"] = self._generate_summary(results["organizations"])

            logger.info(
                f"Analysis completed: {len(results['organizations'])} organizations analyzed"
            )
            return results

        except Exception as e:
            logger.error(f"Organization analysis failed: {e}")
            raise

    async def _search_organizations(self, query: str) -> List[Dict[str, Any]]:
        """Search for organizations using the GitHub MCP server."""
        from mcp_agent.mcp.gen_client import gen_client

        async with gen_client(
            "github", server_registry=self.context.server_registry, context=self.context
        ) as github_client:
            result = await github_client.call_tool(
                "search_orgs",
                {"query": query, "perPage": 10, "sort": "best-match", "order": "desc"},
            )

            organizations = []
            if result.content:
                for content_item in result.content:
                    if hasattr(content_item, "text"):
                        try:
                            data = json.loads(content_item.text)
                            if isinstance(data, dict) and "items" in data:
                                organizations.extend(data["items"])
                            elif isinstance(data, list):
                                organizations.extend(data)
                        except json.JSONDecodeError:
                            pass

            return organizations

    async def _analyze_organization_details(
        self, org: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze detailed information about an organization."""
        details = {
            "activity_score": self._calculate_activity_score(org),
            "size_category": self._categorize_size(org.get("public_repos", 0)),
            "age_years": self._calculate_age(org.get("created_at", "")),
        }

        return details

    def _calculate_activity_score(self, org: Dict[str, Any]) -> float:
        """Calculate a simple activity score based on available metrics."""
        repos = org.get("public_repos", 0)
        followers = org.get("followers", 0)

        # Simple scoring algorithm
        score = (repos * 0.1) + (followers * 0.01)
        return min(score, 100.0)  # Cap at 100

    def _categorize_size(self, repo_count: int) -> str:
        """Categorize organization size based on repository count."""
        if repo_count < 10:
            return "small"
        elif repo_count < 50:
            return "medium"
        elif repo_count < 200:
            return "large"
        else:
            return "enterprise"

    def _calculate_age(self, created_at: str) -> float:
        """Calculate organization age in years."""
        if not created_at:
            return 0.0

        try:
            from datetime import datetime

            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            now = datetime.now(created.tzinfo)
            return (now - created).days / 365.25
        except Exception:
            return 0.0

    def _generate_summary(self, organizations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics from organization analysis."""
        if not organizations:
            return {"total": 0, "message": "No organizations analyzed"}

        total_repos = sum(org.get("public_repos", 0) for org in organizations)
        total_followers = sum(org.get("followers", 0) for org in organizations)

        size_categories = {}
        for org in organizations:
            category = org.get("size_category", "unknown")
            size_categories[category] = size_categories.get(category, 0) + 1

        return {
            "total_organizations": len(organizations),
            "total_public_repos": total_repos,
            "total_followers": total_followers,
            "average_repos_per_org": total_repos / len(organizations),
            "size_distribution": size_categories,
            "top_organizations": sorted(
                organizations, key=lambda x: x.get("activity_score", 0), reverse=True
            )[:5],
        }


# Create workflow using the @app.async_tool decorator
app = MCPApp(name="oauth_workflow_example")


@app.async_tool
async def analyze_github_ecosystem(
    app_ctx: Context, focus_areas: List[str], include_details: bool = True
) -> Dict[str, Any]:
    """
    Analyze the GitHub ecosystem based on focus areas.

    This workflow demonstrates using pre-authorized OAuth tokens
    to analyze organizations across different domains.

    Args:
        focus_areas: Areas to focus on (e.g., ["AI/ML", "cloud", "security"])
        include_details: Whether to include detailed analysis

    Returns:
        Comprehensive analysis of the GitHub ecosystem
    """
    logger = app_ctx.logger
    logger.info(f"Starting GitHub ecosystem analysis for: {focus_areas}")

    # Create the analyzer agent
    analyzer = GitHubOrganizationAnalyzer(context=app_ctx)

    # Map focus areas to search queries
    query_mapping = {
        "AI/ML": [
            "machine-learning",
            "artificial-intelligence",
            "deep-learning",
            "tensorflow",
            "pytorch",
        ],
        "cloud": ["cloud-computing", "aws", "azure", "kubernetes", "docker"],
        "security": ["cybersecurity", "security", "encryption", "vulnerability"],
        "web": ["web-development", "javascript", "react", "vue", "angular"],
        "mobile": ["mobile-development", "android", "ios", "react-native", "flutter"],
        "data": ["data-science", "analytics", "big-data", "database", "sql"],
        "devtools": ["developer-tools", "ci-cd", "testing", "monitoring", "automation"],
    }

    all_queries = []
    for area in focus_areas:
        queries = query_mapping.get(area.lower(), [area.lower()])
        all_queries.extend(queries)

    # Remove duplicates while preserving order
    unique_queries = list(dict.fromkeys(all_queries))

    logger.info(f"Executing {len(unique_queries)} organization searches")

    try:
        # Perform the analysis
        analysis_results = await analyzer.analyze_organizations(
            queries=unique_queries, detailed_analysis=include_details
        )

        # Add ecosystem-level insights
        ecosystem_analysis = {
            "focus_areas": focus_areas,
            "timestamp": time.time(),
            "queries_executed": unique_queries,
            "results": analysis_results,
            "insights": _generate_ecosystem_insights(analysis_results),
        }

        logger.info("GitHub ecosystem analysis completed successfully")
        return ecosystem_analysis

    except Exception as e:
        logger.error(f"Ecosystem analysis failed: {e}")
        raise


def _generate_ecosystem_insights(results: Dict[str, Any]) -> Dict[str, Any]:
    """Generate high-level insights from the ecosystem analysis."""
    organizations = results.get("organizations", [])

    if not organizations:
        return {"message": "No data available for insights"}

    # Find trends and patterns
    insights = {
        "dominant_languages": _analyze_language_trends(organizations),
        "geographic_distribution": _analyze_geographic_distribution(organizations),
        "maturity_analysis": _analyze_organization_maturity(organizations),
        "activity_patterns": _analyze_activity_patterns(organizations),
    }

    return insights


def _analyze_language_trends(organizations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze programming language trends from organization data."""
    # This is a simplified example - in a real implementation,
    # you might use additional GitHub API calls to get language data
    return {
        "message": "Language trend analysis would require additional API calls",
        "suggestion": "Use repository listing and language detection APIs",
    }


def _analyze_geographic_distribution(
    organizations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze geographic distribution of organizations."""
    locations = {}
    for org in organizations:
        location = org.get("location", "").strip()
        if location:
            locations[location] = locations.get(location, 0) + 1

    return {
        "total_with_location": len(
            [org for org in organizations if org.get("location")]
        ),
        "top_locations": dict(
            sorted(locations.items(), key=lambda x: x[1], reverse=True)[:10]
        ),
    }


def _analyze_organization_maturity(
    organizations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze the maturity of organizations."""
    mature_count = sum(1 for org in organizations if org.get("age_years", 0) > 5)
    established_count = sum(
        1 for org in organizations if 2 <= org.get("age_years", 0) <= 5
    )
    new_count = sum(1 for org in organizations if org.get("age_years", 0) < 2)

    return {
        "mature_orgs": mature_count,  # > 5 years
        "established_orgs": established_count,  # 2-5 years
        "new_orgs": new_count,  # < 2 years
        "maturity_ratio": mature_count / len(organizations) if organizations else 0,
    }


def _analyze_activity_patterns(organizations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze activity patterns across organizations."""
    if not organizations:
        return {}

    activity_scores = [org.get("activity_score", 0) for org in organizations]

    return {
        "average_activity": sum(activity_scores) / len(activity_scores),
        "high_activity_count": sum(1 for score in activity_scores if score > 75),
        "low_activity_count": sum(1 for score in activity_scores if score < 25),
        "activity_distribution": {
            "high": sum(1 for score in activity_scores if score > 75),
            "medium": sum(1 for score in activity_scores if 25 <= score <= 75),
            "low": sum(1 for score in activity_scores if score < 25),
        },
    }


async def demonstrate_pre_auth_workflow():
    """
    Demonstrate the workflow with pre-authorization.
    """
    print("OAuth Workflow Pre-Authorization Example")
    print("=" * 50)

    # Note: In a real scenario, you would use the MCP agent server
    # to call the workflow_pre_auth endpoint before running the workflow
    print("\n1. Pre-authorization step:")
    print("   Before running this workflow, you should pre-authorize OAuth tokens:")
    print("   Use the workflow_pre_auth endpoint with the following structure:")

    example_tokens = [
        {
            "access_token": "github_oauth_access_token_here",
            "refresh_token": "github_oauth_refresh_token_here",
            "server_name": "github",
            "scopes": ["read:org", "public_repo"],
            "authorization_server": "https://github.com/login/oauth/authorize",
        }
    ]

    print(f"   Token structure: {json.dumps(example_tokens, indent=2)}")

    print("\n2. Running workflow with pre-authorized tokens:")

    try:
        async with app.run() as workflow_app:
            # Simulate workflow execution
            # In practice, this would be called through the MCP agent server
            context = workflow_app.context

            result = await analyze_github_ecosystem(
                app_ctx=context,
                focus_areas=["AI/ML", "cloud", "security"],
                include_details=True,
            )

            print("\n3. Workflow Results:")
            print(f"   - Focus areas analyzed: {result['focus_areas']}")
            print(f"   - Queries executed: {len(result['queries_executed'])}")
            print(
                f"   - Organizations found: {result['results']['summary'].get('total_organizations', 0)}"
            )

            if result["results"]["errors"]:
                print(f"   - Errors encountered: {len(result['results']['errors'])}")

            print("\n4. Ecosystem Insights:")
            insights = result["insights"]
            if "geographic_distribution" in insights:
                top_locations = insights["geographic_distribution"].get(
                    "top_locations", {}
                )
                if top_locations:
                    print(f"   - Top locations: {list(top_locations.keys())[:3]}")

            if "maturity_analysis" in insights:
                maturity = insights["maturity_analysis"]
                print(f"   - Mature organizations: {maturity.get('mature_orgs', 0)}")
                print(f"   - Maturity ratio: {maturity.get('maturity_ratio', 0):.2%}")

    except Exception as e:
        print(f"   Workflow failed: {e}")
        print("\n   This is expected if OAuth tokens are not properly configured.")
        print("   To run this example successfully:")
        print("   1. Set up a GitHub OAuth app")
        print("   2. Configure mcp_agent.config.yaml with OAuth settings")
        print("   3. Use workflow_pre_auth to store valid tokens")
        print("   4. Run the workflow through the MCP agent server")


async def main():
    """
    Main function demonstrating the workflow pre-authorization pattern.
    """
    await demonstrate_pre_auth_workflow()


if __name__ == "__main__":
    asyncio.run(main())
