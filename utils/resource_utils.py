import base64
from pathlib import Path
from typing import List, Optional, Tuple

from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    ImageContent,
    TextResourceContents,
)
from pydantic import AnyUrl

import mcp_agent.utils.mime_utils as mime_utils

HTTP_TIMEOUT = 10  # Default timeout for HTTP requests

# Define a type alias for resource content results
ResourceContent = Tuple[str, str, bool]


def find_resource_file(resource_path: str, prompt_files: List[Path]) -> Optional[Path]:
    """Find a resource file relative to one of the prompt files"""
    for prompt_file in prompt_files:
        potential_path = prompt_file.parent / resource_path
        if potential_path.exists():
            return potential_path
    return None


def load_resource_content(
    resource_path: str, prompt_files: List[Path]
) -> ResourceContent:
    """
    Load a resource's content and determine its mime type

    Args:
        resource_path: Path to the resource file
        prompt_files: List of prompt files (to find relative paths)

    Returns:
        Tuple of (content, mime_type, is_binary)
        - content: String content for text files, base64-encoded string for binary files
        - mime_type: The MIME type of the resource
        - is_binary: Whether the content is binary (and base64-encoded)

    Raises:
        FileNotFoundError: If the resource cannot be found
    """
    # Try to locate the resource file
    resource_file = find_resource_file(resource_path, prompt_files)
    if resource_file is None:
        raise FileNotFoundError(f"Resource not found: {resource_path}")

    # Determine mime type
    mime_type = mime_utils.guess_mime_type(str(resource_file))
    is_binary = mime_utils.is_binary_content(mime_type)

    if is_binary:
        # For binary files, read as binary and base64 encode
        with open(resource_file, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
    else:
        # For text files, read as text
        with open(resource_file, "r", encoding="utf-8") as f:
            content = f.read()

    return content, mime_type, is_binary


# Create a safe way to generate resource URIs that Pydantic accepts
def create_resource_uri(path: str) -> str:
    """Create a resource URI from a path"""
    return f"resource://mcp-agent/{Path(path).name}"


def create_resource_reference(uri: str, mime_type: str) -> "EmbeddedResource":
    """
    Create a reference to a resource without embedding its content directly.

    This creates an EmbeddedResource that references another resource URI.
    When the client receives this, it will make a separate request to fetch
    the resource content using the provided URI.

    Args:
        uri: URI for the resource
        mime_type: MIME type of the resource

    Returns:
        An EmbeddedResource object
    """

    # Create a resource reference
    resource_contents = TextResourceContents(
        uri=uri,
        mimeType=mime_type,
        text="",  # Empty text as we're just referencing
    )

    return EmbeddedResource(type="resource", resource=resource_contents)


def create_embedded_resource(
    resource_path: str, content: str, mime_type: str, is_binary: bool = False
) -> EmbeddedResource:
    """Create an embedded resource content object"""
    # Format a valid resource URI string
    resource_uri_str = create_resource_uri(resource_path)

    # Create common resource args dict to reduce duplication
    resource_args = {
        "uri": AnyUrl(url=resource_uri_str),
        "mimeType": mime_type,
    }

    if is_binary:
        return EmbeddedResource(
            type="resource",
            resource=BlobResourceContents(
                **resource_args,
                blob=content,
            ),
        )
    else:
        return EmbeddedResource(
            type="resource",
            resource=TextResourceContents(
                **resource_args,
                text=content,
            ),
        )


def create_image_content(data: str, mime_type: str) -> ImageContent:
    """Create an image content object from base64-encoded data"""
    return ImageContent(
        type="image",
        data=data,
        mimeType=mime_type,
    )


def create_blob_resource(
    resource_path: str, content: str, mime_type: str
) -> EmbeddedResource:
    """Create an embedded resource for binary data"""
    return EmbeddedResource(
        type="resource",
        resource=BlobResourceContents(
            uri=AnyUrl(url=resource_path),
            mimeType=mime_type,
            blob=content,  # Content should already be base64 encoded
        ),
    )


def create_text_resource(
    resource_path: str, content: str, mime_type: str
) -> EmbeddedResource:
    """Create an embedded resource for text data"""
    return EmbeddedResource(
        type="resource",
        resource=TextResourceContents(
            uri=AnyUrl(url=resource_path),
            mimeType=mime_type,
            text=content,
        ),
    )


def normalize_uri(uri_or_filename: str) -> str:
    """
    Normalize a URI or filename to ensure it's a valid URI.
    Converts simple filenames to file:// URIs if needed.

    Args:
        uri_or_filename: A URI string or simple filename

    Returns:
        A properly formatted URI string
    """
    if not uri_or_filename:
        return ""

    # Check if it's already a valid URI with a scheme
    if "://" in uri_or_filename:
        return uri_or_filename

    # Handle Windows-style paths with backslashes
    normalized_path = uri_or_filename.replace("\\", "/")

    # If it's a simple filename or relative path, convert to file:// URI
    # Make sure it has three slashes for an absolute path
    if normalized_path.startswith("/"):
        return f"file://{normalized_path}"
    else:
        return f"file:///{normalized_path}"


def extract_title_from_uri(uri: AnyUrl) -> str:
    """Extract a readable title from a URI."""
    # Simple attempt to get filename from path
    uri_str = str(uri)
    try:
        # For HTTP(S) URLs
        if uri.scheme in ("http", "https"):
            # Get the last part of the path
            path_parts = uri.path.split("/")
            filename = next((p for p in reversed(path_parts) if p), "")
            return filename if filename else uri_str

        # For file URLs or other schemes
        elif uri.path:
            import os.path

            return os.path.basename(uri.path)

    except Exception:
        pass

    # Fallback to the full URI if parsing fails
    return uri_str
