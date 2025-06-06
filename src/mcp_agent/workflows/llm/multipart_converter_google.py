from typing import List, Sequence, Union

import base64
from google.genai import types

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

_logger = get_logger("multipart_converter_google")

# List of image MIME types supported by Google Gemini API
SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class GoogleConverter:
    """Converts MCP message types to Google API format."""

    @staticmethod
    def _is_supported_image_type(mime_type: str) -> bool:
        """Check if the given MIME type is supported by Google's image API.

        Args:
            mime_type: The MIME type to check

        Returns:
            True if the MIME type is supported, False otherwise
        """
        return mime_type in SUPPORTED_IMAGE_MIME_TYPES

    @staticmethod
    def convert_to_google(multipart_msg: PromptMessageMultipart) -> types.Content:
        """
        Convert a PromptMessageMultipart message to Google API format.

        Args:
            multipart_msg: The PromptMessageMultipart message to convert

        Returns:
            A Google API Content object
        """
        role = multipart_msg.role

        # Handle empty content case
        if not multipart_msg.content:
            return types.Content(role=role, parts=[])

        google_parts = GoogleConverter._convert_content_items(multipart_msg.content)

        return types.Content(role=role, parts=google_parts)

    @staticmethod
    def convert_prompt_message_to_google(message: PromptMessage) -> types.Content:
        """
        Convert a standard PromptMessage to Google API format.

        Args:
            message: The PromptMessage to convert

        Returns:
            A Google API Content object
        """
        multipart = PromptMessageMultipart(role=message.role, content=[message.content])
        return GoogleConverter.convert_to_google(multipart)

    @staticmethod
    def _convert_content_items(
        content_items: Sequence[Union[TextContent, ImageContent, EmbeddedResource]],
    ) -> List[types.Part]:
        """
        Convert a list of content items to Google content parts.

        Args:
            content_items: Sequence of MCP content items

        Returns:
            List of Google content parts
        """
        google_parts: List[types.Part] = []

        for content_item in content_items:
            if is_text_content(content_item):
                text = get_text(content_item)
                google_parts.append(types.Part.from_text(text=text))

            elif is_image_content(content_item):
                image_content = content_item  # type: ImageContent
                if not GoogleConverter._is_supported_image_type(image_content.mimeType):
                    data_size = len(image_content.data) if image_content.data else 0
                    google_parts.append(
                        types.Part.from_text(
                            text=f"Image with unsupported format '{image_content.mimeType}' ({data_size} bytes)"
                        )
                    )
                else:
                    image_data = get_image_data(image_content)
                    if image_data:
                        google_parts.append(
                            types.Part.from_bytes(
                                data=base64.b64decode(image_data),
                                mime_type=image_content.mimeType,
                            )
                        )
                    else:
                        # Fallback to text if image data is missing
                        google_parts.append(
                            types.Part.from_text(
                                text=f"Image missing data for '{image_content.mimeType}'"
                            )
                        )

            elif is_resource_content(content_item):
                part = GoogleConverter._convert_embedded_resource(content_item)
                google_parts.append(part)

        return google_parts

    @staticmethod
    def _convert_embedded_resource(
        resource: EmbeddedResource,
    ) -> types.Part:
        """
        Convert EmbeddedResource to appropriate Google Part.

        Args:
            resource: The embedded resource to convert

        Returns:
            A Google Part for the resource
        """
        resource_content = resource.resource
        uri = getattr(resource_content, "uri", None)
        # TODO: jerron - check if these are needed
        # uri_str = get_resource_uri(resource)
        # is_url: bool = uri and uri.scheme in ("http", "https")

        mime_type = GoogleConverter._determine_mime_type(resource_content)
        title = extract_title_from_uri(uri) if uri else "resource"

        if mime_type == "image/svg+xml":
            return GoogleConverter._convert_svg_resource(resource_content)

        elif is_image_mime_type(mime_type):
            if not GoogleConverter._is_supported_image_type(mime_type):
                return GoogleConverter._create_fallback_text(
                    f"Image with unsupported format '{mime_type}'", resource
                )

            image_data = get_image_data(resource)
            if image_data:
                return types.Part.from_bytes(
                    data=base64.b64decode(image_data),
                    mime_type=mime_type,
                )
            else:
                return GoogleConverter._create_fallback_text(
                    "Image missing data", resource
                )

        elif mime_type == "application/pdf":
            if hasattr(resource_content, "blob"):
                return types.Part.from_bytes(
                    data=base64.b64decode(resource_content.blob),
                    mime_type="application/pdf",
                )
            return types.Part.from_text(text=f"[PDF resource missing data: {title}]")

        elif is_text_mime_type(mime_type):
            text = get_text(resource)
            if text:
                return types.Part.from_text(text=text)
            else:
                return types.Part.from_text(
                    text=f"[Text content could not be extracted from {title}]"
                )

        # Default fallback - convert to text if possible
        text = get_text(resource)
        if text:
            return types.Part.from_text(text=text)

        # For binary resources
        if isinstance(resource.resource, BlobResourceContents) and hasattr(
            resource.resource, "blob"
        ):
            blob_length = len(resource.resource.blob)
            return types.Part.from_text(
                text=f"Embedded Resource {str(uri)} with unsupported format {mime_type} ({blob_length} characters)"
            )

        return GoogleConverter._create_fallback_text(
            f"Unsupported resource ({mime_type})", resource
        )

    @staticmethod
    def _determine_mime_type(
        resource: Union[TextResourceContents, BlobResourceContents],
    ) -> str:
        """
        Determine the MIME type of a resource.

        Args:
            resource: The resource to check

        Returns:
            The MIME type as a string
        """
        if getattr(resource, "mimeType", None):
            return resource.mimeType

        if getattr(resource, "uri", None):
            return guess_mime_type(str(resource.uri))

        if hasattr(resource, "blob"):
            return "application/octet-stream"

        return "text/plain"

    @staticmethod
    def _convert_svg_resource(resource_content) -> types.Part:
        """
        Convert SVG resource to text part with XML code formatting.

        Args:
            resource_content: The resource content containing SVG data

        Returns:
            A types.Part with formatted SVG content
        """
        if hasattr(resource_content, "text"):
            svg_content = resource_content.text
            return types.Part.from_text(text=f"```xml\n{svg_content}\n```")
        return types.Part.from_text(text="[SVG content could not be extracted]")

    @staticmethod
    def _create_fallback_text(
        message: str, resource: Union[TextContent, ImageContent, EmbeddedResource]
    ) -> types.Part:
        """
        Create a fallback text part for unsupported resource types.

        Args:
            message: The fallback message
            resource: The resource that couldn't be converted

        Returns:
            A types.Part with the fallback message
        """
        if isinstance(resource, EmbeddedResource) and hasattr(resource.resource, "uri"):
            uri = resource.resource.uri
            return types.Part.from_text(text=f"[{message}: {str(uri)}]")

        return types.Part.from_text(text=f"[{message}]")

    @staticmethod
    def convert_tool_result_to_google(
        tool_result: CallToolResult, tool_use_id: str
    ) -> types.Part:
        """
        Convert an MCP CallToolResult to a Google function response part.

        Args:
            tool_result: The tool result from a tool call
            tool_use_id: The ID of the associated tool use

        Returns:
            A Google function response part
        """
        google_content = []

        for item in tool_result.content:
            if isinstance(item, EmbeddedResource):
                part = GoogleConverter._convert_embedded_resource(item)
                google_content.append(part)
            elif isinstance(item, (TextContent, ImageContent)):
                parts = GoogleConverter._convert_content_items([item])
                google_content.extend(parts)

        if not google_content:
            google_content = [types.Part.from_text(text="[No content in tool result]")]

        # Serialize content parts to dicts for embedding in function response
        serialized_parts = [part.to_json_dict() for part in google_content]

        # Build the function response payload
        function_response = {"content": serialized_parts}
        if tool_result.isError:
            function_response["error"] = str(tool_result.content)

        return types.Part.from_function_response(
            name=tool_use_id,
            response=function_response,
        )

    @staticmethod
    def create_tool_results_message(
        tool_results: List[tuple[str, CallToolResult]],
    ) -> types.Content:
        """
        Create a user message containing tool results.

        Args:
            tool_results: List of (tool_use_id, tool_result) tuples

        Returns:
            A Content with role='user' containing all tool results
        """
        parts = []

        for tool_use_id, result in tool_results:
            part = GoogleConverter.convert_tool_result_to_google(result, tool_use_id)
            parts.append(part)

        return types.Content(role="user", parts=parts)

    @staticmethod
    def convert_mixed_messages_to_google(
        message: MessageTypes,
    ) -> List[types.Content]:
        """
        Convert a list of mixed messages to a list of Google-compatible messages.

        Args:
            messages: List of mixed message objects

        Returns:
            A list of Google-compatible message objects
        """
        messages: list[types.Content] = []

        # Convert message to Content
        if isinstance(message, str):
            messages.append(
                types.Content(role="user", parts=[types.Part.from_text(text=message)])
            )
        elif isinstance(message, PromptMessage):
            messages.append(GoogleConverter.convert_prompt_message_to_google(message))
        elif isinstance(message, list):
            for m in message:
                if isinstance(m, PromptMessage):
                    messages.append(GoogleConverter.convert_prompt_message_to_google(m))
                elif isinstance(m, str):
                    messages.append(
                        types.Content(role="user", parts=[types.Part.from_text(text=m)])
                    )
                else:
                    messages.append(m)
        else:
            messages.append(message)

        return messages
