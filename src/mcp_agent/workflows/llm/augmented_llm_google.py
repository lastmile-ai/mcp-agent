from typing import Type
import base64
from google.genai import Client
from google.genai import types
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

from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    MCPMessageParam,
    MCPMessageResult,
    ModelT,
    ProviderToMCPConverter,
    RequestParams,
    image_url_to_mime_and_base64,
    CallToolResult,
)


class GoogleAugmentedLLM(
    AugmentedLLM[
        types.Content,
        types.Content,
    ]
):
    """
    The basic building block of agentic systems is an LLM enhanced with augmentations
    such as retrieval, tools, and memory provided from a collection of MCP servers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, type_converter=GoogleMCPTypeConverter, **kwargs)

        self.provider = "Google"
        # Initialize logger with name if available
        self.logger = get_logger(f"{__name__}.{self.name}" if self.name else __name__)

        self.model_preferences = self.model_preferences or ModelPreferences(
            costPriority=0.3,
            speedPriority=0.4,
            intelligencePriority=0.3,
        )
        # Get default model from config if available
        default_model = "gemini-2.0-flash"  # Fallback default

        if self.context.config.google:
            if hasattr(self.context.config.google, "default_model"):
                default_model = self.context.config.google.default_model

        if self.context.config.google and self.context.config.google.vertexai:
            self.google_client = Client(
                vertexai=self.context.config.google.vertexai,
                project=self.context.config.google.project,
                location=self.context.config.google.location,
            )
        else:
            self.google_client = Client(api_key=self.context.config.google.api_key)

        self.default_request_params = self.default_request_params or RequestParams(
            model=default_model,
            modelPreferences=self.model_preferences,
            maxTokens=4096,
            systemPrompt=self.instruction,
            parallel_tool_calls=True,
            max_iterations=10,
            use_history=True,
        )

    async def generate(self, message, request_params: RequestParams | None = None):
        """
        Process a query using an LLM and available tools.
        The default implementation uses AWS Nova's ChatCompletion as the LLM.
        Override this method to use a different LLM.
        """

        messages: list[types.Content] = []
        params = self.get_request_params(request_params)

        if params.use_history:
            messages.extend(self.history.get())

        if isinstance(message, str):
            messages.append(
                types.Content(role="user", parts=[types.Part.from_text(text=message)])
            )
        elif isinstance(message, list):
            messages.extend(message)
        else:
            messages.append(message)

        response = await self.aggregator.list_tools()

        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters=transform_mcp_tool_schema(tool.inputSchema),
                    )
                ]
            )
            for tool in response.tools
        ]

        responses: list[types.Content] = []
        model = await self.select_model(params)

        for i in range(params.max_iterations):
            inference_config = types.GenerateContentConfig(
                max_output_tokens=params.maxTokens,
                temperature=params.temperature,
                stop_sequences=params.stopSequences or [],
                system_instruction=self.instruction or params.systemPrompt,
                tools=tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
                candidate_count=1,
                **(params.metadata or {}),
            )

            arguments = {
                "model": model,
                "contents": messages,
                "config": inference_config,
            }

            self.logger.debug(f"{arguments}")
            self._log_chat_progress(chat_turn=(len(messages) + 1) // 2, model=model)

            executor_result = await self.executor.execute(
                self.google_client.models.generate_content, **arguments
            )

            response = executor_result[0]

            if isinstance(response, BaseException):
                self.logger.error(f"Error: {response}")
                break

            self.logger.debug(f"{model} response:", data=response)

            if not response.candidates:
                break

            candidate = response.candidates[0]

            response_as_message = self.convert_message_to_message_param(
                candidate.content
            )

            messages.append(response_as_message)

            if not candidate.content or not candidate.content.parts:
                break

            responses.append(candidate.content)

            function_calls = [
                self.execute_tool_call(part.function_call)
                for part in candidate.content.parts
                if part.function_call
            ]

            if function_calls:
                results = await self.executor.execute(*function_calls)

                self.logger.debug(
                    f"Iteration {i}: Tool call results: {str(results) if results else 'None'}"
                )

                for result in results:
                    if isinstance(result, BaseException):
                        self.logger.error(
                            f"Warning: Unexpected error during tool execution: {result}. Continuing.."
                        )
                        break
                    if result is not None:
                        messages.append(result)
            else:
                self.logger.debug(
                    f"Iteration {i}: Stopping because finish_reason is '{candidate.finish_reason}'"
                )
                break

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
        The default implementation uses gemini-2.0-flash as the LLM
        Override this method to use a different LLM.
        """
        contents = await self.generate(
            message=message,
            request_params=request_params,
        )

        response = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[part for content in contents for part in content.parts],
                    )
                )
            ]
        )

        return response.text or ""

    async def generate_structured(
        self,
        message,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        import instructor

        response = await self.generate_str(
            message=message,
            request_params=request_params,
        )

        client = instructor.from_genai(
            self.google_client, mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS
        )

        params = self.get_request_params(request_params)
        model = await self.select_model(params) or "gemini-2.0-flash"

        structured_response = client.chat.completions.create(
            model=model,
            response_model=response_model,
            messages=[
                {"role": "user", "content": response},
            ],
        )

        return structured_response

    @classmethod
    def convert_message_to_message_param(cls, message, **kwargs):
        """Convert a response object to an input parameter object to allow LLM calls to be chained."""
        return message

    async def execute_tool_call(
        self,
        function_call: types.FunctionCall,
    ) -> types.Content | None:
        """
        Execute a single tool call and return the result message.
        Returns None if there's no content to add to messages.
        """
        tool_name = function_call.name
        tool_args = function_call.args
        tool_call_id = function_call.id

        if not tool_name or not tool_call_id:
            self.logger.error("Missing function call name or function call id.")
            return None

        tool_call_request = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=tool_name, arguments=tool_args),
        )

        result = await self.call_tool(
            request=tool_call_request, tool_call_id=tool_call_id
        )

        # Pass tool_name instead of tool_call_id because Google uses tool_name
        # to associate function response to function call
        function_response_content = self.from_mcp_tool_result(result, tool_name)

        return function_response_content

    def message_param_str(self, message) -> str:
        """Convert an input message to a string representation."""
        # TODO: Jerron - to make more comprehensive
        return str(message.model_dump())

    def message_str(self, message) -> str:
        """Convert an output message to a string representation."""
        # TODO: Jerron - to make more comprehensive
        return str(message.model_dump())


class GoogleMCPTypeConverter(ProviderToMCPConverter[types.Content, types.Content]):
    """
    Convert between Azure and MCP types.
    """

    @classmethod
    def from_mcp_message_result(cls, result: MCPMessageResult) -> types.Content:
        if result.role != "assistant":
            raise ValueError(
                f"Expected role to be 'assistant' but got '{result.role}' instead."
            )
        if isinstance(result.content, TextContent):
            return types.Content(
                role="model", parts=[types.Part.from_text(result.content.text)]
            )
        else:
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_bytes(
                        data=base64.b64decode(result.content.data),
                        mime_type=result.content.mimeType,
                    )
                ],
            )

    @classmethod
    def from_mcp_message_param(cls, param: MCPMessageParam) -> types.Content:
        if param.role == "assistant":
            return types.Content(
                role="model", parts=[types.Part.from_text(param.content)]
            )
        elif param.role == "user":
            return types.Content(
                role="user", parts=mcp_content_to_google_parts([param.content])
            )
        else:
            raise ValueError(
                f"Unexpected role: {param.role}, MCP only supports 'assistant' and 'user'"
            )

    @classmethod
    def to_mcp_message_result(cls, result: types.Content) -> MCPMessageResult:
        contents = google_parts_to_mcp_content(result.parts)
        if len(contents) > 1:
            raise NotImplementedError(
                "Multiple content elements in a single message are not supported in MCP yet"
            )
        return MCPMessageResult(
            role=result.role,
            content=contents[0],
            model=None,
            stopReason=None,
        )

    @classmethod
    def to_mcp_message_param(cls, param: types.Content) -> MCPMessageParam:
        contents = google_parts_to_mcp_content(param.parts)

        # TODO: saqadri - the mcp_content can have multiple elements
        # while sampling message content has a single content element
        # Right now we error out if there are > 1 elements in mcp_content
        # We need to handle this case properly going forward
        if len(contents) > 1:
            raise NotImplementedError(
                "Multiple content elements in a single message are not supported"
            )
        elif len(contents) == 0:
            raise ValueError("No content elements in a message")

        mcp_content: TextContent | ImageContent | EmbeddedResource = contents[0]

        if param.role == "model":
            return MCPMessageParam(
                role="assistant",
                content=mcp_content,
            )
        elif param.role == "user":
            return MCPMessageParam(
                role="user",
                content=mcp_content,
            )
        elif param.role == "tool":
            raise NotImplementedError(
                "Tool messages are not supported in SamplingMessage yet"
            )
        else:
            raise ValueError(
                f"Unexpected role: {param.role}, Google only supports 'model', 'user', 'tool'"
            )

    @classmethod
    def from_mcp_tool_result(
        cls, result: CallToolResult, tool_use_id: str
    ) -> types.Content:
        """Convert an MCP tool result to an LLM input type"""
        if result.isError:
            function_response = {"error": str(result.content)}
        else:
            function_response_parts = mcp_content_to_google_parts(result.content)
            function_response = {"result": function_response_parts}

        function_response_part = types.Part.from_function_response(
            name=tool_use_id,
            response=function_response,
        )

        function_response_content = types.Content(
            role="tool", parts=[function_response_part]
        )

        return function_response_content


def transform_mcp_tool_schema(schema: dict) -> dict:
    """Transform JSON Schema to OpenAPI Schema format compatible with Gemini.

    Key transformations:
    1. Convert camelCase properties to snake_case (e.g., maxLength -> max_length)
    2. Remove explicitly excluded fields (e.g., "default")
    3. Recursively process nested structures (properties, items, anyOf)
    4. Handle nullable types by setting nullable=true when anyOf includes type:"null"
    5. Remove unsupported format values based on data type
    6. For anyOf fields, only the first non-null type is used (true union types not supported)
    7. Preserve unsupported keywords by adding them to the description field

    Notes:
    - This implementation only supports nullable types (Type | None) for anyOf fields
    - True union types (e.g., str | int) are not supported - only the first non-null type is used
    - Unsupported fields are preserved in the description to ensure the LLM understands all constraints

    Args:
        schema: A JSON Schema dictionary

    Returns:
        A cleaned OpenAPI schema dictionary compatible with Gemini
    """
    # TODO: jerron - workaround until gemini get json schema support for function calling

    # Get the field names from the Schema class using Pydantic's model_fields
    supported_schema_props = set(types.Schema.model_fields.keys())

    # Properties to exclude even if they would otherwise be supported
    # 'default' is excluded because Google throws error if included.
    EXCLUDED_PROPERTIES = {"default"}

    # Special case mappings for camelCase to snake_case conversions
    CAMEL_TO_SNAKE_MAPPINGS = {
        "anyOf": "any_of",
        "maxLength": "max_length",
        "minLength": "min_length",
        "minProperties": "min_properties",
        "maxProperties": "max_properties",
        "maxItems": "max_items",
        "minItems": "min_items",
    }

    # Supported formats by data type in Gemini
    SUPPORTED_FORMATS = {
        "string": {"enum", "date-time"},
        "number": {"float", "double"},
        "integer": {"int32", "int64"},
    }

    # Handle non-dict schemas
    if not isinstance(schema, dict):
        return schema

    result = {}
    unsupported_keywords = []

    for key, value in schema.items():
        # Add excluded properties to unsupported keywords
        if key in EXCLUDED_PROPERTIES:
            unsupported_keywords.append(f"{key}: {value}")
            continue

        # Handle format field based on data type
        if key == "format":
            schema_type = schema.get("type", "").lower()
            if schema_type in SUPPORTED_FORMATS:
                if value not in SUPPORTED_FORMATS[schema_type]:
                    # Add unsupported format to unsupported keywords list
                    unsupported_keywords.append(f"{key}: {value}")
                    continue

        # Apply special case mappings if available
        if key in CAMEL_TO_SNAKE_MAPPINGS:
            snake_key = CAMEL_TO_SNAKE_MAPPINGS[key]
        else:
            # Standard camelCase to snake_case conversion
            snake_key = "".join("_" + c.lower() if c.isupper() else c for c in key)

        # If key is not supported in Gemini schema, add to unsupported_keywords
        if snake_key not in supported_schema_props:
            unsupported_keywords.append(f"{key}: {value}")
            continue

        # Handle nested structures that need recursive processing
        if key == "properties" and isinstance(value, dict):
            # For properties, process each property's schema
            result[snake_key] = {
                prop_k: transform_mcp_tool_schema(prop_v)
                for prop_k, prop_v in value.items()
            }
        elif key == "items" and isinstance(value, dict):
            # For items, process the schema
            result[snake_key] = transform_mcp_tool_schema(value)
        elif key == "anyOf" and isinstance(value, list):
            # NOTE: This implementation only supports nullable types (Type | None)
            # True union types (e.g., str | int) are not supported in the OpenAPI Schema
            # conversion for Gemini. Only the first non-null type will be used.

            has_null_type = False
            non_null_schema = None

            # Find if we have a null type and get the first non-null schema
            for item in value:
                if isinstance(item, dict):
                    if item.get("type") == "null":
                        has_null_type = True
                    elif non_null_schema is None:
                        non_null_schema = item

            # Set nullable if we had a null type
            if has_null_type:
                result["nullable"] = True

            # If we found a non-null schema, merge it with parent
            if non_null_schema:
                # We need to transform the schema to handle nested structures and camelCase conversions
                transformed_schema = transform_mcp_tool_schema(non_null_schema)
                # Merge transformed schema with parent (result)
                for k, v in transformed_schema.items():
                    if k not in result:  # Don't overwrite existing fields like nullable
                        result[k] = v

            # We don't add any_of to the result at all
        else:
            # For other properties, use the value as is
            result[snake_key] = value

    # Add unsupported keywords to description
    if unsupported_keywords:
        keywords_text = ", ".join(unsupported_keywords)
        result["description"] = (
            result.setdefault("description", "")
            + f". Additional properties: {keywords_text}"
        )

    return result


def mcp_content_to_google_parts(
    content: list[TextContent | ImageContent | EmbeddedResource],
) -> list[types.Part]:
    google_parts: list[types.Part] = []

    for block in content:
        if isinstance(block, TextContent):
            google_parts.append(types.Part.from_text(text=block.text))
        elif isinstance(block, ImageContent):
            google_parts.append(
                types.Part.from_bytes(
                    data=base64.b64decode(block.data), mime_type=block.mimeType
                )
            )
        elif isinstance(block, EmbeddedResource):
            if isinstance(block.resource, TextResourceContents):
                google_parts.append(types.Part.from_text(text=block.text))
            else:
                google_parts.append(
                    types.Part.from_bytes(
                        data=base64.b64decode(block.resource.blob),
                        mime_type=block.resource.mimeType,
                    )
                )
        else:
            # Last effort to convert the content to a string
            google_parts.append(types.Part.from_text(text=str(block)))
    return google_parts


def google_parts_to_mcp_content(
    google_parts: list[types.Part],
) -> list[TextContent | ImageContent | EmbeddedResource]:
    mcp_content: list[TextContent | ImageContent | EmbeddedResource] = []

    for part in google_parts:
        if part.text:
            mcp_content.append(TextContent(type="text", text=part.text))
        elif part.file_data:
            if part.file_data.file_uri.startswith(
                "data:"
            ) and part.file_data.mime_type.startswith("image/"):
                _, base64_data = image_url_to_mime_and_base64(part.file_data.file_uri)
                mcp_content.append(
                    ImageContent(
                        type="image",
                        mimeType=part.file_data.mime_type,
                        data=base64_data,
                    )
                )
            else:
                mcp_content.append(
                    EmbeddedResource(
                        type="resource",
                        resource=BlobResourceContents(
                            mimeType=part.file_data.mime_type,
                            uri=part.file_data.file_uri,
                        ),
                    )
                )
        elif part.function_call:
            mcp_content.append(
                TextContent(
                    type="text",
                    text=str(part.function_call),
                )
            )
        else:
            # Last effort to convert the content to a string
            mcp_content.append(TextContent(type="text", text=str(part)))

    return mcp_content
