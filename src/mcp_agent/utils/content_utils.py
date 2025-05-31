"""
Helper functions for working with content objects.

These utilities simplify extracting content from content structures
without repetitive type checking.
"""

from typing import Optional, Union

from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    ImageContent,
    TextContent,
    TextResourceContents,
)


def get_text(
    content: Union[TextContent, ImageContent, EmbeddedResource],
) -> Optional[str]:
    """
    Extract text content from a content object if available.

    Args:
        content: A content object (TextContent, ImageContent, or EmbeddedResource)

    Returns:
        The text content as a string or None if not a text content
    """
    if isinstance(content, TextContent):
        return content.text

    if isinstance(content, TextResourceContents):
        return content.text

    if isinstance(content, EmbeddedResource):
        if isinstance(content.resource, TextResourceContents):
            return content.resource.text

    return None


def get_image_data(
    content: Union[TextContent, ImageContent, EmbeddedResource],
) -> Optional[str]:
    """
    Extract image data from a content object if available.

    Args:
        content: A content object (TextContent, ImageContent, or EmbeddedResource)

    Returns:
        The image data as a base64 string or None if not an image content
    """
    if isinstance(content, ImageContent):
        return content.data

    if isinstance(content, EmbeddedResource):
        if isinstance(content.resource, BlobResourceContents):
            # This assumes the blob might be an image, which isn't always true
            # Consider checking the mimeType if needed
            return content.resource.blob

    return None


def get_resource_uri(
    content: Union[TextContent, ImageContent, EmbeddedResource],
) -> Optional[str]:
    """
    Extract resource URI from an EmbeddedResource if available.

    Args:
        content: A content object (TextContent, ImageContent, or EmbeddedResource)

    Returns:
        The resource URI as a string or None if not an embedded resource
    """
    if isinstance(content, EmbeddedResource):
        return str(content.resource.uri)

    return None


def is_text_content(
    content: Union[TextContent, ImageContent, EmbeddedResource],
) -> bool:
    """
    Check if the content is text content.

    Args:
        content: A content object (TextContent, ImageContent, or EmbeddedResource)

    Returns:
        True if the content is TextContent, False otherwise
    """
    return isinstance(content, TextContent) or isinstance(content, TextResourceContents)


def is_image_content(
    content: Union[TextContent, ImageContent, EmbeddedResource],
) -> bool:
    """
    Check if the content is image content.

    Args:
        content: A content object (TextContent, ImageContent, or EmbeddedResource)

    Returns:
        True if the content is ImageContent, False otherwise
    """
    return isinstance(content, ImageContent)


def is_resource_content(
    content: Union[TextContent, ImageContent, EmbeddedResource],
) -> bool:
    """
    Check if the content is an embedded resource.

    Args:
        content: A content object (TextContent, ImageContent, or EmbeddedResource)

    Returns:
        True if the content is EmbeddedResource, False otherwise
    """
    return isinstance(content, EmbeddedResource)
