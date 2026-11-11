from urllib.parse import unquote, urlsplit

import pytest
from pydantic import AnyUrl

from mcp_agent.utils.resource_utils import (
    create_embedded_resource,
    extract_title_from_uri,
)


@pytest.mark.parametrize(
    "filename", ["report#1.txt", "report?draft.txt", "100%20done.txt", "plain.txt"]
)
def test_embedded_resource_preserves_literal_filename(filename: str) -> None:
    resource = create_embedded_resource(filename, "contents", "text/plain")
    uri = urlsplit(str(resource.resource.uri))
    assert uri.query == ""
    assert uri.fragment == ""
    assert unquote(uri.path) == "/" + filename
    assert resource.resource.text == "contents"
    assert extract_title_from_uri(resource.resource.uri) == filename


@pytest.mark.parametrize(
    "uri", ["https://example.com/files/report%231.pdf", "file:///tmp/report%231.pdf"]
)
def test_title_decodes_encoded_basename(uri: str) -> None:
    assert extract_title_from_uri(AnyUrl(uri)) == "report#1.pdf"
