from typing import List, Sequence, Union, TYPE_CHECKING

from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    PromptMessage,
    TextContent,
    TextResourceContents,
)

from mcp_agent.logging.logger import get_logger
from mcp_agent.utils.content_utils import (
    get_image_data,
    get_resource_uri,
    get_text,
    is_image_content,
    is_resource_content,
    is_text_content,
)
from mcp_agent.utils.mime_utils import (
    guess_mime_type,
    is_image_mime_type,
    is_text_mime_type,
)
from mcp_agent.utils.prompt_message_multipart import PromptMessageMultipart
from mcp_agent.utils.resource_utils import extract_title_from_uri
from mcp_agent.workflows.llm.augmented_llm import MessageTypes

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime.type_defs import (
        MessageUnionTypeDef,
        ContentBlockUnionTypeDef,
        ToolResultBlockTypeDef,
    )
else:
    MessageUnionTypeDef = dict
    ContentBlockUnionTypeDef = dict
    ToolResultBlockTypeDef = dict

_logger = get_logger("multipart_converter_bedrock")

SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}


class BedrockConverter:
    """Converts MCP message types to Amazon Bedrock API format."""

    @staticmethod
    def _is_supported_image_type(mime_type: str) -> bool:
        """Check if the given MIME type is supported by Bedrock's image API."""
        return mime_type in SUPPORTED_IMAGE_MIME_TYPES

    @staticmethod
    def convert_to_bedrock(
        multipart_msg: PromptMessageMultipart,
    ) -> MessageUnionTypeDef:
        """
        Convert a PromptMessageMultipart message to Bedrock API format.
        """
        role = multipart_msg.role

        if not multipart_msg.content:
            return {"role": role, "content": []}

        bedrock_blocks = BedrockConverter._convert_content_items(multipart_msg.content)
        return {"role": role, "content": bedrock_blocks}

    @staticmethod
    def convert_prompt_message_to_bedrock(
        message: PromptMessage,
    ) -> MessageUnionTypeDef:
        """
        Convert a standard PromptMessage to Bedrock API format.
        """
        multipart = PromptMessageMultipart(role=message.role, content=[message.content])
        return BedrockConverter.convert_to_bedrock(multipart)

    @staticmethod
    def _convert_content_items(
        content_items: Sequence[Union[TextContent, ImageContent, EmbeddedResource]],
    ) -> List[ContentBlockUnionTypeDef]:
        """
        Convert a list of content items to Bedrock content blocks.
        """
        bedrock_blocks: List[ContentBlockUnionTypeDef] = []

        for content_item in content_items:
            if is_text_content(content_item):
                text = get_text(content_item)
                bedrock_blocks.append({"text": text})

            elif is_image_content(content_item):
                image_content = content_item  # type: ignore
                if not BedrockConverter._is_supported_image_type(
                    image_content.mimeType
                ):
                    data_size = len(image_content.data) if image_content.data else 0
                    bedrock_blocks.append(
                        {
                            "text": f"Image with unsupported format '{image_content.mimeType}' ({data_size} bytes)"
                        }
                    )
                else:
                    image_data = get_image_data(image_content)
                    bedrock_blocks.append(
                        {
                            "image": {
                                "format": image_content.mimeType,
                                "source": image_data,
                            }
                        }
                    )

            elif is_resource_content(content_item):
                block = BedrockConverter._convert_embedded_resource(content_item)
                bedrock_blocks.append(block)

        return bedrock_blocks

    @staticmethod
    def _convert_embedded_resource(
        resource: EmbeddedResource,
    ) -> ContentBlockUnionTypeDef:
        """
        Convert EmbeddedResource to appropriate Bedrock block type.
        """
        resource_content = resource.resource
        uri_str = get_resource_uri(resource)
        uri = getattr(resource_content, "uri", None)
        # TODO: jerron - check if we need to handle URLs differently
        # is_url: bool = uri and getattr(uri, "scheme", None) in ("http", "https")

        mime_type = BedrockConverter._determine_mime_type(resource_content)
        title = extract_title_from_uri(uri) if uri else "resource"

        if mime_type == "image/svg+xml":
            return BedrockConverter._convert_svg_resource(resource_content)

        elif is_image_mime_type(mime_type):
            if not BedrockConverter._is_supported_image_type(mime_type):
                return BedrockConverter._create_fallback_text(
                    f"Image with unsupported format '{mime_type}'", resource
                )
            image_data = get_image_data(resource)
            if image_data:
                return {
                    "image": {
                        "format": mime_type,
                        "source": {"bytes": image_data},
                    }
                }
            return BedrockConverter._create_fallback_text(
                "Image missing data", resource
            )

        elif mime_type == "application/pdf":
            if hasattr(resource_content, "blob"):
                # Bedrock expects: {"document": {"format": ..., "name": ..., "source": {"bytes": ...}}}
                return {
                    "document": {
                        "format": "pdf",
                        "name": title,
                        "source": {"bytes": resource_content.blob},
                    }
                }
            return {"text": f"[PDF resource missing data: {title}]"}

        elif is_text_mime_type(mime_type):
            text = get_text(resource)
            if not text:
                return {"text": f"[Text content could not be extracted from {title}]"}
            return {"text": text}

        text = get_text(resource)
        if text:
            return {"text": text}

        if isinstance(resource.resource, BlobResourceContents) and hasattr(
            resource.resource, "blob"
        ):
            blob_length = len(resource.resource.blob)
            return {
                "text": f"Embedded Resource {getattr(uri, '_url', uri_str)} with unsupported format {mime_type} ({blob_length} characters)"
            }

        return BedrockConverter._create_fallback_text(
            f"Unsupported resource ({mime_type})", resource
        )

    @staticmethod
    def _determine_mime_type(
        resource: Union[TextResourceContents, BlobResourceContents],
    ) -> str:
        """
        Determine the MIME type of a resource.
        """
        if getattr(resource, "mimeType", None):
            return resource.mimeType
        if getattr(resource, "uri", None):
            return guess_mime_type(str(resource.uri))
        if hasattr(resource, "blob"):
            return "application/octet-stream"
        return "text/plain"

    @staticmethod
    def _convert_svg_resource(resource_content) -> ContentBlockUnionTypeDef:
        """
        Convert SVG resource to text block with XML code formatting.
        """
        if hasattr(resource_content, "text"):
            svg_content = resource_content.text
            return {"text": f"```xml\n{svg_content}\n```"}
        return {"text": "[SVG content could not be extracted]"}

    @staticmethod
    def _create_fallback_text(
        message: str, resource: Union[TextContent, ImageContent, EmbeddedResource]
    ) -> ContentBlockUnionTypeDef:
        """
        Create a fallback text block for unsupported resource types.
        """
        if isinstance(resource, EmbeddedResource) and hasattr(resource.resource, "uri"):
            uri = resource.resource.uri
            return {"text": f"[{message}: {getattr(uri, '_url', str(uri))}]"}
        return {"text": f"[{message}]"}

    @staticmethod
    def convert_tool_result_to_bedrock(
        tool_result: CallToolResult, tool_use_id: str
    ) -> ToolResultBlockTypeDef:
        """
        Convert an MCP CallToolResult to a Bedrock ToolResultBlockTypeDef.
        """
        bedrock_content = BedrockConverter._convert_content_items(tool_result.content)
        if not bedrock_content:
            bedrock_content = [{"text": "[No content in tool result]"}]
        return {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": bedrock_content,
                "status": "error" if tool_result.isError else "success",
            }
        }

    @staticmethod
    def create_tool_results_message(
        tool_results: List[tuple[str, CallToolResult]],
    ) -> MessageUnionTypeDef:
        """
        Create a user message containing tool results.
        """
        content_blocks = []
        for tool_use_id, result in tool_results:
            bedrock_content = BedrockConverter._convert_content_items(result.content)
            if not bedrock_content:
                bedrock_content = [{"text": "[No content in tool result]"}]
            content_blocks.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "content": bedrock_content,
                        "status": "error" if result.isError else "success",
                    }
                }
            )
        return {"role": "user", "content": content_blocks}

    @staticmethod
    def convert_mixed_messages_to_bedrock(
        message: MessageTypes,
    ) -> List[MessageUnionTypeDef]:
        """
        Convert a list of mixed messages to a list of Bedrock-compatible messages.

        Args:
            messages: List of mixed message objects

        Returns:
            A list of Bedrock-compatible MessageParam objects
        """
        messages: list[MessageUnionTypeDef] = []

        # Convert message to MessageUnionTypeDef
        if isinstance(message, str):
            messages.append({"role": "user", "content": [{"text": message}]})
        elif isinstance(message, PromptMessage):
            messages.append(BedrockConverter.convert_prompt_message_to_bedrock(message))
        elif isinstance(message, list):
            for m in message:
                if isinstance(m, PromptMessage):
                    messages.append(
                        BedrockConverter.convert_prompt_message_to_bedrock(m)
                    )
                elif isinstance(m, str):
                    messages.append({"role": "user", "content": [{"text": m}]})
                else:
                    messages.append(m)
        else:
            messages.append(message)

        return messages
