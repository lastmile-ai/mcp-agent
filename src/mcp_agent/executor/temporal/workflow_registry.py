import asyncio

from typing import (
    Any,
    Dict,
    Optional,
    List,
    TYPE_CHECKING,
)

from mcp_agent.logging.logger import get_logger
from mcp_agent.executor.workflow_registry import WorkflowRegistry

if TYPE_CHECKING:
    from mcp_agent.executor.temporal import TemporalExecutor
    from mcp_agent.executor.workflow import Workflow

logger = get_logger(__name__)


class TemporalWorkflowRegistry(WorkflowRegistry):
    """
    Registry for tracking workflow instances in Temporal.
    This implementation queries Temporal for workflow status and manages workflows.
    """

    def __init__(self, executor: "TemporalExecutor"):
        super().__init__()
        self._executor = executor
        # We still keep a local cache for fast lookups, but the source of truth is Temporal
        self._local_workflows: Dict[str, "Workflow"] = {}  # run_id -> workflow
        self._workflow_ids: Dict[str, List[str]] = {}  # workflow_id -> list of run_ids

    async def register(
        self,
        workflow: "Workflow",
        run_id: str | None = None,
        workflow_id: str | None = None,
        task: Optional["asyncio.Task"] = None,
    ) -> None:
        self._local_workflows[run_id] = workflow

        # Add run_id to the list for this workflow_id
        if workflow_id not in self._workflow_ids:
            self._workflow_ids[workflow_id] = []
        self._workflow_ids[workflow_id].append(run_id)

    async def unregister(self, run_id: str, workflow_id: str | None = None) -> None:
        if run_id in self._local_workflows:
            workflow = self._local_workflows[run_id]
            workflow_id = workflow.name if workflow_id is None else workflow_id

            # Remove from workflow_ids mapping
            if workflow_id in self._workflow_ids:
                if run_id in self._workflow_ids[workflow_id]:
                    self._workflow_ids[workflow_id].remove(run_id)
                if not self._workflow_ids[workflow_id]:
                    del self._workflow_ids[workflow_id]

            # Remove workflow from local cache
            self._local_workflows.pop(run_id, None)

    async def get_workflow(
        self, run_id: str, workflow_id: str | None = None
    ) -> Optional["Workflow"]:
        return self._local_workflows.get(run_id)

    async def resume_workflow(
        self,
        run_id: str,
        workflow_id: str | None = None,
        signal_name: str | None = "resume",
        payload: Any | None = None,
    ) -> bool:
        # Ensure the Temporal client is connected
        await self._executor.ensure_client()

        try:
            workflow = await self.get_workflow(run_id)
            workflow_id = (
                workflow.name if workflow and workflow_id is None else workflow_id
            )

            if not workflow_id:
                # In Temporal, we need both workflow_id and run_id to target a specific run
                logger.error(
                    f"Workflow with run_id {run_id} not found in local registry and workflow_id not provided"
                )
                return False

            # Get the handle and send the signal
            handle = self._executor.client.get_workflow_handle(
                workflow_id=workflow_id, run_id=run_id
            )
            await handle.signal(signal_name, payload)

            logger.info(
                f"Sent signal {signal_name} to workflow {workflow_id} run {run_id}"
            )

            return True
        except Exception as e:
            logger.error(f"Error signaling workflow {run_id}: {e}")
            return False

    async def cancel_workflow(
        self, run_id: str, workflow_id: str | None = None
    ) -> bool:
        # Ensure the Temporal client is connected
        await self._executor.ensure_client()

        try:
            # Get the workflow from local registry
            workflow = await self.get_workflow(run_id)
            workflow_id = (
                workflow.name if workflow and workflow_id is None else workflow_id
            )

            if not workflow_id:
                # In Temporal, we need both workflow_id and run_id to target a specific run
                logger.error(
                    f"Workflow with run_id {run_id} not found in local registry and workflow_id not provided"
                )
                return False

            # Get the handle and cancel the workflow
            handle = self._executor.client.get_workflow_handle(
                workflow_id=workflow_id, run_id=run_id
            )
            await handle.cancel()
            logger.info(f"Cancelled workflow {workflow_id} run {run_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling workflow {run_id}: {e}")
            return False

    async def get_workflow_status(
        self, run_id: str, workflow_id: str | None = None
    ) -> Optional[Dict[str, Any]]:
        workflow = await self.get_workflow(run_id)
        workflow_id = (
            (workflow.id or workflow.name)
            if workflow and workflow_id is None
            else workflow_id
        )

        if not workflow_id:
            # In Temporal, we need both workflow_id and run_id to target a specific run
            logger.error(
                f"Workflow with run_id {run_id} not found in local registry and workflow_id not provided"
            )
            return False

        status_dict: Dict[str, Any] = {}

        if workflow:
            # If we have a local workflow, use its status, and merge with Temporal status
            status_dict = await workflow.get_status()

        # Query Temporal for the status
        temporal_status = await self._get_temporal_workflow_status(
            workflow_id=workflow_id, run_id=run_id
        )

        # Merge the local status with the Temporal status
        status_dict["temporal"] = temporal_status

        return status_dict

    async def list_workflow_statuses(self) -> List[Dict[str, Any]]:
        result = []
        for run_id, workflow in self._local_workflows.items():
            # Get the workflow status directly to have consistent behavior
            status = await workflow.get_status()
            workflow_id = workflow.id or workflow.name

            # Query Temporal for the status
            temporal_status = await self._get_temporal_workflow_status(
                workflow_id=workflow_id, run_id=run_id
            )

            status["temporal"] = temporal_status

            result.append(status)

        return result

    async def list_workflows(self) -> List["Workflow"]:
        """
        List all registered workflow instances.

        Returns:
            A list of workflow instances
        """
        return list(self._local_workflows.values())

    async def _get_temporal_workflow_status(
        self, workflow_id: str, run_id: str
    ) -> Dict[str, Any]:
        """
        Get the status of a workflow directly from Temporal.

        Args:
            workflow_id: The workflow ID
            run_id: The run ID

        Returns:
            A dictionary with workflow status information from Temporal
        """
        # Ensure the Temporal client is connected
        await self._executor.ensure_client()

        try:
            # Get the workflow handle and describe the workflow
            handle = self._executor.client.get_workflow_handle(
                workflow_id=workflow_id, run_id=run_id
            )

            # Get the workflow description
            describe = await handle.describe()

            # Convert to a dictionary with our standard format
            status = {
                "id": workflow_id,
                "workflow_id": workflow_id,
                "run_id": run_id,
                "name": describe.id,
                "type": describe.workflow_type,
                "status": describe.status.name,
                "start_time": describe.start_time.timestamp()
                if describe.start_time
                else None,
                "execution_time": describe.execution_time.timestamp()
                if describe.execution_time
                else None,
                "close_time": describe.close_time.timestamp()
                if describe.close_time
                else None,
                "history_length": describe.history_length,
                "parent_workflow_id": describe.parent_id,
                "parent_run_id": describe.parent_run_id,
            }

            return status
        except Exception as e:
            logger.error(f"Error getting temporal workflow status: {e}")
            # Return basic status with error information
            return {
                "id": workflow_id,
                "workflow_id": workflow_id,
                "run_id": run_id,
                "status": "ERROR",
                "error": str(e),
            }
