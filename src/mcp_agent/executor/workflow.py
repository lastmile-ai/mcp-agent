from abc import ABC, abstractmethod
from datetime import datetime
from typing import (
    Any,
    Dict,
    Generic,
    TypeVar,
    Union,
)

from pydantic import BaseModel, ConfigDict, Field

from mcp_agent.executor.executor import Executor

T = TypeVar("T")


class WorkflowState(BaseModel):
    """
    Simple container for persistent workflow state.
    This can hold fields that should persist across tasks.
    """

    status: str = "initialized"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: float | None = None
    error: Dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    def record_error(self, error: Exception) -> None:
        self.error = {
            "type": type(error).__name__,
            "message": str(error),
            "timestamp": datetime.utcnow().timestamp(),
        }


class WorkflowResult(BaseModel, Generic[T]):
    value: Union[T, None] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    start_time: float | None = None
    end_time: float | None = None


class Workflow(ABC, Generic[T]):
    """
    Base class for user-defined workflows.
    Handles execution and state management.
    Some key notes:
        - To enable the executor engine to recognize and orchestrate the workflow,
            - the class MUST be decorated with @workflow.
            - the main entrypoint method MUST be decorated with @workflow_run.
            - any task methods MUST be decorated with @workflow_task.

        - Persistent state: Provides a simple `state` object for storing data across tasks.
    """

    def __init__(
        self,
        executor: Executor,
        name: str | None = None,
        metadata: Dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        self.executor = executor
        self.name = name or self.__class__.__name__
        self.init_kwargs = kwargs
        # TODO: handle logging
        # self._logger = logging.getLogger(self.name)

        # A simple workflow state object
        # If under Temporal, storing it as a field on this class
        # means it can be replayed automatically
        self.state = WorkflowState(name=name, metadata=metadata or {})

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> "WorkflowResult[T]":
        """
        Main workflow implementation. Must be overridden by subclasses.
        """

    async def update_state(self, **kwargs):
        """Syntactic sugar to update workflow state."""
        for key, value in kwargs.items():
            self.state[key] = value
            setattr(self.state, key, value)

        self.state.updated_at = datetime.utcnow().timestamp()

    async def wait_for_input(self, description: str = "Provide input") -> str:
        """
        Convenience method for human input. Uses `human_input` signal
        so we can unify local (console input) and Temporal signals.
        """
        return await self.executor.wait_for_signal(
            "human_input", description=description
        )


# ############################
# # Example: DocumentWorkflow
# ############################


# @workflow_defn  # <-- This becomes @temporal_workflow.defn if in Temporal mode, else no-op
# class DocumentWorkflow(Workflow[List[Dict[str, Any]]]):
#     """
#     Example workflow with persistent state.
#     If run locally, `self.state` is ephemeral.
#     If run in Temporal mode, `self.state` is replayed automatically.
#     """

#     @workflow_task(
#         schedule_to_close_timeout=timedelta(minutes=10),
#         retry_policy={"initial_interval": 1, "max_attempts": 3},
#     )
#     async def process_document(self, doc_id: str) -> Dict[str, Any]:
#         """Activity that simulates document processing."""
#         await asyncio.sleep(1)
#         # Optionally mutate workflow state
#         self.state.metadata.setdefault("processed_docs", []).append(doc_id)
#         return {
#             "doc_id": doc_id,
#             "status": "processed",
#             "timestamp": datetime.utcnow().isoformat(),
#         }

#     @workflow_run  # <-- This becomes @temporal_workflow.run(...) if Temporal is used
#     async def _run_impl(
#         self, documents: List[str], batch_size: int = 2
#     ) -> List[Dict[str, Any]]:
#         """Main workflow logic, which becomes the official 'run' in Temporal mode."""
#         self._logger.info("Workflow starting, state=%s", self.state)
#         self.state.update_status("running")

#         all_results = []
#         for i in range(0, len(documents), batch_size):
#             batch = documents[i : i + batch_size]
#             tasks = [self.process_document(doc) for doc in batch]
#             results = await self.executor.execute(*tasks)

#             for res in results:
#                 if isinstance(res.value, Exception):
#                     self._logger.error(
#                         f"Error processing document: {res.metadata.get('error')}"
#                     )
#                 else:
#                     all_results.append(res.value)

#         self.state.update_status("completed")
#         return all_results


# ########################
# # 12. Example Local Usage
# ########################


# async def run_example_local():
#     from . import AsyncIOExecutor, DocumentWorkflow  # if in a package

#     executor = AsyncIOExecutor()
#     wf = DocumentWorkflow(executor)

#     documents = ["doc1", "doc2", "doc3", "doc4"]
#     result = await wf.run(documents, batch_size=2)

#     print("Local results:", result.value)
#     print("Local workflow final state:", wf.state)
#     # Notice `wf.state.metadata['processed_docs']` has the processed doc IDs.


# ########################
# # Example Temporal Usage
# ########################


# async def run_example_temporal():
#     from . import TemporalExecutor, DocumentWorkflow  # if in a package

#     # 1) Create a TemporalExecutor (client side)
#     executor = TemporalExecutor(task_queue="my_task_queue")
#     await executor.ensure_client()

#     # 2) Start a worker in the same process (or do so in a separate process)
#     asyncio.create_task(executor.start_worker())
#     await asyncio.sleep(2)  # Wait for worker to be up

#     # 3) Now we can run the workflow by normal means if we like,
#     #    or rely on the Worker picking it up. Typically, you'd do:
#     #    handle = await executor._client.start_workflow(...)
#     #    but let's keep it simple and show conceptually
#     #    that 'DocumentWorkflow' is now recognized as a real Temporal workflow
#     print(
#         "Temporal environment is running. Use the Worker logs or CLI to start 'DocumentWorkflow'."
#     )
