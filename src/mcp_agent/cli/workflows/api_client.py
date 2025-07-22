"""Workflows API client implementation for the MCP Agent Cloud API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from ..core.api_client import APIClient


class WorkflowInfo(BaseModel):
    """Information about a workflow."""

    workflowId: str
    runId: Optional[str] = None
    name: str
    createdAt: datetime
    principalId: str
    executionStatus: Optional[str] = None


WORKFLOW_ID_PREFIX = "wf_"


def is_valid_workflow_id_format(workflow_id: str) -> bool:
    """Check if the given workflow ID has a valid format.

    Args:
        workflow_id: The workflow ID to validate

    Returns:
        bool: True if the workflow ID is a valid format, False otherwise
    """
    return workflow_id.startswith(WORKFLOW_ID_PREFIX)


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
            ValueError: If the workflow_id is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """

        if not is_valid_workflow_id_format(workflow_id):
            raise ValueError(f"Invalid workflow ID format: {workflow_id}")

        response = await self.post("/workflow/get", {"workflowId": workflow_id})

        res = response.json()
        if not res or "workflow" not in res:
            raise ValueError("API response did not contain the workflow data")

        return WorkflowInfo(**res["workflow"])
