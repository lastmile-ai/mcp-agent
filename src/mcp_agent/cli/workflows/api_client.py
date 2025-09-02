"""Workflows API client implementation for the MCP Agent Cloud API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from mcp_agent.cli.core.api_client import APIClient


class WorkflowInfo(BaseModel):
    """Information about a workflow."""

    workflowId: str
    runId: Optional[str] = None
    name: str
    createdAt: datetime
    principalId: str
    executionStatus: Optional[str] = None


class WorkflowAPIClient(APIClient):
    """Client for interacting with the Workflow API service over HTTP."""

    # TODO(LAS-1852): Support fetching by run_id
    async def get_workflow(self, workflow_id: str) -> WorkflowInfo:
        """Get a Workflow by its ID via the API.

        Args:
            workflow_id: The UUID of the workflow to retrieve

        Returns:
            WorkflowInfo: The retrieved Workflow information

        Raises:
            ValueError: If the API response is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """

        response = await self.post("/workflow/get", {"workflowId": workflow_id})

        res = response.json()
        if not res or "workflow" not in res:
            raise ValueError("API response did not contain the workflow data")

        return WorkflowInfo(**res["workflow"])
