import asyncio
import base64
from datetime import datetime, timedelta
from typing import (
    Any,
    Dict,
    Optional,
    List,
    TYPE_CHECKING,
)

from mcp_agent.logging.logger import get_logger
from mcp_agent.executor.workflow_registry import WorkflowRegistry, WorkflowRunsPage

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

        workflow_id = workflow_id or workflow.id or workflow.name

        # Add run_id to the list for this workflow_id
        if workflow_id not in self._workflow_ids:
            self._workflow_ids[workflow_id] = []
        self._workflow_ids[workflow_id].append(run_id)

    async def unregister(self, run_id: str, workflow_id: str | None = None) -> None:
        if run_id in self._local_workflows:
            workflow = self._local_workflows[run_id]
            workflow_id = workflow_id or workflow.id or workflow.name

            # Remove from workflow_ids mapping
            if workflow_id in self._workflow_ids:
                if run_id in self._workflow_ids[workflow_id]:
                    self._workflow_ids[workflow_id].remove(run_id)
                if not self._workflow_ids[workflow_id]:
                    del self._workflow_ids[workflow_id]

            # Remove workflow from local cache
            self._local_workflows.pop(run_id, None)

    async def get_workflow(
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> Optional["Workflow"]:
        if not (run_id or workflow_id):
            raise ValueError("Either run_id or workflow_id must be provided.")
        if run_id:
            return self._local_workflows.get(run_id)
        if workflow_id:
            run_ids = self._workflow_ids.get(workflow_id, [])
            if run_ids:
                return self._local_workflows.get(run_ids[-1])
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

        # Ensure the Temporal client is connected
        await self._executor.ensure_client()

        try:
            workflow = await self.get_workflow(run_id, workflow_id)
            if workflow and not workflow_id:
                workflow_id = workflow.id or workflow.name

            # For temporal operations, we need to have both workflow_id and run_id
            if not workflow_id:
                logger.error(
                    f"Cannot resume workflow: workflow_id not found for run_id {run_id or 'unknown'}"
                )
                return False

            if not run_id:
                # Get the run_id from the workflow_ids dict if we have a workflow_id
                run_ids = self._workflow_ids.get(workflow_id, [])
                if run_ids:
                    run_id = run_ids[-1]  # Use the latest run

            if not run_id:
                logger.error(
                    f"Cannot resume workflow: run_id not found for workflow_id {workflow_id}"
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
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> bool:
        if not (run_id or workflow_id):
            raise ValueError("Either run_id or workflow_id must be provided.")

        # Ensure the Temporal client is connected
        await self._executor.ensure_client()

        try:
            workflow = await self.get_workflow(run_id, workflow_id)
            if workflow and not workflow_id:
                workflow_id = workflow.id or workflow.name

            # For temporal operations, we need to have both workflow_id and run_id
            if not workflow_id:
                logger.error(
                    f"Cannot cancel workflow: workflow_id not found for run_id {run_id or 'unknown'}"
                )
                return False

            if not run_id:
                # Get the run_id from the workflow_ids dict if we have a workflow_id
                run_ids = self._workflow_ids.get(workflow_id, [])
                if run_ids:
                    run_id = run_ids[-1]  # Use the latest run

            if not run_id:
                logger.error(
                    f"Cannot cancel workflow: run_id not found for workflow_id {workflow_id}"
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
        self, run_id: str | None = None, workflow_id: str | None = None
    ) -> Optional[Dict[str, Any]]:
        if not (run_id or workflow_id):
            raise ValueError("Either run_id or workflow_id must be provided.")

        workflow = await self.get_workflow(run_id, workflow_id)
        if workflow and not workflow_id:
            workflow_id = workflow.id or workflow.name

        # For temporal operations, we need to have both workflow_id and run_id
        if not workflow_id:
            logger.error(
                f"Cannot get status: workflow_id not found for run_id {run_id or 'unknown'}"
            )
            return False

        if not run_id:
            # Get the run_id from the workflow_ids dict if we have a workflow_id
            run_ids = self._workflow_ids.get(workflow_id, [])
            if run_ids:
                run_id = run_ids[-1]  # Use the latest run

        if not run_id:
            logger.error(
                f"Cannot get status: run_id not found for workflow_id {workflow_id}"
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

    async def list_workflow_statuses(
        self,
        *,
        query: str | None = None,
        limit: int | None = None,
        page_size: int | None = None,
        next_page_token: bytes | None = None,
        rpc_metadata: Dict[str, str] | None = None,
        rpc_timeout: timedelta | None = None,
    ) -> List[Dict[str, Any]] | WorkflowRunsPage:
        """
        List workflow runs by querying Temporal visibility (preferred).

        - When Temporal listing succeeds, only runs returned by Temporal are included; local
          cache is used to enrich entries where possible.
        - On failure or when listing is unsupported, fall back to locally tracked runs.

        Args:
            query: Optional Temporal visibility list filter; defaults to newest first when unset.
            limit: Maximum number of runs to return; enforced locally if backend doesn't apply it.
            page_size: Page size to request from Temporal, if supported by SDK version.
            next_page_token: Opaque pagination token from prior call, if supported by SDK version.
            rpc_metadata: Optional per-RPC headers for Temporal (not exposed via server tool).
            rpc_timeout: Optional per-RPC timeout (not exposed via server tool).

        Returns:
            A list of dictionaries with workflow information, or a WorkflowRunsPage object.
        """
        results: List[Dict[str, Any]] = []

        # Collect all executions for this task queue (best effort)
        try:
            await self._executor.ensure_client()
            client = self._executor.client

            # TODO(saqadri): Multi-user auth scoping
            # When supporting multiple users on one server, auth scoping should be enforced
            # by the proxy layer using RPC metadata (e.g., API key). This client code should
            # simply pass through rpc_metadata and let the backend filter results and manage
            # pagination accordingly.
            iterator = client.list_workflows(
                query=query,
                limit=limit,
                page_size=page_size or 1000,
                next_page_token=next_page_token,
                rpc_metadata=rpc_metadata or {},
                rpc_timeout=rpc_timeout,
            )

            # Build quick lookup from local cache by (workflow_id, run_id)
            in_memory_workflows: Dict[tuple[str, str], "Workflow"] = {}
            for run_id, wf in self._local_workflows.items():
                workflow_id = wf.id or wf.name
                if workflow_id and run_id:
                    in_memory_workflows[(workflow_id, run_id)] = wf

            count = 0
            max_count = limit if isinstance(limit, int) and limit > 0 else None

            async for workflow_info in iterator:
                # Extract workflow_id and run_id robustly from various shapes
                workflow_id = workflow_info.id
                run_id = workflow_info.run_id

                if not workflow_id or not run_id:
                    # Can't build a handle without both IDs
                    continue

                # If we have a local workflow, start with its detailed status
                wf = in_memory_workflows.get((workflow_id, run_id))
                if wf is not None:
                    status_dict = await wf.get_status()
                else:
                    # Create a minimal status when not tracked locally
                    status_dict = {
                        "id": run_id,
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "name": workflow_info.workflow_type or workflow_id,
                        "status": "unknown",
                        "running": False,
                        "state": {"status": "unknown", "metadata": {}, "error": None},
                    }

                temporal_status: Dict[str, Any] = {}
                try:
                    status: str | None = None
                    if workflow_info.status:
                        status = (
                            workflow_info.status.name
                            if workflow_info.status.name
                            else str(workflow_info.status)
                        )

                    start_time = workflow_info.start_time
                    close_time = workflow_info.close_time
                    execution_time = workflow_info.execution_time

                    def _to_timestamp(dt: datetime | None):
                        if dt is None:
                            return None
                        try:
                            if isinstance(dt, (int, float)):
                                return float(dt)
                            return dt.timestamp()
                        except Exception:
                            return None

                    workflow_type = workflow_info.workflow_type

                    temporal_status = {
                        "id": workflow_id,
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "name": workflow_info.id,
                        "type": workflow_type,
                        "status": status,
                        "start_time": _to_timestamp(start_time),
                        "execution_time": _to_timestamp(execution_time),
                        "close_time": _to_timestamp(close_time),
                        "history_length": workflow_info.history_length,
                        "parent_workflow_id": workflow_info.parent_id,
                        "parent_run_id": workflow_info.parent_run_id,
                    }
                except Exception:
                    temporal_status = await self._get_temporal_workflow_status(
                        workflow_id=workflow_id, run_id=run_id
                    )

                status_dict["temporal"] = temporal_status

                # Reflect Temporal status into top-level summary
                try:
                    ts = (
                        temporal_status.get("status")
                        if isinstance(temporal_status, dict)
                        else None
                    )
                    if isinstance(ts, str):
                        status_dict["status"] = ts.lower()
                        status_dict["running"] = ts.upper() in {"RUNNING", "OPEN"}
                except Exception:
                    pass

                results.append(status_dict)
                count += 1
                if max_count is not None and count >= max_count:
                    break

            token = getattr(iterator, "next_page_token", None)
            if token:
                if isinstance(token, str):
                    try:
                        token = token.encode("utf-8")
                    except Exception:
                        token = None
            if token:
                return WorkflowRunsPage(
                    runs=results,
                    next_page_token=base64.b64encode(token).decode("ascii"),
                )
            else:
                return results
        except Exception as e:
            logger.warning(
                f"Error listing workflows from Temporal; falling back to local cache: {e}"
            )
            # Fallback – return local cache augmented with Temporal describe where possible
            for run_id, wf in self._local_workflows.items():
                status = await wf.get_status()
                workflow_id = wf.id or wf.name
                try:
                    status["temporal"] = await self._get_temporal_workflow_status(
                        workflow_id=workflow_id, run_id=run_id
                    )
                except Exception:
                    # This is expected if we couldn't get a hold of the temporal client
                    pass

                results.append(status)
            return results

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
