"""
A derived client session for the MCP Agent framework.
It adds logging and supports sampling requests.
"""

from datetime import timedelta
from typing import Any, Callable, Optional, TYPE_CHECKING
from opentelemetry import trace
from opentelemetry.propagate import inject


from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientNotification, ClientRequest, ClientSession
from mcp.shared.session import (
    ReceiveResultT,
    ReceiveNotificationT,
    RequestId,
    SendResultT,
    ProgressFnT,
)

from mcp.shared.context import RequestContext
from mcp.shared.message import MessageMetadata

from mcp.client.session import (
    ListRootsFnT,
    LoggingFnT,
    MessageHandlerFnT,
    SamplingFnT,
    ElicitationFnT,
)

from mcp.types import (
    CallToolRequestParams,
    CreateMessageRequest,
    CreateMessageRequestParams,
    CreateMessageResult,
    GetPromptRequestParams,
    ErrorData,
    Implementation,
    JSONRPCMessage,
    ServerRequest,
    ListRootsResult,
    NotificationParams,
    RequestParams,
    Root,
    ElicitRequestParams as MCPElicitRequestParams,
    ElicitRequest,
    ElicitResult,
    PaginatedRequestParams,
)

from mcp_agent.config import MCPServerSettings
from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.logging.logger import get_logger
from mcp_agent.tracing.semconv import (
    MCP_METHOD_NAME,
    MCP_PROMPT_NAME,
    MCP_REQUEST_ARGUMENT_KEY,
    MCP_REQUEST_ID,
    MCP_SESSION_ID,
    MCP_TOOL_NAME,
)
from mcp_agent.tracing.telemetry import get_tracer, record_attributes
from mcp_agent.mcp.sampling_handler import SamplingHandler

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class MCPAgentClientSession(ClientSession, ContextDependent):
    """
    MCP Agent framework acts as a client to the servers providing tools/resources/prompts for the agent workloads.
    This is a simple client session for those server connections, and supports
        - handling sampling requests
        - notifications
        - MCP root configuration

    Developers can extend this class to add more custom functionality as needed
    """

    def __init__(
        self,
        read_stream: MemoryObjectReceiveStream[JSONRPCMessage | Exception],
        write_stream: MemoryObjectSendStream[JSONRPCMessage],
        read_timeout_seconds: timedelta | None = None,
        sampling_callback: SamplingFnT | None = None,
        list_roots_callback: ListRootsFnT | None = None,
        elicitation_callback: ElicitationFnT | None = None,
        logging_callback: LoggingFnT | None = None,
        message_handler: MessageHandlerFnT | None = None,
        client_info: Implementation | None = None,
        context: Optional["Context"] = None,
    ):
        ContextDependent.__init__(self, context=context)

        if sampling_callback is None:
            sampling_callback = self._handle_sampling_callback
        if list_roots_callback is None:
            list_roots_callback = self._handle_list_roots_callback
        if elicitation_callback is None:
            elicitation_callback = self._handle_elicitation_callback

        ClientSession.__init__(
            self,
            read_stream=read_stream,
            write_stream=write_stream,
            read_timeout_seconds=read_timeout_seconds,
            sampling_callback=sampling_callback,
            list_roots_callback=list_roots_callback,
            logging_callback=logging_callback,
            message_handler=message_handler,
            client_info=client_info,
            elicitation_callback=elicitation_callback,
        )

        self.server_config: Optional[MCPServerSettings] = None
        self._sampling_handler = SamplingHandler(context=self.context)

        # Session ID handling for Streamable HTTP transport
        self._get_session_id_callback: Optional[Callable[[], str | None]] = None

    def set_session_id_callback(self, callback: Callable[[], str | None]) -> None:
        """
        Set the callback for retrieving the session ID.
        This is used by transports that support session IDs, like Streamable HTTP.

        Args:
            callback: A function that returns the current session ID or None
        """
        self._get_session_id_callback = callback
        logger.debug("Session ID callback set")

    def get_session_id(self) -> str | None:
        """
        Get the current session ID if available for this session's transport.

        Returns:
            The session ID if available, None otherwise
        """
        if self._get_session_id_callback:
            session_id = self._get_session_id_callback()
            logger.debug(f"Retrieved session ID: {session_id}")
            return session_id
        return None

    async def send_request(
        self,
        request: ClientRequest,
        result_type: type[ReceiveResultT],
        request_read_timeout_seconds: timedelta | None = None,
        metadata: MessageMetadata = None,
        progress_callback: ProgressFnT | None = None,
    ) -> ReceiveResultT:
        logger.debug("send_request: request=", data=request.model_dump())
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.send_request", kind=trace.SpanKind.CLIENT
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(MCP_SESSION_ID, self.get_session_id() or "unknown")
                span.set_attribute("result_type", str(result_type))
                span.set_attribute(MCP_METHOD_NAME, request.root.method)

                params = request.root.params
                if params:
                    if isinstance(params, GetPromptRequestParams):
                        span.set_attribute(MCP_PROMPT_NAME, params.name)
                        record_attributes(
                            span, params.arguments or {}, MCP_REQUEST_ARGUMENT_KEY
                        )
                    elif isinstance(params, CallToolRequestParams):
                        span.set_attribute(MCP_TOOL_NAME, params.name)
                        record_attributes(
                            span, params.arguments or {}, MCP_REQUEST_ARGUMENT_KEY
                        )
                    else:
                        record_attributes(
                            span, params.model_dump(), MCP_REQUEST_ARGUMENT_KEY
                        )

                # Propagate trace context in request.params._meta
                trace_headers = {}
                inject(trace_headers)
                if "traceparent" in trace_headers or "tracestate" in trace_headers:
                    if params is None:
                        params = PaginatedRequestParams(
                            cursor=None,
                            meta=RequestParams.Meta(
                                traceparent=trace_headers.get("traceparent"),
                                tracestate=trace_headers.get("tracestate"),
                            ),
                        )
                    else:
                        if params.meta is None:
                            params.meta = RequestParams.Meta(
                                traceparent=trace_headers.get("traceparent"),
                                tracestate=trace_headers.get("tracestate"),
                            )
                    request.root = request.root.model_copy(update={"params": params})

                if metadata and metadata.resumption_token:
                    span.set_attribute(
                        "metadata.resumption_token", metadata.resumption_token
                    )
                if request_read_timeout_seconds is not None:
                    span.set_attribute(
                        "request_read_timeout_seconds",
                        str(request_read_timeout_seconds),
                    )

            try:
                result = await super().send_request(
                    request,
                    result_type,
                    request_read_timeout_seconds,
                    metadata,
                    progress_callback,
                )
                res_data = result.model_dump()
                logger.debug("send_request: response=", data=res_data)

                if self.context.tracing_enabled:
                    record_attributes(span, res_data, "result")

                return result
            except Exception as e:
                logger.error(f"send_request failed: {e}")
                raise

    async def send_notification(
        self,
        notification: ClientNotification,
        related_request_id: RequestId | None = None,
    ) -> None:
        logger.debug("send_notification:", data=notification.model_dump())
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.send_notification", kind=trace.SpanKind.CLIENT
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(MCP_SESSION_ID, self.get_session_id() or "unknown")
                span.set_attribute(MCP_METHOD_NAME, notification.root.method)
                if related_request_id:
                    span.set_attribute(MCP_REQUEST_ID, str(related_request_id))

                params = notification.root.params
                if params:
                    record_attributes(
                        span,
                        params.model_dump(),
                        MCP_REQUEST_ARGUMENT_KEY,
                    )

                # Propagate trace context in request.params._meta
                trace_headers = {}
                inject(trace_headers)
                if "traceparent" in trace_headers or "tracestate" in trace_headers:
                    if params is None:
                        params = NotificationParams()
                    if params.meta is None:
                        params.meta = NotificationParams.Meta()
                    if "traceparent" in trace_headers:
                        params.meta.traceparent = trace_headers["traceparent"]
                    if "tracestate" in trace_headers:
                        params.meta.tracestate = trace_headers["tracestate"]
                    notification.root.params = params

            try:
                return await super().send_notification(notification, related_request_id)
            except Exception as e:
                logger.error("send_notification failed", data=e)
                raise

    async def _send_response(
        self, request_id: RequestId, response: SendResultT | ErrorData
    ) -> None:
        logger.debug(
            f"send_response: request_id={request_id}, response=",
            data=response.model_dump(),
        )
        return await super()._send_response(request_id, response)

    async def _received_notification(self, notification: ReceiveNotificationT) -> None:
        """
        Can be overridden by subclasses to handle a notification without needing
        to listen on the message stream.
        """
        logger.info(
            "_received_notification: notification=",
            data=notification.model_dump(),
        )
        return await super()._received_notification(notification)

    async def send_progress_notification(
        self,
        progress_token: str | int,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        """
        Sends a progress notification for a request that is currently being
        processed.
        """
        logger.debug(
            f"send_progress_notification: progress_token={progress_token}, progress={progress}, total={total}, message={message}"
        )

        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.send_progress_notification",
            kind=trace.SpanKind.CLIENT,
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute(MCP_SESSION_ID, self.get_session_id() or "unknown")
                span.set_attribute(MCP_METHOD_NAME, "notifications/progress")
                span.set_attribute("progress_token", progress_token)
                span.set_attribute("progress", progress)
                if total is not None:
                    span.set_attribute("total", total)
                if message:
                    span.set_attribute("message", message)

            return await super().send_progress_notification(
                progress_token=progress_token,
                progress=progress,
                total=total,
                message=message,
            )

    async def _handle_sampling_callback(
        self,
        context: RequestContext["ClientSession", Any],
        params: CreateMessageRequestParams,
    ) -> CreateMessageResult | ErrorData:
        logger.debug(f"Handling sampling request: {params}")
        server_session = self.context.upstream_session
        if server_session is not None:
            try:
                # If a server_session is available, we'll pass-through the sampling request to the upstream client
                result = await server_session.send_request(
                    request=ServerRequest(
                        CreateMessageRequest(
                            method="sampling/createMessage", params=params
                        )
                    ),
                    result_type=CreateMessageResult,
                )
                # Pass the result from the upstream client back to the server. We just act as a pass-through client here.
                return result
            except Exception as e:
                return ErrorData(code=-32603, message=str(e))
        else:
            # No upstream session: handle locally via SamplingHandler
            return await self._sampling_handler.handle_sampling(params=params)

    async def _handle_elicitation_callback(
        self,
        context: RequestContext["ClientSession", Any],
        params: MCPElicitRequestParams,
    ) -> ElicitResult | ErrorData:
        """Handle elicitation requests by prompting user for input via console."""
        logger.info("Handling elicitation request", data=params.model_dump())

        try:
            # Prefer upstream pass-through when an upstream session exists
            server_session = self.context.upstream_session
            if server_session is not None:
                try:
                    result = await server_session.send_request(
                        request=ServerRequest(
                            ElicitRequest(method="elicitation/create", params=params)
                        ),
                        result_type=ElicitResult,
                    )
                    return result
                except Exception as e:
                    logger.warning(
                        f"Upstream elicitation forwarding failed; falling back locally: {e}"
                    )

            if not self.context.elicitation_handler:
                logger.error(
                    "No elicitation handler configured for elicitation. Rejecting elicitation."
                )
                return ElicitResult(action="decline")

            server_name = None
            if hasattr(self, "server_config") and self.server_config:
                server_name = getattr(self.server_config, "name", None)

            elicitation_request = params.model_copy(update={"server_name": server_name})
            elicitation_response = await self.context.elicitation_handler(
                elicitation_request
            )
            return elicitation_response
        except KeyboardInterrupt:
            logger.info("User cancelled elicitation")
            return ElicitResult(action="cancel")
        except TimeoutError:
            logger.info("Elicitation timed out")
            return ElicitResult(action="cancel")
        except Exception as e:
            logger.error(f"Error handling elicitation: {e}")
            return ErrorData(
                code=-32603, message=f"Failed to handle elicitation: {str(e)}"
            )

    async def _handle_list_roots_callback(
        self,
        context: RequestContext["ClientSession", Any],
    ) -> ListRootsResult | ErrorData:
        # Handle list_roots request by returning configured roots
        if hasattr(self, "server_config") and self.server_config.roots:
            roots = [
                Root(
                    uri=root.server_uri_alias or root.uri,
                    name=root.name,
                )
                for root in self.server_config.roots
            ]

            return ListRootsResult(roots=roots)
        else:
            return ListRootsResult(roots=[])
