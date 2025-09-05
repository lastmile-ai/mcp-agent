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

    async def suspend_workflow(self, workflow_id: str, run_id: Optional[str] = None) -> WorkflowInfo:
        """Suspend a workflow execution via the API.

        Args:
            workflow_id: The UUID of the workflow to suspend
            run_id: Optional run ID for specific execution

        Returns:
            WorkflowInfo: The updated workflow information after suspension

        Raises:
            ValueError: If the API response is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        payload = {"workflowId": workflow_id}
        if run_id:
            payload["runId"] = run_id

        response = await self.post("/workflow/suspend", payload)

        res = response.json()
        if not res or "workflow" not in res:
            raise ValueError("API response did not contain the workflow data")

        return WorkflowInfo(**res["workflow"])

    async def resume_workflow(
        self, 
        workflow_id: str, 
        run_id: Optional[str] = None, 
        payload: Optional[str] = None
    ) -> WorkflowInfo:
        """Resume a suspended workflow execution via the API.

        Args:
            workflow_id: The UUID of the workflow to resume
            run_id: Optional run ID for specific execution
            payload: Optional payload data to pass to resumed workflow

        Returns:
            WorkflowInfo: The updated workflow information after resume

        Raises:
            ValueError: If the API response is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        request_payload = {"workflowId": workflow_id}
        if run_id:
            request_payload["runId"] = run_id
        if payload:
            request_payload["payload"] = payload

        response = await self.post("/workflow/resume", request_payload)

        res = response.json()
        if not res or "workflow" not in res:
            raise ValueError("API response did not contain the workflow data")

        return WorkflowInfo(**res["workflow"])

    async def cancel_workflow(
        self, 
        workflow_id: str, 
        run_id: Optional[str] = None, 
        reason: Optional[str] = None
    ) -> WorkflowInfo:
        """Cancel a workflow execution via the API.

        Args:
            workflow_id: The UUID of the workflow to cancel
            run_id: Optional run ID for specific execution
            reason: Optional reason for cancellation

        Returns:
            WorkflowInfo: The updated workflow information after cancellation

        Raises:
            ValueError: If the API response is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        payload = {"workflowId": workflow_id}
        if run_id:
            payload["runId"] = run_id
        if reason:
            payload["reason"] = reason

        response = await self.post("/workflow/cancel", payload)

        res = response.json()
        if not res or "workflow" not in res:
            raise ValueError("API response did not contain the workflow data")

        return WorkflowInfo(**res["workflow"])
