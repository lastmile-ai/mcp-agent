from typing import List, Sequence, Union, Optional

from azure.ai.inference.models import (
    ContentItem,
    TextContentItem,
    ImageContentItem,
    AudioContentItem,
    ImageUrl,
    UserMessage,
    SystemMessage,
    AssistantMessage,
    ToolMessage,
    DeveloperMessage,
)
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

_logger = get_logger("multipart_converter_azure")

SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class AzureConverter:
    """Converts MCP message types to Azure API format."""

    @staticmethod
    def _is_supported_image_type(mime_type: str) -> bool:
        return mime_type in SUPPORTED_IMAGE_MIME_TYPES

    @staticmethod
    def convert_to_azure(
        multipart_msg: PromptMessageMultipart,
    ) -> UserMessage | AssistantMessage:
        """
        Convert a PromptMessageMultipart message to Azure API format.

        Args:
            multipart_msg: The PromptMessageMultipart message to convert

        Returns:
            An Azure UserMessage or AssistantMessage object
        """
        role = multipart_msg.role

        if not multipart_msg.content:
            if role == "assistant":
                return AssistantMessage(content="")
            else:
                return UserMessage(content="")

        azure_blocks = AzureConverter._convert_content_items(multipart_msg.content)

        # For assistant, only text is allowed as content (Azure allows text or list[ContentItem])
        if role == "assistant":
            text_blocks = []
            for block in azure_blocks:
                if isinstance(block, TextContentItem):
                    text_blocks.append(block.text)
                else:
                    _logger.warning(
                        f"Removing non-text block from assistant message: {type(block)}"
                    )
            content = "\n".join(text_blocks)
            return AssistantMessage(content=content)
        else:
            # For user, can be list[ContentItem]
            content = azure_blocks
            return UserMessage(content=content)

    @staticmethod
    def convert_prompt_message_to_azure(
        message: PromptMessage,
    ) -> UserMessage | AssistantMessage:
        """
        Convert a standard PromptMessage to Azure API format.

        Args:
            message: The PromptMessage to convert

        Returns:
            An Azure UserMessage or AssistantMessage object
        """
        multipart = PromptMessageMultipart(role=message.role, content=[message.content])
        return AzureConverter.convert_to_azure(multipart)

    @staticmethod
    def _convert_content_items(
        content_items: Sequence[Union[TextContent, ImageContent, EmbeddedResource]],
    ) -> List[ContentItem]:
        """
        Convert a list of content items to Azure content blocks.

        Args:
            content_items: Sequence of MCP content items

        Returns:
            List of Azure ContentItem
        """
        azure_blocks: List[ContentItem] = []

        for content_item in content_items:
            if is_text_content(content_item):
                text = get_text(content_item)
                if text:
                    azure_blocks.append(TextContentItem(text=text))

            elif is_image_content(content_item):
                image_content = content_item  # type: ImageContent
                if not AzureConverter._is_supported_image_type(image_content.mimeType):
                    data_size = len(image_content.data) if image_content.data else 0
                    azure_blocks.append(
                        TextContentItem(
                            text=f"Image with unsupported format '{image_content.mimeType}' ({data_size} bytes)"
                        )
                    )
                else:
                    image_data = get_image_data(image_content)
                    data_url = f"data:{image_content.mimeType};base64,{image_data}"
                    azure_blocks.append(
                        ImageContentItem(image_url=ImageUrl(url=data_url))
                    )

            elif is_resource_content(content_item):
                block = AzureConverter._convert_embedded_resource(content_item)
                if block is not None:
                    azure_blocks.append(block)

        return azure_blocks

    @staticmethod
    def _convert_embedded_resource(
        resource: EmbeddedResource,
    ) -> Optional[ContentItem]:
        """
        Convert EmbeddedResource to appropriate Azure ContentItem.

        Args:
            resource: The embedded resource to convert

        Returns:
            An appropriate ContentItem for the resource, or None if not convertible
        """
        resource_content = resource.resource
        uri_str = get_resource_uri(resource)
        uri = getattr(resource_content, "uri", None)
        is_url: bool = uri and getattr(uri, "scheme", None) in ("http", "https")

        mime_type = AzureConverter._determine_mime_type(resource_content)
        title = extract_title_from_uri(uri) if uri else "resource"

        if mime_type == "image/svg+xml":
            return AzureConverter._convert_svg_resource(resource_content)

        elif is_image_mime_type(mime_type):
            if not AzureConverter._is_supported_image_type(mime_type):
                return AzureConverter._create_fallback_text(
                    f"Image with unsupported format '{mime_type}'", resource
                )

            if is_url and uri_str:
                return ImageContentItem(image_url=ImageUrl(url=uri_str))

            image_data = get_image_data(resource)
            if image_data:
                data_url = f"data:{mime_type};base64,{image_data}"
                return ImageContentItem(image_url=ImageUrl(url=data_url))

            return AzureConverter._create_fallback_text("Image missing data", resource)

        elif mime_type == "application/pdf":
            # Azure does not support PDF as content item, fallback to text
            return TextContentItem(text=f"[PDF resource: {title}]")

        elif is_text_mime_type(mime_type):
            text = get_text(resource)
            if not text:
                return TextContentItem(
                    text=f"[Text content could not be extracted from {title}]"
                )
            return TextContentItem(text=text)

        text = get_text(resource)
        if text:
            return TextContentItem(text=text)

        if isinstance(resource.resource, BlobResourceContents) and hasattr(
            resource.resource, "blob"
        ):
            blob_length = len(resource.resource.blob)
            return TextContentItem(
                text=f"Embedded Resource {getattr(uri, '_url', '')} with unsupported format {mime_type} ({blob_length} characters)"
            )

        return AzureConverter._create_fallback_text(
            f"Unsupported resource ({mime_type})", resource
        )

    @staticmethod
    def _determine_mime_type(
        resource: Union[TextResourceContents, BlobResourceContents],
    ) -> str:
        if getattr(resource, "mimeType", None):
            return resource.mimeType
        if getattr(resource, "uri", None):
            return guess_mime_type(str(resource.uri))
        if hasattr(resource, "blob"):
            return "application/octet-stream"
        return "text/plain"

    @staticmethod
    def _convert_svg_resource(resource_content) -> TextContentItem:
        if hasattr(resource_content, "text"):
            svg_content = resource_content.text
            return TextContentItem(text=f"```xml\n{svg_content}\n```")
        return TextContentItem(text="[SVG content could not be extracted]")

    @staticmethod
    def _create_fallback_text(
        message: str, resource: Union[TextContent, ImageContent, EmbeddedResource]
    ) -> TextContentItem:
        if isinstance(resource, EmbeddedResource) and hasattr(resource.resource, "uri"):
            uri = resource.resource.uri
            return TextContentItem(text=f"[{message}: {getattr(uri, '_url', '')}]")
        return TextContentItem(text=f"[{message}]")

    @staticmethod
    def convert_tool_result_to_azure(
        tool_result: CallToolResult, tool_use_id: str
    ) -> ToolMessage:
        """
        Convert an MCP CallToolResult to an Azure ToolMessage.

        Args:
            tool_result: The tool result from a tool call
            tool_use_id: The ID of the associated tool use

        Returns:
            An Azure ToolMessage containing the tool result content as text.
        """
        azure_content = []

        for item in tool_result.content:
            if isinstance(item, EmbeddedResource):
                resource_block = AzureConverter._convert_embedded_resource(item)
                if resource_block is not None:
                    azure_content.append(resource_block)
            elif isinstance(item, (TextContent, ImageContent)):
                blocks = AzureConverter._convert_content_items([item])
                azure_content.extend(blocks)

        if not azure_content:
            azure_content = [TextContentItem(text="[No content in tool result]")]

        content_text = AzureConverter._extract_text_from_azure_content_blocks(
            azure_content
        )

        return ToolMessage(
            tool_call_id=tool_use_id,
            content=content_text,
        )

    @staticmethod
    def _extract_text_from_azure_content_blocks(
        blocks: list[TextContentItem | ImageContentItem | AudioContentItem],
    ) -> str:
        """
        Extract and concatenate text from Azure content blocks for ToolMessage.
        """
        texts = []
        for block in blocks:
            # TextContentItem
            if hasattr(block, "text") and isinstance(block.text, str):
                texts.append(block.text)
            # ImageContentItem
            elif hasattr(block, "image_url"):
                url = getattr(block.image_url, "url", None)
                if url:
                    texts.append(f"[Image: {url}]")
                else:
                    texts.append("[Image]")
            else:
                texts.append(str(block))
        return "\n".join(texts)

    @staticmethod
    def create_tool_results_message(
        tool_results: List[tuple[str, CallToolResult]],
    ) -> List[ToolMessage]:
        """
        Create a list of ToolMessage objects for tool results.

        Args:
            tool_results: List of (tool_use_id, tool_result) tuples

        Returns:
            A list of ToolMessage objects, one for each tool result.
        """
        tool_messages = []
        for tool_use_id, result in tool_results:
            tool_message = AzureConverter.convert_tool_result_to_azure(
                result, tool_use_id
            )
            tool_messages.append(tool_message)
        return tool_messages

    @staticmethod
    def convert_mixed_messages_to_azure(
        message: MessageTypes,
    ) -> List[
        Union[
            SystemMessage, UserMessage, AssistantMessage, ToolMessage, DeveloperMessage
        ]
    ]:
        """
        Convert a list of mixed messages to a list of Azure-compatible messages.

        Args:
            messages: List of mixed message objects

        Returns:
            A list of Azure-compatible MessageParam objects
        """
        messages = []

        # Convert message to ResponseMessage
        if isinstance(message, str):
            messages.append(UserMessage(content=message))
        elif isinstance(message, PromptMessage):
            messages.append(AzureConverter.convert_prompt_message_to_azure(message))
        elif isinstance(message, list):
            for m in message:
                if isinstance(m, PromptMessage):
                    messages.append(AzureConverter.convert_prompt_message_to_azure(m))
                elif isinstance(m, str):
                    messages.append(UserMessage(content=m))
                else:
                    messages.append(m)
        else:
            messages.append(message)

        return messages
