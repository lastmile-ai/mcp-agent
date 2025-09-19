from contextlib import AbstractAsyncContextManager
from typing import AsyncIterator
import warnings
import temporalio
from temporalio.worker import (
    Plugin as WorkerPlugin,
    Replayer,
    ReplayerConfig,
    Worker,
    WorkerConfig,
    WorkflowReplayResult,
)
from temporalio.client import ClientConfig, Plugin as ClientPlugin, WorkflowHistory
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
from temporalio.contrib.pydantic import (
    PydanticPayloadConverter,
    pydantic_data_converter,
)
from temporalio.converter import DataConverter, DefaultPayloadConverter
from temporalio.service import ConnectConfig, ServiceClient
from temporalio.contrib.opentelemetry import TracingInterceptor
from mcp_agent.executor.temporal.interceptor import ContextPropagationInterceptor


class MCPAgentPlugin(ClientPlugin, WorkerPlugin):
    """Temporal client and worker plugin for Pydantic AI."""

    def init_client_plugin(self, next: ClientPlugin) -> None:
        self.next_client_plugin = next

    def init_worker_plugin(self, next: WorkerPlugin) -> None:
        self.next_worker_plugin = next

    def configure_client(self, config: ClientConfig) -> ClientConfig:
        config["data_converter"] = self._get_new_data_converter(
            config.get("data_converter")
        )
        config["interceptors"] = list(config.get("interceptors") or []) + [
            TracingInterceptor(),
            ContextPropagationInterceptor(),
        ]
        config["namespace"] = ...
        return self.next_client_plugin.configure_client(config)

    async def connect_service_client(self, config: ConnectConfig) -> ServiceClient:
        config.api_key = ...
        config.tls = ...
        config.target_host = ...
        config.rpc_metadata = ...
        return await self.next_client_plugin.connect_service_client(config)

    def configure_worker(self, config: WorkerConfig) -> WorkerConfig:
        # TODO: jerron - insert compulsory activities here
        config["activities"] = list(config.get("activities") or [])
        config["interceptors"] = list(config.get("interceptors") or []) + [
            ContextPropagationInterceptor(),
        ]
        config["task_queue"] = ...
        config["workflows"] = ...
        config["client"] = ...
        return self.next_worker_plugin.configure_worker(config)

    async def run_worker(self, worker: Worker) -> None:
        await self.next_worker_plugin.run_worker(worker)

    def configure_replayer(self, config: ReplayerConfig) -> ReplayerConfig:
        config["data_converter"] = self._get_new_data_converter(
            config.get("data_converter")
        )
        return self.next_worker_plugin.configure_replayer(config)

    def run_replayer(
        self,
        replayer: Replayer,
        histories: AsyncIterator[WorkflowHistory],
    ) -> AbstractAsyncContextManager[AsyncIterator[WorkflowReplayResult]]:
        return self.next_worker_plugin.run_replayer(replayer, histories)

    def _get_new_data_converter(self, converter: DataConverter | None) -> DataConverter:
        if converter and converter.payload_converter_class not in (
            DefaultPayloadConverter,
            PydanticPayloadConverter,
        ):
            warnings.warn(
                "A non-default Temporal data converter was used which has been replaced with the Pydantic data converter."
            )

        return pydantic_data_converter
