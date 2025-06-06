from typing import List, Optional, Union

from mcp.types import (
    EmbeddedResource,
    GetPromptResult,
    ImageContent,
    PromptMessage,
    Role,
    TextContent,
)
from pydantic import BaseModel

from mcp_agent.utils.content_utils import get_text


class PromptMessageMultipart(BaseModel):
    """
    Extension of PromptMessage that handles multiple content parts.
    Internally converts to/from a sequence of standard PromptMessages.
    """

    role: Role
    content: List[Union[TextContent, ImageContent, EmbeddedResource]]

    @classmethod
    def to_multipart(
        cls, messages: List[PromptMessage]
    ) -> List["PromptMessageMultipart"]:
        """Convert a sequence of PromptMessages into PromptMessageMultipart objects."""
        if not messages:
            return []

        result = []
        current_group = None
        current_role = None

        for msg in messages:
            if msg.role != current_role:
                # Role changed, start new message
                if current_group is not None:
                    result.append(current_group)
                current_role = msg.role
                current_group = cls(role=msg.role, content=[msg.content])
            else:
                # Same role, add to current message
                if current_group is not None:
                    current_group.content.append(msg.content)

        # Add the last group
        if current_group is not None:
            result.append(current_group)

        return result

    def from_multipart(self) -> List[PromptMessage]:
        """Convert this PromptMessageMultipart to a sequence of standard PromptMessages."""
        return [
            PromptMessage(role=self.role, content=content_part)
            for content_part in self.content
        ]

    def first_text(self) -> str:
        """
        Get the first available text content from a message. Note this could be tool content etc.

        Args:
            message: A PromptMessage or PromptMessageMultipart

        Returns:
            First text content or None if no text content exists
        """
        for content in self.content:
            text = get_text(content)
            if text is not None:
                return text

        return "<no text>"

    def last_text(self) -> str:
        """
        Get the last available text content from a message. This will usually be the final
        generation from the Assistant.

        Args:
            message: A PromptMessage or PromptMessageMultipart

        Returns:
            First text content or None if no text content exists
        """
        for content in reversed(self.content):
            text = get_text(content)
            if text is not None:
                return text

        return "<no text>"

    def all_text(self) -> str:
        """
        Get all the text available.

        Args:
            message: A PromptMessage or PromptMessageMultipart

        Returns:
            First text content or None if no text content exists
        """
        result = []
        for content in self.content:
            text = get_text(content)
            if text is not None:
                result.append(text)

        return "\n".join(result)

    def add_text(self, to_add: str) -> TextContent:
        text = TextContent(type="text", text=to_add)
        self.content.append(text)
        return text

    @classmethod
    def parse_get_prompt_result(
        cls, result: GetPromptResult
    ) -> List["PromptMessageMultipart"]:
        """
        Parse a GetPromptResult into PromptMessageMultipart objects.

        Args:
            result: GetPromptResult from MCP server

        Returns:
            List of PromptMessageMultipart objects
        """
        return cls.to_multipart(result.messages)

    @classmethod
    def from_get_prompt_result(
        cls, result: Optional[GetPromptResult]
    ) -> List["PromptMessageMultipart"]:
        """
        Convert a GetPromptResult to PromptMessageMultipart objects with error handling.
        This method safely handles None values and empty results.

        Args:
            result: GetPromptResult from MCP server or None

        Returns:
            List of PromptMessageMultipart objects or empty list if result is None/empty
        """
        if not result or not result.messages:
            return []
        return cls.to_multipart(result.messages)
