from mcp.types import (
    EmbeddedResource,
    GetPromptResult,
    ImageContent,
    PromptMessage,
    TextContent,
    TextResourceContents,
)

from mcp_agent.utils.prompt_message_multipart import PromptMessageMultipart


class TestPromptMessageMultipart:
    def test_init(self):
        content = [TextContent(type="text", text="Hello")]
        msg = PromptMessageMultipart(role="user", content=content)
        assert msg.role == "user"
        assert msg.content == content

    def test_to_multipart_empty_list(self):
        result = PromptMessageMultipart.to_multipart([])
        assert result == []

    def test_to_multipart_single_message(self):
        messages = [
            PromptMessage(role="user", content=TextContent(type="text", text="Hello"))
        ]
        result = PromptMessageMultipart.to_multipart(messages)

        assert len(result) == 1
        assert result[0].role == "user"
        assert len(result[0].content) == 1
        assert result[0].content[0].text == "Hello"

    def test_to_multipart_same_role_consecutive(self):
        messages = [
            PromptMessage(role="user", content=TextContent(type="text", text="Hello")),
            PromptMessage(role="user", content=TextContent(type="text", text="World")),
        ]
        result = PromptMessageMultipart.to_multipart(messages)

        assert len(result) == 1
        assert result[0].role == "user"
        assert len(result[0].content) == 2
        assert result[0].content[0].text == "Hello"
        assert result[0].content[1].text == "World"

    def test_to_multipart_different_roles(self):
        messages = [
            PromptMessage(role="user", content=TextContent(type="text", text="Hello")),
            PromptMessage(
                role="assistant", content=TextContent(type="text", text="Hi there")
            ),
            PromptMessage(
                role="user", content=TextContent(type="text", text="How are you?")
            ),
        ]
        result = PromptMessageMultipart.to_multipart(messages)

        assert len(result) == 3
        assert result[0].role == "user"
        assert result[0].content[0].text == "Hello"
        assert result[1].role == "assistant"
        assert result[1].content[0].text == "Hi there"
        assert result[2].role == "user"
        assert result[2].content[0].text == "How are you?"

    def test_from_multipart(self):
        content = [
            TextContent(type="text", text="Hello"),
            TextContent(type="text", text="World"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)

        messages = multipart.from_multipart()

        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content.text == "Hello"
        assert messages[1].role == "user"
        assert messages[1].content.text == "World"

    def test_first_text(self):
        content = [
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
            TextContent(type="text", text="First text"),
            TextContent(type="text", text="Second text"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)

        assert multipart.first_text() == "First text"

    def test_first_text_no_text_content(self):
        content = [
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)

        assert multipart.first_text() == "<no text>"

    def test_first_text_from_embedded_resource(self):
        resource = TextResourceContents(
            uri="file://test.txt", mimeType="text/plain", text="Resource text"
        )
        embedded = EmbeddedResource(type="resource", resource=resource)
        content = [embedded]
        multipart = PromptMessageMultipart(role="user", content=content)

        assert multipart.first_text() == "Resource text"

    def test_last_text(self):
        content = [
            TextContent(type="text", text="First text"),
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
            TextContent(type="text", text="Last text"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)

        assert multipart.last_text() == "Last text"

    def test_last_text_no_text_content(self):
        content = [
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)

        assert multipart.last_text() == "<no text>"

    def test_all_text(self):
        content = [
            TextContent(type="text", text="First text"),
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
            TextContent(type="text", text="Second text"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)

        assert multipart.all_text() == "First text\nSecond text"

    def test_all_text_no_text_content(self):
        content = [
            ImageContent(type="image", data="imagedata", mimeType="image/png"),
        ]
        multipart = PromptMessageMultipart(role="user", content=content)

        assert multipart.all_text() == ""

    def test_add_text(self):
        content = [TextContent(type="text", text="Initial")]
        multipart = PromptMessageMultipart(role="user", content=content)

        added = multipart.add_text("Added text")

        assert len(multipart.content) == 2
        assert multipart.content[1].text == "Added text"
        assert added.text == "Added text"
        assert added.type == "text"

    def test_parse_get_prompt_result(self):
        messages = [
            PromptMessage(role="user", content=TextContent(type="text", text="Hello")),
            PromptMessage(
                role="assistant", content=TextContent(type="text", text="Hi")
            ),
        ]
        result = GetPromptResult(description="Test prompt", messages=messages)

        multipart_messages = PromptMessageMultipart.parse_get_prompt_result(result)

        assert len(multipart_messages) == 2
        assert multipart_messages[0].role == "user"
        assert multipart_messages[1].role == "assistant"

    def test_from_get_prompt_result_with_result(self):
        messages = [
            PromptMessage(role="user", content=TextContent(type="text", text="Hello")),
        ]
        result = GetPromptResult(description="Test prompt", messages=messages)

        multipart_messages = PromptMessageMultipart.from_get_prompt_result(result)

        assert len(multipart_messages) == 1
        assert multipart_messages[0].role == "user"

    def test_from_get_prompt_result_with_none(self):
        multipart_messages = PromptMessageMultipart.from_get_prompt_result(None)
        assert multipart_messages == []

    def test_from_get_prompt_result_with_empty_messages(self):
        result = GetPromptResult(description="Test prompt", messages=[])
        multipart_messages = PromptMessageMultipart.from_get_prompt_result(result)
        assert multipart_messages == []
