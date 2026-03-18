import asyncio
import functools
import json
from typing import TYPE_CHECKING, AsyncIterator, Type
from boto3 import Session

from pydantic import BaseModel

from mcp.types import (
    CallToolRequestParams,
    CallToolRequest,
    EmbeddedResource,
    ImageContent,
    ModelPreferences,
    TextContent,
    TextResourceContents,
    BlobResourceContents,
)
from mcp_agent.config import BedrockSettings
from mcp_agent.executor.workflow_task import workflow_task
from mcp_agent.utils.common import typed_dict_extras
from mcp_agent.utils.pydantic_type_serializer import serialize_model, deserialize_model
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    ModelT,
    MCPMessageParam,
    MCPMessageResult,
    ProviderToMCPConverter,
    RequestParams,
)
from mcp_agent.workflows.llm.streaming_events import StreamEvent, StreamEventType
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.multipart_converter_bedrock import BedrockConverter
from mcp_agent.tracing.token_tracking_decorator import track_tokens

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime.type_defs import (
        MessageOutputTypeDef,
        ConverseRequestTypeDef,
        ConverseResponseTypeDef,
        MessageUnionTypeDef,
        ContentBlockUnionTypeDef,
        ToolConfigurationTypeDef,
    )
else:
    MessageOutputTypeDef = object
    ConverseRequestTypeDef = object
    ConverseResponseTypeDef = object
    MessageUnionTypeDef = object
    ContentBlockUnionTypeDef = object
    ToolConfigurationTypeDef = object


class BedrockAugmentedLLM(AugmentedLLM[MessageUnionTypeDef, MessageUnionTypeDef]):
    """
    The basic building block of agentic systems is an LLM enhanced with augmentations
    such as retrieval, tools, and memory provided from a collection of MCP servers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, type_converter=BedrockMCPTypeConverter, **kwargs)

        self.provider = "Amazon Bedrock"
        # Initialize logger with name if available
        self.logger = get_logger(f"{__name__}.{self.name}" if self.name else __name__)

        self.model_preferences = self.model_preferences or ModelPreferences(
            costPriority=0.3,
            speedPriority=0.4,
            intelligencePriority=0.3,
        )
        # Get default model from config if available
        default_model = "us.amazon.nova-lite-v1:0"  # Fallback default

        if self.context.config.bedrock:
            if hasattr(self.context.config.bedrock, "default_model"):
                default_model = self.context.config.bedrock.default_model
        else:
            self.logger.error(
                "Bedrock configuration not found. Please provide Bedrock configuration."
            )
            raise ValueError(
                "Bedrock configuration not found. Please provide Bedrock configuration."
            )

        self.default_request_params = self.default_request_params or RequestParams(
            model=default_model,
            modelPreferences=self.model_preferences,
            maxTokens=4096,
            systemPrompt=self.instruction,
            parallel_tool_calls=True,
            max_iterations=10,
            use_history=True,
        )

    @classmethod
    def get_provider_config(cls, context):
        return getattr(getattr(context, "config", None), "bedrock", None)

    @track_tokens()
    async def generate(self, message, request_params: RequestParams | None = None):
        """
        Process a query using an LLM and available tools.
        The default implementation uses AWS Nova's ChatCompletion as the LLM.
        Override this method to use a different LLM.
        """

        messages: list[MessageUnionTypeDef] = []
        params = self.get_request_params(request_params)

        if params.use_history:
            messages.extend(self.history.get())

        messages.extend(BedrockConverter.convert_mixed_messages_to_bedrock(message))

        response = await self.agent.list_tools(tool_filter=params.tool_filter)

        tool_config: ToolConfigurationTypeDef = {
            "tools": [
                {
                    "toolSpec": {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": {"json": tool.inputSchema},
                    }
                }
                for tool in response.tools
            ],
            "toolChoice": {"auto": {}},
        }

        responses: list[MessageUnionTypeDef] = []
        model = await self.select_model(params)

        for i in range(params.max_iterations):
            inference_config = {
                "maxTokens": params.maxTokens,
                "temperature": params.temperature,
                "stopSequences": params.stopSequences or [],
            }

            system_content = [
                {
                    "text": self.instruction or params.systemPrompt,
                }
            ]

            arguments: ConverseRequestTypeDef = {
                "modelId": model,
                "messages": messages,
                "system": system_content,
                "inferenceConfig": inference_config,
            }

            if isinstance(tool_config["tools"], list) and len(tool_config["tools"]) > 0:
                arguments["toolConfig"] = tool_config

            if params.metadata:
                arguments = {
                    **arguments,
                    "additionalModelRequestFields": params.metadata,
                }

            self.logger.debug("Completion request arguments:", data=arguments)
            self._log_chat_progress(chat_turn=(len(messages) + 1) // 2, model=model)

            response: ConverseResponseTypeDef = await self.executor.execute(
                BedrockCompletionTasks.request_completion_task,
                RequestCompletionRequest(
                    config=self.context.config.bedrock,
                    payload=arguments,
                ),
            )

            if isinstance(response, BaseException):
                self.logger.error(f"Error: {response}")
                break

            self.logger.debug(f"{model} response:", data=response)

            response_as_message = self.convert_message_to_message_param(
                response["output"]["message"]
            )

            messages.append(response_as_message)
            responses.append(response["output"]["message"])

            if response["stopReason"] == "end_turn":
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is 'end_turn'"
                )
                break
            elif response["stopReason"] == "stop_sequence":
                # We have reached a stop sequence
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is 'stop_sequence'"
                )
                break
            elif response["stopReason"] == "max_tokens":
                # We have reached the max tokens limit
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is 'max_tokens'"
                )
                # TODO: saqadri - would be useful to return the reason for stopping to the caller
                break
            elif response["stopReason"] == "guardrail_intervened":
                # Guardrail intervened
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is 'guardrail_intervened'"
                )
                break
            elif response["stopReason"] == "content_filtered":
                # Content filtered
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is 'content_filtered'"
                )
                break
            elif response["stopReason"] == "tool_use":
                # Collect all tool results first
                tool_results = []

                for content in response["output"]["message"]["content"]:
                    if content.get("toolUse"):
                        tool_use_block = content["toolUse"]
                        tool_name = tool_use_block["name"]
                        tool_args = self._parse_tool_input(tool_use_block["input"])
                        tool_use_id = tool_use_block["toolUseId"]

                        tool_call_request = CallToolRequest(
                            method="tools/call",
                            params=CallToolRequestParams(
                                name=tool_name, arguments=tool_args
                            ),
                        )

                        result = await self.call_tool(
                            request=tool_call_request, tool_call_id=tool_use_id
                        )

                        tool_results.append((tool_use_id, result))

                # Create a single message with all tool results
                if tool_results:
                    tool_result_message = BedrockConverter.create_tool_results_message(
                        tool_results
                    )

                    messages.append(tool_result_message)
                    responses.append(tool_result_message)

        if params.use_history:
            self.history.set(messages)

        self._log_chat_finished(model=model)

        return responses

    @staticmethod
    def _parse_tool_input(tool_input):
        """Parse tool input from JSON string to dict if needed.

        Bedrock streams tool input as a JSON string that needs parsing.
        Returns empty dict for None and empty strings (tools with no arguments).
        Falls back to the original value if parsing fails.
        """
        if tool_input is None:
            return {}
        if isinstance(tool_input, str):
            # Handle empty string as no arguments
            if tool_input == "":
                return {}
            try:
                return json.loads(tool_input)
            except json.JSONDecodeError:
                return tool_input
        return tool_input

    @track_tokens()
    async def generate_stream(
        self,
        message,
        request_params: RequestParams | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Stream LLM generation events using Bedrock's native streaming API.

        This method provides real-time updates during generation, including:
        - Text deltas as they're generated
        - Tool use events and execution
        - Iteration boundaries
        - Token usage per iteration
        """
        try:
            config = self.context.config
            messages: list[MessageUnionTypeDef] = []
            params = self.get_request_params(request_params)

            if params.use_history:
                messages.extend(self.history.get())

            messages.extend(BedrockConverter.convert_mixed_messages_to_bedrock(message))

            async def update_tools():
                response = await self.agent.list_tools(tool_filter=params.tool_filter)
                tool_config: ToolConfigurationTypeDef = {
                    "tools": [
                        {
                            "toolSpec": {
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": {"json": tool.inputSchema},
                            }
                        }
                        for tool in response.tools
                    ],
                    "toolChoice": {"auto": {}},
                }
                return tool_config
            tool_config = await update_tools()

            responses: list[MessageUnionTypeDef] = []
            model = await self.select_model(params)
            last_stop_reason = None

            # Track total token usage across all iterations
            total_input_tokens = 0
            total_output_tokens = 0

            for i in range(params.max_iterations):
                # Yield iteration start event
                yield StreamEvent(
                    type=StreamEventType.ITERATION_START,
                    iteration=i,
                    model=model,
                    metadata={"messages_count": len(messages)},
                )

                # Final iteration check: If we're on the last iteration and the previous
                # response was a tool call, inject a prompt to force a final answer.
                # This must happen BEFORE the API call (can't check after - we'd be past max).
                if (
                    i == params.max_iterations - 1
                    and responses
                    and last_stop_reason == "tool_use"
                ):
                    final_prompt_message: MessageUnionTypeDef = {
                        "role": "user",
                        "content": [
                            {
                                "text": """We've reached the maximum number of iterations.
                                Please stop using tools now and provide your final comprehensive answer based on all tool results so far.
                                At the beginning of your response, clearly indicate that your answer may be incomplete due to reaching the maximum number of tool usage iterations,
                                and explain what additional information you would have needed to provide a more complete answer."""
                            }
                        ],
                    }
                    messages.append(final_prompt_message)

                # Build inference config
                inference_config = {
                    "maxTokens": params.maxTokens,
                    "temperature": params.temperature,
                    "stopSequences": params.stopSequences or [],
                }

                # Build system content
                system_content = [
                    {
                        "text": self.instruction or params.systemPrompt,
                    }
                ]

                # Build request arguments
                arguments: ConverseRequestTypeDef = {
                    "modelId": model,
                    "messages": messages,
                    "system": system_content,
                    "inferenceConfig": inference_config,
                }

                if tool_config["tools"]:
                    arguments["toolConfig"] = tool_config

                self.logger.debug("Streaming request arguments:", data=arguments)
                self._log_chat_progress(chat_turn=(len(messages) + 1) // 2, model=model)

                # Create Bedrock client
                bedrock_config = config.bedrock if config.bedrock else BedrockSettings()
                session = Session(profile_name=bedrock_config.profile)
                bedrock_client = session.client(
                    "bedrock-runtime",
                    aws_access_key_id=bedrock_config.aws_access_key_id,
                    aws_secret_access_key=bedrock_config.aws_secret_access_key,
                    aws_session_token=bedrock_config.aws_session_token,
                    region_name=bedrock_config.aws_region,
                )

                # Use native streaming API (run in executor since boto3 is synchronous)
                loop = asyncio.get_running_loop()
                stream_response = await loop.run_in_executor(
                    None, functools.partial(bedrock_client.converse_stream, **arguments)
                )

                # Process streaming events and build final message
                stop_reason = None
                response_content: list[ContentBlockUnionTypeDef] = []
                current_text_block = ""
                current_tool_use_block = None
                usage_data = {}

                for event in stream_response["stream"]:
                    # Handle content block start
                    if "contentBlockStart" in event:
                        block_start = event["contentBlockStart"]
                        if "toolUse" in block_start.get("start", {}):
                            current_tool_use_block = dict(block_start["start"]["toolUse"])

                    # Handle text deltas
                    elif "contentBlockDelta" in event:
                        delta = event["contentBlockDelta"]["delta"]
                        if "text" in delta:
                            text_delta = delta["text"]
                            current_text_block += text_delta
                            yield StreamEvent(
                                type=StreamEventType.TEXT_DELTA,
                                content=text_delta,
                                iteration=i,
                                model=model,
                            )
                        elif "toolUse" in delta:
                            # Accumulate tool use input
                            if current_tool_use_block:
                                if "input" not in current_tool_use_block:
                                    current_tool_use_block["input"] = ""
                                current_tool_use_block["input"] += delta["toolUse"].get(
                                    "input", ""
                                )

                    # Handle content block stop
                    elif "contentBlockStop" in event:
                        # Finalize current block
                        if current_text_block:
                            response_content.append({"text": current_text_block})
                            current_text_block = ""
                        elif current_tool_use_block:
                            # Parse tool input JSON string to dict for message history
                            current_tool_use_block["input"] = self._parse_tool_input(
                                current_tool_use_block.get("input")
                            )
                            response_content.append({"toolUse": current_tool_use_block})
                            current_tool_use_block = None

                    # Handle message stop
                    elif "messageStop" in event:
                        stop_reason = event["messageStop"]["stopReason"]
                        last_stop_reason = stop_reason
                        # Don't break - continue to receive metadata event

                    # Handle metadata event for usage
                    elif "metadata" in event:
                        usage_data = event["metadata"].get("usage", {})
                        break  # Now we can break after receiving usage

                # Get usage from captured metadata event
                usage = usage_data
                iteration_input = usage.get("inputTokens", 0)
                iteration_output = usage.get("outputTokens", 0)

                # Build response message
                response_message: MessageUnionTypeDef = {
                    "role": "assistant",
                    "content": response_content,
                }

                self.logger.debug(f"{model} response:", data=response_message)

                # Add response to messages
                messages.append(response_message)
                responses.append(response_message)

                # Accumulate total token usage
                total_input_tokens += iteration_input
                total_output_tokens += iteration_output

                # Token tracking
                if self.context.token_counter:
                    await self.context.token_counter.record_usage(
                        input_tokens=iteration_input,
                        output_tokens=iteration_output,
                        model_name=model,
                        provider=self.provider,
                    )

                # Yield iteration end event with usage
                yield StreamEvent(
                    type=StreamEventType.ITERATION_END,
                    iteration=i,
                    model=model,
                    stop_reason=stop_reason,
                    usage={
                        "input_tokens": iteration_input,
                        "output_tokens": iteration_output,
                    },
                )

                # Handle stop reasons
                if stop_reason in ["end_turn", "stop_sequence", "max_tokens"]:
                    self.logger.debug(
                        f"Iteration {i}: Stopping because stopReason is '{stop_reason}'"
                    )
                    break
                elif stop_reason == "tool_use":
                    # Collect all tool results first
                    tool_results = []

                    for content in response_message["content"]:
                        if content.get("toolUse"):
                            tool_use_block = content["toolUse"]
                            tool_name = tool_use_block["name"]
                            tool_args_raw = tool_use_block["input"]
                            tool_use_id = tool_use_block["toolUseId"]

                            # Parse tool args if it's a JSON string
                            tool_args = self._parse_tool_input(tool_args_raw)

                            # Yield tool use start event
                            yield StreamEvent(
                                type=StreamEventType.TOOL_USE_START,
                                content={
                                    "name": tool_name,
                                    "input": tool_args,
                                },
                                iteration=i,
                                model=model,
                                metadata={"tool_id": tool_use_id},
                            )

                            # Execute tool
                            tool_call_request = CallToolRequest(
                                method="tools/call",
                                params=CallToolRequestParams(
                                    name=tool_name, arguments=tool_args
                                ),
                            )

                            result = await self.call_tool(
                                request=tool_call_request, tool_call_id=tool_use_id
                            )

                            # Yield tool result event
                            yield StreamEvent(
                                type=StreamEventType.TOOL_RESULT,
                                content={
                                    "result": str(result.content),
                                    "is_error": result.isError,
                                },
                                iteration=i,
                                model=model,
                                metadata={"tool_id": tool_use_id},
                            )

                            # Collect tool result
                            tool_results.append((tool_use_id, result))

                            # Yield tool use end event
                            yield StreamEvent(
                                type=StreamEventType.TOOL_USE_END,
                                iteration=i,
                                model=model,
                                metadata={"tool_id": tool_use_id},
                            )

                    # Create a single message with all tool results
                    if tool_results:
                        tool_result_message = BedrockConverter.create_tool_results_message(
                            tool_results
                        )
                        messages.append(tool_result_message)

                    # Refresh tools to pick up any newly available tools enabled by previous execution
                    tool_config = await update_tools()

            # Update history
            if params.use_history:
                self.history.set(messages)

            self._log_chat_finished(model=model)

            # Note: Tracing attributes are set by the @track_tokens() decorator
            # Unlike Anthropic's implementation, Bedrock doesn't manually manage spans here

            # Yield completion event with total usage
            yield StreamEvent(
                type=StreamEventType.COMPLETE,
                model=model,
                usage={
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                },
                metadata={
                    "iterations": len(responses),
                },
            )

        except Exception as e:
            # Yield error event
            self.logger.error(f"Error during streaming generation: {e}")

            yield StreamEvent(
                type=StreamEventType.ERROR,
                content={"error": str(e), "type": type(e).__name__},
                metadata={"exception": str(e)},
            )

    async def generate_str(
        self,
        message,
        request_params: RequestParams | None = None,
    ):
        """
        Process a query using an LLM and available tools.
        The default implementation uses AWS Nova's ChatCompletion as the LLM.
        Override this method to use a different LLM.
        """
        responses = await self.generate(
            message=message,
            request_params=request_params,
        )

        final_text: list[str] = []

        for response in responses:
            for content in response["content"]:
                if content.get("text"):
                    final_text.append(content["text"])
                elif content.get("toolUse"):
                    final_text.append(
                        f"[Calling tool {content['toolUse']['name']} with args {content['toolUse']['input']}]"
                    )
                elif content.get("toolResult"):
                    final_text.append(
                        f"[Tool result: {content['toolResult']['content']}]"
                    )

        return "\n".join(final_text)

    async def generate_structured(
        self,
        message,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        response = await self.generate_str(
            message=message,
            request_params=request_params,
        )

        params = self.get_request_params(request_params)
        model = await self.select_model(params) or "us.amazon.nova-lite-v1:0"

        serialized_response_model: str | None = None

        if self.executor and self.executor.execution_engine == "temporal":
            # Serialize the response model to a string
            serialized_response_model = serialize_model(response_model)

        structured_response = await self.executor.execute(
            BedrockCompletionTasks.request_structured_completion_task,
            RequestStructuredCompletionRequest(
                config=self.context.config.bedrock,
                response_model=response_model
                if not serialized_response_model
                else None,
                serialized_response_model=serialized_response_model,
                response_str=response,
                params=params,
                model=model,
            ),
        )

        # TODO: saqadri (MAC) - fix request_structured_completion_task to return ensure_serializable
        # Convert dict back to the proper model instance if needed
        if isinstance(structured_response, dict):
            structured_response = response_model.model_validate(structured_response)

        return structured_response

    @classmethod
    def convert_message_to_message_param(
        cls, message: MessageOutputTypeDef, **kwargs
    ) -> MessageUnionTypeDef:
        """Convert a response object to an input parameter object to allow LLM calls to be chained."""
        return message

    def message_str(
        self, message: MessageUnionTypeDef, content_only: bool = False
    ) -> str:
        """Convert an output message to a string representation."""
        if message.get("content"):
            final_text: list[str] = []
            for content in message["content"]:
                if content.get("text"):
                    final_text.append(content["text"])
                else:
                    final_text.append(str(content))
            return "\n".join(final_text)
        elif content_only:
            # If content_only is True, return empty string if no content
            return ""

        return str(message)


class RequestCompletionRequest(BaseModel):
    config: BedrockSettings
    payload: dict


class RequestStructuredCompletionRequest(BaseModel):
    config: BedrockSettings
    params: RequestParams
    response_model: Type[ModelT] | None = None
    serialized_response_model: str | None = None
    response_str: str
    model: str


class BedrockCompletionTasks:
    @staticmethod
    @workflow_task
    async def request_completion_task(
        request: RequestCompletionRequest,
    ) -> ConverseResponseTypeDef:
        """
        Request a completion from Bedrock's API.
        """

        if request.config:
            session = Session(profile_name=request.config.profile)
            bedrock_client = session.client(
                "bedrock-runtime",
                aws_access_key_id=request.config.aws_access_key_id,
                aws_secret_access_key=request.config.aws_secret_access_key,
                aws_session_token=request.config.aws_session_token,
                region_name=request.config.aws_region,
            )
        else:
            session = Session()
            bedrock_client = session.client("bedrock-runtime")

        payload = request.payload
        # Offload to a thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, functools.partial(bedrock_client.converse, **payload)
        )
        return response

    @staticmethod
    @workflow_task
    async def request_structured_completion_task(
        request: RequestStructuredCompletionRequest,
    ):
        """
        Request a structured completion using Instructor's Bedrock API.
        """
        import instructor

        if request.response_model:
            response_model = request.response_model
        elif request.serialized_response_model:
            response_model = deserialize_model(request.serialized_response_model)
        else:
            raise ValueError(
                "Either response_model or serialized_response_model must be provided for structured completion."
            )

        if request.config:
            session = Session(profile_name=request.config.profile)
            bedrock_client = session.client(
                "bedrock-runtime",
                aws_access_key_id=request.config.aws_access_key_id,
                aws_secret_access_key=request.config.aws_secret_access_key,
                aws_session_token=request.config.aws_session_token,
                region_name=request.config.aws_region,
            )
        else:
            session = Session()
            bedrock_client = session.client("bedrock-runtime")

        client = instructor.from_bedrock(bedrock_client)

        # Extract structured data from natural language without blocking
        loop = asyncio.get_running_loop()
        structured_response = await loop.run_in_executor(
            None,
            functools.partial(
                client.chat.completions.create,
                modelId=request.model,
                messages=[{"role": "user", "content": request.response_str}],
                response_model=response_model,
            ),
        )

        return structured_response


class BedrockMCPTypeConverter(
    ProviderToMCPConverter[MessageUnionTypeDef, MessageUnionTypeDef]
):
    """
    Convert between Bedrock and MCP types.
    """

    @classmethod
    def from_mcp_message_result(cls, result: MCPMessageResult) -> MessageUnionTypeDef:
        if result.role != "assistant":
            raise ValueError(
                f"Expected role to be 'assistant' but got '{result.role}' instead."
            )

        return {
            "role": "assistant",
            "content": mcp_content_to_bedrock_content(result.content),
        }

    @classmethod
    def to_mcp_message_result(cls, result: MessageUnionTypeDef) -> MCPMessageResult:
        contents = bedrock_content_to_mcp_content(result["content"])
        if len(contents) > 1:
            raise NotImplementedError(
                "Multiple content elements in a single message are not supported in MCP yet"
            )
        mcp_content = contents[0]

        return MCPMessageResult(
            role=result.role,
            content=mcp_content,
            model=None,
            stopReason=None,
        )

    @classmethod
    def from_mcp_message_param(cls, param: MCPMessageParam) -> MessageUnionTypeDef:
        return {
            "role": param.role,
            "content": mcp_content_to_bedrock_content([param.content]),
        }

    @classmethod
    def to_mcp_message_param(cls, param: MessageUnionTypeDef) -> MCPMessageParam:
        # Implement the conversion from Bedrock response message to MCP message param

        contents = bedrock_content_to_mcp_content(param["content"])

        # TODO: saqadri - the mcp_content can have multiple elements
        # while sampling message content has a single content element
        # Right now we error out if there are > 1 elements in mcp_content
        # We need to handle this case properly going forward
        if len(contents) > 1:
            raise NotImplementedError(
                "Multiple content elements in a single message are not supported"
            )
        mcp_content = contents[0]

        return MCPMessageParam(
            role=param["role"],
            content=mcp_content,
            **typed_dict_extras(param, ["role", "content"]),
        )


def mcp_content_to_bedrock_content(
    content: list[TextContent | ImageContent | EmbeddedResource],
) -> list[ContentBlockUnionTypeDef]:
    bedrock_content: list[ContentBlockUnionTypeDef] = []

    for block in content:
        if isinstance(block, TextContent):
            bedrock_content.append({"text": block.text})
        elif isinstance(block, ImageContent):
            bedrock_content.append(
                {
                    "image": {
                        "format": block.mimeType,
                        "source": block.data,
                    }
                }
            )
        elif isinstance(block, EmbeddedResource):
            if isinstance(block.resource, TextResourceContents):
                bedrock_content.append({"text": block.resource.text})
            else:
                bedrock_content.append(
                    {
                        "document": {
                            "format": block.resource.mimeType,
                            "source": block.resource.blob,
                        }
                    }
                )
        else:
            # Last effort to convert the content to a string
            bedrock_content.append({"text": str(block)})
    return bedrock_content


def bedrock_content_to_mcp_content(
    content: list[ContentBlockUnionTypeDef],
) -> list[TextContent | ImageContent | EmbeddedResource]:
    mcp_content = []

    for block in content:
        if block.get("text"):
            mcp_content.append(TextContent(type="text", text=block["text"]))
        elif block.get("image"):
            mcp_content.append(
                ImageContent(
                    type="image",
                    data=block["image"]["source"],
                    mimeType=block["image"]["format"],
                )
            )
        elif block.get("toolUse"):
            # Best effort to convert a tool use to text (since there's no ToolUseContent)
            mcp_content.append(
                TextContent(
                    type="text",
                    text=str(block["toolUse"]),
                )
            )
        elif block.get("document"):
            mcp_content.append(
                EmbeddedResource(
                    type="document",
                    resource=BlobResourceContents(
                        mimeType=block["document"]["format"],
                        blob=block["document"]["source"],
                    ),
                )
            )

    return mcp_content
