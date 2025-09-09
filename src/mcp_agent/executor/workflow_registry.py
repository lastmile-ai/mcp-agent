import asyncio

from abc import ABC, abstractmethod
from typing import (
    Any,
    Dict,
    Optional,
    List,
    TYPE_CHECKING,
)

from mcp_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from mcp_agent.executor.workflow import Workflow

logger = get_logger(__name__)


class WorkflowRegistry(ABC):
    """
    Abstract base class for registry tracking workflow instances.
    Provides a central place to register, look up, and manage workflow instances.
    """

    def __init__(self):
        pass

    @abstractmethod
    async def register(
        self,
        workflow: "Workflow",
        run_id: str | None = None,
        workflow_id: str | None = None,
        task: Optional["asyncio.Task"] = None,
    ) -> None:
        """
        Register a workflow instance (i.e. a workflow run).

         Args:
            workflow: The workflow instance
            run_id: The unique ID for this specific workflow run. If unspecified, it will be retrieved from the workflow instance.
            workflow_id: The unique ID for the workflow type. If unspecified, it will be retrieved from the workflow instance.
            task: The asyncio task running the workflow
        """
        pass

    @abstractmethod
    async def unregister(self, run_id: str, workflow_id: str | None = None) -> None:
        """
        Remove a workflow instance from the registry.

        Args:
            run_id: The unique ID for this specific workflow run.
            workflow_id: The ID of the workflow.
        """
        pass

    @abstractmethod
    async def get_workflow(
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> Optional["Workflow"]:
        """
        Get a workflow instance by run ID or workflow ID.

        Args:
            run_id: The unique ID for a specific workflow run to retrieve.
            workflow_id: The ID of the workflow to retrieve.

        Returns:
            The workflow instance, or None if not found
        """
        pass

    @abstractmethod
    async def resume_workflow(
        self,
        run_id: str | None = None,
        workflow_id: str | None = None,
        signal_name: str | None = "resume",
        payload: Any | None = None,
    ) -> bool:
        """
        Resume a paused workflow.

        Args:
            run_id: The unique ID for this specific workflow run
            workflow_id: The ID of the workflow to resume
            signal_name: Name of the signal to send to the workflow (default is "resume")
            payload: Payload to send with the signal

        Returns:
            True if the resume signal was sent successfully, False otherwise
        """
        pass

    @abstractmethod
    async def cancel_workflow(
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> bool:
        """
        Cancel (terminate) a running workflow.

        Args:
            run_id: The unique ID for this specific workflow run
            workflow_id: The ID of the workflow to cancel

        Returns:
            True if the cancel signal was sent successfully, False otherwise
        """
        pass

    @abstractmethod
    async def get_workflow_status(
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the status of a workflow run.

        Args:
            run_id: The unique ID for this specific workflow run
            workflow_id: The ID of the workflow to cancel

        Returns:
            The last available workflow status if found, None otherwise
        """
        pass

    @abstractmethod
    async def list_workflow_statuses(self) -> List[Dict[str, Any]]:
        """
        List all registered workflow instances with their status.

        Returns:
            A list of dictionaries with workflow information
        """
        pass

    @abstractmethod
    async def list_workflows(self) -> List["Workflow"]:
        """
        List all registered workflow instances.

        Returns:
            A list of workflow instances
        """
        pass


class InMemoryWorkflowRegistry(WorkflowRegistry):
    """
    Registry for tracking workflow instances in memory for AsyncioExecutor.
    """

    def __init__(self):
        super().__init__()
        self._workflows: Dict[str, "Workflow"] = {}  # run_id -> Workflow instance
        self._tasks: Dict[str, "asyncio.Task"] = {}  # run_id -> task
        self._workflow_ids: Dict[str, List[str]] = {}  # workflow_id -> list of run_ids
        self._lock = asyncio.Lock()

    async def register(
        self,
        workflow: "Workflow",
        run_id: str | None = None,
        workflow_id: str | None = None,
        task: Optional["asyncio.Task"] = None,
    ) -> None:
        if run_id is None:
            run_id = workflow.run_id
        if workflow_id is None:
            workflow_id = workflow.id

        if not run_id or not workflow_id:
            raise ValueError(
                "Both run_id and workflow_id must be specified or available from the workflow instance."
            )

        async with self._lock:
            self._workflows[run_id] = workflow
            if task:
                self._tasks[run_id] = task

            # Add run_id to the list for this workflow_id
            if workflow_id not in self._workflow_ids:
                self._workflow_ids[workflow_id] = []
            self._workflow_ids[workflow_id].append(run_id)

    async def unregister(
        self,
        run_id: str,
        workflow_id: str | None = None,
    ) -> None:
        workflow = self._workflows.get(run_id)
        workflow_id = workflow.id if workflow else workflow_id
        if not workflow_id:
            raise ValueError("Cannot unregister workflow: workflow_id not provided.")

        async with self._lock:
            # Remove workflow and task
            self._workflows.pop(run_id, None)
            self._tasks.pop(run_id, None)

            # Remove from workflow_ids mapping
            if workflow_id in self._workflow_ids:
                if run_id in self._workflow_ids[workflow_id]:
                    self._workflow_ids[workflow_id].remove(run_id)
                if not self._workflow_ids[workflow_id]:
                    del self._workflow_ids[workflow_id]

    async def get_workflow(
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> Optional["Workflow"]:
        if not (run_id or workflow_id):
            raise ValueError("Either run_id or workflow_id must be provided.")
        if run_id:
            return self._workflows.get(run_id)
        if workflow_id:
            run_ids = self._workflow_ids.get(workflow_id, [])
            if run_ids:
                return self._workflows.get(run_ids[-1])
        return None

    async def resume_workflow(
        self,
        run_id: str | None = None,
        workflow_id: str | None = None,
        signal_name: str | None = "resume",
        payload: Any | None = None,
    ) -> bool:
        if not (run_id or workflow_id):
            raise ValueError("Either run_id or workflow_id must be provided.")
        workflow = await self.get_workflow(run_id, workflow_id)
        if not workflow:
            logger.error(
                f"Cannot resume workflow with run ID {run_id or 'unknown'}, workflow ID {workflow_id or 'unknown'}: workflow not found in registry"
            )
            return False

        return await workflow.resume(signal_name, payload)

    async def cancel_workflow(
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> bool:
        if not (run_id or workflow_id):
            raise ValueError("Either run_id or workflow_id must be provided.")
        workflow = await self.get_workflow(run_id, workflow_id)
        if not workflow:
            logger.error(
                f"Cannot cancel workflow with run ID {run_id or 'unknown'}, workflow ID {workflow_id or 'unknown'}: workflow not found in registry"
            )
            return False

        return await workflow.cancel()

    async def get_workflow_status(
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> Optional[Dict[str, Any]]:
        if not (run_id or workflow_id):
            raise ValueError("Either run_id or workflow_id must be provided.")
        workflow = await self.get_workflow(run_id, workflow_id)
        if not workflow:
            logger.error(
                f"Cannot get status for workflow with run ID {run_id or 'unknown'}, workflow ID {workflow_id or 'unknown'}: workflow not found in registry"
            )
            return None

        return await workflow.get_status()

    async def list_workflow_statuses(self) -> List[Dict[str, Any]]:
        result = []
        for workflow in self._workflows.values():
            # Get the workflow status directly to have consistent behavior
            status = await workflow.get_status()
            result.append(status)

        return result

    async def list_workflows(self) -> List["Workflow"]:
        return list(self._workflows.values())
