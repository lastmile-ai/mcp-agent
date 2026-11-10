from urllib.parse import unquote, urlsplit

import pytest

from mcp_agent.utils.resource_utils import create_embedded_resource


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
