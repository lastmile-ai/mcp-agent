from typing import Any, Dict, List, Optional, Tuple, Union

from mcp.types import (
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    PromptMessage,
    TextContent,
)
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam

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

_logger = get_logger("multipart_converter_openai")

# Define type aliases for content blocks
ContentBlock = Dict[str, Any]
OpenAIMessage = Dict[str, Any]


class OpenAIConverter:
    """Converts MCP message types to OpenAI API format."""

    @staticmethod
    def _is_supported_image_type(mime_type: str) -> bool:
        """
        Check if the given MIME type is supported by OpenAI's image API.

        Args:
            mime_type: The MIME type to check

        Returns:
            True if the MIME type is generally supported, False otherwise
        """
        return (
            mime_type is not None
            and is_image_mime_type(mime_type)
            and mime_type != "image/svg+xml"
        )

    @staticmethod
    def convert_to_openai(
        multipart_msg: PromptMessageMultipart, concatenate_text_blocks: bool = False
    ) -> Dict[str, str | ContentBlock | List[ContentBlock]]:
        """
        Convert a PromptMessageMultipart message to OpenAI API format.

        Args:
            multipart_msg: The PromptMessageMultipart message to convert
            concatenate_text_blocks: If True, adjacent text blocks will be combined

        Returns:
            An OpenAI API message object
        """
        role = multipart_msg.role

        # Handle empty content
        if not multipart_msg.content:
            return {"role": role, "content": ""}

        # single text block
        if 1 == len(multipart_msg.content) and is_text_content(
            multipart_msg.content[0]
        ):
            return {"role": role, "content": get_text(multipart_msg.content[0])}

        # For user messages, convert each content block
        content_blocks: List[ContentBlock] = []

        for item in multipart_msg.content:
            try:
                if is_text_content(item):
                    text = get_text(item)
                    content_blocks.append({"type": "text", "text": text})

                elif is_image_content(item):
                    content_blocks.append(OpenAIConverter._convert_image_content(item))

                elif is_resource_content(item):
                    block = OpenAIConverter._convert_embedded_resource(item)
                    if block:
                        content_blocks.append(block)

                else:
                    _logger.warning(f"Unsupported content type: {type(item)}")
                    # Create a text block with information about the skipped content
                    fallback_text = f"[Unsupported content type: {type(item).__name__}]"
                    content_blocks.append({"type": "text", "text": fallback_text})

            except Exception as e:
                _logger.warning(f"Error converting content item: {e}")
                # Create a text block with information about the conversion error
                fallback_text = f"[Content conversion error: {str(e)}]"
                content_blocks.append({"type": "text", "text": fallback_text})

        if not content_blocks:
            return {"role": role, "content": ""}

        # If concatenate_text_blocks is True, combine adjacent text blocks
        if concatenate_text_blocks:
            content_blocks = OpenAIConverter._concatenate_text_blocks(content_blocks)

        # Return user message with content blocks
        return {"role": role, "content": content_blocks}

    @staticmethod
    def _concatenate_text_blocks(blocks: List[ContentBlock]) -> List[ContentBlock]:
        """
        Combine adjacent text blocks into single blocks.

        Args:
            blocks: List of content blocks

        Returns:
            List with adjacent text blocks combined
        """
        if not blocks:
            return []

        combined_blocks: List[ContentBlock] = []
        current_text = ""

        for block in blocks:
            if block["type"] == "text":
                # Add to current text accumulator
                if current_text:
                    current_text += " " + block["text"]
                else:
                    current_text = block["text"]
            else:
                # Non-text block found, flush accumulated text if any
                if current_text:
                    combined_blocks.append({"type": "text", "text": current_text})
                    current_text = ""
                # Add the non-text block
                combined_blocks.append(block)

        # Don't forget any remaining text
        if current_text:
            combined_blocks.append({"type": "text", "text": current_text})

        return combined_blocks

    @staticmethod
    def convert_prompt_message_to_openai(
        message: PromptMessage, concatenate_text_blocks: bool = False
    ) -> ChatCompletionMessageParam:
        """
        Convert a standard PromptMessage to OpenAI API format.

        Args:
            message: The PromptMessage to convert
            concatenate_text_blocks: If True, adjacent text blocks will be combined

        Returns:
            An OpenAI API message object
        """
        # Convert the PromptMessage to a PromptMessageMultipart containing a single content item
        multipart = PromptMessageMultipart(role=message.role, content=[message.content])

        # Use the existing conversion method with the specified concatenation option
        return OpenAIConverter.convert_to_openai(multipart, concatenate_text_blocks)

    @staticmethod
    def _convert_image_content(content: ImageContent) -> ContentBlock:
        """Convert ImageContent to OpenAI image_url content block."""
        # Get image data using helper
        image_data = get_image_data(content)

        # OpenAI requires image URLs or data URIs for images
        if not image_data:
            return {
                "type": "text",
                "text": f"[Image missing data for {content.mimeType}]",
            }
        image_url = {"url": f"data:{content.mimeType};base64,{image_data}"}

        # Check if the image has annotations for detail level
        if hasattr(content, "annotations") and content.annotations:
            if hasattr(content.annotations, "detail"):
                detail = content.annotations.detail
                if detail in ("auto", "low", "high"):
                    image_url["detail"] = detail

        return {"type": "image_url", "image_url": image_url}

    @staticmethod
    def _determine_mime_type(resource_content) -> str:
        """
        Determine the MIME type of a resource.

        Args:
            resource_content: The resource content to check

        Returns:
            The determined MIME type as a string
        """
        if hasattr(resource_content, "mimeType") and resource_content.mimeType:
            return resource_content.mimeType

        if hasattr(resource_content, "uri") and resource_content.uri:
            mime_type = guess_mime_type(str(resource_content.uri))
            return mime_type

        if hasattr(resource_content, "blob"):
            return "application/octet-stream"

        return "text/plain"

    @staticmethod
    def _convert_embedded_resource(
        resource: EmbeddedResource,
    ) -> Optional[ContentBlock]:
        """
        Convert EmbeddedResource to appropriate OpenAI content block.

        Args:
            resource: The embedded resource to convert

        Returns:
            An appropriate OpenAI content block or None if conversion failed
        """
        resource_content = resource.resource
        uri_str = get_resource_uri(resource)
        uri = getattr(resource_content, "uri", None)
        is_url = uri and str(uri).startswith(("http://", "https://"))
        title = extract_title_from_uri(uri) if uri else "resource"
        mime_type = OpenAIConverter._determine_mime_type(resource_content)

        # Handle different resource types based on MIME type

        # Handle images
        if OpenAIConverter._is_supported_image_type(mime_type):
            if is_url and uri_str:
                return {"type": "image_url", "image_url": {"url": uri_str}}

            # Try to get image data
            image_data = get_image_data(resource)
            if image_data:
                return {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
                }
            else:
                return {"type": "text", "text": f"[Image missing data: {title}]"}

        # Handle PDFs
        elif mime_type == "application/pdf":
            if is_url and uri_str:
                # OpenAI doesn't directly support PDF URLs, explain this limitation
                return {
                    "type": "text",
                    "text": f"[PDF URL: {uri_str}]\nOpenAI requires PDF files to be uploaded or provided as base64 data.",
                }
            elif hasattr(resource_content, "blob"):
                return {
                    "type": "file",
                    "file": {
                        "filename": title or "document.pdf",
                        "file_data": f"data:application/pdf;base64,{resource_content.blob}",
                    },
                }

        # Handle SVG (convert to text)
        elif mime_type == "image/svg+xml":
            text = get_text(resource)
            if text:
                file_text = (
                    f'<mcp-agent:file title="{title}" mimetype="{mime_type}">\n'
                    f"{text}\n"
                    f"</mcp-agent:file>"
                )
                return {"type": "text", "text": file_text}

        # Handle text files
        elif is_text_mime_type(mime_type):
            text = get_text(resource)
            if text:
                file_text = (
                    f'<mcp-agent:file title="{title}" mimetype="{mime_type}">\n'
                    f"{text}\n"
                    f"</mcp-agent:file>"
                )
                return {"type": "text", "text": file_text}

        # Default fallback for text resources
        text = get_text(resource)
        if text:
            return {"type": "text", "text": text}

        # Default fallback for binary resources
        elif hasattr(resource_content, "blob"):
            return {
                "type": "text",
                "text": f"[Binary resource: {title} ({mime_type})]",
            }

        # Last resort fallback
        return {
            "type": "text",
            "text": f"[Unsupported resource: {title} ({mime_type})]",
        }

    @staticmethod
    def _extract_text_from_content_blocks(
        content: Union[str, List[ContentBlock]],
    ) -> str:
        """
        Extract and combine text from content blocks.

        Args:
            content: Content blocks or string

        Returns:
            Combined text as a string
        """
        if isinstance(content, str):
            return content

        if not content:
            return ""

        # Extract only text blocks
        text_parts = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        return (
            " ".join(text_parts)
            if text_parts
            else "[Complex content converted to text]"
        )

    @staticmethod
    def convert_tool_result_to_openai(
        tool_result: CallToolResult,
        tool_call_id: str,
        concatenate_text_blocks: bool = False,
    ) -> Union[Dict[str, Any], Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        Convert a CallToolResult to an OpenAI tool message.

        If the result contains non-text elements, those are converted to separate user messages
        since OpenAI tool messages can only contain text.

        Args:
            tool_result: The tool result from a tool call
            tool_call_id: The ID of the associated tool use
            concatenate_text_blocks: If True, adjacent text blocks will be combined

        Returns:
            Either a single OpenAI message for the tool response (if text only),
            or a tuple containing the tool message and a list of additional messages for non-text content
        """
        # Handle empty content case
        if not tool_result.content:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": "[No content in tool result]",
            }

        # Separate text and non-text content
        text_content = []
        non_text_content = []

        for item in tool_result.content:
            if isinstance(item, TextContent):
                text_content.append(item)
            else:
                non_text_content.append(item)

        # Create tool message with text content
        tool_message_content = ""
        if text_content:
            # Convert text content to OpenAI format
            temp_multipart = PromptMessageMultipart(role="user", content=text_content)
            converted = OpenAIConverter.convert_to_openai(
                temp_multipart, concatenate_text_blocks=concatenate_text_blocks
            )

            # Extract text from content blocks
            tool_message_content = OpenAIConverter._extract_text_from_content_blocks(
                converted.get("content", "")
            )

        if not tool_message_content:
            tool_message_content = "[Tool returned non-text content]"

        # Create the tool message with just the text
        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": tool_message_content,
        }

        # If there's no non-text content, return just the tool message
        if not non_text_content:
            return tool_message

        # Process non-text content as a separate user message
        non_text_multipart = PromptMessageMultipart(
            role="user", content=non_text_content
        )

        # Convert to OpenAI format
        user_message = OpenAIConverter.convert_to_openai(non_text_multipart)

        # We need to add tool_call_id manually
        user_message["tool_call_id"] = tool_call_id

        return (tool_message, [user_message])

    @staticmethod
    def convert_function_results_to_openai(
        results: List[Tuple[str, CallToolResult]],
        concatenate_text_blocks: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Convert a list of function call results to OpenAI messages.

        Args:
            results: List of (tool_call_id, result) tuples
            concatenate_text_blocks: If True, adjacent text blocks will be combined

        Returns:
            List of OpenAI API messages for tool responses
        """
        messages = []

        for tool_call_id, result in results:
            converted = OpenAIConverter.convert_tool_result_to_openai(
                tool_result=result,
                tool_call_id=tool_call_id,
                concatenate_text_blocks=concatenate_text_blocks,
            )

            # Handle the case where we have mixed content and get back a tuple
            if isinstance(converted, tuple):
                tool_message, additional_messages = converted
                messages.append(tool_message)
                messages.extend(additional_messages)
            else:
                # Single message case (text-only)
                messages.append(converted)

        return messages

    @staticmethod
    def convert_mixed_messages_to_openai(
        message: MessageTypes,
    ) -> List[ChatCompletionMessageParam]:
        """
        Convert a list of mixed messages to a list of OpenAI-compatible messages.

        Args:
            messages: List of mixed message objects

        Returns:
            A list of OpenAI-compatible MessageParam objects
        """
        messages: list[ChatCompletionMessageParam] = []

        if isinstance(message, str):
            messages.append(
                ChatCompletionUserMessageParam(role="user", content=message)
            )
        elif isinstance(message, PromptMessage):
            messages.append(OpenAIConverter.convert_prompt_message_to_openai(message))
        elif isinstance(message, list):
            for m in message:
                if isinstance(m, PromptMessage):
                    messages.append(OpenAIConverter.convert_prompt_message_to_openai(m))
                elif isinstance(m, str):
                    messages.append(
                        ChatCompletionUserMessageParam(role="user", content=m)
                    )
                else:
                    messages.append(m)
        else:
            messages.append(message)

        return messages
