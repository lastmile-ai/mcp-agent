from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Mapping, Protocol, Type

import temporalio.activity
import temporalio.api.common.v1
import temporalio.client
import temporalio.converter
import temporalio.worker
import temporalio.workflow
from mcp_agent.logging.logger import get_logger
from mcp_agent.executor.temporal.temporal_context import (
    EXECUTION_ID_KEY,
    get_execution_id,
    set_execution_id,
)


class _InputWithHeaders(Protocol):
    headers: Mapping[str, temporalio.api.common.v1.Payload]


logger = get_logger(__name__)


def set_header_from_context(
    input: _InputWithHeaders, payload_converter: temporalio.converter.PayloadConverter
) -> None:
    execution_id_val = get_execution_id()

    if execution_id_val:
        input.headers = {
            **input.headers,
            EXECUTION_ID_KEY: payload_converter.to_payload(execution_id_val),
        }


@contextmanager
def context_from_header(
    input: _InputWithHeaders, payload_converter: temporalio.converter.PayloadConverter
):
    prev_exec_id = get_execution_id()
    execution_id_payload = input.headers.get(EXECUTION_ID_KEY)
    execution_id_from_header = (
        payload_converter.from_payload(execution_id_payload, str)
        if execution_id_payload
        else None
    )
    set_execution_id(execution_id_from_header if execution_id_from_header else None)

    try:
        yield
    finally:
        set_execution_id(prev_exec_id)


class ContextPropagationInterceptor(
    temporalio.client.Interceptor, temporalio.worker.Interceptor
):
    """Interceptor that propagates a value through client, workflow and activity calls.

    This interceptor implements methods `temporalio.client.Interceptor` and  `temporalio.worker.Interceptor` so that

    (1) an execution ID key is taken from context by the client code and sent in a header field with outbound requests
    (2) workflows take this value from their task input, set it in context, and propagate it into the header field of
        their outbound calls
    (3) activities similarly take the value from their task input and set it in context so that it's available for their
        outbound calls
    """

    def __init__(
        self,
        payload_converter: temporalio.converter.PayloadConverter = temporalio.converter.default().payload_converter,
    ) -> None:
        self._payload_converter = payload_converter

    def intercept_client(
        self, next: temporalio.client.OutboundInterceptor
    ) -> temporalio.client.OutboundInterceptor:
        return _ContextPropagationClientOutboundInterceptor(
            next, self._payload_converter
        )

    def intercept_activity(
        self, next: temporalio.worker.ActivityInboundInterceptor
    ) -> temporalio.worker.ActivityInboundInterceptor:
        return _ContextPropagationActivityInboundInterceptor(next)

    def workflow_interceptor_class(
        self, input: temporalio.worker.WorkflowInterceptorClassInput
    ) -> Type[_ContextPropagationWorkflowInboundInterceptor]:
        return _ContextPropagationWorkflowInboundInterceptor


class _ContextPropagationClientOutboundInterceptor(
    temporalio.client.OutboundInterceptor
):
    def __init__(
        self,
        next: temporalio.client.OutboundInterceptor,
        payload_converter: temporalio.converter.PayloadConverter,
    ) -> None:
        super().__init__(next)
        self._payload_converter = payload_converter

    async def start_workflow(
        self, input: temporalio.client.StartWorkflowInput
    ) -> temporalio.client.WorkflowHandle[Any, Any]:
        set_header_from_context(input, self._payload_converter)
        return await super().start_workflow(input)

    async def query_workflow(self, input: temporalio.client.QueryWorkflowInput) -> Any:
        set_header_from_context(input, self._payload_converter)
        return await super().query_workflow(input)

    async def signal_workflow(
        self, input: temporalio.client.SignalWorkflowInput
    ) -> None:
        set_header_from_context(input, self._payload_converter)
        await super().signal_workflow(input)

    async def start_workflow_update(
        self, input: temporalio.client.StartWorkflowUpdateInput
    ) -> temporalio.client.WorkflowUpdateHandle[Any]:
        set_header_from_context(input, self._payload_converter)
        return await self.next.start_workflow_update(input)


class _ContextPropagationActivityInboundInterceptor(
    temporalio.worker.ActivityInboundInterceptor
):
    async def execute_activity(
        self, input: temporalio.worker.ExecuteActivityInput
    ) -> Any:
        with context_from_header(input, temporalio.activity.payload_converter()):
            return await self.next.execute_activity(input)


class _ContextPropagationWorkflowInboundInterceptor(
    temporalio.worker.WorkflowInboundInterceptor
):
    def init(self, outbound: temporalio.worker.WorkflowOutboundInterceptor) -> None:
        self.next.init(_ContextPropagationWorkflowOutboundInterceptor(outbound))

    async def execute_workflow(
        self, input: temporalio.worker.ExecuteWorkflowInput
    ) -> Any:
        with context_from_header(input, temporalio.workflow.payload_converter()):
            return await self.next.execute_workflow(input)

    async def handle_signal(self, input: temporalio.worker.HandleSignalInput) -> None:
        with context_from_header(input, temporalio.workflow.payload_converter()):
            return await self.next.handle_signal(input)

    async def handle_query(self, input: temporalio.worker.HandleQueryInput) -> Any:
        with context_from_header(input, temporalio.workflow.payload_converter()):
            return await self.next.handle_query(input)

    def handle_update_validator(
        self, input: temporalio.worker.HandleUpdateInput
    ) -> None:
        with context_from_header(input, temporalio.workflow.payload_converter()):
            self.next.handle_update_validator(input)

    async def handle_update_handler(
        self, input: temporalio.worker.HandleUpdateInput
    ) -> Any:
        with context_from_header(input, temporalio.workflow.payload_converter()):
            return await self.next.handle_update_handler(input)


class _ContextPropagationWorkflowOutboundInterceptor(
    temporalio.worker.WorkflowOutboundInterceptor
):
    async def signal_child_workflow(
        self, input: temporalio.worker.SignalChildWorkflowInput
    ) -> None:
        set_header_from_context(input, temporalio.workflow.payload_converter())
        return await self.next.signal_child_workflow(input)

    async def signal_external_workflow(
        self, input: temporalio.worker.SignalExternalWorkflowInput
    ) -> None:
        set_header_from_context(input, temporalio.workflow.payload_converter())
        return await self.next.signal_external_workflow(input)

    def start_activity(
        self, input: temporalio.worker.StartActivityInput
    ) -> temporalio.workflow.ActivityHandle:
        set_header_from_context(input, temporalio.workflow.payload_converter())
        return self.next.start_activity(input)

    async def start_child_workflow(
        self, input: temporalio.worker.StartChildWorkflowInput
    ) -> temporalio.workflow.ChildWorkflowHandle:
        set_header_from_context(input, temporalio.workflow.payload_converter())
        return await self.next.start_child_workflow(input)

    def start_local_activity(
        self, input: temporalio.worker.StartLocalActivityInput
    ) -> temporalio.workflow.ActivityHandle:
        set_header_from_context(input, temporalio.workflow.payload_converter())
        return self.next.start_local_activity(input)
