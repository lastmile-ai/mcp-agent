import asyncio
import functools
from typing import TYPE_CHECKING, Type
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
                        tool_args = tool_use_block["input"]
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

                        tool_results.append(
                            {
                                "toolResult": {
                                    "content": mcp_content_to_bedrock_content(
                                        result.content
                                    ),
                                    "toolUseId": tool_use_id,
                                    "status": "error" if result.isError else "success",
                                }
                            }
                        )

                # Create a single message with all tool results
                if tool_results:
                    tool_result_message = {
                        "role": "user",
                        "content": tool_results,
                    }

                    messages.append(tool_result_message)
                    responses.append(tool_result_message)

        if params.use_history:
            self.history.set(messages)

        self._log_chat_finished(model=model)

        return responses

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
