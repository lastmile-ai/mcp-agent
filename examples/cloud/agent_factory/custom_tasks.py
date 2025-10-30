"""Custom workflow tasks for the cloud agent factory demo."""

from __future__ import annotations

from typing import Dict, List, Tuple

from mcp_agent.executor.workflow_task import workflow_task


_KNOWLEDGE_BASE: Tuple[Dict[str, str], ...] = (
    {
        "topic": "pricing",
        "summary": "Current pricing tiers: Free, Pro ($29/mo), Enterprise (custom).",
        "faq": (
            "Pro tier includes 3 seats, Enterprise supports SSO and audit logging. "
            "Discounts available for annual billing."
        ),
    },
    {
        "topic": "availability",
        "summary": "The service offers 99.9% uptime backed by regional failover.",
        "faq": (
            "Scheduled maintenance occurs Sundays 02:00-03:00 UTC. "
            "Status page: https://status.example.com"
        ),
    },
    {
        "topic": "integrations",
        "summary": "Native integrations include Slack, Jira, and Salesforce connectors.",
        "faq": (
            "Slack integration supports slash commands. Jira integration syncs tickets "
            "bi-directionally every 5 minutes."
        ),
    },
    {
        "topic": "security",
        "summary": "SOC 2 Type II certified, data encrypted in transit and at rest.",
        "faq": (
            "Role-based access control is available on Pro+. Admins can require MFA. "
            "Security whitepaper: https://example.com/security"
        ),
    },
)


@workflow_task(name="cloud_agent_factory.knowledge_base_lookup")
async def knowledge_base_lookup_task(request: dict) -> List[str]:
    """
    Return the most relevant knowledge-base snippets for a customer query.

    The knowledge base is embedded in the code so the example works identically
    in local and hosted environments.
    """

    query = str(request.get("query", "")).lower()
    limit = max(1, int(request.get("limit", 3)))

    if not query.strip():
        return []

    ranked = sorted(
        _KNOWLEDGE_BASE,
        key=lambda entry: _score(query, entry),
        reverse=True,
    )
    top_entries = ranked[:limit]

    formatted: List[str] = []
    for entry in top_entries:
        formatted.append(
            f"*Topic*: {entry['topic']}\nSummary: {entry['summary']}\nFAQ: {entry['faq']}"
        )
    return formatted


def _score(query: str, entry: Dict[str, str]) -> int:
    score = 0
    for token in query.split():
        if len(token) < 3:
            continue
        token_lower = token.lower()
        if token_lower in entry["topic"].lower():
            score += 3
        if token_lower in entry["summary"].lower():
            score += 2
        if token_lower in entry["faq"].lower():
            score += 1
    return score
